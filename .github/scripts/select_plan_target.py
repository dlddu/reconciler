#!/usr/bin/env python3
"""reconciler-work-planner 워크플로의 「Select target」 스텝.

reconciler-work-planner 스킬의 Step 0(대상 선정 · 진입 게이트)을 기계적으로 옮긴 것이다.
판단 기준은 reconciler-local의 타이머 게이트(`planner/precheck-plan.py`)와 같다 — 두 경로가
"계획할 것이 있다"를 같은 뜻으로 쓰도록. 이번 실행이 계획할 ReconciliationTask **한 건**을 골라
GitHub Actions output으로 내보낸다. 레포에는 아무것도 쓰지 않는다(읽기 전용) — `planning`으로의
점유 커밋은 Claude Code 경로에선 스킬 Step 1, MiniMax 경로에선 claim_plan_target.py의 몫이다.

계획 대상(ready) = 미점유 인수인계 지점에 있는 task:
  - action_required   detector가 조치 필요로 판정해 planner에 넘긴 것
  - review_rejected   검토 거부 — 재작업 진입점
  - failed            검증 실패 — 재작업 진입점
그리고 그 task의 ToBeModel이 꺼져 있지 않을 것(`checkPolicy.enabled: false`가 아닐 것).
꺼진 모델의 인수인계 지점 task는 대기열이 아니라 주차(parked)된 것으로 본다 — 감지가 꺼져
후속 단계도 그 결과를 쓰지 않는다.

`planning`은 대상이 아니다. 스킬의 resume(이 planner가 잡고 있던 task)은 매 실행이 새 러너라
해당이 없고, 새 실행은 버려진 lock과 살아 있는 lock을 구별할 수 없다.

선정(single in-flight): 지목(rct_… · tbm_… · tbm_…/rct_…)이 있으면 그 대상만 본다. task id는 모델
파일 안에서만 유일하므로, 여러 모델에 같은 rct_ id가 있으면 tbm_…/rct_… 형식으로 지목해야 한다. 아니면 ready 중 인수인계 지점에 가장
오래 머문 것(`updatedAt`, 없으면 `createdAt`이 이른 순, 같으면 id 순) 한 건. 나머지는 미점유로
남겨 다음 실행 몫으로 둔다.

출력(GITHUB_OUTPUT): found, target_id, target_kind(task), model_id, from_status, reason,
                    attempt_count, ready_count
  reason ∈ explicit | oldest_ready

종료 코드: 0 선정 완료(대상 유무와 무관), 2 데이터가 깨졌거나 지목이 잘못돼 판단 불가.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

MODELS_FILE = Path("data") / "to-be-models.json"
TASKS_DIR = Path("data") / "reconciliation-tasks"
READY_STATUSES = ("action_required", "review_rejected", "failed")
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

# ready가 아닌 status가 왜 이번 계획 대상이 아닌지(스킬 Step 0의 "제외" 목록).
NOT_OURS = {
    "assessing": "감지 판정 미완 — detector 몫",
    "no_action_needed": "조치 불필요로 판정됨 — 계획할 gap 없음",
    "planning": "다른 planner 워커가 점유 중 — 새 러너는 resume하지 않음",
    "planned": "계획 완료, 검토 판단 대기 — work-review 몫",
    "reviewing": "검토 판정 중 — work-review 점유",
    "approved": "검토 통과, 실행 대기 — work-executor 몫",
    "executing": "실행 중 — work-executor 점유",
    "verifying": "검증 중 — work-executor 점유",
    "succeeded": "종료됨",
    "cancelled": "취소됨",
}


class SelectionError(Exception):
    """데이터가 깨졌거나 지목이 잘못돼 선정 자체를 할 수 없을 때."""


def parse_time(value) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SelectionError(f"{path}: {exc}") from exc


def is_enabled(model: dict | None) -> bool:
    """`checkPolicy.enabled`가 JSON false일 때만 꺼진 것으로 본다(precheck-plan.py와 같은 술어).
    필드가 없거나 boolean이 아니면 켜진 것 — 깨진 정책은 조용히 주차하지 않고 계획 쪽으로 연다."""
    if model is None:
        return True
    return (model.get("checkPolicy") or {}).get("enabled") is not False


def waiting_since(ref: "TaskRef") -> dt.datetime:
    """task가 지금 status에 들어선 시각의 근사치. 기록이 없으면 가장 오래 기다린 것으로 친다."""
    task = ref.task
    return parse_time(task.get("updatedAt")) or parse_time(task.get("createdAt")) or EPOCH


# ── 상태 읽기 ────────────────────────────────────────────────────────────────


@dataclass
class TaskRef:
    model_id: str
    task: dict

    @property
    def id(self) -> str:
        return self.task.get("id") or ""

    @property
    def status(self):
        # 최상위 status만 본다. attempts[] 안의 중첩 status는 이력이다.
        return self.task.get("status")


@dataclass
class State:
    models: dict                     # id -> ToBeModel
    tasks: list                      # [TaskRef]
    orphans: list                    # 모델 레코드가 없는 task 파일의 모델 id


def load_state(repo: Path) -> State:
    raw_models = load_json(repo / MODELS_FILE)
    if not isinstance(raw_models, list):
        raise SelectionError(f"{MODELS_FILE}은 배열이어야 함")
    models = {m.get("id"): m for m in raw_models if isinstance(m, dict)}

    tasks_dir = repo / TASKS_DIR
    if not tasks_dir.is_dir():
        raise SelectionError(f"{TASKS_DIR}/ 디렉터리가 없음")
    tasks, orphans = [], []
    # 모델 목록이 아니라 task 파일을 훑는다 — 모델 레코드 없이 남은 task도 놓치지 않도록.
    for path in sorted(tasks_dir.glob("*.json")):
        model_id = path.stem
        records = load_json(path)
        if not isinstance(records, list):
            raise SelectionError(f"{path.relative_to(repo)}은 배열이어야 함")
        if model_id not in models:
            orphans.append(model_id)
        for rec in records:
            if not isinstance(rec, dict):
                raise SelectionError(f"{path.relative_to(repo)}에 객체가 아닌 레코드가 있음")
            tasks.append(TaskRef(model_id, rec))
    return State(models, tasks, orphans)


# ── 선정 ─────────────────────────────────────────────────────────────────────


@dataclass
class Selection:
    found: bool = False
    target_id: str = ""
    model_id: str = ""
    from_status: str = ""
    reason: str = ""
    detail: str = ""
    attempt_count: int = 0
    ready_count: int = 0
    skipped: list = field(default_factory=list)    # (대상, 사유)
    warnings: list = field(default_factory=list)   # (대상, 메시지)
    others: dict = field(default_factory=dict)     # status -> 건수 (ready 아닌 것)

    def pick(self, ref: TaskRef, *, reason: str, detail: str) -> "Selection":
        self.found = True
        self.target_id, self.model_id = ref.id, ref.model_id
        self.from_status = ref.status
        self.reason, self.detail = reason, detail
        self.attempt_count = len(ref.task.get("attempts") or [])
        return self


def why_not(ref: TaskRef, state: State) -> str | None:
    """ref가 계획 대상이면 None, 아니면 사유."""
    if ref.status not in READY_STATUSES:
        return f"status={ref.status} — {NOT_OURS.get(ref.status, '알 수 없는 status')}"
    if not is_enabled(state.models.get(ref.model_id)):
        return f"status={ref.status}지만 모델 {ref.model_id} 감지 비활성(enabled:false) — 주차됨"
    return None


def describe_wait(ref: TaskRef) -> str:
    since = ref.task.get("updatedAt") or ref.task.get("createdAt") or "시각 기록 없음"
    return f"{ref.status} 상태로 대기({since}부터)"


def parse_target(raw: str) -> tuple[str | None, str | None]:
    """지목 문자열 → (model_id, task_id). 형식: rct_… | tbm_… | tbm_…/rct_…. 잘못되면 SelectionError."""
    model_id, sep, task_id = raw.partition("/")
    if not sep:
        if raw.startswith("rct_"):
            return None, raw
        model_id, task_id = raw, None
    if not model_id.startswith("tbm_") or (task_id is not None and not task_id.startswith("rct_")):
        raise SelectionError(f"target_id 형식은 rct_… · tbm_… · tbm_…/rct_… 중 하나여야 함: {raw}")
    return model_id, task_id


def select_explicit(target: str, state: State, sel: Selection) -> Selection:
    model_id, task_id = parse_target(target)
    if task_id:
        # task id는 모델 파일 안에서만 유일하다(next-id가 파일별로 번호를 매긴다).
        matches = [r for r in state.tasks if r.id == task_id and model_id in (None, r.model_id)]
        if not matches:
            raise SelectionError(f"task {target}를 찾을 수 없음")
        if len(matches) > 1:
            where = ", ".join(f"{r.model_id}/{r.id}({r.status})" for r in matches)
            raise SelectionError(f"task id {task_id}가 여러 모델에 있어 하나로 정할 수 없음 — "
                                 f"tbm_…/rct_… 형식으로 지목: {where}")
        ref = matches[0]
        target = f"{ref.model_id}/{ref.id}"
        reason = why_not(ref, state)
        if reason:
            sel.skipped.append((target, reason))
            return sel
        sel.ready_count = 1
        return sel.pick(ref, reason="explicit", detail=f"지목된 task — {describe_wait(ref)}")

    if target not in state.models and not any(r.model_id == target for r in state.tasks):
        raise SelectionError(f"모델 {target}를 찾을 수 없음")
    if not is_enabled(state.models.get(target)):
        sel.skipped.append((target, "감지 비활성(enabled:false) — 인수인계 지점 task가 있어도 주차됨"))
        return sel
    own = [r for r in state.tasks if r.model_id == target]
    ready = sorted((r for r in own if r.status in READY_STATUSES),
                   key=lambda r: (waiting_since(r), r.id))
    if not ready:
        statuses = ", ".join(f"{r.id}={r.status}" for r in own) or "task 없음"
        sel.skipped.append((target, f"계획 대상 task 없음({statuses})"))
        return sel
    sel.ready_count = len(ready)
    if len(ready) > 1:
        sel.skipped.append((f"{target}의 ready {len(ready) - 1}건",
                            "이번엔 점유하지 않고 미점유로 남김: " + ", ".join(r.id for r in ready[1:])))
    ref = ready[0]
    return sel.pick(ref, reason="explicit",
                    detail=f"지목된 모델에서 가장 오래 기다린 task — {describe_wait(ref)}")


def select_target(repo: Path, explicit: str | None = None,
                  exclude: frozenset = frozenset()) -> Selection:
    """exclude: 이번 실행에서 빼둘 `tbm_…/rct_…` 키(점유 경쟁에서 진 task) — 자동 선정에만 적용."""
    state = load_state(repo)
    sel = Selection()
    for model_id in state.orphans:
        sel.warnings.append((model_id, "task 파일은 있는데 ToBeModel 레코드가 없음 — 켜진 모델로 취급"))

    if explicit:
        return select_explicit(explicit, state, sel)

    ready, parked = [], []
    for ref in state.tasks:
        if f"{ref.model_id}/{ref.id}" in exclude:
            continue
        if ref.status not in READY_STATUSES:
            sel.others[ref.status] = sel.others.get(ref.status, 0) + 1
        elif is_enabled(state.models.get(ref.model_id)):
            ready.append(ref)
        else:
            parked.append(ref)

    for ref in parked:
        sel.skipped.append((f"{ref.model_id}/{ref.id}",
                            f"{ref.status}지만 모델 감지 비활성(enabled:false) — 주차됨"
                            " (checkPolicy.enabled를 켜면 다시 계획 대상)"))

    if not ready:
        return sel

    ready.sort(key=lambda r: (waiting_since(r), r.id))
    sel.ready_count = len(ready)
    if len(ready) > 1:
        sel.skipped.append((f"ready {len(ready) - 1}건",
                            "이번엔 점유하지 않고 미점유로 남김: "
                            + ", ".join(f"{r.model_id}/{r.id}" for r in ready[1:])))
    ref = ready[0]
    return sel.pick(ref, reason="oldest_ready", detail=describe_wait(ref))


# ── 출력 ─────────────────────────────────────────────────────────────────────


def write_outputs(sel: Selection, path: str | None) -> None:
    lines = {
        "found": "true" if sel.found else "false",
        "target_id": sel.target_id,
        "target_kind": "task" if sel.found else "",
        "model_id": sel.model_id,
        "from_status": sel.from_status or "",
        "reason": sel.reason,
        "attempt_count": str(sel.attempt_count),
        "ready_count": str(sel.ready_count),
    }
    text = "".join(f"{k}={v}\n" for k, v in lines.items())
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def render_summary(sel: Selection) -> str:
    out = ["#### Select target"]
    if sel.found:
        rework = f", 이전 시도 {sel.attempt_count}건" if sel.attempt_count else ""
        out.append(f"- 선정: `{sel.model_id}/{sel.target_id}` ({sel.from_status}, {sel.reason}{rework})"
                   f" — {sel.detail}")
    else:
        out.append("- 이번에 계획할 대상 없음")
    for target, why in sel.skipped:
        out.append(f"- 제외 · {target}: {why}")
    if sel.others:
        for status, count in sorted(sel.others.items(), key=lambda kv: str(kv[0])):
            out.append(f"- 대상 아님 · {status} {count}건: {NOT_OURS.get(status, '알 수 없는 status')}")
    for target, msg in sel.warnings:
        out.append(f"- ⚠️ {target}: {msg}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="reconciler checkout 경로")
    parser.add_argument("--target", default="",
                        help="지목 대상(rct_… task · tbm_… 모델 · tbm_…/rct_…), 비우면 자동 선정")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    parser.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = parser.parse_args(argv)

    target = args.target.strip() or None
    try:
        if target:
            parse_target(target)  # 데이터를 읽기 전에 형식부터 거른다
        sel = select_target(Path(args.repo), explicit=target)
    except SelectionError as exc:
        print(f"::error::{exc}")
        return 2

    for target_id, msg in sel.warnings:
        print(f"::warning::{target_id}: {msg}")
    summary = render_summary(sel)
    print(summary, end="")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as fh:
            fh.write(summary)
    write_outputs(sel, args.github_output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
