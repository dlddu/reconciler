#!/usr/bin/env python3
"""reconciler-drift-detector 워크플로의 「Claim target」 스텝 — 대상 선정 + 점유(claim).

감지 스킬의 Step 0(대상 선정)과 Step 1(점유)을 러너가 결정적으로 수행한다. MiniMax Code는 점유가
push된 task 한 건을 넘겨받아 수집·판정만 한다(근거는 README 「점유는 러너가 한다」).

절차(후보 하나당):
  1. 원격 기본 브랜치로 맞춘다(fetch + reset --hard).
  2. select_drift_target.select_target으로 한 건을 고른다(경쟁에서 진 모델은 제외).
  3. 점유 커밋: 선정 시점 값(premise)이 그대로인지 재확인 → task 생성(또는 재진입 표시)과
     모델 갱신을 한 커밋으로 → 즉시 push. 이 push가 lock이다.
     - push가 non-fast-forward로 거절되면(무관한 커밋이 먼저 들어온 경우 포함) 1부터 다시 해
       premise를 새 상태에서 재확인한다. premise가 그대로면 다시 커밋·push한다.
     - premise가 바뀌었으면 다른 워커가 먼저 집은 것 → 그 모델을 빼고 2로(지목 실행이면 종료).

점유 커밋 형태(스킬의 기존 계약 그대로):
  version_changed  새 task(assessing, trigger.source=version_change, 바뀐 side 버전) + 그 side의
                   lastObservedVersion/At 갱신 — `detect(<tbm>/<rct>): claim`
  manual_trigger   새 task(trigger.source=manual, reason=요청 사유 원문, 버전이 바뀌었으면 함께) +
                   manualTriggerRequestedAt/Reason을 짝으로 null — `detect(<tbm>/<rct>): claim manual`
  recheck_expired  기존 assessing task의 recheckAfter를 null로 — `detect(<tbm>/<rct>): claim recheck`
  explicit(모델)   새 task — 버전이 바뀌었으면 version_change, 아니면 manual(reason=지목 사유)
  explicit(task)   기존 assessing task를 이어받음(recheckAfter null, updatedAt) — `claim takeover`

출력(GITHUB_OUTPUT): found, claimed, task_id, model_id, claim_reason, claim_commit, claim_message, lost_count
종료 코드: 0 = 점유했거나 대상 없음, 1 = 오류(대상 없음을 단정할 수 없음 포함), 2 = 사용법/데이터 오류
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import select_drift_target as sdt  # noqa: E402

MODELS_FILE = "data/to-be-models.json"
TASKS_DIR = "data/reconciliation-tasks"
MAX_CANDIDATES = 5


class ClaimError(Exception):
    """점유를 진행할 수 없는 오류(경쟁 패배가 아님)."""


@dataclass
class ClaimResult:
    status: str  # claimed | lost
    task_id: str = ""
    commit: str = ""
    detail: str = ""
    message: str = ""


@dataclass
class Outcome:
    selection: sdt.Selection | None = None
    claim: ClaimResult | None = None
    lost: list = field(default_factory=list)  # (model_id, 사유)


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
    if any(k in text for k in ("[rejected]", "non-fast-forward", "fetch first", "stale info", "[remote rejected] (cannot lock ref")):
        return "rejected"
    raise ClaimError(f"push 실패: {text.strip()[-400:]}")


# ── 레코드 ───────────────────────────────────────────────────────────────────


def load(repo: Path, rel: str, default=None):
    path = repo / rel
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def dump(repo: Path, rel: str, data) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validators(repo: Path):
    import jsonschema

    def make(name):
        schema = json.loads((repo / "schemas" / name).read_text(encoding="utf-8"))
        cls = jsonschema.validators.validator_for(schema)
        return cls(schema, format_checker=cls.FORMAT_CHECKER)

    return make("to-be-model.schema.json"), make("reconciliation-task.schema.json")


def check_valid(validator, record: dict, label: str) -> None:
    errors = sorted(validator.iter_errors(record), key=lambda e: list(map(str, e.absolute_path)))
    if errors:
        first = errors[0]
        where = "/".join(map(str, first.absolute_path)) or "<root>"
        raise ClaimError(f"{label} 스키마 위반 — {where}: {first.message}")


def next_task_id(tasks: list, now: dt.datetime) -> str:
    prefix = f"rct_{now:%Y%m%d}-"
    seqs = [int(t["id"][len(prefix):]) for t in tasks
            if str(t.get("id", "")).startswith(prefix) and t["id"][len(prefix):].isdigit()]
    return f"{prefix}{(max(seqs) + 1 if seqs else 1):04d}"


def open_assessing(tasks: list) -> list:
    return [t for t in tasks if t.get("status") == "assessing"]


# ── 점유 ─────────────────────────────────────────────────────────────────────


@dataclass
class Plan:
    """한 번의 점유 시도에서 쓸 변경. premise가 깨졌으면 lost에 사유."""
    lost: str = ""
    task_id: str = ""
    message: str = ""
    detail: str = ""


def plan_claim(models: list, tasks: list, sel: sdt.Selection, now: dt.datetime,
               versions: dict | None, explicit_reason: str) -> Plan:
    """models/tasks(in-place)에 점유 변경을 적용한다. premise가 바뀌었으면 Plan.lost."""
    stamp = sdt.fmt_time(now)
    model = next((m for m in models if m["id"] == sel.model_id), None)
    if model is None:
        return Plan(lost=f"모델 {sel.model_id}가 사라짐")
    if not sdt.is_enabled(model):
        return Plan(lost="그 사이 감지가 비활성화됨(enabled:false)")
    pre = sel.premise

    if sel.target_kind == "task":
        task = next((t for t in tasks if t.get("id") == sel.target_id), None)
        if task is None or task.get("status") != "assessing":
            return Plan(lost=f"{sel.target_id}가 더 이상 assessing이 아님({(task or {}).get('status')})")
        current = (task.get("assessment") or {}).get("recheckAfter")
        if current != pre.get("recheckAfter"):
            return Plan(lost=f"recheckAfter가 {pre.get('recheckAfter')} → {current}로 바뀜(다른 워커가 이어받음)")
        if "assessment" in task:
            task["assessment"]["recheckAfter"] = None
        task["updatedAt"] = stamp
        verb = "claim recheck" if sel.reason == "recheck_expired" else "claim takeover"
        return Plan(task_id=task["id"], message=f"detect({model['id']}/{task['id']}): {verb}",
                    detail=f"기존 task {task['id']} 재진입")

    if open_assessing(tasks):
        return Plan(lost=f"{open_assessing(tasks)[0]['id']}가 이미 assessing으로 열려 있음(다른 워커가 점유)")

    trigger: dict = {"detectedAt": stamp}
    changed_sides: dict = {}
    if sel.reason == "version_changed":
        for side in pre["changed"]:
            stored = (model.get(side) or {}).get("lastObservedVersion")
            if stored != pre["previous"][side]:
                return Plan(lost=f"{side}.lastObservedVersion이 이미 갱신됨(다른 워커가 이 변화를 점유)")
            changed_sides[side] = pre["current"][side]
        trigger["source"] = "version_change"
        verb = "claim"
    elif sel.reason == "manual_trigger":
        policy = model.get("checkPolicy") or {}
        if policy.get("manualTriggerRequestedAt") != pre["requestedAt"]:
            return Plan(lost="manualTriggerRequestedAt이 바뀌거나 지워짐(다른 워커가 요청을 소비)")
        trigger.update(source="manual", reason=policy["manualTriggerReason"])
        policy["manualTriggerRequestedAt"] = None
        policy["manualTriggerReason"] = None
        verb = "claim manual"
    elif sel.reason == "explicit":
        verb = "claim"
        trigger["source"] = "version_change"
    else:
        raise ClaimError(f"알 수 없는 선정 사유: {sel.reason}")

    # 수동·지목 점유: 버전이 함께 바뀌었으면 그 side도 기록하고 기준선을 옮긴다(다음 스윕이 같은 변화로 또 열지 않게).
    if sel.reason in ("manual_trigger", "explicit") and versions:
        for side, current in versions.items():
            stored = (model.get(side) or {}).get("lastObservedVersion")
            if not sdt.version_matches(stored, current):
                pre.setdefault("previous", {})[side] = stored
                changed_sides[side] = current
    if sel.reason == "explicit" and not changed_sides:
        trigger.update(source="manual", reason=explicit_reason)
        verb = "claim manual"

    for side, current in changed_sides.items():
        trigger[side] = {"previousVersion": pre["previous"][side], "currentVersion": current}
        model[side]["lastObservedVersion"] = current
        model[side]["lastObservedAt"] = stamp
    if sel.reason == "version_changed" and not changed_sides:
        raise ClaimError("버전 변화 대상인데 바뀐 side가 없음")

    task_id = next_task_id(tasks, now)
    tasks.append({"id": task_id, "toBeModelId": model["id"], "status": "assessing",
                  "trigger": trigger, "createdAt": stamp})
    sides = ", ".join(changed_sides) or "버전 변화 없음"
    return Plan(task_id=task_id, message=f"detect({model['id']}/{task_id}): {verb}",
                detail=f"새 task {task_id} ({trigger['source']}; {sides})")


def claim(repo: Path, sel: sdt.Selection, now: dt.datetime, *, remote: str, branch: str,
          versions: dict | None = None, explicit_reason: str = "",
          max_push_attempts: int = 5, before_push=None) -> ClaimResult:
    """선정된 한 건을 compare-and-set으로 점유한다. 경쟁에서 지면 status=lost."""
    model_validator, task_validator = validators(repo)
    for attempt in range(1, max_push_attempts + 1):
        if attempt > 1:
            sync(repo, remote, branch)
        models = load(repo, MODELS_FILE)
        task_rel = f"{TASKS_DIR}/{sel.model_id}.json"
        tasks = load(repo, task_rel, default=[])
        plan = plan_claim(models, tasks, sel, now, versions, explicit_reason)
        if plan.lost:
            return ClaimResult(status="lost", detail=plan.lost)
        model = next(m for m in models if m["id"] == sel.model_id)
        task = next(t for t in tasks if t["id"] == plan.task_id)
        check_valid(model_validator, model, f"모델 {model['id']}")
        check_valid(task_validator, task, f"task {task['id']}")
        dump(repo, MODELS_FILE, models)
        dump(repo, task_rel, tasks)
        git(repo, "add", MODELS_FILE, task_rel)
        if not git(repo, "diff", "--cached", "--quiet", check=False).returncode:
            raise ClaimError("점유 커밋에 변경이 없음")
        git(repo, "commit", "--quiet", "-m", plan.message)
        commit = git(repo, "rev-parse", "HEAD").stdout.strip()
        if before_push:
            before_push(attempt)
        if push(repo, remote, branch) == "ok":
            return ClaimResult(status="claimed", task_id=plan.task_id, commit=commit,
                               detail=plan.detail, message=plan.message)
        # 원격이 앞섰다 — 새 상태에서 premise를 다시 확인한다(무관한 커밋이면 그대로 재시도된다).
    raise ClaimError(f"push가 {max_push_attempts}회 연속 거절됨 — 원격이 계속 움직이는 중")


def compute_versions(computer: sdt.VersionComputer, repo: Path, model_id: str) -> dict | None:
    """수동·지목 점유용 현재 버전. 계산 실패는 None(버전 없이 점유 — manual은 스키마가 허용)."""
    model = next(m for m in load(repo, MODELS_FILE) if m["id"] == model_id)
    try:
        return {side: sdt.last_line(computer.compute(model[side])) for side in sdt.SIDES}
    except sdt.VersionError as exc:
        print(f"::warning::{model_id}: 버전 계산 실패 — 버전 기록 없이 점유: {exc}")
        return None


def run(repo: Path, now: dt.datetime, computer: sdt.VersionComputer, *, explicit: str | None,
        remote: str, branch: str, explicit_reason: str,
        before_push=None) -> Outcome:
    out = Outcome()
    excluded: set[str] = set()
    for _ in range(MAX_CANDIDATES):
        sync(repo, remote, branch)
        sel = sdt.select_target(repo, now, computer, explicit=explicit, exclude=frozenset(excluded))
        out.selection = sel
        if not sel.found:
            return out
        versions = None
        if sel.target_kind == "model" and sel.reason in ("manual_trigger", "explicit"):
            versions = compute_versions(computer, repo, sel.model_id)
        result = claim(repo, sel, now, remote=remote, branch=branch,
                       versions=versions, explicit_reason=explicit_reason, before_push=before_push)
        if result.status == "claimed":
            out.claim = result
            return out
        out.lost.append((sel.model_id, result.detail))
        if explicit:
            return out  # 지목 실행은 다른 후보로 넘어가지 않는다
        excluded.add(sel.model_id)
    return out


# ── 출력 ─────────────────────────────────────────────────────────────────────


def write_outputs(out: Outcome, path: str | None) -> None:
    sel, c = out.selection, out.claim
    lines = {
        "found": "true" if c else "false",
        "claimed": "true" if c else "false",
        "task_id": c.task_id if c else "",
        "model_id": sel.model_id if (c and sel) else "",
        "claim_reason": sel.reason if (c and sel) else "",
        "claim_commit": c.commit if c else "",
        "claim_message": c.message if c else "",
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
    for model_id, why in out.lost:
        lines.append(f"- 점유 경쟁에서 짐 · {model_id}: {why}")
    if out.claim:
        sel = out.selection
        lines.append(f"- 점유: `{sel.model_id}` → `{out.claim.task_id}` ({sel.reason}) — {out.claim.detail}")
        lines.append(f"- 커밋: `{out.claim.message}`")
    else:
        lines.append("- 이번에 점유한 대상 없음")
    if out.selection:
        lines.append("")
        lines.append(sdt.render_summary(out.selection).rstrip())
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", default=".", type=Path)
    p.add_argument("--target", default="", help="지목 대상(tbm_... 또는 rct_...), 비우면 자동 선정")
    p.add_argument("--reason", default="", help="지목 실행에서 버전 변화가 없을 때 manual task의 사유")
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default="main")
    p.add_argument("--now", help="기준 시각(ISO 8601, 테스트용)")
    p.add_argument("--work-dir", help="대상 레포 클론 위치")
    p.add_argument("--repo-url-template", default="https://github.com/{repository}.git")
    p.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    p.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = p.parse_args(argv)

    now = sdt.parse_time(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    target = args.target.strip() or None
    if target and not target.startswith(("tbm_", "rct_")):
        print(f"::error::target_id는 tbm_ 또는 rct_로 시작해야 함: {target}")
        return 2
    actor = os.environ.get("GITHUB_ACTOR", "")
    explicit_reason = args.reason.strip() or (
        f"워크플로 지목 감지 요청(target_id={target}" + (f", by {actor})" if actor else ")"))

    tmp = None
    work_dir = args.work_dir and Path(args.work_dir) or Path(tmp := tempfile.mkdtemp(prefix="claim-target-"))
    work_dir.mkdir(parents=True, exist_ok=True)
    computer = sdt.VersionComputer(work_dir=work_dir, url_template=args.repo_url_template,
                                   token=os.environ.get("SOURCE_GITHUB_TOKEN") or None)
    try:
        out = run(args.repo, now, computer, explicit=target, remote=args.remote, branch=args.branch,
                  explicit_reason=explicit_reason)
    except (ClaimError, sdt.SelectionError) as exc:
        print(f"::error::{exc}")
        return 2 if isinstance(exc, sdt.SelectionError) else 1
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    sel = out.selection
    for target_id, msg in (sel.errors if sel else []):
        print(f"::warning::{target_id}: {msg}")
    summary = render(out)
    print(summary, end="")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as fh:
            fh.write(summary)
    write_outputs(out, args.github_output)
    if not out.claim and sel and sel.errors and not out.lost:
        print(f"::error::{len(sel.errors)}개 모델의 버전을 확인하지 못해 대상 없음으로 확정할 수 없음")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
