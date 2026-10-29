#!/usr/bin/env python3
"""리뷰 스킬 빌드 test job의 replay 시나리오 — 이미 리뷰된 task를 점유 직전(`planned`)으로 되돌려 다시 판정시킨다.

**샌드박스 전용.** test job의 reconciler 체크아웃은 origin을 러너 로컬 bare 레포로 바꿔 둔다(README 「리뷰 스킬
MiniMax 파이프라인」). 이 스크립트는 그 원격이 로컬 경로가 아니면 아무것도 쓰지 않고 실패한다 — 운영 데이터에
되감기 커밋이 들어가면 같은 task를 실제 리뷰 워커가 다시 집기 때문이다.

운영 데이터에 `planned`가 늘 있지는 않다. 그래서 git 이력에서 최근 `review(<tbm>/<rct>): claim` 커밋을 찾아,
그 부모 커밋의 task 레코드(점유 직전 = planned)를 현재 파일에 되돌려 놓고 샌드박스 원격에 push한다. 그 위에서
러너 점유(claim_review_target.py)와 생성 스킬의 판정이 운영과 똑같이 돈다 — 스킬은 이것이 replay인지 모른다.

고르는 후보(최근 점유부터):
  - 점유 직전 레코드가 `planned`이고 리뷰 전제(select_review_target.unready_reason)를 갖췄다
  - 그 레코드가 **현재 스키마**를 통과한다(스키마가 바뀐 옛 레코드는 건너뜀)
  - 모델이 꺼져 있지 않다(`checkPolicy.enabled: false`가 아님)
  - 그 task가 지금 `planned`·`reviewing`이 아니다(살아 있는 작업은 live 시나리오 몫)

기대 결과: PR이 지금 머지·종료됐으면 그 계획은 더 이상 실행할 수 없으므로 승인하면 안 된다 —
`expect_statuses=review_rejected,cancelled`. PR이 열려 있거나 직접 액션이면 기대를 걸지 않는다(빈 값).
PR 상태 조회에는 `--token-env`의 읽기 토큰을 쓴다(없으면 조회하지 않고 기대도 걸지 않는다).

출력(GITHUB_OUTPUT): target(tbm_.../rct_...), model_id, task_id, pull_request_url, pr_state, expect_statuses,
                     original_claim, original_verdict, replay_commit
종료 코드: 0 = 되감아 push함, 1 = 후보 없음/오류, 2 = 사용법 오류
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import select_review_target as srt  # noqa: E402

TASKS_DIR = "data/reconciliation-tasks"
MODELS_FILE = "data/to-be-models.json"
CLAIM_RE = re.compile(r"^review\((tbm_[^/\s)]+)/(rct_[0-9]{8}-[0-9]{4})\): claim$")
LIVE = {"planned", "reviewing"}
PR_RE = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")


class ReplayError(Exception):
    pass


@dataclass
class Replay:
    model_id: str
    task_id: str
    record: dict
    original_claim: str
    original_verdict: str
    pull_request_url: str = ""
    pr_state: str = ""
    expect_statuses: str = ""
    commit: str = ""


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if check and proc.returncode:
        raise ReplayError(f"git {' '.join(args)} 실패: {proc.stderr.strip()[-400:]}")
    return proc.stdout


def is_local_url(url: str) -> bool:
    url = url.strip()
    if not url:
        return False
    if url.startswith("file://"):
        return True
    if "://" in url:
        return False
    # scp 형태(user@host:path, host:path)도 원격이다. 그 밖은 로컬 경로(절대·상대).
    return not re.match(r"^[^/]+:", url)


def assert_sandbox(repo: Path, remote: str) -> None:
    for args in (("remote", "get-url", remote), ("remote", "get-url", "--push", remote)):
        url = git(repo, *args).strip()
        if not is_local_url(url):
            raise ReplayError(f"{remote}이 로컬 샌드박스가 아님({' '.join(args[1:])} → 원격 URL) — replay는 샌드박스에서만 쓴다")


def show_json(repo: Path, rev: str, path: str):
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{path}"], capture_output=True, text=True)
    if proc.returncode:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def by_id(items) -> dict:
    return {t.get("id"): t for t in (items or []) if isinstance(t, dict)}


def make_validator(repo: Path):
    import jsonschema

    schema = json.loads((repo / "schemas" / "reconciliation-task.schema.json").read_text(encoding="utf-8"))
    cls = jsonschema.validators.validator_for(schema)
    return cls(schema, format_checker=cls.FORMAT_CHECKER)


def verdict_of(current: dict | None, attempt_index: int) -> str:
    """원래 판정(현재 레코드에서 같은 시도의 review.status)과 지금 task status."""
    if not current:
        return "task 없음"
    attempts = current.get("attempts") or []
    review = (attempts[attempt_index].get("review") or {}) if 0 <= attempt_index < len(attempts) else {}
    parts = [f"review {review['status']}"] if review.get("status") else []
    if review.get("manualApproval"):
        parts.append("manualApproval")
    parts.append(f"지금 status {current.get('status')}")
    return " · ".join(parts)


def candidates(repo: Path, target: str | None, scan: int):
    """(claim sha, model_id, task_id) — 최근 점유부터."""
    for line in git(repo, "log", f"-{scan}", "--format=%H%x09%s", "HEAD").splitlines():
        sha, _, subject = line.partition("\t")
        m = CLAIM_RE.match(subject)
        if not m:
            continue
        if target and f"{m.group(1)}/{m.group(2)}" != target:
            continue
        yield sha, m.group(1), m.group(2)


def find(repo: Path, target: str | None, scan: int, skipped: list) -> Replay:
    validator = make_validator(repo)
    models = {m.get("id"): m for m in (json.loads((repo / MODELS_FILE).read_text(encoding="utf-8")) or [])}
    seen: set[str] = set()
    for sha, model_id, task_id in candidates(repo, target, scan):
        key = f"{model_id}/{task_id}"
        if key in seen:
            continue
        seen.add(key)
        rel = f"{TASKS_DIR}/{model_id}.json"
        before = by_id(show_json(repo, f"{sha}^", rel)).get(task_id)
        current = by_id(show_json(repo, "HEAD", rel)).get(task_id)
        why = None
        if not before or before.get("status") != "planned":
            why = "점유 직전 레코드가 planned가 아님"
        elif current and current.get("status") in LIVE:
            why = f"지금 {current.get('status')} — 살아 있는 작업(live 시나리오 몫)"
        elif not srt.is_enabled(models.get(model_id)):
            why = "모델 감지 비활성(enabled:false)"
        elif (reason := srt.unready_reason(before)):
            why = f"리뷰 전제 미충족 — {reason}"
        elif (errs := list(validator.iter_errors(before))):
            why = f"현재 스키마 위반 — {errs[0].message[:120]}"
        if why:
            skipped.append((key, why))
            continue
        last = len(before.get("attempts") or []) - 1
        prep = (before["attempts"][-1].get("preparation") or {})
        return Replay(model_id=model_id, task_id=task_id, record=before, original_claim=sha,
                      original_verdict=verdict_of(current, last),
                      pull_request_url=prep.get("pullRequestUrl") or "")
    scope = f"지목 {target}" if target else f"최근 {scan}개 커밋"
    raise ReplayError(f"replay 후보 없음({scope}의 review claim 커밋 중 조건을 만족하는 것이 없음)")


def pr_state(url: str, token: str | None) -> str:
    """open | closed | merged — 조회할 수 없으면 빈 문자열."""
    m = PR_RE.match(url or "")
    if not (m and token):
        return ""
    req = urllib.request.Request(f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/pulls/{m.group(3)}",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "reconciler-replay"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
    except Exception as exc:  # noqa: BLE001 — 조회 실패는 기대를 걸지 않는 것으로 처리
        print(f"::warning::PR 상태 조회 실패({url}): {type(exc).__name__}")
        return ""
    if data.get("merged") or data.get("merged_at"):
        return "merged"
    return str(data.get("state") or "")


def apply(repo: Path, rp: Replay, *, remote: str, branch: str) -> None:
    rel = f"{TASKS_DIR}/{rp.model_id}.json"
    path = repo / rel
    tasks = json.loads(path.read_text(encoding="utf-8"))
    idx = next((i for i, t in enumerate(tasks) if isinstance(t, dict) and t.get("id") == rp.task_id), None)
    if idx is None:
        tasks.append(rp.record)
    else:
        tasks[idx] = rp.record
    path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    git(repo, "add", rel)
    git(repo, "commit", "--quiet", "-m",
        f"test({rp.model_id}/{rp.task_id}): replay as planned from {rp.original_claim[:7]}^ (sandbox only)")
    rp.commit = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "push", "--quiet", remote, f"HEAD:refs/heads/{branch}")


def write_outputs(rp: Replay, path: str | None) -> None:
    lines = {
        "target": f"{rp.model_id}/{rp.task_id}",
        "model_id": rp.model_id,
        "task_id": rp.task_id,
        "pull_request_url": rp.pull_request_url,
        "pr_state": rp.pr_state,
        "expect_statuses": rp.expect_statuses,
        "original_claim": rp.original_claim,
        "original_verdict": rp.original_verdict,
        "replay_commit": rp.commit,
    }
    text = "".join(f"{k}={v}\n" for k, v in lines.items())
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def render(rp: Replay | None, skipped: list) -> str:
    out = ["#### Replay fixture (sandbox)"]
    if rp:
        pr = rp.pull_request_url or "직접 액션(PR 없음)"
        out.append(f"- 되감음: `{rp.model_id}/{rp.task_id}` ← `{rp.original_claim[:7]}^`의 planned 레코드 · {pr}"
                   + (f" (지금 {rp.pr_state})" if rp.pr_state else ""))
        out.append(f"- 원래 판정: {rp.original_verdict}")
        out.append(f"- 기대: {rp.expect_statuses or '제한 없음(종료 상태 중 하나)'}")
    for key, why in skipped[:10]:
        out.append(f"- 건너뜀 · {key}: {why}")
    if len(skipped) > 10:
        out.append(f"- 건너뜀 {len(skipped) - 10}건 더")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None, lookup=pr_state) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--target", default="", help="tbm_.../rct_... — 비우면 최근 점유부터 자동 선택")
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default="main")
    p.add_argument("--scan", type=int, default=400, help="review claim 커밋을 찾을 최근 커밋 수")
    p.add_argument("--token-env", default="", help="PR 상태 조회용 읽기 토큰이 든 환경 변수 이름")
    p.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    p.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = p.parse_args(argv)

    target = args.target.strip() or None
    if target and not re.fullmatch(r"tbm_[^/\s]+/rct_[0-9]{8}-[0-9]{4}", target):
        print(f"::error::replay 지목은 tbm_.../rct_... 형태여야 함: {target}")
        return 2
    skipped: list = []
    rp = None
    try:
        assert_sandbox(args.repo, args.remote)
        rp = find(args.repo, target, args.scan, skipped)
        rp.pr_state = lookup(rp.pull_request_url, os.environ.get(args.token_env) if args.token_env else None)
        if rp.pr_state in ("merged", "closed"):
            rp.expect_statuses = "review_rejected,cancelled"
        apply(args.repo, rp, remote=args.remote, branch=args.branch)
    except ReplayError as exc:
        print(render(None, skipped), end="")
        print(f"::error::{exc}")
        return 1
    summary = render(rp, skipped)
    print(summary, end="")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as fh:
            fh.write(summary)
    write_outputs(rp, args.github_output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
