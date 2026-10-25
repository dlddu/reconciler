#!/usr/bin/env python3
"""drift-detector 스킬 테스트 실행 결과 점검.

생성된 스킬로 감지를 한 번 돌린 뒤(드라이런 — push 없음), reconciler 체크아웃에 남은 변경이
감지 단계 계약을 지키는지 기계적으로 확인한다. 기준은 실행 직전 커밋(`--base`)이다.

  - 범위: 바뀐 파일이 data/to-be-models.json 과 data/reconciliation-tasks/<model>.json 뿐인가
           (스키마·다른 모델 파일은 건드리면 안 된다), 모델 배열에서 바뀐 건 대상 모델뿐인가
  - 스키마: 바뀐 레코드가 schemas/의 현재 스키마를 통과하는가
  - 단일 점유: 손댄 task가 정확히 한 건인가
  - 종료 상태: no_action_needed | action_required | assessing+recheckAfter 중 하나인가,
               stateSummary(asIs/toBe/gap)·assessment.reason이 채워졌나
  - 계기별 정합: 버전 변화면 trigger 버전과 모델 lastObservedVersion이 맞물리나, 수동 트리거면
               사유를 그대로 옮기고 요청 필드를 지웠나, 재확인 만료면 기존 task를 이어받았나
  - 커밋: 커밋 메시지가 `detect(<model>/<task>): ...` 규약을 따르나
  - 점유 순서(--transcript): 첫 커밋(점유) 전에 대상 레포 diff 읽기·하네스 실행 같은 수집을 했나

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

MODELS_FILE = "data/to-be-models.json"
TASKS_DIR = "data/reconciliation-tasks"
COMMIT_RE = re.compile(r"^detect\((tbm_[^/\s)]+)/(rct_[0-9]{8}-[0-9]{4})\): \S")
FINAL_STATUSES = {"no_action_needed", "action_required", "assessing"}


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
    if proc.returncode:
        return None
    return json.loads(proc.stdout)


def load_worktree(repo: Path, path: str):
    file = repo / path
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else None


def changed_files(repo: Path, base: str) -> list[str]:
    tracked = git(repo, "diff", "--name-only", base).split()
    untracked = git(repo, "ls-files", "--others", "--exclude-standard").split()
    return sorted(set(tracked) | set(untracked))


def make_validator(schema: dict):
    import jsonschema  # 러너에서 pip로 설치한다
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema, format_checker=cls.FORMAT_CHECKER)


def schema_errors(validator, record: dict) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(validator.iter_errors(record), key=lambda e: list(map(str, e.absolute_path)))][:5]


def by_id(items) -> dict:
    return {item.get("id"): item for item in (items or []) if isinstance(item, dict)}


def check(repo: Path, base: str, model_id: str, target_id: str, target_kind: str, reason: str) -> Result:
    res = Result()
    task_file = f"{TASKS_DIR}/{model_id}.json"

    # ── 커밋 ──
    log = git(repo, "log", "--format=%H%x09%s", f"{base}..HEAD").strip().splitlines()
    commits = [line.split("\t", 1) for line in log if line]
    res.facts["commits"] = [s for _, s in reversed(commits)]
    if not commits:
        res.errors.append("새 커밋이 없음 — 스킬이 점유·기록 커밋을 남기지 않았다")
    for _, subject in commits:
        m = COMMIT_RE.match(subject)
        if not m:
            res.errors.append(f"커밋 메시지 규약 위반: {subject!r}")
        elif m.group(1) != model_id:
            res.errors.append(f"다른 모델의 커밋: {subject!r}")
    if commits and all(COMMIT_RE.match(s) for _, s in commits):
        res.passed.append(f"커밋 {len(commits)}개 모두 detect(...) 규약")
    dirty = [line for line in git(repo, "status", "--porcelain", "--untracked-files=all").splitlines() if line.strip()]
    if dirty:
        res.warnings.append("커밋되지 않은 변경이 남아 있음: " + ", ".join(line[3:] for line in dirty[:10]))

    # ── 범위 ──
    files = changed_files(repo, base)
    res.facts["changed_files"] = files
    allowed = {MODELS_FILE, task_file}
    outside = [f for f in files if f not in allowed]
    if outside:
        res.errors.append("허용 범위 밖 파일 변경: " + ", ".join(outside))
    else:
        res.passed.append("변경 파일이 대상 모델·task 파일로 한정")

    # ── 스키마 ──
    model_validator = make_validator(json.loads((repo / "schemas/to-be-model.schema.json").read_text()))
    task_validator = make_validator(json.loads((repo / "schemas/reconciliation-task.schema.json").read_text()))
    base_models, cur_models = by_id(load_at(repo, base, MODELS_FILE)), by_id(load_worktree(repo, MODELS_FILE))
    base_tasks, cur_tasks = by_id(load_at(repo, base, task_file)), by_id(load_worktree(repo, task_file))

    touched_models = sorted(k for k in set(base_models) | set(cur_models) if base_models.get(k) != cur_models.get(k))
    res.facts["touched_models"] = touched_models
    if [m for m in touched_models if m != model_id]:
        res.errors.append("대상 외 모델 변경: " + ", ".join(m for m in touched_models if m != model_id))
    model = cur_models.get(model_id)
    if model is None:
        res.errors.append(f"대상 모델 {model_id}이 to-be-models.json에 없음")
        return res
    errs = schema_errors(model_validator, model)
    if errs:
        res.errors.extend(f"모델 스키마 위반 {model_id} · {e}" for e in errs)
    else:
        res.passed.append("대상 모델 스키마 통과")

    touched = sorted(k for k in set(base_tasks) | set(cur_tasks) if base_tasks.get(k) != cur_tasks.get(k))
    res.facts["touched_tasks"] = touched
    if len(touched) != 1:
        res.errors.append(f"손댄 task가 정확히 1건이 아님: {touched or '없음'}")
        return res
    res.passed.append(f"단일 점유: {touched[0]}")
    task_id = touched[0]
    task = cur_tasks.get(task_id)
    if task is None:
        res.errors.append(f"{task_id}가 삭제됨")
        return res
    errs = schema_errors(task_validator, task)
    if errs:
        res.errors.extend(f"task 스키마 위반 {task_id} · {e}" for e in errs)
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

    # ── 계기별 정합 ──
    trigger = task.get("trigger") or {}
    base_model = base_models.get(model_id) or {}
    if target_kind == "task":
        if task_id != target_id:
            res.errors.append(f"지목/재확인 대상 {target_id} 대신 {task_id}를 다룸")
        elif task_id not in base_tasks:
            res.errors.append(f"기존 task {target_id}를 이어받지 않고 새로 만듦")
        else:
            res.passed.append("기존 task 이어받기")
    elif task_id in base_tasks:
        res.errors.append(f"새 task를 열어야 하는데 기존 {task_id}를 고침")
    if reason == "manual_trigger":
        cp_base = base_model.get("checkPolicy") or {}
        cp_now = model.get("checkPolicy") or {}
        if trigger.get("source") != "manual":
            res.errors.append("수동 트리거인데 trigger.source가 manual이 아님")
        if cp_base.get("manualTriggerReason") and trigger.get("reason") != cp_base.get("manualTriggerReason"):
            res.errors.append("trigger.reason이 모델의 manualTriggerReason을 그대로 옮기지 않음")
        if cp_now.get("manualTriggerRequestedAt") or cp_now.get("manualTriggerReason"):
            res.errors.append("모델의 수동 트리거 요청 필드가 지워지지 않음")
        else:
            res.passed.append("수동 트리거 요청 소비")
    elif reason == "version_changed":
        sides = [s for s in ("asIs", "toBe") if isinstance(trigger.get(s), dict)]
        if not sides:
            res.errors.append("버전 변화 task인데 trigger에 asIs/toBe 버전 기록이 없음")
        for side in sides:
            cur = trigger[side].get("currentVersion")
            observed = (model.get(side) or {}).get("lastObservedVersion")
            if cur != observed:
                res.errors.append(f"{side}: trigger.currentVersion과 모델 lastObservedVersion 불일치")
        if sides and not any(e.startswith(tuple(sides)) for e in res.errors):
            res.passed.append("trigger 버전 ↔ lastObservedVersion 일치")
    elif reason == "recheck_expired" and status == "assessing":
        if assessment.get("recheckAfter") == ((base_tasks.get(task_id) or {}).get("assessment") or {}).get("recheckAfter"):
            res.errors.append("재확인 만료 task를 이어받았는데 recheckAfter가 그대로임")
    return res


# 점유 전에 하면 안 되는 일(수집·판정). 버전 계산용 토큰 발급·클론·versionScript 실행은 허용된다.
PRE_CLAIM_FORBIDDEN = [
    ("대상 레포 diff/내용 읽기", re.compile(r"\bgit\b[^\n|;&]*\s(diff|show)\b|\bgit\b[^\n|;&]*\slog\b[^\n|;&]*\s(-p|--patch|--stat|--name-status)\b")),
    ("하네스·의존성 실행", re.compile(r"\b(npm|pnpm|yarn)\s+(install|ci|test|run)\b|\bpytest\b|\bgo\s+test\b")),
]
PRE_CLAIM_WARN_TOOLS = ("resource_get", "resource_list")


def tool_calls_with_time(transcript: Path) -> list[tuple[int, str, str]]:
    """(완료 timestampMs, 도구 이름, 입력 값들을 이은 원문) — item id 기준 첫 완료 시각."""
    seen: dict[str, tuple[int, str, str]] = {}
    with open(transcript, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = ev.get("item") or {}
            call = item.get("toolCall")
            if item.get("type") != "tool_call" or not isinstance(call, dict) or ev.get("type") != "item.completed":
                continue
            key = item.get("id") or str(len(seen))
            if key not in seen:
                inp = call.get("input") or {}
                text = "\n".join(str(v) for v in inp.values()) if isinstance(inp, dict) else str(inp)
                seen[key] = (int(ev.get("timestampMs") or 0), str(call.get("name") or ""), text)
    return sorted(seen.values())


def check_claim_order(repo: Path, base: str, transcript: Path, res: Result) -> None:
    """점유 커밋이 수집·판정보다 먼저인지 대화 기록의 시간순으로 본다."""
    first = git(repo, "log", "--reverse", "--format=%ct%x09%s", f"{base}..HEAD").strip().splitlines()
    if not first:
        return
    claim_ms = int(first[0].split("\t", 1)[0]) * 1000
    calls = tool_calls_with_time(transcript)
    before = [c for c in calls if c[0] and c[0] < claim_ms]
    res.facts["pre_claim_tool_calls"] = len(before)
    res.facts["total_tool_calls"] = len(calls)
    violations = []
    own = str(repo.resolve())  # reconciler 체크아웃 자체를 보는 git diff(작업 트리 점검)는 수집이 아니다
    for _, name, args in before:
        for label, pattern in PRE_CLAIM_FORBIDDEN:
            if name == "bash" and pattern.search(args) and own not in args:
                violations.append(label)
        if name.endswith(PRE_CLAIM_WARN_TOOLS):
            res.warnings.append(f"점유 전에 쿠버네티스 관측({name}) — 버전 계산 목적이 아니면 순서 위반")
    if violations:
        counts = {v: violations.count(v) for v in dict.fromkeys(violations)}
        res.errors.append("점유 커밋 전에 수집을 함(점유가 먼저여야 함): "
                          + ", ".join(f"{k} {n}회" for k, n in counts.items()))
    else:
        res.passed.append(f"점유 순서: 점유 전 도구 호출 {len(before)}회 중 수집·판정 없음")


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
    p.add_argument("--base", required=True, help="스킬 실행 직전 커밋")
    p.add_argument("--model-id", required=True)
    p.add_argument("--target-id", required=True)
    p.add_argument("--target-kind", required=True, choices=["model", "task"])
    p.add_argument("--reason", default="")
    p.add_argument("--report", type=Path)
    p.add_argument("--json", type=Path)
    p.add_argument("--patch", type=Path, help="base 대비 전체 diff(커밋+미커밋)를 쓸 경로")
    p.add_argument("--transcript", type=Path, help="mcode stream-json 대화 기록 — 주면 점유 순서를 점검한다")
    args = p.parse_args(argv)

    if args.patch:
        git(args.repo, "add", "-N", ".", check=False)  # 미추적 파일도 diff에 보이게(intent-to-add)
        args.patch.write_text(git(args.repo, "diff", args.base), encoding="utf-8")
        git(args.repo, "reset", "-q", check=False)
    try:
        res = check(args.repo, args.base, args.model_id, args.target_id, args.target_kind, args.reason)
        if args.transcript and args.transcript.is_file():
            check_claim_order(args.repo, args.base, args.transcript, res)
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
