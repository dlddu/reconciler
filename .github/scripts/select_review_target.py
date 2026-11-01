#!/usr/bin/env python3
"""reconciler-work-review 워크플로의 「Select target」 스텝.

reconciler-work-review 스킬의 Step 0(대상 선정 · 진입 게이트, 4-0)을 기계적으로 옮긴 것이다.
이번 실행이 판정할 task **한 건**을 골라 GitHub Actions output으로 내보낸다. 레포에는 아무것도
쓰지 않는다(읽기 전용) — `planned → reviewing` 점유 커밋은 스킬 Step 1 몫이다.
대상 레포에도 접근하지 않는다(PR 신선도 확인은 스킬 Step 2 몫) — 그래서 토큰이 필요 없다.

대상(ready) = 다음을 모두 만족하는 task:
  - 최상위 status가 `planned` (스킬의 유일한 입구. 중첩된 attempts[].*.status는 이력이라 보지 않는다)
  - 마지막 attempts 항목에 plan.steps · plan.executionGuide가 있다
  - 마지막 attempts 항목에 preparation.preparedAt이 있고, PR url이 있거나
    직접 액션(pullRequestUrl:null)이면 preparation.notes가 있다
뒤의 두 조건은 reconciler-local의 claim.py(review 단계 전제 검사)와 같다. status만 보고 고르면
점유가 exit 4(ineligible)로 튕기므로 여기서 미리 거른다. 전제가 빠진 `planned`는 아무 단계도
집지 못하는 막힌 task라 오류로 보고한다.

`reviewing`은 고르지 않는다 — 다른 워커가 잡은 lock이고, 오래됐다는 이유로 회수하지 않는다.
`approved`(executor 몫), `review_rejected`(planner 재계획 몫) 등 나머지 status도 대상이 아니다.
모델이 꺼져 있으면(`checkPolicy.enabled: false`) 그 task는 planned여도 고르지 않는다 — 주차된 것으로 본다
(select_plan_target.py와 같은 술어). reconciler-local의 claim.py review는 이것을 보지 않지만, 꺼진 모델의
오래된 planned task가 「가장 오래 기다린 것」으로 먼저 집혀 승인까지 간 일이 있어(2026-10-28) 막는다.

우선순위: 지목 → 오래 기다린 순(updatedAt = planned가 된 시각, 없으면 createdAt) → id.
여러 건이어도 한 건만 고르고 나머지는 `planned`로 남긴다.

지목(워크플로 입력): `tbm_...`(그 모델 안에서 자동 선정), `tbm_.../rct_...`(정확히 그 task),
`rct_...`. task id는 모델 안에서만 유일해 같은 rct_ id가 여러 모델 파일에 있으므로, rct_만 주면
그중 planned인 한 건으로 좁히고 planned가 둘 이상이면 모델까지 지목하라고 오류를 낸다.

출력(GITHUB_OUTPUT): found, target_id, target_kind(task), model_id, reason, pull_request_url,
                     ready_count, error_count
  reason ∈ explicit | oldest_planned
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

TASKS_DIR = Path("data") / "reconciliation-tasks"
MODELS_FILE = Path("data") / "to-be-models.json"
READY_STATUS = "planned"
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

# 대상이 아닌 status가 누구 몫인지(스킬 Step 0의 「대상이 아님」 목록).
OWNER = {
    "assessing": "감지 단계(drift-detector) 몫",
    "no_action_needed": "감지 단계 판정 — 조치 불필요",
    "action_required": "계획 전 — planner 몫",
    "planning": "planner가 점유 중",
    "reviewing": "다른 리뷰 워커가 점유 중 — 회수하지 않음",
    "approved": "판정 끝난 실행 대기 — executor 몫",
    "executing": "executor가 점유 중",
    "verifying": "executor가 점유 중",
    "review_rejected": "거부됨 — planner 재계획 몫",
    "failed": "재작업 진입점 — planner 몫",
    "succeeded": "종료",
    "cancelled": "종료",
}
# 요약에 id까지 적을 status(건수가 적고, 사람이 볼 이유가 있는 것).
LIST_IDS = {"reviewing", "approved", "review_rejected"}


class SelectionError(Exception):
    """데이터가 깨졌거나 지목 대상이 없어 선정 자체를 할 수 없을 때."""


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
    """`checkPolicy.enabled`가 JSON false일 때만 꺼진 것으로 본다(select_plan_target.py와 같은 술어)."""
    if not isinstance(model, dict):
        return True
    return (model.get("checkPolicy") or {}).get("enabled") is not False


def load_models(repo: Path) -> dict:
    models = load_json(repo / MODELS_FILE)
    if not isinstance(models, list):
        raise SelectionError(f"{MODELS_FILE}는 배열이어야 함")
    return {m.get("id"): m for m in models if isinstance(m, dict)}


PARKED = "planned지만 모델 감지 비활성(enabled:false) — 주차됨 (checkPolicy.enabled를 켜면 다시 리뷰 대상)"


def last_attempt(task: dict) -> dict:
    attempts = task.get("attempts") or []
    return attempts[-1] if attempts and isinstance(attempts[-1], dict) else {}


def unready_reason(task: dict) -> str | None:
    """`planned` task가 리뷰 전제를 못 갖췄으면 그 사유, 갖췄으면 None."""
    if not task.get("attempts"):
        return "attempts[]가 없음 — 계획된 적 없음"
    last = last_attempt(task)
    plan = last.get("plan") or {}
    if not plan.get("steps"):
        return "마지막 attempt에 plan.steps가 없음"
    if not plan.get("executionGuide"):
        return "마지막 attempt에 plan.executionGuide가 없음"
    prep = last.get("preparation") or {}
    if not prep.get("preparedAt"):
        return "마지막 attempt가 준비되지 않음(preparation.preparedAt 없음)"
    if not prep.get("pullRequestUrl") and not (prep.get("notes") or "").strip():
        return "PR도 없고 직접 액션 notes도 없음(preparation.pullRequestUrl·notes 모두 비어 있음)"
    return None


def waiting_since(task: dict) -> dt.datetime:
    return parse_time(task.get("updatedAt")) or parse_time(task.get("createdAt")) or EPOCH


# ── 선정 ─────────────────────────────────────────────────────────────────────


@dataclass
class Selection:
    found: bool = False
    target_id: str = ""
    model_id: str = ""
    reason: str = ""
    detail: str = ""
    pull_request_url: str = ""
    ready_count: int = 0
    skipped: list = field(default_factory=list)   # (id, 사유)
    errors: list = field(default_factory=list)    # (id, 메시지)
    others: Counter = field(default_factory=Counter)        # 대상 아닌 status별 건수
    other_ids: dict = field(default_factory=dict)           # status -> [id]

    def pick(self, task: dict, model_id: str, reason: str, detail: str):
        self.found = True
        self.target_id, self.model_id = task["id"], model_id
        self.reason, self.detail = reason, detail
        self.pull_request_url = (last_attempt(task).get("preparation") or {}).get("pullRequestUrl") or ""
        return self


def load_tasks(repo: Path, only_model: str | None = None) -> list[tuple[str, dict]]:
    """(model_id, task) 목록. 파일 이름이 모델 id다."""
    tasks_dir = repo / TASKS_DIR
    if not tasks_dir.is_dir():
        raise SelectionError(f"{TASKS_DIR}가 없음 — reconciler checkout이 맞는지 확인")
    out = []
    for path in sorted(tasks_dir.glob("*.json")):
        model_id = path.stem
        if only_model and model_id != only_model:
            continue
        records = load_json(path)
        if not isinstance(records, list):
            raise SelectionError(f"{path.relative_to(repo)}는 배열이어야 함")
        for task in records:
            if not isinstance(task, dict) or not task.get("id"):
                raise SelectionError(f"{path.relative_to(repo)}에 id 없는 레코드가 있음")
            out.append((model_id, task))
    return out


def model_ids(repo: Path) -> set[str]:
    models = load_json(repo / MODELS_FILE)
    if not isinstance(models, list):
        raise SelectionError(f"{MODELS_FILE}는 배열이어야 함")
    return {m.get("id") for m in models if isinstance(m, dict)}


def scan(sel: Selection, tasks: list[tuple[str, dict]], models: dict | None = None,
         exclude: frozenset = frozenset()) -> list[tuple[str, dict]]:
    """ready 목록을 돌려주고, 나머지는 sel에 사유별로 적는다. exclude(`model/task`)는 점유 경쟁에서 진 것이라 건너뛴다."""
    models = models or {}
    ready = []
    for model_id, task in tasks:
        if f"{model_id}/{task['id']}" in exclude:
            sel.skipped.append((f"{model_id}/{task['id']}", "점유 경쟁에서 짐 — 이번 실행에서는 다시 고르지 않음"))
            continue
        status = task.get("status")
        if status != READY_STATUS:
            sel.others[status] += 1
            if status in LIST_IDS:
                sel.other_ids.setdefault(status, []).append(f"{model_id}/{task['id']}")
            continue
        if not is_enabled(models.get(model_id)):
            sel.skipped.append((f"{model_id}/{task['id']}", PARKED))
            continue
        why = unready_reason(task)
        if why:
            sel.errors.append((f"{model_id}/{task['id']}", f"planned인데 리뷰 전제 미충족 — {why}"))
            continue
        ready.append((model_id, task))
    ready.sort(key=lambda mt: (waiting_since(mt[1]), mt[1]["id"]))
    sel.ready_count = len(ready)
    return ready


def select_explicit_task(target: str, tasks: list[tuple[str, dict]], model: str | None = None,
                         models: dict | None = None) -> Selection:
    """task id는 모델 안에서만 유일하다(같은 rct_ id가 여러 모델 파일에 있다). 그래서
    `tbm_.../rct_...`로 모델까지 지목할 수 있고, rct_만 주면 그중 planned인 한 건으로 좁힌다."""
    sel = Selection()
    label = f"{model}/{target}" if model else target
    matches = [(m, t) for m, t in tasks if t["id"] == target and (model is None or m == model)]
    if not matches:
        raise SelectionError(f"task {label}를 찾을 수 없음")
    planned = [(m, t) for m, t in matches if t.get("status") == READY_STATUS]
    if len(planned) > 1:
        where = ", ".join(m for m, _ in planned)
        raise SelectionError(f"task {target}가 여러 모델에서 planned({where}) — tbm_.../{target} 형태로 모델까지 지목할 것")
    if not planned:
        for model_id, task in matches:
            status = task.get("status")
            sel.skipped.append((f"{model_id}/{target}", f"status={status} — {OWNER.get(status, '리뷰 대상 아님')}"))
        return sel
    model_id, task = planned[0]
    if not is_enabled((models or {}).get(model_id)):
        sel.skipped.append((f"{model_id}/{target}", PARKED))
        return sel
    why = unready_reason(task)
    if why:
        sel.errors.append((f"{model_id}/{target}", f"planned인데 리뷰 전제 미충족 — {why}"))
        return sel
    sel.ready_count = 1
    others = len(matches) - 1
    note = f" (같은 id의 다른 모델 task {others}건은 planned 아님)" if others else ""
    return sel.pick(task, model_id, "explicit", f"워크플로 입력으로 지목된 planned task{note}")


def select_target(repo: Path, explicit: str | None = None, exclude: frozenset = frozenset()) -> Selection:
    models = load_models(repo)
    if explicit and "/" in explicit:
        model, _, task_id = explicit.partition("/")
        return select_explicit_task(task_id, load_tasks(repo, model), model=model, models=models)
    if explicit and explicit.startswith("rct_"):
        return select_explicit_task(explicit, load_tasks(repo), models=models)

    only_model = None
    if explicit:  # tbm_
        if explicit not in models and not (repo / TASKS_DIR / f"{explicit}.json").exists():
            raise SelectionError(f"모델 {explicit}를 찾을 수 없음")
        only_model = explicit

    sel = Selection()
    ready = scan(sel, load_tasks(repo, only_model), models, exclude)
    if not ready:
        return sel
    model_id, task = ready[0]
    since = waiting_since(task)
    when = since.strftime("%Y-%m-%dT%H:%M:%SZ") if since != EPOCH else "시각 미상"
    scope = f"지목된 모델 {only_model}의 " if only_model else ""
    if len(ready) > 1:
        rest = ", ".join(f"{m}/{t['id']}" for m, t in ready[1:])
        sel.skipped.append((f"planned {len(ready) - 1}건", f"이번엔 점유하지 않고 planned로 남김: {rest}"))
    return sel.pick(task, model_id, "explicit" if only_model else "oldest_planned",
                    f"{scope}가장 오래 기다린 planned task ({when}부터 대기)")


# ── 출력 ─────────────────────────────────────────────────────────────────────


def write_outputs(sel: Selection, path: str | None) -> None:
    lines = {
        "found": "true" if sel.found else "false",
        "target_id": sel.target_id,
        "target_kind": "task" if sel.found else "",
        "model_id": sel.model_id,
        "reason": sel.reason,
        "pull_request_url": sel.pull_request_url,
        "ready_count": str(sel.ready_count),
        "error_count": str(len(sel.errors)),
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
        pr = f" · PR {sel.pull_request_url}" if sel.pull_request_url else " · 직접 액션(PR 없음)"
        out.append(f"- 선정: `{sel.model_id}/{sel.target_id}` ({sel.reason}) — {sel.detail}{pr}")
    else:
        out.append("- 이번에 판정할 대상 없음")
    for target, why in sel.skipped:
        out.append(f"- 제외 · {target}: {why}")
    for status, n in sorted(sel.others.items(), key=lambda kv: (-kv[1], str(kv[0]))):
        ids = sel.other_ids.get(status)
        tail = f" ({', '.join(ids)})" if ids else ""
        out.append(f"- 대상 아님 · {status} {n}건: {OWNER.get(status, '알 수 없는 status')}{tail}")
    for target, msg in sel.errors:
        out.append(f"- ⚠️ {target}: {msg}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="reconciler checkout 경로")
    parser.add_argument("--target", default="", help="지목 대상(rct_... 또는 tbm_...), 비우면 자동 선정")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    parser.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = parser.parse_args(argv)

    target = args.target.strip() or None
    if target and not re.fullmatch(r"(tbm_[^/\s]+/)?rct_[^/\s]+|tbm_[^/\s]+", target):
        print(f"::error::target_id는 rct_..., tbm_..., tbm_.../rct_... 중 하나여야 함: {target}")
        return 2

    try:
        sel = select_target(Path(args.repo), explicit=target)
    except SelectionError as exc:
        print(f"::error::{exc}")
        return 2

    for target_id, msg in sel.errors:
        print(f"::warning::{target_id}: {msg}")
    summary = render_summary(sel)
    print(summary, end="")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as fh:
            fh.write(summary)
    write_outputs(sel, args.github_output)

    # 고를 것이 없는데 전제가 깨진 planned가 있으면, 그 task는 어느 단계도 집지 못한 채 막혀 있다.
    # "판정할 것 없음"으로 조용히 끝내지 않고 실패로 드러낸다(reconciler-local 러너의 fail-closed와 같은 취지).
    if not sel.found and sel.errors:
        print(f"::error::리뷰 전제가 깨진 planned task {len(sel.errors)}건 — 대상 없음으로 확정할 수 없음")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
