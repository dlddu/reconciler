#!/usr/bin/env python3
"""reconciler-drift-detector 워크플로의 「Select target」 스텝.

reconciler-drift-detector 스킬의 Step 0(대상 선정 · 진입 게이트)을 기계적으로 옮긴 것이다.
이번 실행이 감지할 대상 **한 건**을 골라 GitHub Actions output으로 내보낸다. 레포에는 아무것도
쓰지 않는다(읽기 전용) — `lastObservedVersion` 갱신과 task 생성은 스킬 Step 1의 점유 커밋 몫이다.

탐색 순서(앞에서 찾으면 뒤는 보지 않는다):
  0. 지목      — 워크플로 입력으로 tbm_/rct_ id가 주어지면 그 대상만 검사한다.
  1. 재확인 만료 — `assessing` + `assessment.recheckAfter` <= now 인 task.
  2. 수동 트리거 — 활성 모델 중 `checkPolicy.manualTriggerRequestedAt`이 적힌 것(오래 기다린 순).
  3. 새 변화   — 활성 모델의 versionScript를 돌려 `lastObservedVersion`과 다른 것
                 (`lastObservedAt`이 오래된 모델부터 보고, 처음 찾은 한 건에서 멈춘다).
스킬의 resume(이 세션이 잡고 있던 task)은 매 실행이 새 러너라 해당이 없다.

제외: `checkPolicy.enabled == false` 모델(버전 스크립트도 돌리지 않는다), 열린 `assessing` task가
있는 모델(다른 워커 점유 중이거나 재확인 유예 중), 그 밖의 이후 단계 status는 후보 판단에 쓰지 않는다.

출력(GITHUB_OUTPUT): found, target_id, target_kind(model|task), model_id, reason
  reason ∈ explicit | recheck_expired | manual_trigger | version_changed
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SIDES = ("asIs", "toBe")
RUNTIMES = {"bash": ["bash"], "python": ["python3"], "node": ["node"]}
# 버전 스크립트에 넘기지 않는 환경 변수(스크립트는 체크아웃된 레포만 읽는다).
SCRUBBED_ENV = ("SOURCE_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN",
                "ACTIONS_ID_TOKEN_REQUEST_TOKEN", "ACTIONS_RUNTIME_TOKEN")
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


class SelectionError(Exception):
    """데이터가 깨져 선정 자체를 할 수 없을 때."""


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def fmt_time(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SelectionError(f"{path}: {exc}") from exc


def is_enabled(model: dict) -> bool:
    return (model.get("checkPolicy") or {}).get("enabled", True) is not False


def oldest_observed(model: dict) -> dt.datetime:
    """모델의 두 side 중 더 오래된 관측 시각. 관측 이력이 없으면 가장 오래된 것으로 친다."""
    times = []
    for side in SIDES:
        observed = parse_time((model.get(side) or {}).get("lastObservedAt"))
        times.append(observed or EPOCH)
    return min(times)


# ── 버전 계산 ────────────────────────────────────────────────────────────────


class VersionError(Exception):
    pass


@dataclass
class VersionComputer:
    """github dataSource를 (repository, ref) 단위로 한 번만 클론해 versionScript를 돌린다."""

    work_dir: Path
    url_template: str = "https://github.com/{repository}.git"
    token: str | None = None
    _checkouts: dict = field(default_factory=dict)

    def _git_auth_args(self) -> list[str]:
        if not self.token:
            return []
        basic = base64.b64encode(f"x-access-token:{self.token}".encode()).decode()
        return ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic}"]

    def checkout(self, data_source: dict) -> Path:
        if data_source.get("type") != "github":
            raise VersionError(f"dataSource.type={data_source.get('type')!r}은 아직 지원하지 않음")
        repository = data_source["repository"]
        ref = data_source.get("ref") or "main"
        key = (repository, ref)
        cached = self._checkouts.get(key)
        if isinstance(cached, VersionError):
            raise cached
        if cached is not None:
            return cached

        dest = self.work_dir / f"{repository.replace('/', '__')}@{ref.replace('/', '_')}"
        if dest.exists():
            shutil.rmtree(dest)
        url = self.url_template.format(repository=repository)
        cmd = ["git", *self._git_auth_args(), "clone", "--quiet", "--depth", "1",
               "--single-branch", "--branch", ref, url, str(dest)]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if result.returncode != 0:
            err = VersionError(f"clone {repository}@{ref} 실패: {self._redact(result.stderr).strip()[-300:]}")
            self._checkouts[key] = err
            raise err
        self._checkouts[key] = dest
        return dest

    def _redact(self, text: str) -> str:
        return text.replace(self.token, "***") if self.token else text

    def compute(self, tracked: dict) -> str:
        checkout = self.checkout(tracked["dataSource"])
        script = tracked["versionScript"]
        runtime = script.get("runtime")
        if runtime not in RUNTIMES:
            raise VersionError(f"versionScript.runtime={runtime!r} 미지원")
        env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
        for key, value in (script.get("env") or {}).items():
            if value.startswith("secretRef:"):
                raise VersionError(f"versionScript.env.{key}의 secretRef는 아직 해석하지 않음")
            env[key] = value
        timeout = int(script.get("timeoutSeconds") or 60)

        with tempfile.NamedTemporaryFile("w", suffix=".script", dir=self.work_dir,
                                         delete=False, encoding="utf-8") as fh:
            fh.write(script["code"])
            script_path = fh.name
        try:
            result = subprocess.run([*RUNTIMES[runtime], script_path], cwd=checkout, env=env,
                                    capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise VersionError(f"versionScript가 {timeout}s 안에 끝나지 않음") from exc
        finally:
            os.unlink(script_path)
        if result.returncode != 0:
            tail = result.stderr.strip().splitlines()[-1:] or ["(stderr 없음)"]
            raise VersionError(f"versionScript 종료 코드 {result.returncode}: {tail[0][:300]}")
        version = result.stdout.strip()
        if not version:
            raise VersionError("versionScript stdout이 비어 있음")
        return version


def version_matches(stored: str | None, current: str) -> bool:
    """저장값과 같은지. README 계약은 stdout 마지막 줄이지만, 기존 레코드는 여러 줄 stdout을
    통째로 저장한 경우가 있어 둘 중 하나와 같으면 같은 버전으로 본다."""
    if stored is None:
        return False
    stored = stored.strip()
    last_line = current.splitlines()[-1].strip()
    return stored in (current, last_line)


# ── 선정 ─────────────────────────────────────────────────────────────────────


@dataclass
class Selection:
    found: bool = False
    target_id: str = ""
    target_kind: str = ""
    model_id: str = ""
    reason: str = ""
    detail: str = ""
    skipped: list = field(default_factory=list)   # (id, 사유)
    errors: list = field(default_factory=list)    # (id, 메시지)
    scanned: int = 0
    remaining_unknown: bool = False

    def pick(self, *, target_id, target_kind, model_id, reason, detail):
        self.found = True
        self.target_id, self.target_kind = target_id, target_kind
        self.model_id, self.reason, self.detail = model_id, reason, detail
        return self


def load_state(repo: Path):
    models = load_json(repo / "data" / "to-be-models.json")
    if not isinstance(models, list):
        raise SelectionError("data/to-be-models.json은 배열이어야 함")
    tasks_by_model = {}
    for model in models:
        path = repo / "data" / "reconciliation-tasks" / f"{model['id']}.json"
        tasks_by_model[model["id"]] = load_json(path) if path.exists() else []
    return models, tasks_by_model


def classify_assessing(task: dict, now: dt.datetime) -> str:
    """assessing task를 expired(재확인 시각 지남) / parked(유예 중) / claimed(점유 중)로 가른다."""
    recheck = parse_time((task.get("assessment") or {}).get("recheckAfter"))
    if recheck is None:
        return "claimed"
    return "expired" if recheck <= now else "parked"


def open_assessing(tasks: list, now: dt.datetime) -> list[tuple[dict, str]]:
    return [(t, classify_assessing(t, now)) for t in tasks if t.get("status") == "assessing"]


def describe_open(task: dict, kind: str) -> str:
    if kind == "parked":
        return f"{task['id']} 재확인 유예 중({task['assessment']['recheckAfter']} 이후)"
    return f"{task['id']} 다른 워커가 점유 중(assessing)"


def select_explicit(target: str, models: list, tasks_by_model: dict, now: dt.datetime) -> Selection:
    sel = Selection()
    by_id = {m["id"]: m for m in models}
    if target.startswith("rct_"):
        for model_id, tasks in tasks_by_model.items():
            for task in tasks:
                if task.get("id") != target:
                    continue
                if not is_enabled(by_id[model_id]):
                    sel.skipped.append((target, f"모델 {model_id} 감지 비활성(enabled:false)"))
                    return sel
                if task.get("status") != "assessing":
                    sel.skipped.append((target, f"status={task.get('status')} — 감지 단계 대상이 아님"))
                    return sel
                kind = classify_assessing(task, now)
                if kind == "parked":
                    sel.skipped.append((target, describe_open(task, kind)))
                    return sel
                return sel.pick(target_id=target, target_kind="task", model_id=model_id,
                                reason="explicit", detail=f"지목된 assessing task ({kind})")
        raise SelectionError(f"task {target}를 찾을 수 없음")

    model = by_id.get(target)
    if model is None:
        raise SelectionError(f"모델 {target}를 찾을 수 없음")
    if not is_enabled(model):
        sel.skipped.append((target, "감지 비활성(enabled:false)"))
        return sel
    opened = open_assessing(tasks_by_model.get(target, []), now)
    expired = [t for t, k in opened if k == "expired"]
    if expired:
        task = expired[0]
        return sel.pick(target_id=task["id"], target_kind="task", model_id=target,
                        reason="recheck_expired",
                        detail=f"지목된 모델에 재확인 만료 task가 있어 그것을 이어받음(recheckAfter {task['assessment']['recheckAfter']})")
    if opened:
        task, kind = opened[0]
        sel.skipped.append((target, describe_open(task, kind)))
        return sel
    return sel.pick(target_id=target, target_kind="model", model_id=target,
                    reason="explicit", detail="워크플로 입력으로 지목된 모델")


def select_target(repo: Path, now: dt.datetime, computer: VersionComputer | None,
                  explicit: str | None = None, full_sweep: bool = False) -> Selection:
    models, tasks_by_model = load_state(repo)

    if explicit:
        return select_explicit(explicit, models, tasks_by_model, now)

    sel = Selection()
    enabled = [m for m in models if is_enabled(m)]
    disabled = [m for m in models if not is_enabled(m)]
    if disabled:
        sel.skipped.append((f"{len(disabled)}개 모델", "감지 비활성(enabled:false) — 버전 스크립트 생략"))

    # 열린 assessing이 있는 모델은 후보에서 뺀다(한 모델에 감지 task를 두 건 열지 않는다).
    expired: list[tuple[dt.datetime, dict, str]] = []
    available: list[dict] = []
    for model in enabled:
        opened = open_assessing(tasks_by_model.get(model["id"], []), now)
        if not opened:
            available.append(model)
            continue
        for task, kind in opened:
            if kind == "expired":
                expired.append((parse_time(task["assessment"]["recheckAfter"]), task, model["id"]))
            else:
                sel.skipped.append((model["id"], describe_open(task, kind)))

    # 1) 재확인 만료 — 가장 먼저 만료된 것부터.
    if expired:
        expired.sort(key=lambda x: (x[0], x[1]["id"]))
        when, task, model_id = expired[0]
        if len(expired) > 1:
            sel.skipped.append((f"재확인 만료 {len(expired) - 1}건", "이번엔 점유하지 않고 다음 실행에 넘김"))
        return sel.pick(target_id=task["id"], target_kind="task", model_id=model_id,
                        reason="recheck_expired", detail=f"recheckAfter {fmt_time(when)} 경과")

    # 2) 수동 트리거 — 가장 오래 기다린 요청부터.
    manual = []
    for model in available:
        policy = model.get("checkPolicy") or {}
        requested = parse_time(policy.get("manualTriggerRequestedAt"))
        if requested is None:
            continue
        if not (policy.get("manualTriggerReason") or "").strip():
            sel.errors.append((model["id"], "manualTriggerRequestedAt은 있는데 manualTriggerReason이 비어 있음 — 요청이 깨져 건너뜀"))
            continue
        manual.append((requested, model))
    if manual:
        manual.sort(key=lambda x: (x[0], x[1]["id"]))
        requested, model = manual[0]
        if len(manual) > 1:
            sel.skipped.append((f"수동 트리거 {len(manual) - 1}건", "이번엔 점유하지 않고 다음 실행에 넘김"))
        return sel.pick(target_id=model["id"], target_kind="model", model_id=model["id"],
                        reason="manual_trigger",
                        detail=f"{fmt_time(requested)} 요청 — {model['checkPolicy']['manualTriggerReason']}")

    # 3) 새 변화 — 오래 관측되지 않은 모델부터 버전을 계산하고, 처음 바뀐 한 건에서 멈춘다.
    if computer is None:
        raise SelectionError("버전 계산기가 없음")
    changed = []
    for model in sorted(available, key=lambda m: (oldest_observed(m), m["id"])):
        sel.scanned += 1
        diffs = []
        try:
            for side in SIDES:
                current = computer.compute(model[side])
                if not version_matches(model[side].get("lastObservedVersion"), current):
                    diffs.append(side)
        except VersionError as exc:
            sel.errors.append((model["id"], str(exc)))
            continue
        if diffs:
            changed.append((model, diffs))
            if not full_sweep:
                break
    if changed:
        model, diffs = changed[0]
        if full_sweep and len(changed) > 1:
            sel.skipped.append((f"버전 변화 {len(changed) - 1}건",
                                "이번엔 점유하지 않고 lastObservedVersion을 그대로 둠: "
                                + ", ".join(m["id"] for m, _ in changed[1:])))
        sel.remaining_unknown = not full_sweep and sel.scanned < len(available)
        return sel.pick(target_id=model["id"], target_kind="model", model_id=model["id"],
                        reason="version_changed", detail=f"바뀐 side: {', '.join(diffs)}")

    clean = sel.scanned - len(sel.errors)
    sel.skipped.append((f"활성 {len(available)}개", f"{clean}개 버전 변화 없음"))
    return sel


# ── 출력 ─────────────────────────────────────────────────────────────────────


def write_outputs(sel: Selection, path: str | None) -> None:
    lines = {
        "found": "true" if sel.found else "false",
        "target_id": sel.target_id,
        "target_kind": sel.target_kind,
        "model_id": sel.model_id,
        "reason": sel.reason,
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
        out.append(f"- 선정: `{sel.target_id}` ({sel.target_kind}, {sel.reason}) — {sel.detail}")
        if sel.remaining_unknown:
            out.append("- 첫 변화에서 스윕을 멈춤 — 나머지 모델은 다음 실행이 본다")
    else:
        out.append("- 이번에 감지할 대상 없음")
    for target, why in sel.skipped:
        out.append(f"- 제외 · {target}: {why}")
    for target, msg in sel.errors:
        out.append(f"- ⚠️ {target}: {msg}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="reconciler checkout 경로")
    parser.add_argument("--target", default="", help="지목 대상(tbm_... 또는 rct_...), 비우면 자동 선정")
    parser.add_argument("--now", help="기준 시각(ISO 8601, 테스트용). 기본은 현재 UTC")
    parser.add_argument("--work-dir", help="대상 레포 클론 위치. 기본은 임시 디렉터리")
    parser.add_argument("--repo-url-template", default="https://github.com/{repository}.git")
    parser.add_argument("--full-sweep", action="store_true",
                        help="첫 변화에서 멈추지 않고 모든 활성 모델의 버전을 계산")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    parser.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = parser.parse_args(argv)

    now = parse_time(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    target = args.target.strip() or None
    if target and not target.startswith(("tbm_", "rct_")):
        print(f"::error::target_id는 tbm_ 또는 rct_로 시작해야 함: {target}")
        return 2

    tmp = None
    work_dir = Path(args.work_dir) if args.work_dir else Path(tmp := tempfile.mkdtemp(prefix="select-target-"))
    work_dir.mkdir(parents=True, exist_ok=True)
    computer = VersionComputer(work_dir=work_dir, url_template=args.repo_url_template,
                               token=os.environ.get("SOURCE_GITHUB_TOKEN") or None)
    try:
        sel = select_target(Path(args.repo), now, computer, explicit=target, full_sweep=args.full_sweep)
    except SelectionError as exc:
        print(f"::error::{exc}")
        return 2
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    for target_id, msg in sel.errors:
        print(f"::warning::{target_id}: {msg}")
    summary = render_summary(sel)
    print(summary, end="")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as fh:
            fh.write(summary)
    write_outputs(sel, args.github_output)

    # 대상이 없는데 일부 모델을 확인하지 못했다면 "감지할 것 없음"이라고 단정할 수 없다.
    if not sel.found and sel.errors:
        print(f"::error::{len(sel.errors)}개 모델의 버전을 확인하지 못해 대상 없음으로 확정할 수 없음")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
