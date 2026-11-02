#!/usr/bin/env python3
"""work-planner 스킬 실행 결과 점검 — 러너가 planning으로 점유한 task 한 건을 스킬이 계약대로 계획했나.

대상 선정·점유는 러너(claim_plan_target.py)가 끝냈고, 기준(`--base`)은 그 점유 커밋이다.
그 뒤에 스킬이 남긴 변경을 기계적으로 확인한다.

  - 커밋: 새 커밋이 있고 모두 `plan(<model>/<task>): ...` 규약인가
  - 범위: 스킬 커밋이 바꾼 파일이 data/reconciliation-tasks/<model>.json 하나뿐인가
          (pull --rebase로 섞인 다른 작업자의 커밋은 HEAD reflog로 가려 뺀다 — check_detector_result와 같은 규칙)
  - 단일 대상: 손댄 task가 점유한 그 한 건뿐인가
  - 보존: 그 task의 id·toBeModelId·trigger·createdAt·stateSummary·assessment, 이전 attempts 항목이 그대로인가
  - 스키마: task가 schemas/의 현재 스키마를 통과하는가
  - lock 해제 뒤 쓰기: planned로 넘긴 커밋 뒤에 스킬이 같은 task를 다시 고친 커밋이 있으면 오류
  - 종료 상태: planned + 새 attempts 항목 정확히 1개(plan.summary·steps·executionGuide, preparation),
               재작업이면 reason = 점유 전 status.
               또는 완주하지 못해 시도를 남기지 않고 점유 전 status로 lock을 푼 것(계약상 허용 — 경고).
               planning으로 끝나면 아무도 풀 수 없는 lock이라 오류.

`--github-log`(스킬 빌드 test의 GitHub 대역 기록)가 있으면 스킬이 대상 레포에 실제로 한 일도 본다
(github_log.py `plan` 규칙): 머지 시도 0건, commit status 쓰기 0건, 기본 브랜치 직접·강제 push 0건,
연 PR은 최대 1개이고 preparation.pullRequestUrl과 일치. planned였다면 그 PR의 마지막 head CI가 성공이고(합성 CI),
planned 커밋 시각 뒤의 대상 레포 쓰기가 없어야 한다.

결과 diff를 패치 파일로, 최종 task를 JSON으로 남긴다(아티팩트용). 오류가 있으면 종료 코드 1.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import github_log  # noqa: E402
from check_detector_result import (  # noqa: E402
    Result, by_id, changed_files, git, load_at, load_worktree, make_validator, resolve_base, split_commits,
    touched_task_ids)

TASKS_DIR = "data/reconciliation-tasks"
COMMIT_RE = re.compile(r"^plan\((tbm_[^/\s)]+)/(rct_[0-9]{8}-[0-9]{4})\): \S")
PRESERVED = ("id", "toBeModelId", "trigger", "createdAt", "stateSummary", "assessment")
REWORK = ("review_rejected", "failed")
ROLLBACK = re.compile(r"롤백|되돌|원복|revert|rollback", re.I)


def check_attempt(attempt: dict, from_status: str, res: Result) -> None:
    plan = attempt.get("plan") or {}
    prep = attempt.get("preparation")
    res.facts.update(summary=plan.get("summary"), riskLevel=plan.get("riskLevel"),
                     steps=len(plan.get("steps") or []), preparation=prep)
    missing = [k for k in ("summary", "executionGuide") if not str(plan.get(k) or "").strip()]
    if not plan.get("steps"):
        missing.append("steps")
    if missing:
        res.errors.append("plan 필수 내용 누락: " + ", ".join(missing))
    else:
        res.passed.append(f"plan(summary · steps {len(plan['steps'])}개 · executionGuide) 작성")
    for key in ("riskLevel", "plannedAt"):
        if not plan.get(key):
            res.warnings.append(f"plan.{key} 없음")
    seqs = [s.get("seq") for s in plan.get("steps") or []]
    if seqs and seqs != list(range(1, len(seqs) + 1)):
        res.warnings.append(f"steps.seq가 1부터 연속이 아님: {seqs}")
    if plan.get("steps") and not all(str(s.get("expectedOutcome") or "").strip() for s in plan["steps"]):
        res.warnings.append("expectedOutcome이 없는 단계가 있음 — 검증 가능한 단위가 아님")
    if plan.get("executionGuide") and not ROLLBACK.search(plan["executionGuide"]):
        res.warnings.append("executionGuide에 롤백·되돌리기 절차가 보이지 않음")

    if not isinstance(prep, dict):
        res.errors.append("preparation 없음 — planned로 넘기려면 준비가 기록돼 있어야 함")
    else:
        res.passed.append("preparation 기록" + ("" if prep.get("pullRequestUrl") else " (PR 없음 — 직접 액션)"))

    expected = from_status if from_status in REWORK else None
    if attempt.get("reason") != expected:
        res.warnings.append(f"새 attempts 항목 reason={attempt.get('reason')!r} — 기대값 {expected!r}"
                            "(재작업이면 점유 전 status, 첫 시도면 생략)")


def check(repo: Path, base: str, model_id: str, task_id: str, from_status: str, *,
          claim_subject: str | None = None) -> Result:
    res = Result()
    task_file = f"{TASKS_DIR}/{model_id}.json"
    base = resolve_base(repo, base, claim_subject, res)

    # 스킬의 pull --rebase로 다른 작업자의 커밋이 섞인다 — 이 체크아웃이 만든 커밋만 스킬 결과로 본다.
    own, foreign = split_commits(repo, base, res)
    log = [subject for _, subject in own]
    res.facts["commits"] = log
    if foreign:
        res.warnings.append(f"실행 중 원격에서 rebase로 들어온 다른 작업자의 커밋 {len(foreign)}개는 점검에서 제외: "
                            + ", ".join(f"`{sha[:7]} {subject}`" for sha, subject in foreign[:5]))
    if not log:
        res.errors.append("점유 이후 새 커밋이 없음 — 스킬이 계획을 기록하지 않았다")
    bad = [s for s in log if not (m := COMMIT_RE.match(s)) or (m.group(1), m.group(2)) != (model_id, task_id)]
    for subject in bad:
        res.errors.append(f"커밋 규약 위반 또는 다른 대상: {subject!r}")
    if log and not bad:
        res.passed.append(f"커밋 {len(log)}개 모두 plan({model_id}/{task_id}) 규약")
    dirty = [line for line in git(repo, "status", "--porcelain", "--untracked-files=all").splitlines() if line.strip()]
    if dirty:
        res.warnings.append("커밋되지 않은 변경이 남아 있음: " + ", ".join(line[3:] for line in dirty[:10]))

    files = changed_files(repo, own)
    res.facts["changed_files"] = files
    outside = [f for f in files if f != task_file]
    if outside:
        res.errors.append("허용 범위 밖 파일 변경(모델·스키마·다른 task·대상 레포 클론 금지): " + ", ".join(outside))
    else:
        res.passed.append(f"변경 파일이 {task_file} 하나로 한정")

    base_tasks, cur_tasks = by_id(load_at(repo, base, task_file)), by_id(load_worktree(repo, task_file))
    touched = sorted(touched_task_ids(repo, own, task_file))
    res.facts["touched_tasks"] = touched
    if touched != [task_id]:
        res.errors.append(f"점유한 {task_id} 한 건만 바뀌어야 하는데 바뀐 task: {touched or '없음'}")
    claimed, task = base_tasks.get(task_id), cur_tasks.get(task_id)
    if claimed is None:
        res.errors.append(f"기준 커밋에 점유된 {task_id}가 없음 — --base가 점유 커밋인지 확인")
        return res
    if task is None:
        res.errors.append(f"{task_id}가 삭제됨")
        return res
    res.facts["task"] = task
    if claimed.get("status") != "planning":
        res.errors.append(f"기준 커밋의 task status가 planning이 아님({claimed.get('status')})")
    altered = [k for k in PRESERVED if claimed.get(k) != task.get(k)]
    if altered:
        res.errors.append("고치면 안 되는 필드를 바꿈: " + ", ".join(altered))
    else:
        res.passed.append("점유·감지 기록(trigger·createdAt·stateSummary·assessment) 보존")

    old, new = claimed.get("attempts") or [], task.get("attempts") or []
    if new[:len(old)] != old:
        res.errors.append("이전 attempts 항목을 고치거나 지움 — append-only 위반")
    elif old:
        res.passed.append(f"이전 attempts {len(old)}건 보존")

    schema = json.loads((repo / "schemas/reconciliation-task.schema.json").read_text(encoding="utf-8"))
    errs = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(make_validator(schema).iter_errors(task), key=lambda e: list(map(str, e.absolute_path)))][:5]
    if errs:
        res.errors.extend(f"task 스키마 위반 · {e}" for e in errs)
    else:
        res.passed.append("task 스키마 통과")

    planned_at, late = writes_after_planned(repo, own, task_file, task_id)
    if planned_at:
        res.facts["planned_at"] = planned_at
    if late:
        res.errors.append("planned로 넘긴 뒤 같은 task를 다시 고침(lock을 놓은 뒤 쓰기): " + ", ".join(f"`{s}`" for s in late))
    elif planned_at:
        res.passed.append("planned 전이가 이 task의 마지막 기록")

    status = task.get("status")
    res.facts.update(task_id=task_id, status=status, from_status=from_status)
    added = len(new) - len(old)
    if status == "planned":
        res.passed.append("종료 상태 planned(검토 대기로 lock 해제)")
        if added != 1:
            res.errors.append(f"새 attempts 항목이 정확히 1개여야 하는데 {added}개")
        else:
            check_attempt(new[-1], from_status, res)
    elif status == from_status:
        if added:
            res.errors.append(f"{from_status}로 lock을 풀었는데 attempts가 {added}개 늘어남 — 되돌릴 땐 시도를 남기지 않는다")
        else:
            res.warnings.append(f"계획을 완주하지 못해 시도 없이 {from_status}로 lock 해제 — 사유는 mcode 최종 보고")
    elif status == "planning":
        res.errors.append("planning으로 끝남 — 아무도 풀 수 없는 lock")
    else:
        res.errors.append(f"계획 단계가 남기면 안 되는 status: {status}")
    return res


def writes_after_planned(repo: Path, own: list, task_file: str, task_id: str) -> tuple[str | None, list[str]]:
    """(처음 planned가 된 스킬 커밋의 커밋 시각 UTC, 그 뒤 task를 바꾼 스킬 커밋 제목들)."""
    planned_sha, snapshot, late = None, None, []
    for sha, subject in own:
        cur = by_id(load_at(repo, sha, task_file)).get(task_id)
        if planned_sha is None:
            if cur and cur.get("status") == "planned":
                planned_sha, snapshot = sha, cur
        elif cur != snapshot:
            late.append(subject)
            snapshot = cur
    if planned_sha is None:
        return None, []
    when = git(repo, "show", "-s", "--format=%ct", planned_sha).strip()
    import datetime as dt
    stamp = dt.datetime.fromtimestamp(int(when), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return stamp, late


def check_github(res: Result, entries: list[dict]) -> None:
    """대역 기록으로 대상 레포에 실제로 한 일을 본다. 계획을 완주했으면(planned) 마지막 시도의 preparation과 대조한다."""
    task = res.facts.get("task") or {}
    prep = None
    if task.get("status") == "planned" and task.get("attempts"):
        prep = task["attempts"][-1].get("preparation") or {}
    github_log.merge_into(res, github_log.evaluate(entries, "plan", preparation=prep,
                                                   planned_at=res.facts.get("planned_at")))


def render(res: Result) -> str:
    f = res.facts
    out = ["### 계획 결과 점검", f"- 결과: {'✅ 통과' if res.ok else '❌ 실패'}"]
    if f.get("task_id"):
        out.append(f"- task: `{f['task_id']}` {f.get('from_status')} → planning(러너) → `{f.get('status')}`")
    if f.get("summary"):
        out.append(f"- 계획: {str(f['summary']).strip()[:600]}")
        out.append(f"- 위험도 `{f.get('riskLevel')}` · 단계 {f.get('steps')}개")
    prep = f.get("preparation")
    if isinstance(prep, dict):
        out.append(f"- 준비: {prep.get('repository') or '-'} · 브랜치 `{prep.get('branch') or '-'}` · "
                   f"PR {prep.get('pullRequestUrl') or '없음'}")
        if prep.get("notes"):
            out.append(f"  - {str(prep['notes']).strip()[:400]}")
    if f.get("commits"):
        out.append("- 커밋: " + " → ".join(f"`{c}`" for c in f["commits"]))
    out.extend(github_log.render_facts(f.get("github")))
    for title, items, mark in (("오류", res.errors, "❌"), ("경고", res.warnings, "⚠️"), ("통과", res.passed, "✅")):
        if items:
            out.append(f"\n**{title}** ({len(items)})")
            out.extend(f"- {mark} {i}" for i in items)
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--base", required=True, help="러너의 점유 커밋")
    p.add_argument("--model-id", required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--from-status", required=True, help="러너가 점유하기 전 status")
    p.add_argument("--claim-subject", help="점유 커밋 제목 — rebase로 해시가 바뀐 경우 이것으로 찾는다")
    p.add_argument("--report", type=Path)
    p.add_argument("--json", type=Path)
    p.add_argument("--patch", type=Path, help="base 대비 전체 diff(커밋+미커밋)를 쓸 경로")
    p.add_argument("--task-out", type=Path, help="최종 task 레코드를 쓸 경로")
    p.add_argument("--github-log", type=Path, help="GitHub 대역 기록(JSONL) — 있으면 대상 레포에 한 일도 점검")
    args = p.parse_args(argv)

    try:
        if args.patch:
            base = resolve_base(args.repo, args.base, args.claim_subject, Result())
            git(args.repo, "add", "-N", ".", check=False)
            args.patch.write_text(git(args.repo, "diff", base), encoding="utf-8")
            git(args.repo, "reset", "-q", check=False)
        res = check(args.repo, args.base, args.model_id, args.task_id, args.from_status,
                    claim_subject=args.claim_subject)
        if args.github_log:
            check_github(res, github_log.load(args.github_log))
    except (RuntimeError, json.JSONDecodeError, OSError) as exc:
        res = Result(errors=[f"점검 자체가 실패: {exc}"])
    task = res.facts.pop("task", None)
    if args.task_out and task is not None:
        args.task_out.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = render(res)
    print(text, end="")
    if args.report:
        args.report.write_text(text, encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps({"ok": res.ok, "errors": res.errors, "warnings": res.warnings,
                                         "passed": res.passed, "facts": res.facts},
                                        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    for err in res.errors:
        print(f"::error::{err}")
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
