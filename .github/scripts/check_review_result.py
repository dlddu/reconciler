#!/usr/bin/env python3
"""work-review 스킬 실행 결과 점검 — 러너가 점유한 task 한 건을 스킬이 계약대로 판정했나.

대상 선정·점유(`planned → reviewing`)는 러너(claim_review_target.py)가 끝냈고, 기준(`--base`)은 그 점유 커밋이다.
그 뒤에 스킬이 남긴 변경을 기계적으로 확인한다. 커밋 출처 가르기·rebase된 점유 커밋 찾기는
check_detector_result.py와 같은 방식을 쓴다.

  - 커밋: 새 커밋이 있고 모두 `review(<model>/<task>): ...` 규약인가
  - 범위: 스킬 커밋이 바꾼 파일이 data/reconciliation-tasks/<model>.json 하나뿐인가
  - 단일 대상: 손댄 task가 점유한 그 한 건뿐인가
  - 기록 보존: 그 task의 id·toBeModelId·trigger·createdAt·stateSummary·assessment, 이전 attempts 항목,
               마지막 항목의 review 밖 키(plan·preparation 등)가 점유 때 그대로인가
  - 스키마: task가 schemas/의 현재 스키마를 통과하는가
  - 종료 상태: approved | review_rejected | cancelled (reviewing이면 풀리지 않은 lock, planned면 판정 없이 해제)
  - 판정 기록: review.status가 status와 맞고 reviewedAt·reason이 있으며, 거부면 comment가 있고,
               manualApproval은 승인에만 있다
  - (선택) 기대 status: --expect-statuses 중 하나인가 — replay에서 머지·종료된 PR을 승인하면 실패
  - (선택) 대화 기록: 대상 레포에 쓰는 호출(commit status·머지·코멘트·리뷰)이 없는가

결과 diff·판정된 task를 파일로 남긴다(아티팩트용). 오류가 있으면 종료 코드 1.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_detector_result as cdr  # noqa: E402

TASKS_DIR = "data/reconciliation-tasks"
COMMIT_RE = re.compile(r"^review\((tbm_[^/\s)]+)/(rct_[0-9]{8}-[0-9]{4})\): \S")
FINAL = {"approved": "approved", "review_rejected": "rejected", "cancelled": "rejected"}
PRESERVED = ("id", "toBeModelId", "trigger", "createdAt", "stateSummary", "assessment")
REASON_SOFT_LIMIT = 1500
# 대화 기록의 도구 호출(이름+인자 JSON)에서 대상 레포에 쓰는 동작으로 보는 패턴.
TARGET_WRITES = [
    ("commit status 쓰기(MCP)", r"github_commit_status_create"),
    ("commit status 쓰기(API)", r"(-X\s*POST|--method\s+POST|method=.?POST)[^\n]{0,200}/statuses/|/statuses/[0-9a-f]{7,40}[^\n]{0,80}(-X\s*POST|-f\s+state=)"),
    ("PR 머지", r"gh\s+pr\s+merge|/pulls/\d+/merge"),
    ("PR 코멘트·리뷰", r"gh\s+pr\s+(comment|review)\b|/issues/\d+/comments[^\n]{0,80}(POST|-f\s+body)|/pulls/\d+/reviews[^\n]{0,80}(POST|-f\s+event)"),
]


# 도구 결과(output 등)는 보지 않는다 — 스킬이 금지 서술이 든 자기 SKILL.md를 읽기만 해도 걸리기 때문이다.
OUTPUT_KEYS = {"output", "result", "results", "content", "error", "status"}


def call_text(call: dict) -> str:
    """도구 호출에서 이름과 입력만 텍스트로."""
    return json.dumps({k: v for k, v in call.items() if k not in OUTPUT_KEYS}, ensure_ascii=False)


def check(repo: Path, base: str, model_id: str, task_id: str, claim_subject: str | None = None,
          expect: list[str] | None = None, transcript: Path | None = None) -> cdr.Result:
    res = cdr.Result()
    task_file = f"{TASKS_DIR}/{model_id}.json"
    base = cdr.resolve_base(repo, base, claim_subject, res)

    # ── 커밋 ──
    own, foreign = cdr.split_commits(repo, base, res)
    log = [subject for _, subject in own]
    res.facts["commits"] = log
    if foreign:
        res.facts["foreign_commits"] = [subject for _, subject in foreign]
        res.warnings.append(f"실행 중 원격에서 rebase로 들어온 다른 커밋 {len(foreign)}개는 점검에서 제외: "
                            + ", ".join(f"`{sha[:7]} {subject}`" for sha, subject in foreign[:5]))
    if not log:
        res.errors.append("점유 이후 새 커밋이 없음 — 스킬이 판정을 기록하지 않았다")
    bad = [s for s in log if not (m := COMMIT_RE.match(s)) or (m.group(1), m.group(2)) != (model_id, task_id)]
    for subject in bad:
        res.errors.append(f"커밋 규약 위반 또는 다른 대상: {subject!r}")
    if log and not bad:
        res.passed.append(f"커밋 {len(log)}개 모두 review({model_id}/{task_id}) 규약")
    dirty = [line for line in cdr.git(repo, "status", "--porcelain", "--untracked-files=all").splitlines() if line.strip()]
    if dirty:
        res.warnings.append("커밋되지 않은 변경이 남아 있음: " + ", ".join(line[3:] for line in dirty[:10]))

    # ── 범위 ──
    files = cdr.changed_files(repo, own)
    res.facts["changed_files"] = files
    outside = [f for f in files if f != task_file]
    if outside:
        res.errors.append("점유 이후 허용 범위 밖 파일 변경(모델·스키마·다른 task 파일은 리뷰 몫이 아님): " + ", ".join(outside))
    else:
        res.passed.append(f"변경 파일이 {task_file} 하나로 한정")

    # ── 대상 task ──
    claimed = cdr.by_id(cdr.load_at(repo, base, task_file)).get(task_id)
    task = cdr.by_id(cdr.load_worktree(repo, task_file)).get(task_id)
    touched = sorted(cdr.touched_task_ids(repo, own, task_file))
    res.facts["touched_tasks"] = touched
    if touched != [task_id]:
        res.errors.append(f"점유한 {task_id} 한 건만 바뀌어야 하는데 바뀐 task: {touched or '없음'}")
    if claimed is None:
        res.errors.append(f"기준 커밋에 점유된 {task_id}가 없음 — --base가 점유 커밋인지 확인")
        return res
    if task is None:
        res.errors.append(f"{task_id}가 삭제됨")
        return res
    res.facts["task"] = task
    if claimed.get("status") != "reviewing":
        res.warnings.append(f"기준 커밋의 status가 reviewing이 아님({claimed.get('status')}) — 점유 커밋인지 확인")

    altered = [k for k in PRESERVED if claimed.get(k) != task.get(k)]
    if altered:
        res.errors.append("리뷰 밖 기록을 고침: " + ", ".join(altered))
    else:
        res.passed.append("trigger·stateSummary·assessment 보존")

    before, after = claimed.get("attempts") or [], task.get("attempts") or []
    if len(before) != len(after):
        res.errors.append(f"attempts 항목 수가 바뀜({len(before)} → {len(after)}) — 리뷰는 마지막 항목에 review만 채운다")
    elif not before:
        res.errors.append("attempts가 없음 — 리뷰할 시도가 없다")
    else:
        if before[:-1] != after[:-1]:
            res.errors.append("이전 attempts 항목을 고침 — append-only 위반")
        last_b, last_a = before[-1], after[-1]
        changed = sorted(k for k in set(last_b) | set(last_a) if k != "review" and last_b.get(k) != last_a.get(k))
        if changed:
            res.errors.append("마지막 attempts 항목의 review 밖 키를 고침: " + ", ".join(changed))
        if before[:-1] == after[:-1] and not changed:
            res.passed.append("attempts: 마지막 항목의 review만 바뀜")

    schema = json.loads((repo / "schemas/reconciliation-task.schema.json").read_text(encoding="utf-8"))
    errs = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(cdr.make_validator(schema).iter_errors(task),
                            key=lambda e: list(map(str, e.absolute_path)))][:5]
    if errs:
        res.errors.extend(f"task 스키마 위반 · {e}" for e in errs)
    else:
        res.passed.append("task 스키마 통과")

    # ── 종료 상태와 판정 기록 ──
    status = task.get("status")
    review = (after[-1].get("review") if after else None) or {}
    res.facts.update(task_id=task_id, status=status, review_status=review.get("status"),
                     reason=review.get("reason"), comment=review.get("comment"),
                     manualApproval=review.get("manualApproval"), reviewedAt=review.get("reviewedAt"))
    if status == "reviewing":
        res.errors.append("reviewing으로 끝남 — 아무도 풀 수 없는 lock")
    elif status == "planned":
        res.errors.append("planned로 되돌림 — 판정 없이 lock만 해제(도구 장애 등은 최종 보고·대화 기록 참고)")
    elif status not in FINAL:
        res.errors.append(f"리뷰 단계가 남기면 안 되는 status: {status}")
    else:
        res.passed.append(f"종료 상태 {status}")
        want = FINAL[status]
        if review.get("status") != want:
            res.errors.append(f"status {status}인데 review.status가 {review.get('status')!r}(기대 {want!r})")
        else:
            res.passed.append(f"review.status {want} — status와 일치")
        if not str(review.get("reviewedAt") or "").strip():
            res.errors.append("review.reviewedAt이 없음")
        reason = str(review.get("reason") or "").strip()
        if not reason:
            res.errors.append("review.reason이 비어 있음 — 근거 없는 판정")
        elif len(reason) > REASON_SOFT_LIMIT:
            res.warnings.append(f"review.reason이 {len(reason)}자 — 2~4문장 기준보다 김")
        if want == "rejected" and not str(review.get("comment") or "").strip():
            res.errors.append("거부인데 review.comment가 없음 — planner가 고칠 것이 남지 않는다")
        if review.get("manualApproval") and status != "approved":
            res.errors.append("manualApproval은 승인에만 남긴다")
        elif review.get("manualApproval"):
            res.passed.append(f"사람 승인 요구 기록: {review['manualApproval'].get('context')}")

    if expect:
        if status in expect:
            res.passed.append(f"기대 status 충족: {status} ∈ {expect}")
        else:
            res.errors.append(f"기대 status가 아님: {status} ∉ {expect}")

    # ── 대화 기록: 대상 레포에 쓰지 않았나 ──
    if transcript:
        if not transcript.exists():
            res.warnings.append(f"대화 기록 {transcript}이 없어 대상 레포 쓰기 여부를 보지 못함")
        else:
            import mcode_transcript as mt

            hits = []
            for call in mt.tool_calls(str(transcript)).values():
                text = call_text(call)
                hits += [label for label, pat in TARGET_WRITES if re.search(pat, text)]
            if hits:
                res.errors.append("대상 레포 쓰기 시도: " + ", ".join(sorted(set(hits))))
            else:
                res.passed.append("대화 기록에 대상 레포 쓰기 호출 없음")
    return res


def render(res: cdr.Result) -> str:
    f = res.facts
    out = ["### 스킬 테스트 결과 점검", f"- 결과: {'✅ 통과' if res.ok else '❌ 실패'}"]
    if f.get("task_id"):
        ma = f.get("manualApproval")
        out.append(f"- task: `{f['task_id']}` → status `{f.get('status')}` · review `{f.get('review_status')}`"
                   + (f" · 사람 승인 `{ma.get('context')}` @ `{str(ma.get('sha'))[:7]}`" if isinstance(ma, dict) else ""))
    if f.get("reason"):
        out.append(f"- 근거: {str(f['reason']).strip()[:800]}")
    if f.get("comment"):
        out.append(f"- planner에게: {str(f['comment']).strip()[:800]}")
    if f.get("commits"):
        out.append("- 커밋: " + " → ".join(f"`{c}`" for c in f["commits"]))
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
    p.add_argument("--claim-subject", help="점유 커밋 제목 — rebase로 해시가 바뀐 경우 이것으로 찾는다")
    p.add_argument("--expect-statuses", default="", help="쉼표 구분 — 최종 status가 이 중 하나여야 한다")
    p.add_argument("--transcript", type=Path, help="mcode stream-json 대화 기록")
    p.add_argument("--report", type=Path)
    p.add_argument("--json", type=Path)
    p.add_argument("--patch", type=Path, help="base 대비 전체 diff(커밋+미커밋)를 쓸 경로")
    p.add_argument("--task-out", type=Path, help="판정된 task 레코드(JSON)를 쓸 경로")
    args = p.parse_args(argv)

    expect = [s.strip() for s in args.expect_statuses.split(",") if s.strip()]
    try:
        if args.patch:
            base = cdr.resolve_base(args.repo, args.base, args.claim_subject, cdr.Result())
            cdr.git(args.repo, "add", "-N", ".", check=False)
            args.patch.write_text(cdr.git(args.repo, "diff", base), encoding="utf-8")
            cdr.git(args.repo, "reset", "-q", check=False)
        res = check(args.repo, args.base, args.model_id, args.task_id, args.claim_subject,
                    expect=expect, transcript=args.transcript)
    except (RuntimeError, json.JSONDecodeError, OSError, subprocess.SubprocessError) as exc:
        res = cdr.Result(errors=[f"점검 자체가 실패: {exc}"])
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
                                        ensure_ascii=False, indent=2), encoding="utf-8")
    for err in res.errors:
        print(f"::error::{err}")
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
