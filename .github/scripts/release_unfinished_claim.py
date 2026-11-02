#!/usr/bin/env python3
"""reconciler-drift-detector 워크플로의 「Release unfinished claim」 스텝 — 판정 없이 끝난 점유를 푼다.

러너가 점유(push)한 task는 스킬이 판정을 기록해야 `assessing`을 벗어난다. 스킬이 판정 전에 끝나면
(mcode 타임아웃·런타임 오류·push 실패·작업 취소) task는 `recheckAfter` 없는 `assessing`으로 남는다.
선정 규약상 그런 task는 「다른 워커가 점유 중」이라 아무도 이어받지 않고, 그 모델은 새 버전 변화가 와도
후보에서 빠진다 — 풀 수 없는 lock이다.

이 스크립트는 원격 기본 브랜치에서 그 task를 다시 읽어, 여전히 `assessing`이고 `recheckAfter`가 없을 때만
재확인 유예로 돌린다(`assessment.recheckAfter` = 지금 + 유예). 그러면 시각이 지난 뒤 다음 감지 실행이
「재확인 만료」로 이어받는다(claim_drift_target.py의 recheck_expired). 판정이 이미 기록됐거나(다른 status)
이미 유예 중이면 아무것도 하지 않는다.

커밋: `detect(<model>/<task>): park unfinished`. push가 거절되면 원격 상태로 다시 맞춰 조건부터 재확인한다.

종료 코드: 0 = 풀었거나 풀 것이 없음, 1 = 오류(그대로 두면 lock이 남으므로 실패로 드러낸다).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import claim_drift_target as cdt  # noqa: E402

DEFAULT_GRACE_MINUTES = 30


def fmt(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def plan_park(task: dict | None, now: dt.datetime, grace: dt.timedelta, note: str) -> tuple[dict | None, str]:
    """(바꾼 task 또는 None, 사유). None이면 손댈 것이 없다."""
    if task is None:
        return None, "task가 원격에 없음 — 점유 커밋이 push되지 않았다"
    if task.get("status") != "assessing":
        return None, f"판정 기록됨(status {task.get('status')}) — 풀 것 없음"
    assessment = dict(task.get("assessment") or {})
    if assessment.get("recheckAfter"):
        return None, f"이미 재확인 유예 중(recheckAfter {assessment['recheckAfter']}) — 풀 것 없음"
    previous = str(assessment.get("reason") or "").strip()
    reason = note + (f"\n\n(이전 기록) {previous}" if previous else "")
    updated = dict(task)
    updated["assessment"] = {**assessment, "reason": reason, "assessedAt": fmt(now),
                             "recheckAfter": fmt(now + grace)}
    updated["updatedAt"] = fmt(now)
    return updated, f"판정 없이 끝난 점유를 재확인 유예로 돌림(recheckAfter {fmt(now + grace)})"


def release(repo: Path, model_id: str, task_id: str, now: dt.datetime, *, remote: str, branch: str,
            grace: dt.timedelta, note: str, max_push_attempts: int = 5, before_push=None) -> tuple[str, str]:
    """('parked' | 'noop', 상세)."""
    _, task_validator = cdt.validators(repo)
    rel = f"{cdt.TASKS_DIR}/{model_id}.json"
    for attempt in range(1, max_push_attempts + 1):
        cdt.sync(repo, remote, branch)
        tasks = cdt.load(repo, rel, default=[])
        index = next((i for i, t in enumerate(tasks) if t.get("id") == task_id), None)
        updated, detail = plan_park(tasks[index] if index is not None else None, now, grace, note)
        if updated is None:
            return "noop", detail
        cdt.check_valid(task_validator, updated, f"task {task_id}")
        tasks[index] = updated
        cdt.dump(repo, rel, tasks)
        cdt.git(repo, "add", rel)
        cdt.git(repo, "commit", "--quiet", "-m", f"detect({model_id}/{task_id}): park unfinished")
        if before_push:
            before_push(attempt)
        if cdt.push(repo, remote, branch) == "ok":
            return "parked", detail
    raise cdt.ClaimError(f"push가 {max_push_attempts}회 연속 거절됨 — 원격이 계속 움직이는 중")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--model-id", required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default="main")
    p.add_argument("--grace-minutes", type=int, default=DEFAULT_GRACE_MINUTES)
    p.add_argument("--run-url", default="")
    p.add_argument("--run-exit", default="")
    p.add_argument("--now", help="기준 시각(ISO 8601, 테스트용). 기본은 현재 UTC")
    p.add_argument("--summary-file")
    args = p.parse_args(argv)

    now = (dt.datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now
           else dt.datetime.now(dt.timezone.utc))
    note = ("러너 정리: 감지 실행이 판정을 기록하지 못하고 끝나(" + (f"mcode exit {args.run_exit}" if args.run_exit else "실행 중단")
            + (f", {args.run_url}" if args.run_url else "") + ") 점유를 재확인 유예로 돌렸다. "
            "recheckAfter가 지나면 다음 감지 실행이 「재확인 만료」로 이어받아 판정한다. 이 기록은 판정이 아니다.")
    try:
        status, detail = release(args.repo, args.model_id, args.task_id, now, remote=args.remote, branch=args.branch,
                                 grace=dt.timedelta(minutes=args.grace_minutes), note=note)
    except (cdt.ClaimError, OSError, ValueError) as exc:
        print(f"::error::미완료 점유 해제 실패 — {args.task_id}가 recheckAfter 없는 assessing으로 남을 수 있다: {exc}")
        return 1
    line = f"- {'⏸️ 재확인 유예로 돌림' if status == 'parked' else '✅ 풀 것 없음'}: `{args.task_id}` — {detail}"
    print(line)
    if status == "parked":
        print(f"::warning::{args.task_id}: {detail}")
    if args.summary_file:
        Path(args.summary_file).write_text("#### Release unfinished claim\n" + line + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
