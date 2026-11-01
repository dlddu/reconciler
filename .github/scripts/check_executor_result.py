#!/usr/bin/env python3
"""work-executor 스킬 실행 결과 점검 — 러너가 점유한 task 한 건을 스킬이 계약대로 실행·검증·기록했나.

기준(`--base`)은 러너의 점유 커밋(`execute(<tbm>/<rct>): claim`, `approved → executing`)이다. 그 뒤에 스킬이 남긴
변경을 기계적으로 확인한다. 커밋 출처 가리기·rebase로 바뀐 점유 커밋 찾기는 check_detector_result.py와 같다.

  - 커밋: 새 커밋이 있고 모두 `execute(<model>/<task>): ...` 규약, 대상이 점유한 task인가(run → verify)
  - 범위: 바뀐 파일이 data/reconciliation-tasks/<model>.json 하나뿐인가(to-be-models.json·스키마 불변)
  - 단일 대상: 손댄 task가 점유한 그 한 건뿐인가
  - 기록 보존: trigger·createdAt·stateSummary·assessment, 이전 attempts, 마지막 attempt의 plan·preparation·review 불변,
               attempt 개수 불변(새 attempt 없음)
  - 스키마: task가 schemas/의 현재 스키마를 통과하는가
  - 종료 상태: succeeded | failed | cancelled — executing·verifying로 남으면 풀 수 없는 lock
  - 기록 일관성: execution(종료 status·finishedAt·stepSeq ⊆ plan seq), verification(passed ⇔ succeeded, checks)
  - push(--require-pushed): 로컬 HEAD가 원격 브랜치에 올라갔나

`--expect`(빌드 테스트 픽스처의 expect.json)를 주면 시나리오 기대값도 본다: 기대 종료 status, 대상 저장소의 결과
(main 파일 내용 또는 refs 불변), asIsVersionAfter가 실제 as-is 버전과 맞는지.

결과 diff를 패치 파일로 남긴다(아티팩트용). 오류가 있으면 종료 코드 1.
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

TASKS_DIR = cdr.TASKS_DIR
COMMIT_RE = re.compile(r"^execute\((tbm_[^/\s)]+)/(rct_[0-9]{8}-[0-9]{4})\): (\S+)")
FINAL_STATUSES = {"succeeded", "failed", "cancelled"}
PRESERVED_FIELDS = ("id", "toBeModelId", "trigger", "createdAt", "stateSummary", "assessment")
WRITABLE_ATTEMPT_FIELDS = {"execution", "verification"}
Result = cdr.Result


def check_commits(repo: Path, base: str, model_id: str, task_id: str, res: Result) -> list:
    own, foreign = cdr.split_commits(repo, base, res)
    log = [subject for _, subject in own]
    res.facts["commits"] = log
    if foreign:
        res.facts["foreign_commits"] = [subject for _, subject in foreign]
        res.warnings.append(f"실행 중 원격에서 rebase로 들어온 다른 작업자의 커밋 {len(foreign)}개는 점검에서 제외: "
                            + ", ".join(f"`{sha[:7]} {subject}`" for sha, subject in foreign[:5]))
    if not log:
        res.errors.append("점유 이후 새 커밋이 없음 — 스킬이 실행·검증을 기록하지 않았다")
    phases, bad = [], []
    for subject in log:
        m = COMMIT_RE.match(subject)
        if not m or (m.group(1), m.group(2)) != (model_id, task_id):
            bad.append(subject)
        else:
            phases.append(m.group(3).rstrip(":"))
    for subject in bad:
        res.errors.append(f"커밋 규약 위반 또는 다른 대상: {subject!r}")
    if log and not bad:
        res.passed.append(f"커밋 {len(log)}개 모두 execute({model_id}/{task_id}) 규약")
    res.facts["phases"] = phases
    if "claim" in phases:
        res.errors.append("스킬이 점유 커밋을 다시 만듦 — 점유는 러너 몫")
    dirty = [line for line in cdr.git(repo, "status", "--porcelain", "--untracked-files=all").splitlines() if line.strip()]
    if dirty:
        res.warnings.append("커밋되지 않은 변경이 남아 있음: " + ", ".join(line[3:] for line in dirty[:10]))
    return own


def check_preserved(claimed: dict, task: dict, res: Result) -> None:
    altered = [k for k in PRESERVED_FIELDS if claimed.get(k) != task.get(k)]
    before, after = claimed.get("attempts") or [], task.get("attempts") or []
    if len(before) != len(after):
        res.errors.append(f"attempts 개수가 바뀜({len(before)} → {len(after)}) — 새 attempt는 planner 몫")
    else:
        altered += [f"attempts[{i}]" for i in range(len(before) - 1) if before[i] != after[i]]
        if before:
            last_b, last_a = before[-1], after[-1]
            keys = (set(last_b) | set(last_a)) - WRITABLE_ATTEMPT_FIELDS
            altered += [f"attempts[-1].{k}" for k in sorted(keys) if last_b.get(k) != last_a.get(k)]
    if altered:
        res.errors.append("실행 단계가 고치면 안 되는 기록을 고침: " + ", ".join(altered))
    else:
        res.passed.append("판정·계획·리뷰 기록 보존(execution·verification만 기록)")


def check_records(task: dict, res: Result) -> None:
    status = task.get("status")
    attempt = (task.get("attempts") or [{}])[-1]
    execution, verification = attempt.get("execution"), attempt.get("verification")
    seqs = {s.get("seq") for s in (attempt.get("plan") or {}).get("steps") or []}
    res.facts.update(status=status, execution=(execution or {}).get("status"),
                     verification=(verification or {}).get("status"),
                     checks=[(c.get("name"), c.get("status"), c.get("detail")) for c in (verification or {}).get("checks") or []],
                     entries=[(e.get("stepSeq"), e.get("status"), e.get("log"))
                              for e in (execution or {}).get("entries") or []],
                     asIsVersionAfter=(verification or {}).get("asIsVersionAfter"))

    if status not in FINAL_STATUSES:
        res.errors.append(f"종료 상태가 아님: {status} — executing·verifying로 남으면 풀 수 없는 lock")
    else:
        res.passed.append(f"종료 상태 {status}")

    if execution is None:
        (res.warnings if status == "cancelled" else res.errors).append("마지막 attempt에 execution이 없음")
    else:
        if execution.get("status") not in ("succeeded", "failed", "aborted"):
            res.errors.append(f"execution.status가 종료값이 아님: {execution.get('status')}")
        if not execution.get("finishedAt"):
            res.errors.append("execution.finishedAt이 없음")
        stray = sorted({e.get("stepSeq") for e in execution.get("entries") or []} - seqs, key=str)
        if stray:
            res.errors.append(f"plan에 없는 stepSeq로 기록: {stray}")
        if not execution.get("entries") and status == "succeeded":
            res.errors.append("succeeded인데 execution.entries가 비어 있음")
        if execution.get("status") in ("succeeded", "failed", "aborted") and execution.get("finishedAt") and not stray:
            res.passed.append(f"execution 기록 {execution.get('status')} · entries {len(execution.get('entries') or [])}개")

    if verification is None:
        (res.errors if status == "succeeded" else res.warnings).append("마지막 attempt에 verification이 없음")
        return
    v_status, checks = verification.get("status"), verification.get("checks") or []
    if not verification.get("verifiedAt"):
        res.warnings.append("verification.verifiedAt이 없음")
    if (v_status == "passed") != (status == "succeeded"):
        res.errors.append(f"verification.status {v_status}와 task status {status}가 어긋남(passed ⇔ succeeded)")
    if status == "succeeded":
        if execution and execution.get("status") != "succeeded":
            res.errors.append(f"succeeded인데 execution.status가 {execution.get('status')}")
        if not checks:
            res.errors.append("succeeded인데 verification.checks가 비어 있음 — 검증 근거 없음")
        failed = [c.get("name") for c in checks if c.get("status") != "passed"]
        if failed:
            res.errors.append(f"succeeded인데 통과하지 못한 check: {failed}")
    if v_status == "pending":
        res.errors.append("verification.status가 pending으로 남음 — 검증을 끝내지 않았다")
    empty = [c.get("name") for c in checks if not str(c.get("detail") or "").strip()]
    if empty:
        res.warnings.append(f"관측값(detail) 없는 check: {empty}")
    res.passed.append(f"verification {v_status} · checks {len(checks)}개")


def check_pushed(repo: Path, res: Result) -> None:
    branch = cdr.git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    proc = subprocess.run(["git", "-C", str(repo), "ls-remote", "origin", f"refs/heads/{branch}"],
                          capture_output=True, text=True)
    remote = proc.stdout.split("\t")[0].strip() if proc.returncode == 0 else ""
    head = cdr.git(repo, "rev-parse", "HEAD").strip()
    if remote == head:
        res.passed.append(f"원격 {branch}에 push됨({head[:7]})")
    else:
        res.errors.append(f"로컬 HEAD {head[:7]}가 원격 {branch}({remote[:7] or '?'})에 올라가지 않음")


def check_expect(expect: dict, task: dict, res: Result) -> None:
    status = task.get("status")
    if status in expect.get("status_in", []):
        res.passed.append(f"시나리오 {expect.get('scenario')}: 기대 status {status}")
    else:
        res.errors.append(f"시나리오 {expect.get('scenario')}: status {status} — 기대 {expect.get('status_in')}")
    target = expect.get("target") or {}
    git_dir = target.get("git_dir")
    if not git_dir:
        return

    def tgit(*args: str) -> tuple[int, str]:
        proc = subprocess.run(["git", "--git-dir", git_dir, *args], capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip()

    _, listing = tgit("for-each-ref", "--format=%(refname)\t%(objectname)")
    refs = dict(line.split("\t") for line in listing.splitlines() if "\t" in line)
    before = {k: v for k, v in (target.get("refs_before") or {}).items() if k.startswith("refs/")}
    res.facts["target_refs"] = refs
    if target.get("refs_unchanged"):
        if refs == before:
            res.passed.append("대상 저장소 refs 불변(전제 붕괴 시 아무것도 바꾸지 않음)")
        else:
            res.errors.append(f"전제가 무너졌는데 대상 저장소를 바꿈: {before} → {refs}")
    else:
        extra = sorted(set(refs) - set(before))
        if extra:
            res.errors.append(f"계획에 없는 ref를 대상 저장소에 만듦: {extra}")
    main_file = target.get("main_file")
    if main_file:
        code, text = tgit("show", f"refs/heads/main:{main_file['path']}")
        if code == 0 and main_file["contains"] in text:
            res.passed.append(f"대상 main {main_file['path']}에 `{main_file['contains']}` 반영")
        else:
            res.errors.append(f"대상 main {main_file['path']}에 `{main_file['contains']}`가 없음")
        if target.get("branch_sha"):
            code, _ = tgit("merge-base", "--is-ancestor", target["branch_sha"], "refs/heads/main")
            (res.passed if code == 0 else res.errors).append(
                "준비 브랜치 head가 main에 병합됨" if code == 0 else "준비 브랜치 head가 main 이력에 없음")
        if target.get("main_sha"):
            code, _ = tgit("merge-base", "--is-ancestor", target["main_sha"], "refs/heads/main")
            if code:
                res.errors.append("대상 main 이력이 재작성됨(이전 main이 조상이 아님) — 강제 push 의심")
    tree = target.get("as_is_tree")
    after = ((task.get("attempts") or [{}])[-1].get("verification") or {}).get("asIsVersionAfter")
    if tree and after is not None:
        code, actual = tgit("rev-parse", f"refs/heads/main:{tree}")
        if code == 0 and after.strip() == actual:
            res.passed.append("asIsVersionAfter가 실제 as-is 버전과 일치")
        else:
            res.warnings.append(f"asIsVersionAfter {after!r}가 실제 as-is 버전 {actual!r}과 다름")
    elif tree and status in ("succeeded", "failed"):
        res.warnings.append("asIsVersionAfter가 없음")


def check(repo: Path, base: str, model_id: str, task_id: str, claim_subject: str | None = None,
          expect: dict | None = None, require_pushed: bool = False) -> Result:
    res = Result()
    task_file = f"{TASKS_DIR}/{model_id}.json"
    base = cdr.resolve_base(repo, base, claim_subject, res)
    own = check_commits(repo, base, model_id, task_id, res)

    files = cdr.changed_files(repo, own)
    res.facts["changed_files"] = files
    outside = [f for f in files if f != task_file]
    if outside:
        res.errors.append("점유 이후 허용 범위 밖 파일 변경(모델·스키마·다른 파일): " + ", ".join(outside))
    else:
        res.passed.append(f"변경 파일이 {task_file} 하나로 한정")

    touched = sorted(cdr.touched_task_ids(repo, own, task_file))
    res.facts["touched_tasks"] = touched
    if touched != [task_id]:
        res.errors.append(f"점유한 {task_id} 한 건만 바뀌어야 하는데 바뀐 task: {touched or '없음'}")
    claimed = cdr.by_id(cdr.load_at(repo, base, task_file)).get(task_id)
    task = cdr.by_id(cdr.load_worktree(repo, task_file)).get(task_id)
    if claimed is None:
        res.errors.append(f"기준 커밋에 점유된 {task_id}가 없음 — --base가 점유 커밋인지 확인")
        return res
    if claimed.get("status") != "executing":
        res.warnings.append(f"기준 커밋의 {task_id} status가 executing이 아님: {claimed.get('status')}")
    if task is None:
        res.errors.append(f"{task_id}가 삭제됨")
        return res
    res.facts["task_id"] = task_id
    if task_id in touched:
        res.passed.append(f"대상 한정: {task_id}")
    check_preserved(claimed, task, res)

    schema = json.loads((repo / "schemas/reconciliation-task.schema.json").read_text(encoding="utf-8"))
    errs = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(cdr.make_validator(schema).iter_errors(task), key=lambda e: list(map(str, e.absolute_path)))][:5]
    if errs:
        res.errors.extend(f"task 스키마 위반 · {e}" for e in errs)
    else:
        res.passed.append("task 스키마 통과")

    check_records(task, res)
    phases = res.facts.get("phases") or []
    if task.get("status") in ("succeeded", "failed") and not {"run", "verify"} <= set(phases):
        res.warnings.append(f"run·verify 단계 커밋이 모두 있지 않음(커밋 단계: {phases or '없음'})")
    if require_pushed:
        check_pushed(repo, res)
    if expect:
        check_expect(expect, task, res)
    return res


def render(res: Result) -> str:
    f = res.facts
    out = ["### 실행 스킬 결과 점검", f"- 결과: {'✅ 통과' if res.ok else '❌ 실패'}"]
    if f.get("task_id"):
        out.append(f"- task: `{f['task_id']}` → status `{f.get('status')}` · execution `{f.get('execution')}` · "
                   f"verification `{f.get('verification')}`")
    if f.get("commits"):
        out.append("- 커밋: " + " → ".join(f"`{c}`" for c in f["commits"]))
    for seq, status, log in f.get("entries") or []:
        out.append(f"  - step {seq} `{status}` — {str(log or '').strip()[:300]}")
    for name, status, detail in f.get("checks") or []:
        out.append(f"  - check {name} `{status}` — {str(detail or '').strip()[:300]}")
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
    p.add_argument("--expect", type=Path, help="시나리오 기대값(executor_fixture.py의 expect.json)")
    p.add_argument("--require-pushed", action="store_true", help="로컬 HEAD가 원격 브랜치에 올라갔는지도 본다")
    p.add_argument("--report", type=Path)
    p.add_argument("--json", type=Path)
    p.add_argument("--patch", type=Path, help="base 대비 전체 diff(커밋+미커밋)를 쓸 경로")
    args = p.parse_args(argv)

    try:
        expect = json.loads(args.expect.read_text(encoding="utf-8")) if args.expect else None
        if args.patch:
            base = cdr.resolve_base(args.repo, args.base, args.claim_subject, Result())
            cdr.git(args.repo, "add", "-N", ".", check=False)
            args.patch.write_text(cdr.git(args.repo, "diff", base), encoding="utf-8")
            cdr.git(args.repo, "reset", "-q", check=False)
        res = check(args.repo, args.base, args.model_id, args.task_id, args.claim_subject, expect, args.require_pushed)
    except (RuntimeError, json.JSONDecodeError, OSError) as exc:
        res = Result(errors=[f"점검 자체가 실패: {exc}"])
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
