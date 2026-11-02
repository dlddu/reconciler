#!/usr/bin/env python3
"""리뷰 스킬 빌드 test job의 replay 시나리오 — 이미 리뷰된 task를 점유 직전(`planned`)으로 되돌려 다시 판정시킨다.

**샌드박스 전용.** test job의 reconciler 체크아웃은 origin을 러너 로컬 bare 레포로 바꿔 둔다(README 「리뷰 스킬
MiniMax 파이프라인」). 이 스크립트는 그 원격이 로컬 경로가 아니면 아무것도 쓰지 않고 실패한다 — 운영 데이터에
되감기 커밋이 들어가면 같은 task를 실제 리뷰 워커가 다시 집기 때문이다.

운영 데이터에 `planned`가 늘 있지는 않다. 그래서 git 이력에서 최근 `review(<tbm>/<rct>): claim` 커밋을 찾아,
그 부모 커밋의 task 레코드(점유 직전 = planned)를 현재 파일에 되돌려 놓고 샌드박스 원격에 push한다. 그 위에서
러너 점유(claim_review_target.py)와 생성 스킬의 판정이 운영과 똑같이 돈다 — 스킬은 이것이 replay인지 모른다.

후보(최근 점유부터) — 공통:
  - 점유 직전 레코드가 `planned`이고 리뷰 전제(select_review_target.unready_reason)를 갖췄다
  - 그 레코드가 **현재 스키마**를 통과한다(스키마가 바뀐 옛 레코드는 건너뜀)
  - 모델이 꺼져 있지 않다(`checkPolicy.enabled: false`가 아님)
  - 그 task가 지금 `planned`·`reviewing`이 아니다(살아 있는 작업은 live 시나리오 몫)

모드(--mode) — 무엇을 시험하나:
  merged      (시나리오 replay) PR이 **지금 머지·종료된** 후보를 우선 고른다. 그 계획은 더 이상 실행할 수 없으므로
              승인하면 안 된다 — expect_statuses=review_rejected,cancelled. 최근 --max-lookups건 안에 그런 후보가
              없으면(또는 토큰이 없어 조회할 수 없으면) 가장 최근 후보를 기대 없이 쓰고 경고한다.
  ci-failure  (시나리오 replay-ci-failure) PR이 **지금 열린** 후보를 고르고, 그 PR의 head 커밋 위에 GitHub 대역 PR을
              시드로 세운다(--sandbox-root/seed.json: 브랜치 `<head>-2` + PR #90001, 제목·본문은 실제 PR 그대로).
              되돌린 레코드의 preparation(pullRequestUrl·branch)과 마지막 시도 안의 옛 PR 링크·번호·브랜치를 대역 PR로
              바꾼다. 워크플로가 대역을 합성 CI `failure`로 올리면 그 head의 CI는 실패로만 보인다(대역은 자기 PR head의
              실제 체크 런을 섞지 않는다) — CI가 실패한 준비물은 승인하면 안 된다: expect_statuses=review_rejected,cancelled.
              head 커밋·diff·base·실제 commit status(사람 승인 포함)는 실제 그대로라 CI만 다르다. 후보가 없으면 실패한다.

기대 지정(--expect): 모드가 정한 기대를 덮어쓴다(쉼표 구분, approved·review_rejected·cancelled 중). PR이 열려 있어 모드가 기대를
걸지 않는 건을 회귀 케이스로 지목할 때 쓴다 — 예: 계획의 diff 기대값(3파일)과 실제 PR diff(11파일)가 다른데 승인된 건을
`--target tbm_pocket-aide-e2e-mock-policy/rct_20261026-0001 --expect review_rejected`로 다시 판정시킨다.

PR 조회에는 `--token-env`의 읽기 토큰을 쓴다(러너 전용 — 에이전트 환경에서는 뺀다).

출력(GITHUB_OUTPUT): target(tbm_.../rct_...), model_id, task_id, mode, pull_request_url(스킬이 볼 PR), original_pr,
                     pr_state, expect_statuses, original_claim, original_verdict, replay_commit
종료 코드: 0 = 되감아 push함, 1 = 후보 없음/오류, 2 = 사용법 오류
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import select_review_target as srt  # noqa: E402

TASKS_DIR = "data/reconciliation-tasks"
MODELS_FILE = "data/to-be-models.json"
CLAIM_RE = re.compile(r"^review\((tbm_[^/\s)]+)/(rct_[0-9]{8}-[0-9]{4})\): claim$")
LIVE = {"planned", "reviewing"}
PR_RE = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")
MODES = ("merged", "ci-failure")
REJECT = "review_rejected,cancelled"
FINAL_STATUSES = ("approved", "review_rejected", "cancelled")
SANDBOX_PR_NUMBER = 90001  # 대역 PR 번호는 레포마다 90001부터 — 시드가 처음 만든다


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
    original_pr: str = ""
    pr_state: str = ""
    expect_statuses: str = ""
    mode: str = "merged"
    seed: dict | None = None
    expect_source: str = "모드"
    commit: str = ""
    notes: list = field(default_factory=list)


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


def eligible(repo: Path, target: str | None, scan: int, skipped: list):
    """공통 조건을 통과한 후보를 최근 점유부터: (claim sha, model_id, task_id, 점유 직전 레코드, 현재 레코드)."""
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
        yield sha, model_id, task_id, before, current


def pr_url_of(record: dict) -> str:
    return ((record.get("attempts") or [{}])[-1].get("preparation") or {}).get("pullRequestUrl") or ""


def make_replay(sha, model_id, task_id, before, current, mode) -> Replay:
    return Replay(model_id=model_id, task_id=task_id, record=copy.deepcopy(before), original_claim=sha,
                  original_verdict=verdict_of(current, len(before.get("attempts") or []) - 1),
                  pull_request_url=pr_url_of(before), original_pr=pr_url_of(before), mode=mode)


def find(repo: Path, target: str | None, scan: int, skipped: list, *, mode: str = "merged",
         lookup=None, token: str | None = None, max_lookups: int = 20) -> Replay:
    """모드에 맞는 후보 하나. lookup(url, token) → PR 정보 dict(state·head_sha·head_ref·base_ref·title·body) 또는 None."""
    first = None
    looked = 0
    for sha, model_id, task_id, before, current in eligible(repo, target, scan, skipped):
        key = f"{model_id}/{task_id}"
        first = first or (sha, model_id, task_id, before, current)
        url = pr_url_of(before)
        if not url:
            skipped.append((key, "직접 액션(PR 없음) — 이 모드가 시험할 PR이 없음"))
            continue
        if not (lookup and token):
            break  # 조회할 수 없다 — 아래에서 처리
        if looked >= max_lookups:
            skipped.append((key, f"PR 조회 {max_lookups}건 한도"))
            break
        looked += 1
        info = lookup(url, token)
        state = (info or {}).get("state", "")
        if mode == "merged" and state in ("merged", "closed"):
            rp = make_replay(sha, model_id, task_id, before, current, mode)
            rp.pr_state, rp.expect_statuses = state, REJECT
            return rp
        if mode == "ci-failure" and state == "open" and info.get("head_sha") and info.get("head_ref"):
            rp = make_replay(sha, model_id, task_id, before, current, mode)
            rp.pr_state, rp.expect_statuses = state, REJECT
            rehost(rp, info)
            return rp
        skipped.append((key, f"PR {state or '조회 실패'} — {mode} 모드 대상 아님"))

    if mode == "ci-failure":
        why = "읽기 토큰이 없어 PR을 조회할 수 없음" if not (lookup and token) else "지금 열린 PR을 가진 후보가 없음"
        raise ReplayError(f"replay-ci-failure 후보 없음 — {why}")
    if first is None:
        scope = f"지목 {target}" if target else f"최근 {scan}개 커밋"
        raise ReplayError(f"replay 후보 없음({scope}의 review claim 커밋 중 조건을 만족하는 것이 없음)")
    rp = make_replay(*first, mode)
    why = "읽기 토큰이 없어 PR 상태를 조회하지 못함" if not (lookup and token) else "머지·종료된 PR 건을 찾지 못함"
    rp.notes.append(f"{why} — 가장 최근 후보를 기대 없이 판정시킨다(머지된 PR 거부 경로는 이번에 시험하지 않음)")
    return rp


def rehost(rp: Replay, info: dict) -> None:
    """실제 PR의 head 커밋 위에 대역 PR을 세우고, 되돌린 레코드가 그 PR을 가리키게 한다(ci-failure)."""
    m = PR_RE.match(rp.original_pr)
    owner, name, number = m.group(1), m.group(2), m.group(3)
    full = f"{owner}/{name}"
    branch = f"{info['head_ref']}-2"  # 실제 PR과 같은 head 이름이면 실제 GitHub처럼 중복 PR로 거절된다
    new_url = f"https://github.com/{full}/pull/{SANDBOX_PR_NUMBER}"
    rp.seed = {"branches": [{"repository": full, "name": branch, "sha": info["head_sha"]}],
               "pulls": [{"repository": full, "head": branch, "base": info.get("base_ref") or "main",
                          "title": info.get("title") or f"PR #{number}", "body": info.get("body") or "",
                          "number": SANDBOX_PR_NUMBER}]}
    last = rp.record["attempts"][-1]
    text = json.dumps(last, ensure_ascii=False)
    text = text.replace(rp.original_pr, new_url)
    text = re.sub(rf"(?<![\w/])#{number}\b", f"#{SANDBOX_PR_NUMBER}", text)
    old_branch = (last.get("preparation") or {}).get("branch") or info["head_ref"]
    text = re.sub(rf"(?<![\w/.-]){re.escape(old_branch)}(?![\w/.-])", lambda _m: branch, text)
    last = json.loads(text)
    last.setdefault("preparation", {})
    last["preparation"]["pullRequestUrl"] = new_url
    last["preparation"]["branch"] = branch
    rp.record["attempts"][-1] = last
    rp.pull_request_url = new_url


def pr_info(url: str, token: str | None) -> dict | None:
    """실제 PR 조회 → {state: open|closed|merged, head_sha, head_ref, base_ref, title, body}. 실패면 None."""
    m = PR_RE.match(url or "")
    if not (m and token):
        return None
    req = urllib.request.Request(f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/pulls/{m.group(3)}",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "reconciler-replay"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
    except Exception as exc:  # noqa: BLE001 — 조회 실패는 그 후보를 건너뛰는 것으로 처리
        print(f"::warning::PR 조회 실패({url}): {type(exc).__name__}")
        return None
    state = "merged" if (data.get("merged") or data.get("merged_at")) else str(data.get("state") or "")
    return {"state": state, "head_sha": (data.get("head") or {}).get("sha"), "head_ref": (data.get("head") or {}).get("ref"),
            "base_ref": (data.get("base") or {}).get("ref"), "title": data.get("title"), "body": data.get("body")}


def apply(repo: Path, rp: Replay, *, remote: str, branch: str, sandbox_root: Path | None = None) -> None:
    rel = f"{TASKS_DIR}/{rp.model_id}.json"
    path = repo / rel
    errs = list(make_validator(repo).iter_errors(rp.record))
    if errs:
        raise ReplayError(f"되돌린 레코드가 스키마를 통과하지 않음 — {errs[0].message[:200]}")
    if rp.seed is not None:
        if sandbox_root is None:
            raise ReplayError("ci-failure 모드는 --sandbox-root가 필요하다(대역 시드를 둘 곳)")
        sandbox_root.mkdir(parents=True, exist_ok=True)
        seed_path = sandbox_root / "seed.json"
        seed = json.loads(seed_path.read_text(encoding="utf-8")) if seed_path.exists() else {}
        for k, v in rp.seed.items():
            seed.setdefault(k, []).extend(v)
        seed_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
        "mode": rp.mode,
        "pull_request_url": rp.pull_request_url,
        "original_pr": rp.original_pr,
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


def render(rp: Replay | None, skipped: list, mode: str) -> str:
    out = [f"#### Replay fixture (sandbox · {mode})"]
    if rp:
        pr = rp.original_pr or "직접 액션(PR 없음)"
        out.append(f"- 되감음: `{rp.model_id}/{rp.task_id}` ← `{rp.original_claim[:7]}^`의 planned 레코드 · {pr}"
                   + (f" (지금 {rp.pr_state})" if rp.pr_state else ""))
        if rp.seed:
            out.append(f"- 대역 PR: {rp.pull_request_url} — 같은 head 커밋, 합성 CI 실패(실제 CI는 숨김)")
        out.append(f"- 원래 판정: {rp.original_verdict}")
        out.append(f"- 기대: {rp.expect_statuses or '제한 없음(종료 상태 중 하나)'}"
                   + (" (워크플로 입력으로 지정)" if rp.expect_source == "지정" else ""))
        out.extend(f"- ⚠️ {n}" for n in rp.notes)
    for key, why in skipped[:10]:
        out.append(f"- 건너뜀 · {key}: {why}")
    if len(skipped) > 10:
        out.append(f"- 건너뜀 {len(skipped) - 10}건 더")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None, lookup=pr_info) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--target", default="", help="tbm_.../rct_... — 비우면 최근 점유부터 자동 선택")
    p.add_argument("--mode", choices=MODES, default="merged")
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default="main")
    p.add_argument("--scan", type=int, default=400, help="review claim 커밋을 찾을 최근 커밋 수")
    p.add_argument("--max-lookups", type=int, default=20, help="PR 상태를 조회할 후보 수 한도")
    p.add_argument("--token-env", default="", help="PR 조회용 읽기 토큰이 든 환경 변수 이름")
    p.add_argument("--sandbox-root", type=Path, help="GitHub 대역 루트(ci-failure 모드가 seed.json을 둔다)")
    p.add_argument("--expect", default="", help="기대 status 지정(쉼표 구분: approved·review_rejected·cancelled) — 모드의 기대를 덮어쓴다")
    p.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    p.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = p.parse_args(argv)

    target = args.target.strip() or None
    if target and not re.fullmatch(r"tbm_[^/\s]+/rct_[0-9]{8}-[0-9]{4}", target):
        print(f"::error::replay 지목은 tbm_.../rct_... 형태여야 함: {target}")
        return 2
    expect = [x.strip() for x in args.expect.split(",") if x.strip()]
    if bad := [x for x in expect if x not in FINAL_STATUSES]:
        print(f"::error::--expect는 {', '.join(FINAL_STATUSES)} 중에서 고른다: {', '.join(bad)}")
        return 2
    token = os.environ.get(args.token_env) if args.token_env else None
    skipped: list = []
    rp = None
    try:
        assert_sandbox(args.repo, args.remote)
        rp = find(args.repo, target, args.scan, skipped, mode=args.mode, lookup=lookup, token=token,
                  max_lookups=args.max_lookups)
        if expect:
            rp.expect_statuses = ",".join(expect)
            rp.expect_source = "지정"
            rp.notes = [n for n in rp.notes if "기대 없이" not in n]
        apply(args.repo, rp, remote=args.remote, branch=args.branch, sandbox_root=args.sandbox_root)
    except ReplayError as exc:
        print(render(None, skipped, args.mode), end="")
        print(f"::error::{exc}")
        return 1
    summary = render(rp, skipped, args.mode)
    print(summary, end="")
    for n in rp.notes:
        print(f"::warning::{n}")
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as fh:
            fh.write(summary)
    write_outputs(rp, args.github_output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
