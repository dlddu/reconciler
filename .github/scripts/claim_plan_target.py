#!/usr/bin/env python3
"""reconciler-work-planner 워크플로의 「Claim target」 스텝 — 대상 선정 + 점유(claim).

계획 스킬의 Step 0(대상 선정)과 점유(`→ planning` compare-and-set)를 러너가 결정적으로 수행한다.
MiniMax Code는 점유가 끝난 task 한 건을 넘겨받아 계획·준비·지침만 쓴다(근거는 README 「점유는 러너가 한다」 —
감지와 같은 이유).

절차(후보 하나당):
  1. 원격 기본 브랜치로 맞춘다(fetch + reset --hard).
  2. select_plan_target.select_target으로 한 건을 고른다(경쟁에서 진 task는 제외).
     계획 대상 = action_required · review_rejected · failed 이고 모델이 꺼져 있지 않은 task.
  3. 점유 커밋: 선정 시점 status(from_status)가 그대로인지, 모델이 아직 켜져 있는지 재확인 →
     status를 planning으로, updatedAt을 지금으로 → `plan(<tbm>/<rct>): claim` 커밋 → 즉시 push.
     이 push가 lock이다.
     - push가 거절되면(무관한 커밋이 먼저 들어온 경우 포함) 1부터 다시 해 전제를 새 상태에서 재확인한다.
     - 전제가 바뀌었으면 다른 워커가 먼저 집은 것 → 그 task를 빼고 2로(지목 실행이면 종료).

점유 커밋은 그 task의 status·updatedAt만 바꾼다. attempts는 건드리지 않는다 — 새 시도 항목은 스킬이
계획을 쓰면서 덧붙인다(재작업이면 reason에 from_status). Claude Code 계획 스킬의 점유와 같은 형태다.

출력(GITHUB_OUTPUT): found, claimed, task_id, model_id, from_status, claim_reason, claim_commit,
                    claim_message, attempt_count, lost_count
종료 코드: 0 = 점유했거나 대상 없음, 1 = 오류, 2 = 사용법/데이터 오류
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import claim_drift_target as cdt  # noqa: E402  (git·sync·push·검증 헬퍼 재사용)
import select_plan_target as spt  # noqa: E402

TASKS_DIR = "data/reconciliation-tasks"
MODELS_FILE = "data/to-be-models.json"
MAX_CANDIDATES = 5
ClaimError = cdt.ClaimError


@dataclass
class ClaimResult:
    status: str  # claimed | lost
    commit: str = ""
    detail: str = ""
    message: str = ""


@dataclass
class Outcome:
    selection: spt.Selection | None = None
    claim: ClaimResult | None = None
    lost: list = field(default_factory=list)  # (model/task, 사유)


def fmt_time(now: dt.datetime) -> str:
    return now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def plan_claim(models: list, tasks: list, sel: spt.Selection, now: dt.datetime) -> tuple[str, str]:
    """tasks(in-place)에 점유를 적용한다. (lost 사유, 커밋 메시지) — 사유가 있으면 경쟁 패배."""
    task = next((t for t in tasks if t.get("id") == sel.target_id), None)
    if task is None:
        return f"{sel.target_id}가 사라짐", ""
    if task.get("status") != sel.from_status:
        return f"status가 {sel.from_status} → {task.get('status')}로 바뀜(다른 워커가 먼저 점유)", ""
    model = next((m for m in models if m.get("id") == sel.model_id), None)
    if not spt.is_enabled(model):
        return "그 사이 모델 감지가 비활성화됨(enabled:false) — 주차", ""
    task["status"] = "planning"
    task["updatedAt"] = fmt_time(now)
    return "", f"plan({sel.model_id}/{sel.target_id}): claim"


def claim(repo: Path, sel: spt.Selection, now: dt.datetime, *, remote: str, branch: str,
          max_push_attempts: int = 5, before_push=None) -> ClaimResult:
    """선정된 한 건을 compare-and-set으로 점유한다. 경쟁에서 지면 status=lost."""
    _, task_validator = cdt.validators(repo)
    task_rel = f"{TASKS_DIR}/{sel.model_id}.json"
    for attempt in range(1, max_push_attempts + 1):
        if attempt > 1:
            cdt.sync(repo, remote, branch)
        models = cdt.load(repo, MODELS_FILE, default=[])
        tasks = cdt.load(repo, task_rel, default=[])
        lost, message = plan_claim(models, tasks, sel, now)
        if lost:
            return ClaimResult(status="lost", detail=lost)
        task = next(t for t in tasks if t["id"] == sel.target_id)
        cdt.check_valid(task_validator, task, f"task {task['id']}")
        cdt.dump(repo, task_rel, tasks)
        cdt.git(repo, "add", task_rel)
        if not cdt.git(repo, "diff", "--cached", "--quiet", check=False).returncode:
            raise ClaimError("점유 커밋에 변경이 없음")
        cdt.git(repo, "commit", "--quiet", "-m", message)
        commit = cdt.git(repo, "rev-parse", "HEAD").stdout.strip()
        detail = f"{sel.from_status} → planning"
        if before_push:
            before_push(attempt)
        if cdt.push(repo, remote, branch) == "ok":
            return ClaimResult(status="claimed", commit=commit, message=message, detail=detail)
        # 원격이 앞섰다 — 새 상태에서 전제를 다시 확인한다(무관한 커밋이면 그대로 재시도된다).
    raise ClaimError(f"push가 {max_push_attempts}회 연속 거절됨 — 원격이 계속 움직이는 중")


def run(repo: Path, now: dt.datetime, *, explicit: str | None, remote: str, branch: str,
        before_push=None) -> Outcome:
    out = Outcome()
    excluded: set[str] = set()
    for _ in range(MAX_CANDIDATES):
        cdt.sync(repo, remote, branch)
        sel = spt.select_target(repo, explicit=explicit, exclude=frozenset(excluded))
        out.selection = sel
        if not sel.found:
            return out
        result = claim(repo, sel, now, remote=remote, branch=branch, before_push=before_push)
        if result.status == "claimed":
            out.claim = result
            return out
        key = f"{sel.model_id}/{sel.target_id}"
        out.lost.append((key, result.detail))
        if explicit:
            return out  # 지목 실행은 다른 후보로 넘어가지 않는다
        excluded.add(key)
    return out


def write_outputs(out: Outcome, path: str | None) -> None:
    sel, c = out.selection, out.claim
    ok = bool(c and sel)
    lines = {
        "found": "true" if ok else "false",
        "claimed": "true" if ok else "false",
        "task_id": sel.target_id if ok else "",
        "model_id": sel.model_id if ok else "",
        "from_status": sel.from_status if ok else "",
        "claim_reason": sel.reason if ok else "",
        "claim_commit": c.commit if ok else "",
        "claim_message": c.message if ok else "",
        "attempt_count": str(sel.attempt_count) if ok else "0",
        "lost_count": str(len(out.lost)),
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
        rework = f", 이전 시도 {sel.attempt_count}건" if sel.attempt_count else ""
        lines.append(f"- 점유: `{sel.model_id}/{sel.target_id}` ({sel.reason}{rework}) — {out.claim.detail}")
        lines.append(f"- 커밋: `{out.claim.message}`")
    else:
        lines.append("- 이번에 점유한 대상 없음")
    if out.selection:
        lines.append("")
        lines.append(spt.render_summary(out.selection).rstrip())
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", default=".", type=Path)
    p.add_argument("--target", default="", help="지목 대상(rct_… · tbm_… · tbm_…/rct_…), 비우면 자동 선정")
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default="main")
    p.add_argument("--now", help="기준 시각(ISO 8601, 테스트용)")
    p.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    p.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = p.parse_args(argv)

    now = spt.parse_time(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    target = args.target.strip() or None
    try:
        if target:
            spt.parse_target(target)
        out = run(args.repo, now, explicit=target, remote=args.remote, branch=args.branch)
    except spt.SelectionError as exc:
        print(f"::error::{exc}")
        return 2
    except ClaimError as exc:
        print(f"::error::{exc}")
        return 1

    for target_id, msg in (out.selection.warnings if out.selection else []):
        print(f"::warning::{target_id}: {msg}")
    summary = render(out)
    print(summary, end="")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as fh:
            fh.write(summary)
    write_outputs(out, args.github_output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
