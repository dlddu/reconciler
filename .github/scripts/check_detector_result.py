#!/usr/bin/env python3
"""drift-detector 스킬 실행 결과 점검 — 러너가 점유한 task 한 건을 스킬이 계약대로 판정했나.

대상 선정·점유는 러너(claim_drift_target.py)가 끝냈고, 기준(`--base`)은 그 점유 커밋이다.
그 뒤에 스킬이 남긴 변경을 기계적으로 확인한다.

  - 커밋: 새 커밋이 있고 모두 `detect(<model>/<task>): ...` 규약, 대상이 점유한 task인가
  - 범위: 스킬 커밋이 바꾼 파일이 data/reconciliation-tasks/<model>.json 하나뿐인가
          (to-be-models.json·스키마·다른 파일은 점유 이후 건드리면 안 된다)
  - 단일 대상: 손댄 task가 점유한 그 한 건뿐인가(새 task·다른 task 없음)
  - 점유 기록 보존: 그 task의 trigger·createdAt·id·toBeModelId가 점유 때 그대로인가
  - 스키마: task가 schemas/의 현재 스키마를 통과하는가
  - 종료 상태: no_action_needed | action_required | assessing+recheckAfter 중 하나인가,
               stateSummary(asIs/toBe/gap)·assessment.reason이 채워졌나

실제 모드에서는 스킬이 push 전에 `pull --rebase`하므로, 실행 중 다른 작업자가 기본 브랜치에 올린 커밋이
`base..HEAD`에 섞인다. 그 커밋은 스킬의 결과가 아니므로 HEAD reflog로 가려 점검에서 뺀다 — 이 체크아웃에서
만들어진 커밋(`commit:`, rebase·cherry-pick의 `(pick):` 등, 로컬 병합 커밋)만 스킬 커밋으로 보고, 나머지는
원격에서 들어온 커밋으로 경고에만 남긴다. reflog를 읽을 수 없으면 전부 스킬 커밋으로 본다(보수적).

결과 diff를 패치 파일로 남긴다(아티팩트용). 오류가 있으면 종료 코드 1.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

TASKS_DIR = "data/reconciliation-tasks"
COMMIT_RE = re.compile(r"^detect\((tbm_[^/\s)]+)/(rct_[0-9]{8}-[0-9]{4})\): \S")
FINAL_STATUSES = {"no_action_needed", "action_required", "assessing"}
CLAIM_FIELDS = ("id", "toBeModelId", "trigger", "createdAt")
# HEAD reflog에서 이 체크아웃이 커밋을 '만든' 항목. reflog 동작 이름에는 플래그가 붙는다
# (예: `pull -q --rebase (pick): ...`). `(start): checkout <upstream>`·`pull: Fast-forward`·`reset:`은 만든 게 아니다.
LOCAL_REFLOG_RE = re.compile(r"^(commit\b[^:]*:|cherry-pick\b|revert\b|.*\((pick|reword|edit|squash|fixup|continue)\):)"
                             r"|Merge made by")


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and proc.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def load_at(repo: Path, rev: str, path: str):
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{path}"], capture_output=True, text=True)
    return json.loads(proc.stdout) if proc.returncode == 0 else None


def load_worktree(repo: Path, path: str):
    file = repo / path
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else None


def local_commits(repo: Path) -> set[str] | None:
    """이 체크아웃에서 만들어진 커밋(HEAD reflog 기준). reflog가 없으면 None — 출처를 가릴 수 없다."""
    proc = subprocess.run(["git", "-C", str(repo), "reflog", "--format=%H%x09%gs", "HEAD"],
                          capture_output=True, text=True)
    if proc.returncode or not proc.stdout.strip():
        return None
    return {sha for sha, _, action in (line.partition("\t") for line in proc.stdout.splitlines())
            if LOCAL_REFLOG_RE.search(action)}


def split_commits(repo: Path, base: str, res: Result) -> tuple[list, list]:
    """base..HEAD를 (스킬 커밋, 원격에서 rebase로 들어온 커밋)으로 나눈다. 각 항목은 (sha, 제목), 오래된 순."""
    rows = [line.partition("\t") for line in git(repo, "log", "--reverse", "--format=%H%x09%s", f"{base}..HEAD").splitlines()]
    commits = [(sha, subject) for sha, _, subject in rows]
    local = local_commits(repo)
    if local is None:
        if commits:
            res.warnings.append("HEAD reflog를 읽지 못해 커밋 출처를 가릴 수 없음 — 점유 이후 커밋 전부를 스킬 커밋으로 점검")
        return commits, []
    return [c for c in commits if c[0] in local], [c for c in commits if c[0] not in local]


def commit_files(repo: Path, sha: str) -> set[str]:
    # --cc: 병합 커밋은 모든 부모와 다른 파일(충돌 해소분)만 — 병합으로 끌려온 원격 변경은 빼고 본다.
    return set(git(repo, "diff-tree", "-r", "--root", "--no-commit-id", "--name-only", "--cc", sha).split())


def uncommitted_files(repo: Path) -> set[str]:
    tracked = git(repo, "diff", "--name-only", "HEAD").split()
    untracked = git(repo, "ls-files", "--others", "--exclude-standard").split()
    return set(tracked) | set(untracked)


def changed_files(repo: Path, own: list) -> list[str]:
    files = uncommitted_files(repo)
    for sha, _ in own:
        files |= commit_files(repo, sha)
    return sorted(files)


def touched_task_ids(repo: Path, own: list, task_file: str) -> set[str]:
    """스킬 커밋(과 미커밋 변경)이 실제로 바꾼 task id. 원격 커밋이 같은 파일의 다른 task를 바꾼 것은 세지 않는다."""
    def diff(a, b) -> set[str]:
        return {k for k in set(a) | set(b) if a.get(k) != b.get(k)}

    touched: set[str] = set()
    for sha, _ in own:
        after = by_id(load_at(repo, sha, task_file))
        parents = git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
        per_parent = [diff(by_id(load_at(repo, p, task_file)), after) for p in parents] or [diff({}, after)]
        touched |= set.intersection(*per_parent)
    touched |= diff(by_id(load_at(repo, "HEAD", task_file)), by_id(load_worktree(repo, task_file)))
    return touched


def make_validator(schema: dict):
    import jsonschema  # 러너에서 pip로 설치한다
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema, format_checker=cls.FORMAT_CHECKER)


def by_id(items) -> dict:
    return {item.get("id"): item for item in (items or []) if isinstance(item, dict)}


def resolve_base(repo: Path, base: str, claim_subject: str | None, res: Result) -> str:
    """스킬이 push 전에 `pull --rebase`하면 점유 커밋이 새 해시로 다시 쓰인다 — 같은 제목의 커밋을 찾는다."""
    if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", base, "HEAD"]).returncode == 0:
        return base
    if claim_subject:
        for line in git(repo, "log", "-300", "--format=%H%x09%s", "HEAD").splitlines():
            sha, _, subject = line.partition("\t")
            if subject == claim_subject:
                res.warnings.append(f"점유 커밋이 rebase로 다시 쓰임({base[:7]} → {sha[:7]}) — 새 커밋 기준으로 점검")
                return sha
    raise RuntimeError(f"점유 커밋 {base[:7]}이 HEAD 이력에 없고, 같은 제목의 커밋도 찾지 못함")


def check(repo: Path, base: str, model_id: str, task_id: str, claim_subject: str | None = None) -> Result:
    res = Result()
    task_file = f"{TASKS_DIR}/{model_id}.json"
    base = resolve_base(repo, base, claim_subject, res)

    # ── 커밋 ──
    own, foreign = split_commits(repo, base, res)
    log = [subject for _, subject in own]
    res.facts["commits"] = log
    if foreign:
        res.facts["foreign_commits"] = [subject for _, subject in foreign]
        res.warnings.append(f"실행 중 원격에서 rebase로 들어온 다른 작업자의 커밋 {len(foreign)}개는 점검에서 제외: "
                            + ", ".join(f"`{sha[:7]} {subject}`" for sha, subject in foreign[:5]))
    if not log:
        res.errors.append("점유 이후 새 커밋이 없음 — 스킬이 판정을 기록하지 않았다")
    bad = [s for s in log if not (m := COMMIT_RE.match(s)) or (m.group(1), m.group(2)) != (model_id, task_id)]
    for subject in bad:
        res.errors.append(f"커밋 규약 위반 또는 다른 대상: {subject!r}")
    if log and not bad:
        res.passed.append(f"커밋 {len(log)}개 모두 detect({model_id}/{task_id}) 규약")
    dirty = [line for line in git(repo, "status", "--porcelain", "--untracked-files=all").splitlines() if line.strip()]
    if dirty:
        res.warnings.append("커밋되지 않은 변경이 남아 있음: " + ", ".join(line[3:] for line in dirty[:10]))

    # ── 범위 ──
    files = changed_files(repo, own)
    res.facts["changed_files"] = files
    outside = [f for f in files if f != task_file]
    if outside:
        res.errors.append("점유 이후 허용 범위 밖 파일 변경(점유 기록·모델·스키마는 러너 몫): " + ", ".join(outside))
    else:
        res.passed.append(f"변경 파일이 {task_file} 하나로 한정")

    # ── 대상 task ──
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
    if task_id in touched:
        res.passed.append(f"대상 한정: {task_id}")
    altered = [k for k in CLAIM_FIELDS if claimed.get(k) != task.get(k)]
    if altered:
        res.errors.append("점유 기록을 고침: " + ", ".join(altered))
    else:
        res.passed.append("점유 기록(trigger·createdAt) 보존")

    schema = json.loads((repo / "schemas/reconciliation-task.schema.json").read_text(encoding="utf-8"))
    errs = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(make_validator(schema).iter_errors(task), key=lambda e: list(map(str, e.absolute_path)))][:5]
    if errs:
        res.errors.extend(f"task 스키마 위반 · {e}" for e in errs)
    else:
        res.passed.append("task 스키마 통과")

    # ── 종료 상태 ──
    status = task.get("status")
    assessment = task.get("assessment") or {}
    summary = task.get("stateSummary") or {}
    res.facts.update(task_id=task_id, status=status, gap=summary.get("gap"), reason=assessment.get("reason"),
                     recheckAfter=assessment.get("recheckAfter"))
    if status not in FINAL_STATUSES:
        res.errors.append(f"감지 단계가 남기면 안 되는 status: {status}")
    elif status == "assessing" and not assessment.get("recheckAfter"):
        res.errors.append("assessing으로 끝났는데 assessment.recheckAfter가 없음 — 풀 수 없는 lock")
    else:
        res.passed.append(f"종료 상태 {status}" + (" + recheckAfter" if status == "assessing" else ""))
    for key in ("asIs", "toBe", "gap"):
        if not str(summary.get(key) or "").strip():
            (res.errors if key != "gap" else res.warnings).append(f"stateSummary.{key}가 비어 있음")
    if not str(assessment.get("reason") or "").strip():
        res.errors.append("assessment.reason이 비어 있음 — 근거 없는 판정")
    return res


def render(res: Result) -> str:
    f = res.facts
    out = ["### 스킬 테스트 결과 점검", f"- 결과: {'✅ 통과' if res.ok else '❌ 실패'}"]
    if f.get("task_id"):
        out.append(f"- task: `{f['task_id']}` → status `{f.get('status')}`"
                   + (f" (recheckAfter {f['recheckAfter']})" if f.get("recheckAfter") else ""))
    if f.get("gap"):
        out.append(f"- gap: {str(f['gap']).strip()[:400]}")
    if f.get("reason"):
        out.append(f"- 근거: {str(f['reason']).strip()[:600]}")
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
    p.add_argument("--report", type=Path)
    p.add_argument("--json", type=Path)
    p.add_argument("--patch", type=Path, help="base 대비 전체 diff(커밋+미커밋)를 쓸 경로")
    args = p.parse_args(argv)

    try:
        if args.patch:
            base = resolve_base(args.repo, args.base, args.claim_subject, Result())
            git(args.repo, "add", "-N", ".", check=False)  # 미추적 파일도 diff에 보이게(intent-to-add)
            args.patch.write_text(git(args.repo, "diff", base), encoding="utf-8")
            git(args.repo, "reset", "-q", check=False)
        res = check(args.repo, args.base, args.model_id, args.task_id, args.claim_subject)
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
