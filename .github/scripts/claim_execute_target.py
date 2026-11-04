#!/usr/bin/env python3
"""reconciler-work-executor(MiniMax) 워크플로의 「Claim target」 스텝 — 대상 선정 + 진입 게이트 + 점유(claim).

실행 스킬의 Step 0(대상 선정 · 진입 게이트, 4-0)과 Step 1(점유)을 러너가 결정적으로 수행한다. MiniMax Code는
점유가 push된 task 한 건을 넘겨받아 실행·검증만 한다(근거는 README 「점유는 러너가 한다」 — mcode를 부르는 러너가
항상 있으므로 target id를 정하는 컴포넌트가 늘 있다).

절차(후보 하나당):
  1. 원격 기본 브랜치로 맞춘다(fetch + reset --hard).
  2. select_execute_target.select_target으로 executable `approved` 한 건을 고른다(경쟁에서 진 task는 제외).
     진입 게이트(plan·준비 완료, review.manualApproval이면 PR open·head == sha·context status success)는 거기서 본다.
  3. 점유 커밋: 그 task가 여전히 `approved`인지 재확인하고, 게이트를 **다시 판정**한다(선정 이후 PR에 새 커밋이 올라와
     사람 승인이 무효가 됐을 수 있다 — Claude Code 실행 스킬의 Step 1과 같다). 통과하면 `executing`으로 바꿔 한 커밋 →
     즉시 push. 이 push가 lock이다.
     - push가 non-fast-forward로 거절되면(무관한 커밋이 먼저 들어온 경우 포함) 1부터 다시 해 status·게이트를 새 상태에서
       재확인한다.
     - status가 바뀌었으면 다른 워커가 먼저 집은 것(lost), 게이트가 더는 통과하지 않으면 그 task는 이번 실행 대상이
       아님(gate) → 그 task를 빼고 2로(지목 실행이면 종료).

점유 커밋 형태는 Claude Code 실행 스킬의 점유와 같다 — 두 경로가 같은 레포에 쓰므로 맞춘다:
  status만 `approved → executing`, 커밋 제목 `execute(<tbm>/<rct>): claim`. 다른 필드는 건드리지 않는다.

스킬에 남는 계약: 넘겨받은 task가 `executing`인지 확인 → 마지막 attempts 항목의 plan 실행·`execution` 기록(run) →
`verifying` → 검증·`verification` 기록 → `succeeded | failed | cancelled`(verify) → 커밋마다 `pull --rebase` 후 push.

lock 해제(--release <tbm>/<rct>): 점유는 push됐는데 스킬을 돌리기 전에 러너가 실패했을 때(플러그인·mcode 설치) 워크플로가
  부른다. 그 task가 여전히 `executing`이고 마지막 attempts 항목에 `execution`이 없을 때만 `approved`로 되돌린다(같은
  compare-and-set, 커밋 `execute(<tbm>/<rct>): release`). 실행이 시작됐거나 status가 바뀌었으면 아무것도 쓰지 않는다 —
  실행이 시작된 뒤의 되돌림은 무엇이 이미 반영됐는지 모르는 채로 다시 실행하게 만든다.

GitHub 조회(PR·status)는 SOURCE_GITHUB_TOKEN(대상 레포 read)을 우선 쓰고, 없으면 GITHUB_TOKEN. 확인하지 못하면 승인 안 됨
(fail-closed — select_execute_target.py와 같다).

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

import select_execute_target as setg  # noqa: E402

TASKS_DIR = "data/reconciliation-tasks"
FROM_STATUS = "approved"
CLAIM_STATUS = "executing"
MAX_CANDIDATES = 5


class ClaimError(Exception):
    """점유를 진행할 수 없는 오류(경쟁 패배가 아님)."""


@dataclass
class ClaimResult:
    status: str  # claimed | lost | gate
    commit: str = ""
    detail: str = ""
    message: str = ""


@dataclass
class Outcome:
    selection: setg.Selection | None = None
    claim: ClaimResult | None = None
    lost: list = field(default_factory=list)  # (model/task, 사유) — 경쟁 패배와 점유 직전 게이트 탈락
    api_calls: int = 0


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


def load_task(repo: Path, model_id: str, task_id: str) -> tuple[list | None, dict | None]:
    path = repo / TASKS_DIR / f"{model_id}.json"
    if not path.exists():
        return None, None
    tasks = json.loads(path.read_text(encoding="utf-8"))
    task = next((t for t in tasks if isinstance(t, dict) and t.get("id") == task_id), None)
    return tasks, task


def claim(repo: Path, sel: setg.Selection, gh, *, remote: str, branch: str,
          max_push_attempts: int = 5, before_push=None) -> ClaimResult:
    """선정된 task 한 건을 status compare-and-set으로 점유한다. 경쟁에서 지면 lost, 게이트가 무너졌으면 gate."""
    validator = task_validator(repo)
    rel = f"{TASKS_DIR}/{sel.model_id}.json"
    label = f"{sel.model_id}/{sel.task_id}"
    message = f"execute({sel.model_id}/{sel.task_id}): claim"
    for attempt in range(1, max_push_attempts + 1):
        if attempt > 1:
            sync(repo, remote, branch)
        tasks, task = load_task(repo, sel.model_id, sel.task_id)
        if task is None:
            return ClaimResult(status="lost", detail=f"{label}가 사라짐")
        if task.get("status") != FROM_STATUS:
            return ClaimResult(status="lost", detail=f"status가 {task.get('status')}로 바뀜 — 다른 워커가 먼저 집음")
        # 선정 이후 PR head가 바뀌었거나 승인 status가 내려갔을 수 있다 — 점유 직전에 다시 본다(fail-closed).
        verdict, why, _ = setg.judge(task, gh)
        if verdict != setg.EXECUTABLE:
            return ClaimResult(status="gate", detail=f"점유 직전 게이트 재확인 실패({setg.VERDICT_LABEL.get(verdict, verdict)}): {why}")
        task["status"] = CLAIM_STATUS
        check_valid(validator, task, f"task {label}")
        (repo / rel).write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        git(repo, "add", rel)
        if not git(repo, "diff", "--cached", "--quiet", check=False).returncode:
            raise ClaimError("점유 커밋에 변경이 없음")
        git(repo, "commit", "--quiet", "-m", message)
        commit = git(repo, "rev-parse", "HEAD").stdout.strip()
        if before_push:
            before_push(attempt)
        if push(repo, remote, branch) == "ok":
            return ClaimResult(status="claimed", commit=commit, message=message,
                               detail=f"{FROM_STATUS} → {CLAIM_STATUS} ({why})")
        # 원격이 앞섰다 — 새 상태에서 status·게이트를 다시 확인한다(무관한 커밋이면 그대로 재시도된다).
    raise ClaimError(f"push가 {max_push_attempts}회 연속 거절됨 — 원격이 계속 움직이는 중")


def release(repo: Path, key: str, *, remote: str, branch: str, max_push_attempts: int = 5,
            before_push=None) -> str:
    """점유한 task를 실행 없이 approved로 되돌린다. 돌려주는 값: released | skipped:<사유>."""
    model_id, _, task_id = key.partition("/")
    rel = f"{TASKS_DIR}/{model_id}.json"
    validator = task_validator(repo)
    for attempt in range(1, max_push_attempts + 1):
        sync(repo, remote, branch)
        tasks, task = load_task(repo, model_id, task_id)
        if task is None:
            return f"skipped:{key}가 없음"
        if task.get("status") != CLAIM_STATUS:
            return f"skipped:status가 {task.get('status')} — 이미 lock이 풀림"
        last = (task.get("attempts") or [{}])[-1]
        if isinstance(last, dict) and last.get("execution"):
            return "skipped:마지막 attempts 항목에 execution이 있음 — 실행이 시작된 task는 되돌리지 않음"
        task["status"] = FROM_STATUS
        check_valid(validator, task, f"task {key}")
        (repo / rel).write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        git(repo, "add", rel)
        git(repo, "commit", "--quiet", "-m", f"execute({model_id}/{task_id}): release")
        if before_push:
            before_push(attempt)
        if push(repo, remote, branch) == "ok":
            return "released"
    raise ClaimError(f"release push가 {max_push_attempts}회 연속 거절됨")


def run(repo: Path, gh, *, explicit: str | None, remote: str, branch: str, no_sync: bool = False,
        before_push=None) -> Outcome:
    out = Outcome()
    excluded: set[str] = set()
    for _ in range(MAX_CANDIDATES):
        if not no_sync:
            sync(repo, remote, branch)
        sel = setg.select_target(repo, gh, explicit=explicit, exclude=frozenset(excluded))
        out.selection = sel
        if not sel.found:
            break
        result = claim(repo, sel, gh, remote=remote, branch=branch, before_push=before_push)
        if result.status == "claimed":
            out.claim = result
            break
        key = f"{sel.model_id}/{sel.task_id}"
        out.lost.append((key, result.detail))
        if explicit:
            break  # 지목 실행은 다른 후보로 넘어가지 않는다
        excluded.add(key)
        no_sync = False  # 경쟁에서 졌으면 다음 후보는 원격 최신 상태에서 고른다
    out.api_calls = getattr(gh, "calls", 0)
    return out


# ── 출력 ─────────────────────────────────────────────────────────────────────


def write_outputs(out: Outcome, path: str | None) -> None:
    sel, c = out.selection, out.claim
    lines = {
        "found": "true" if c else "false",
        "claimed": "true" if c else "false",
        "task_id": sel.task_id if (c and sel) else "",
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
        lines.append(f"- 점유 못 함 · {key}: {why}")
    if out.claim:
        sel = out.selection
        lines.append(f"- 점유: `{sel.target_id}` ({sel.reason}) — {out.claim.detail}")
        lines.append(f"- 커밋: `{out.claim.message}`")
    else:
        lines.append("- 이번에 점유한 대상 없음")
    if out.selection:
        lines.append("")
        lines.append(setg.render_summary(out.selection, out.api_calls).rstrip())
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", default=".", type=Path)
    p.add_argument("--target", default="", help="지목 대상(<tbm>/<rct>, 모호하지 않은 rct_..., tbm_...), 비우면 자동 선정")
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default="main")
    p.add_argument("--api-url", default=os.environ.get("GITHUB_API_URL") or setg.DEFAULT_API)
    p.add_argument("--release", default="", metavar="TBM/RCT",
                   help="점유를 실행 없이 approved로 되돌린다(스킬 실행 전 러너 실패 시)")
    p.add_argument("--no-sync", action="store_true",
                   help="첫 선정 전에 원격으로 reset하지 않는다(체크아웃 직후라 이미 최신일 때)")
    p.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    p.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = p.parse_args(argv)

    if args.release:
        if not re.fullmatch(r"tbm_[^/\s]+/rct_[^/\s]+", args.release.strip()):
            print(f"::error::--release는 tbm_.../rct_... 형태여야 함: {args.release}")
            return 2
        try:
            result = release(args.repo, args.release.strip(), remote=args.remote, branch=args.branch)
        except ClaimError as exc:
            print(f"::error::{exc}")
            return 1
        line = (f"- lock 해제: `{args.release}` executing → approved" if result == "released"
                else f"- lock 해제 안 함 · `{args.release}`: {result.split(':', 1)[1]}")
        text = "#### Release claim\n" + line + "\n"
        print(text, end="")
        if args.summary_file:
            with open(args.summary_file, "a", encoding="utf-8") as fh:
                fh.write(text)
        return 0

    target = args.target.strip() or None
    if target and not re.fullmatch(r"(tbm_[^/\s]+/)?rct_[^/\s]+|tbm_[^/\s]+", target):
        print(f"::error::target_id는 rct_..., tbm_..., tbm_.../rct_... 중 하나여야 함: {target}")
        return 2

    # 대상 레포 한정 read 토큰이 우선, 없으면 워크플로 토큰으로 공개 레포 조회 한도만 올린다.
    token = os.environ.get("SOURCE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or None
    gh = setg.GitHub(api=args.api_url, token=token)
    try:
        out = run(args.repo, gh, explicit=target, remote=args.remote, branch=args.branch, no_sync=args.no_sync)
    except (ClaimError, setg.SelectionError) as exc:
        print(f"::error::{exc}")
        return 2 if isinstance(exc, setg.SelectionError) else 1

    sel = out.selection
    for ref, verdict, why, _ in (sel.judged if sel else []):
        if verdict == setg.ERROR:
            print(f"::warning::{ref}: {why}")
    summary = render(out)
    print(summary, end="")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as fh:
            fh.write(summary)
    write_outputs(out, args.github_output)
    # 고를 것이 없는데 승인 확인에 실패한 approved가 있으면 "실행할 것 없음"으로 단정할 수 없다(선정 스크립트와 같다).
    if not out.claim and sel and sel.errors and not out.lost:
        print(f"::error::승인 확인에 실패한 approved task {len(sel.errors)}건 — 대상 없음으로 확정할 수 없음")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
