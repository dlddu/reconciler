#!/usr/bin/env python3
"""reconciler-work-review(MiniMax) 워크플로의 「Claim target」 스텝 — 대상 선정 + 점유(claim).

리뷰 스킬의 Step 0(대상 선정 · 진입 게이트)과 Step 1(점유)을 러너가 결정적으로 수행한다. MiniMax Code는
점유가 push된 task 한 건을 넘겨받아 신선도 확인과 승인/거부 판정만 한다(근거는 README 「점유는 러너가 한다」 —
감지와 같은 논리다: mcode를 부르는 러너가 항상 있으므로 target id를 정하는 컴포넌트가 늘 있다).

절차(후보 하나당):
  1. 원격 기본 브랜치로 맞춘다(fetch + reset --hard).
  2. select_review_target.select_target으로 `planned` 한 건을 고른다(경쟁에서 진 task는 제외).
  3. 점유 커밋: 그 task의 status가 여전히 `planned`인지 재확인 → `reviewing`으로 바꿔 한 커밋 → 즉시 push.
     이 push가 lock이다.
     - push가 non-fast-forward로 거절되면(무관한 커밋이 먼저 들어온 경우 포함) 1부터 다시 해 status를
       새 상태에서 재확인한다. 여전히 `planned`면 다시 커밋·push한다.
     - status가 바뀌었으면 다른 워커가 먼저 집은 것 → 그 task를 빼고 2로(지목 실행이면 종료).

점유 커밋 형태는 Claude Code 리뷰 스킬의 점유와 같다 — 두 경로가 같은 레포에 쓰므로 맞춘다:
  status만 `planned → reviewing`, 커밋 제목 `review(<tbm>/<rct>): claim`. 다른 필드는 건드리지 않는다.

스킬에 남는 계약: 넘겨받은 task가 `reviewing`인지 확인 → 신선도 확인 → 마지막 attempts 항목의 `review` 기록 →
`approved | review_rejected | cancelled`로 전이(판정 없이 중단하면 `planned`로 되돌림) → `pull --rebase` 후 push.

출력(GITHUB_OUTPUT): found, claimed, task_id, model_id, claim_reason, claim_commit, claim_message,
                     pull_request_url, lost_count, error_count
종료 코드: 0 = 점유했거나 대상 없음, 1 = 오류(대상 없음을 단정할 수 없음 포함), 2 = 사용법/데이터 오류
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import select_review_target as srt  # noqa: E402

TASKS_DIR = "data/reconciliation-tasks"
FROM_STATUS = "planned"
CLAIM_STATUS = "reviewing"
MAX_CANDIDATES = 5


class ClaimError(Exception):
    """점유를 진행할 수 없는 오류(경쟁 패배가 아님)."""


@dataclass
class ClaimResult:
    status: str  # claimed | lost
    commit: str = ""
    detail: str = ""
    message: str = ""


@dataclass
class Outcome:
    selection: srt.Selection | None = None
    claim: ClaimResult | None = None
    lost: list = field(default_factory=list)  # (model/task, 사유)


# ── git ──────────────────────────────────────────────────────────────────────


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if check and proc.returncode:
        raise ClaimError(f"git {' '.join(args)} 실패: {proc.stderr.strip()[-400:]}")
    return proc


def sync(repo: Path, remote: str, branch: str) -> None:
    git(repo, "fetch", "--quiet", remote, branch)
    git(repo, "reset", "--quiet", "--hard", f"{remote}/{branch}")


def push(repo: Path, remote: str, branch: str) -> str:
    """'ok' | 'rejected'(non-fast-forward 등 원격이 앞섬). 그 밖의 실패는 ClaimError."""
    proc = git(repo, "push", "--porcelain", remote, f"HEAD:refs/heads/{branch}", check=False)
    if proc.returncode == 0:
        return "ok"
    text = proc.stdout + proc.stderr
    if any(k in text for k in ("[rejected]", "non-fast-forward", "fetch first", "stale info",
                               "[remote rejected] (cannot lock ref")):
        return "rejected"
    raise ClaimError(f"push 실패: {text.strip()[-400:]}")


# ── 점유 ─────────────────────────────────────────────────────────────────────


def task_validator(repo: Path):
    import jsonschema

    schema = json.loads((repo / "schemas" / "reconciliation-task.schema.json").read_text(encoding="utf-8"))
    cls = jsonschema.validators.validator_for(schema)
    return cls(schema, format_checker=cls.FORMAT_CHECKER)


def check_valid(validator, record: dict, label: str) -> None:
    errors = sorted(validator.iter_errors(record), key=lambda e: list(map(str, e.absolute_path)))
    if errors:
        first = errors[0]
        where = "/".join(map(str, first.absolute_path)) or "<root>"
        raise ClaimError(f"{label} 스키마 위반 — {where}: {first.message}")


def claim(repo: Path, sel: srt.Selection, *, remote: str, branch: str,
          max_push_attempts: int = 5, before_push=None) -> ClaimResult:
    """선정된 task 한 건을 status compare-and-set으로 점유한다. 경쟁에서 지면 status=lost."""
    validator = task_validator(repo)
    rel = f"{TASKS_DIR}/{sel.model_id}.json"
    label = f"{sel.model_id}/{sel.target_id}"
    message = f"review({sel.model_id}/{sel.target_id}): claim"
    for attempt in range(1, max_push_attempts + 1):
        if attempt > 1:
            sync(repo, remote, branch)
        path = repo / rel
        if not path.exists():
            return ClaimResult(status="lost", detail=f"{rel}가 사라짐")
        tasks = json.loads(path.read_text(encoding="utf-8"))
        task = next((t for t in tasks if isinstance(t, dict) and t.get("id") == sel.target_id), None)
        if task is None:
            return ClaimResult(status="lost", detail=f"{label}가 사라짐")
        if task.get("status") != FROM_STATUS:
            return ClaimResult(status="lost", detail=f"status가 {task.get('status')}로 바뀜 — 다른 워커가 먼저 집음")
        task["status"] = CLAIM_STATUS
        check_valid(validator, task, f"task {label}")
        path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        git(repo, "add", rel)
        if not git(repo, "diff", "--cached", "--quiet", check=False).returncode:
            raise ClaimError("점유 커밋에 변경이 없음")
        git(repo, "commit", "--quiet", "-m", message)
        commit = git(repo, "rev-parse", "HEAD").stdout.strip()
        if before_push:
            before_push(attempt)
        if push(repo, remote, branch) == "ok":
            return ClaimResult(status="claimed", commit=commit, message=message,
                               detail=f"{FROM_STATUS} → {CLAIM_STATUS}")
        # 원격이 앞섰다 — 새 상태에서 status를 다시 확인한다(무관한 커밋이면 그대로 재시도된다).
    raise ClaimError(f"push가 {max_push_attempts}회 연속 거절됨 — 원격이 계속 움직이는 중")


def run(repo: Path, *, explicit: str | None, remote: str, branch: str, no_sync: bool = False,
        before_push=None) -> Outcome:
    out = Outcome()
    excluded: set[str] = set()
    for _ in range(MAX_CANDIDATES):
        if not no_sync:
            sync(repo, remote, branch)
        sel = srt.select_target(repo, explicit=explicit, exclude=frozenset(excluded))
        out.selection = sel
        if not sel.found:
            return out
        result = claim(repo, sel, remote=remote, branch=branch, before_push=before_push)
        if result.status == "claimed":
            out.claim = result
            return out
        key = f"{sel.model_id}/{sel.target_id}"
        out.lost.append((key, result.detail))
        if explicit:
            return out  # 지목 실행은 다른 후보로 넘어가지 않는다
        excluded.add(key)
        no_sync = False  # 경쟁에서 졌으면 다음 후보는 원격 최신 상태에서 고른다
    return out


# ── 출력 ─────────────────────────────────────────────────────────────────────


def write_outputs(out: Outcome, path: str | None) -> None:
    sel, c = out.selection, out.claim
    lines = {
        "found": "true" if c else "false",
        "claimed": "true" if c else "false",
        "task_id": sel.target_id if (c and sel) else "",
        "model_id": sel.model_id if (c and sel) else "",
        "claim_reason": sel.reason if (c and sel) else "",
        "claim_commit": c.commit if c else "",
        "claim_message": c.message if c else "",
        "pull_request_url": sel.pull_request_url if (c and sel) else "",
        "lost_count": str(len(out.lost)),
        "error_count": str(len(sel.errors)) if sel else "0",
    }
    text = "".join(f"{k}={v}\n" for k, v in lines.items())
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def render(out: Outcome) -> str:
    lines = ["#### Claim target"]
    for key, why in out.lost:
        lines.append(f"- 점유 경쟁에서 짐 · {key}: {why}")
    if out.claim:
        sel = out.selection
        lines.append(f"- 점유: `{sel.model_id}/{sel.target_id}` ({sel.reason}) — {out.claim.detail}")
        lines.append(f"- 커밋: `{out.claim.message}`")
    else:
        lines.append("- 이번에 점유한 대상 없음")
    if out.selection:
        lines.append("")
        lines.append(srt.render_summary(out.selection).rstrip())
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", default=".", type=Path)
    p.add_argument("--target", default="", help="지목 대상(rct_..., tbm_..., tbm_.../rct_...), 비우면 자동 선정")
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default="main")
    p.add_argument("--no-sync", action="store_true",
                   help="첫 선정 전에 원격으로 reset하지 않는다(체크아웃 직후라 이미 최신일 때)")
    p.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    p.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = p.parse_args(argv)

    target = args.target.strip() or None
    if target and not re.fullmatch(r"(tbm_[^/\s]+/)?rct_[^/\s]+|tbm_[^/\s]+", target):
        print(f"::error::target_id는 rct_..., tbm_..., tbm_.../rct_... 중 하나여야 함: {target}")
        return 2

    try:
        out = run(args.repo, explicit=target, remote=args.remote, branch=args.branch, no_sync=args.no_sync)
    except (ClaimError, srt.SelectionError) as exc:
        print(f"::error::{exc}")
        return 2 if isinstance(exc, srt.SelectionError) else 1

    sel = out.selection
    for target_id, msg in (sel.errors if sel else []):
        print(f"::warning::{target_id}: {msg}")
    summary = render(out)
    print(summary, end="")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as fh:
            fh.write(summary)
    write_outputs(out, args.github_output)
    # 고를 것이 없는데 전제가 깨진 planned가 있으면 막힌 task다 — 선정 스크립트와 같이 실패로 드러낸다.
    if not out.claim and sel and sel.errors and not out.lost:
        print(f"::error::리뷰 전제가 깨진 planned task {len(sel.errors)}건 — 대상 없음으로 확정할 수 없음")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
