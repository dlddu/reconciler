#!/usr/bin/env python3
"""reconciler-work-executor 워크플로의 「Select target」 스텝.

reconciler-work-executor 스킬의 Step 0(대상 선정 · 진입 게이트, 4-0)을 기계적으로 옮긴 것이다.
판정 규칙은 reconciler-local의 work-executor 게이트(`precheck-execute.py`)와 같다.
이번 실행이 반영할 task **한 건**을 골라 GitHub Actions output으로 내보낸다. 레포에는 아무것도
쓰지 않는다(읽기 전용) — `approved → executing` 점유 커밋은 스킬 Step 1 몫이다.

실행 대상(executable) = 다음을 모두 만족하는 task:
  1. status가 `approved` — 실행 단계의 유일한 입구. `planned`/`reviewing`(검토 전·중)과
     `executing`/`verifying`(누군가 점유 중)은 어떤 경우에도 집지 않는다.
  2. attempts 마지막 항목에 `plan.steps`·`plan.executionGuide`와 planner가 찍은
     `preparation.preparedAt`이 있다(없으면 not_ready).
  3. `review.manualApproval`이 있으면 사람 승인이 끝났다:
     `preparation.pullRequestUrl`의 PR이 열려 있고 head가 `manualApproval.sha` 그대로이며,
     그 sha에 붙은 `manualApproval.context`의 최신 commit status가 `success`.
  4. `attempts[-1].decision`이 있으면 `verdict == approved`이고 PR이 열려 있으며 head가
     `decision.sha` 그대로. (3과 독립 — 둘 다 있으면 둘 다 통과해야 한다.)
  승인 확인은 fail-closed: 확인하지 못하면(API 오류·URL 파싱 실패) 승인 안 됨(error)으로 본다.

모델이 꺼져 있으면(`checkPolicy.enabled: false`) 그 task는 approved여도 고르지 않는다 — 주차된 것으로
보고 승인 확인(API 호출)도 하지 않는다(select_plan_target.py와 같은 술어). reconciler-local의
precheck-execute.py는 이것을 보지 않지만, 꺼진 모델의 task가 실수로 승인까지 간 일이 있어(2026-10-28) 막는다.

선정: 지목(워크플로 입력)이 있으면 그 대상만, 없으면 `review.reviewedAt`이 오래된 approved부터
판정해 처음 executable인 한 건에서 멈춘다(승인이 오래 묵을수록 전제가 흔들리므로). 나머지는
`approved` 그대로 다음 실행 몫이다. 타임스탬프 없는 건은 오래됐다고 할 수 없어 맨 뒤로 간다.

task id는 모델 안에서만 유일하다(같은 rct_ id가 여러 모델에 있다). 그래서 지목·출력 모두
`<tbm_id>/<rct_id>` 형태를 쓰고, 모호한 bare rct_ 지목은 추측하지 않고 거부한다.

출력(GITHUB_OUTPUT): found, target_id(`<tbm>/<rct>`), task_id, model_id, reason,
  pull_request_url, approved_count, error_count
  reason ∈ explicit | oldest_approval
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

TASKS_DIR = Path("data") / "reconciliation-tasks"
MODELS_FILE = Path("data") / "to-be-models.json"
READY_STATUSES = {"approved"}
DEFAULT_API = "https://api.github.com"
API_TIMEOUT = 30
# 파싱이 확실하지 않은 URL은 다른 레포 PR로 추측하지 않고 error로 둔다(fail-closed).
PR_URL_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([0-9]+)/?$")
NO_TIMESTAMP = "￿"

EXECUTABLE, WAITING, STALE, ERROR, NOT_READY = "executable", "waiting", "stale", "error", "not_ready"
PARKED = "parked"
VERDICT_LABEL = {
    PARKED: "주차됨",
    WAITING: "승인 대기",
    STALE: "승인 무효",
    ERROR: "확인 불가",
    NOT_READY: "준비 미완",
}
# 대상이 없을 때 「그럼 지금 누가 들고 있나」를 알리기 위한 다른 단계 status → 담당 스킬.
OTHER_STAGE_OWNER = {
    "planned": "reconciler-work-review 판정 대기",
    "reviewing": "reconciler-work-review 판정 중",
    "action_required": "reconciler-work-planner 계획 대기",
    "planning": "reconciler-work-planner 계획 중",
    "review_rejected": "reconciler-work-planner 재계획 대기",
    "failed": "reconciler-work-planner 재작업 대기",
    "assessing": "reconciler-drift-detector 감지 중",
    "executing": "다른 워커가 실행 중(점유)",
    "verifying": "다른 워커가 검증 중(점유)",
}


class SelectionError(Exception):
    """데이터가 깨졌거나 지목이 잘못돼 선정 자체를 할 수 없을 때."""


class ApprovalCheckError(Exception):
    """한 task의 승인을 확인하지 못했을 때 → 그 task만 error."""


# ── 데이터 ────────────────────────────────────────────────────────────────────


def is_enabled(model: dict | None) -> bool:
    """`checkPolicy.enabled`가 JSON false일 때만 꺼진 것으로 본다(select_plan_target.py와 같은 술어)."""
    if not isinstance(model, dict):
        return True
    return (model.get("checkPolicy") or {}).get("enabled") is not False


def load_models(repo: Path) -> dict:
    path = repo / MODELS_FILE
    if not path.exists():
        return {}
    try:
        models = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SelectionError(f"{MODELS_FILE}: {exc}") from exc
    if not isinstance(models, list):
        raise SelectionError(f"{MODELS_FILE}는 배열이어야 함")
    return {m.get("id"): m for m in models if isinstance(m, dict)}


def load_tasks(repo: Path) -> list[tuple[str, dict]]:
    """[(model_id, task)] — 모든 task 파일. 하나라도 못 읽으면 판단 불가(SelectionError)."""
    tasks_dir = repo / TASKS_DIR
    if not tasks_dir.is_dir():
        raise SelectionError(f"{tasks_dir} 디렉터리가 없음")
    out = []
    for path in sorted(tasks_dir.glob("*.json")):
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SelectionError(f"{path.name}: {exc}") from exc
        if not isinstance(records, list):
            raise SelectionError(f"{path.name}: task 파일은 배열이어야 함")
        out.extend((path.stem, t) for t in records if isinstance(t, dict))
    return out


def reviewed_at(task: dict) -> str | None:
    attempts = task.get("attempts")
    if isinstance(attempts, list) and attempts and isinstance(attempts[-1], dict):
        review = attempts[-1].get("review")
        if isinstance(review, dict):
            return review.get("reviewedAt")
    return None


def approval_order(item: tuple[str, dict]):
    model_id, task = item
    return (reviewed_at(task) or NO_TIMESTAMP, model_id, task.get("id") or "")


# ── GitHub ───────────────────────────────────────────────────────────────────


@dataclass
class GitHub:
    api: str = DEFAULT_API
    token: str | None = None
    calls: int = 0

    def get(self, path: str):
        self.calls += 1
        req = urllib.request.Request(f"{self.api.rstrip('/')}{path}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "reconciler-select-execute-target")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise ApprovalCheckError(f"GET {path} → HTTP {exc.code}") from exc
        except Exception as exc:  # URLError, timeout, decode
            raise ApprovalCheckError(f"GET {path} → {type(exc).__name__}: {exc}") from exc
        try:
            return json.loads(body)
        except ValueError as exc:
            raise ApprovalCheckError(f"GET {path} → JSON 아님 ({exc})") from exc


def latest_status_state(statuses: list, context: str) -> str | None:
    """그 context의 가장 최근 status state. created_at 우선, 같으면 API 순서(최신이 앞)."""
    best = None
    for i, s in enumerate(statuses):
        if not isinstance(s, dict) or s.get("context") != context:
            continue
        key = (s.get("created_at") or "", -i)
        if best is None or key > best[0]:
            best = (key, s.get("state"))
    return None if best is None else best[1]


def fetch_pr(pr_url, gh: GitHub):
    """(ref, None) 또는 (None, (verdict, 사유)). 두 사람 게이트가 같은 PR을 공유하므로 한 번만 가져온다."""
    if not pr_url or not isinstance(pr_url, str):
        return None, (ERROR, "사람 게이트가 있는데 preparation.pullRequestUrl이 없음")
    m = PR_URL_RE.match(pr_url.strip())
    if not m:
        return None, (ERROR, f"PR URL을 해석할 수 없음: {pr_url!r}")
    owner, repo, number = m.groups()
    try:
        pr = gh.get(f"/repos/{owner}/{repo}/pulls/{number}")
    except ApprovalCheckError as exc:
        return None, (ERROR, str(exc))
    if not isinstance(pr, dict):
        return None, (ERROR, f"{owner}/{repo}#{number} PR 응답 형식이 이상함")
    head = pr.get("head") if isinstance(pr.get("head"), dict) else {}
    return {"owner": owner, "repo": repo, "number": number, "pr": pr, "head": head.get("sha")}, None


def check_pr_bound(ref: dict, sha: str, what: str):
    pr, label = ref["pr"], f"{ref['owner']}/{ref['repo']}#{ref['number']}"
    if pr.get("merged") or pr.get("merged_at"):
        return STALE, f"{label} 이미 머지됨 — {what}이 더는 유효하지 않음"
    if pr.get("state") != "open":
        return STALE, f"{label} 상태가 {pr.get('state')!r} (open 아님)"
    if ref["head"] != sha:
        return STALE, f"{label} head가 {str(ref['head'])[:12]}로 바뀜 — {what}은 {sha[:12]}에 묶여 무효"
    return None


def check_manual_approval(ref: dict, manual: dict, gh: GitHub):
    sha, context = manual.get("sha"), manual.get("context")
    if not sha or not context:
        return ERROR, "manualApproval에 sha 또는 context가 없음"
    bound = check_pr_bound(ref, sha, "사람 승인")
    if bound:
        return bound
    try:
        statuses = gh.get(f"/repos/{ref['owner']}/{ref['repo']}/commits/{sha}/statuses?per_page=100")
    except ApprovalCheckError as exc:
        return ERROR, str(exc)
    if not isinstance(statuses, list):
        return ERROR, f"{ref['owner']}/{ref['repo']}@{sha[:12]} statuses 응답 형식이 이상함"
    state = latest_status_state(statuses, context)
    if state is None:
        return WAITING, f"{sha[:12]}에 `{context}` status 없음 — 사람 승인 대기"
    if state != "success":
        return WAITING, f"{sha[:12]}의 최신 `{context}` status가 {state!r} (success 아님)"
    return EXECUTABLE, f"`{context}` success on {sha[:12]} — 사람 승인 완료"


def check_decision(ref: dict, decision: dict):
    sha = decision.get("sha")
    if not sha:
        return ERROR, "decision에 sha가 없음"
    bound = check_pr_bound(ref, sha, "결정")
    if bound:
        return bound
    return EXECUTABLE, f"결정 승인 on {sha[:12]}, PR head 그대로"


def judge(task: dict, gh: GitHub) -> tuple[str, str, dict]:
    """(verdict, 사유, info) — 한 task."""
    info = {"pullRequestUrl": None, "context": None}
    if task.get("status") not in READY_STATUSES:
        return NOT_READY, f"status={task.get('status')} — 실행 단계 대상이 아님", info

    attempts = task.get("attempts")
    if not isinstance(attempts, list) or not attempts or not isinstance(attempts[-1], dict):
        return NOT_READY, "attempts가 없거나 마지막 항목이 깨짐", info
    attempt = attempts[-1]
    plan = attempt.get("plan") if isinstance(attempt.get("plan"), dict) else {}
    prep = attempt.get("preparation") if isinstance(attempt.get("preparation"), dict) else {}
    review = attempt.get("review") if isinstance(attempt.get("review"), dict) else {}
    info["pullRequestUrl"] = prep.get("pullRequestUrl")

    if not plan.get("steps"):
        return NOT_READY, "마지막 시도에 plan.steps가 없음", info
    if not plan.get("executionGuide"):
        return NOT_READY, "마지막 시도에 plan.executionGuide가 없음", info
    # `preparation.prepared`는 스키마에서 빠졌다(preparation 기록 자체가 준비 완료를 뜻함).
    # planner가 스테이징을 끝내며 찍는 preparedAt으로 판단한다.
    if not prep.get("preparedAt"):
        return NOT_READY, "마지막 시도가 준비되지 않음(preparation.preparedAt 없음)", info

    manual, decision = review.get("manualApproval"), attempt.get("decision")
    if manual and not isinstance(manual, dict):
        return ERROR, "review.manualApproval 형식이 깨짐", info
    if decision and not isinstance(decision, dict):
        return ERROR, "attempt.decision 형식이 깨짐", info
    if manual:
        info["context"] = manual.get("context")
    if not manual and not decision:
        # manualApproval 없음 = 리뷰가 사람 승인을 요구하지 않음(필드 이전의 review.required 레거시 포함).
        return EXECUTABLE, "사람 승인 불필요", info

    # 사람 결정이 아직 없는 건은 API를 부르지 않고 바로 대기로 판정한다.
    if decision:
        verdict = decision.get("verdict")
        if verdict is None:
            return WAITING, "decision.verdict 없음 — 사람 결정 대기", info
        if verdict == "rejected":
            return STALE, "decision.verdict=rejected인데 task가 아직 approved", info
        if verdict != "approved":
            return ERROR, f"알 수 없는 decision.verdict {verdict!r}", info

    ref, err = fetch_pr(prep.get("pullRequestUrl"), gh)
    if err:
        return err[0], err[1], info
    reasons = []
    if decision:
        v, r = check_decision(ref, decision)
        if v != EXECUTABLE:
            return v, r, info
        reasons.append(r)
    if manual:
        v, r = check_manual_approval(ref, manual, gh)
        if v != EXECUTABLE:
            return v, r, info
        reasons.append(r)
    return EXECUTABLE, "; ".join(reasons), info


# ── 선정 ─────────────────────────────────────────────────────────────────────


@dataclass
class Selection:
    found: bool = False
    target_id: str = ""
    task_id: str = ""
    model_id: str = ""
    reason: str = ""
    detail: str = ""
    pull_request_url: str = ""
    approved_count: int = 0
    judged: list = field(default_factory=list)    # (ref, verdict, 사유, info) — executable 아닌 것
    deferred: list = field(default_factory=list)  # 판정하지 않고 다음 실행에 넘긴 ref
    other_stages: dict = field(default_factory=dict)
    note: str = ""

    @property
    def errors(self):
        return [j for j in self.judged if j[1] == ERROR]

    def pick(self, model_id, task, reason, detail, info):
        self.found = True
        self.model_id, self.task_id = model_id, task["id"]
        self.target_id = f"{model_id}/{task['id']}"
        self.reason, self.detail = reason, detail
        self.pull_request_url = info.get("pullRequestUrl") or ""
        return self


def resolve_explicit(target: str, tasks: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    if "/" in target:
        model_id, _, task_id = target.partition("/")
        hits = [(m, t) for m, t in tasks if m == model_id and t.get("id") == task_id]
        if not hits:
            raise SelectionError(f"task {target}를 찾을 수 없음")
        return hits
    if target.startswith("tbm_"):
        if not any(m == target for m, _ in tasks):
            raise SelectionError(f"모델 {target}의 task 파일이 없음")
        return [(m, t) for m, t in tasks if m == target and t.get("status") in READY_STATUSES]
    hits = [(m, t) for m, t in tasks if t.get("id") == target]
    if not hits:
        raise SelectionError(f"task {target}를 찾을 수 없음")
    if len(hits) > 1:
        models = ", ".join(sorted(m for m, _ in hits))
        raise SelectionError(f"task {target}가 여러 모델에 있어 모호함({models}) — <tbm_id>/{target}로 지목할 것")
    return hits


def select_target(repo: Path, gh: GitHub, explicit: str | None = None) -> Selection:
    tasks = load_tasks(repo)
    models = load_models(repo)
    sel = Selection()
    approved = sorted(((m, t) for m, t in tasks if t.get("status") in READY_STATUSES), key=approval_order)
    sel.approved_count = len(approved)

    if explicit:
        candidates = sorted(resolve_explicit(explicit, tasks), key=approval_order)
        reason = "explicit"
        if not candidates:
            sel.note = f"지목된 모델 {explicit}에 approved task가 없음"
    else:
        candidates = approved
        reason = "oldest_approval"
        for _, t in tasks:
            st = t.get("status")
            if st in OTHER_STAGE_OWNER:
                sel.other_stages[st] = sel.other_stages.get(st, 0) + 1

    for i, (model_id, task) in enumerate(candidates):
        ref = f"{model_id}/{task.get('id')}"
        if not is_enabled(models.get(model_id)):
            sel.judged.append((ref, PARKED, "모델 감지 비활성(enabled:false) — checkPolicy.enabled를 켜면 다시 실행 대상", {}))
            continue
        verdict, why, info = judge(task, gh)
        if verdict == EXECUTABLE:
            sel.deferred = [f"{m}/{t.get('id')}" for m, t in candidates[i + 1:]]
            detail = why if reason == "explicit" else f"승인 {reviewed_at(task) or '시각 미기록'} — {why}"
            return sel.pick(model_id, task, reason, detail, info)
        sel.judged.append((ref, verdict, why, info))
    return sel


# ── 출력 ─────────────────────────────────────────────────────────────────────


def write_outputs(sel: Selection, path: str | None) -> None:
    lines = {
        "found": "true" if sel.found else "false",
        "target_id": sel.target_id,
        "task_id": sel.task_id,
        "model_id": sel.model_id,
        "reason": sel.reason,
        "pull_request_url": sel.pull_request_url,
        "approved_count": str(sel.approved_count),
        "error_count": str(len(sel.errors)),
    }
    text = "".join(f"{k}={v}\n" for k, v in lines.items())
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def render_summary(sel: Selection, api_calls: int) -> str:
    out = ["#### Select target"]
    if sel.found:
        out.append(f"- 선정: `{sel.target_id}` ({sel.reason}) — {sel.detail}")
        if sel.pull_request_url:
            out.append(f"- PR: {sel.pull_request_url}")
        if sel.deferred:
            out.append(f"- 미판정 approved {len(sel.deferred)}건은 이번에 점유하지 않고 다음 실행에 넘김: "
                       + ", ".join(f"`{r}`" for r in sel.deferred))
    else:
        out.append("- 이번에 실행할 대상 없음" + (f" ({sel.note})" if sel.note else ""))
    for ref, verdict, why, info in sel.judged:
        mark = "⚠️ " if verdict == ERROR else ""
        line = f"- {mark}{VERDICT_LABEL.get(verdict, verdict)} · `{ref}`: {why}"
        if verdict == WAITING and info.get("pullRequestUrl"):
            line += f" — {info['pullRequestUrl']}" + (f" 에 `{info['context']}` 필요" if info.get("context") else "")
        elif verdict == STALE:
            line += " — 재검토(planned) 또는 reconciler-manual-approval에서 거부 필요"
        out.append(line)
    if not sel.found and sel.other_stages:
        parts = [f"{st} {n}건({OTHER_STAGE_OWNER[st]})" for st, n in sorted(sel.other_stages.items())]
        out.append("- 다른 단계: " + ", ".join(parts))
    out.append(f"- GitHub API 호출 {api_calls}회")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="reconciler checkout 경로")
    parser.add_argument("--target", default="",
                        help="지목 대상(<tbm_id>/<rct_id>, rct_..., 또는 tbm_...), 비우면 자동 선정")
    parser.add_argument("--api-url", default=os.environ.get("GITHUB_API_URL") or DEFAULT_API)
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    parser.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = parser.parse_args(argv)

    target = args.target.strip() or None
    if target and not target.startswith(("tbm_", "rct_")):
        print(f"::error::target_id는 <tbm_id>/<rct_id>, rct_... 또는 tbm_... 형태여야 함: {target}")
        return 2

    # 대상 레포 한정 read 토큰(contents·pull_requests·statuses)이 우선이고, 없으면 워크플로 토큰으로
    # 공개 레포 조회 한도만이라도 올린다. 둘 다 없으면 무인증(60회/h).
    token = os.environ.get("SOURCE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or None
    gh = GitHub(api=args.api_url, token=token)
    try:
        sel = select_target(Path(args.repo), gh, explicit=target)
    except SelectionError as exc:
        print(f"::error::{exc}")
        return 2

    for ref, verdict, why, _ in sel.judged:
        if verdict == ERROR:
            print(f"::warning::{ref}: {why}")
    summary = render_summary(sel, gh.calls)
    print(summary, end="")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as fh:
            fh.write(summary)
    write_outputs(sel, args.github_output)

    # 대상이 없는데 승인을 확인하지 못한 건이 있으면 "실행할 것 없음"으로 단정할 수 없다.
    if not sel.found and sel.errors:
        print(f"::error::{len(sel.errors)}건의 승인을 확인하지 못해 대상 없음으로 확정할 수 없음")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
