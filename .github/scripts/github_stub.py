#!/usr/bin/env python3
"""GitHub 대역(test double) — 스킬 빌드 test에서 github.com · api.github.com · raw.githubusercontent.com을 대신 받는다.

스킬은 평소처럼 GitHub에 clone·push·PR 생성·머지·status 조회를 한다. 러너가 이 세 호스트를 127.0.0.1로 돌리고
(/etc/hosts) 이 서버의 인증서를 시스템 CA로 믿게 해 두었으므로(github_sandbox.py), 그 요청이 전부 여기로 온다.
스킬에는 드라이런 분기가 없고 자기가 test 중인지 모른다(README 「드라이런은 없다」).

  github.com                git smart HTTP(clone·fetch·push) — 러너가 미러링해 둔 로컬 bare 레포(`<root>/git/<owner>/<repo>.git`)
                            를 `git http-backend`로 서비스한다. push는 그 bare 레포에만 쌓인다. git 밖 GET(릴리스 내려받기 등
                            공개 자료)은 자격 증명 없이 실제 github.com에 물어 그대로 돌려준다.
  api.github.com            REST·GraphQL. 쓰기(PR 생성·수정·머지, 코멘트, status, 브랜치 삭제)는 전부 이 서버 메모리와 bare 레포에서
                            끝난다. 이 서버가 모델링하지 않는 **읽기(GET)**만, 설정돼 있으면 러너가 준 읽기 전용 토큰으로 실제 GitHub에
                            물어 그대로 돌려준다(read passthrough). 쓰기는 어떤 경우에도 실제 GitHub로 나가지 않는다.
  raw.githubusercontent.com bare 레포의 파일 내용.

인증: 이 서버가 발급한 토큰만 인정한다. 토큰은 관리 API(`POST /_sandbox/tokens`)로 발급되며, MCP 프록시
(mcp_oidc_proxy.py 샌드박스 모드)가 스킬의 `github_app_installation_token` 호출을 이것으로 바꿔 준다. 실제 서버처럼
레포 범위(`repositories`)와 권한(`permissions`)을 지킨다 — 범위 밖 레포는 404, 권한 부족은 403.

가짜 CI: 대역 PR은 진짜 GitHub가 모르니 Actions CI가 돌지 않는다. 그래서 대역이 만든 PR의 head 커밋마다
**합성 체크 런**을 붙인다 — 이름은 실제 ruleset의 필수 체크(예: `ci-success`), 없으면 `ci`. 사람 승인용 status
(`--human-status-prefixes`, 기본 `review/`)는 절대 합성하지 않는다(승인 게이트가 무력해진다). 출력·앱 이름에 합성임을
밝히고 기록(`op: ci.synthetic`, 결론 포함)에 남긴다. 실제 PR의 실제 head에는 붙이지 않는다(진짜 CI가 읽기 중계로 보인다).
다만 실제 PR에 **대역에서 새 head를 push**하면(예: 실행 단계가 실행 지침대로 rebase해 PR 브랜치를 갱신) 그 head에는 진짜 CI가
돌지 않으므로 대역 PR과 같이 합성 CI를 붙인다 — 실제 운영이라면 그 head에 진짜 CI가 돌았을 것이다.
결론은 `--synthetic-ci`로 고른다: success(기본) · failure(매 head 실패 — 고칠 수 없는 CI 실패) · fail-first(PR의 첫
head만 실패, 이후 push는 성공 — 고칠 수 있는 CI 실패) · off(붙이지 않음, `--no-synthetic-ci`와 같다).
실패 런만은 합성임을 드러내지 않는다 — 출력·앱이 실제 Actions 실패처럼 보인다. "합성이라 무시해도 된다"는 판단을
막아야 실패 경로(범위 안에서 고치거나 lock을 푼다)를 시험할 수 있다. 합성 여부는 기록(`ci.synthetic`)에만 남는다.

모든 요청은 JSONL 기록(`--log`)에 남는다. 결과 점검기는 이 기록으로 "PR을 몇 개 열었나 · 머지했나 · 기본 브랜치에
직접 push했나 · status를 썼나"를 판정한다. 이 서버가 모르는 요청은 `op: unsupported`로 남기고 501을 돌려준다
(대역을 넓혀 가는 단서).

관리 API(평문 HTTP, 127.0.0.1 전용): POST /_sandbox/tokens · POST /_sandbox/statuses · GET /_sandbox/state ·
GET /_sandbox/health

시드(`--seed FILE`, JSON): 시험 무대가 "스킬이 오기 전에 이미 있던" 브랜치·PR·commit status를 심는다(실행 빌드 픽스처,
리뷰 빌드 replay-ci-failure).
`{"branches": [{"repository": "o/r", "name": "br", "sha": …}],
  "pulls": [{"repository": "o/r", "head": "br", "base": "main", "title": …, "body": …, "number": 90001}],
  "statuses": [{"repository": "o/r", "sha": …, "state": "success", "context": "review/manual-approval"}]}`
시드는 기록에 `seed.branch`·`seed.pull`·`seed.status`(write: false)로 남는다 — 스킬의 쓰기로 세지 않는다.
대역 PR의 head(합성 CI가 붙은 커밋)에서는 같은 커밋의 실제 체크 런을 중계하지 않는다 — 실제 커밋 위에 세운 대역 PR에서도
CI 결과는 합성 결과 하나다(commit status는 그대로 중계 — 사람 승인 status는 실제 그대로 보인다).
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import gzip
import http.client
import itertools
import json
import os
import re
import secrets
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API_HOST = "api.github.com"
GIT_HOST = "github.com"
RAW_HOST = "raw.githubusercontent.com"
BOT_LOGIN = "reconciler-bot[bot]"
READ_METHODS = ("GET", "HEAD")
# PR 번호는 실제 레포 번호와 겹치지 않게 큰 수에서 시작한다(실제 PR은 read passthrough로 보인다).
DEFAULT_PR_BASE = 90001
NULL_SHA = "0" * 40
SYNTHETIC_APP_SLUG = "reconciler-sandbox"
SYNTHETIC_CI_MODES = ("success", "failure", "fail-first", "off")
# 핸들러 → 기록의 op 이름(거절된 요청도 같은 이름으로 남긴다).
HANDLER_OPS = {"pulls_create": "pulls.create", "pulls_update": "pulls.update", "pulls_merge": "pulls.merge",
               "comments_create": "issues.comments.create", "labels_add": "issues.labels.add",
               "issue_update": "issues.update", "status_create": "statuses.create", "ref_create": "refs.create",
               "ref_update": "refs.update", "ref_delete": "refs.delete", "pulls_sub_write": "pulls.reviews.create",
               "pulls_get": "pulls.get", "pulls_list": "pulls.list", "repo_get": "repos.get",
               "contents": "contents.get", "statuses_list": "statuses.list", "status_combined": "statuses.combined",
               "check_runs": "checks.list", "check_run_get": "checks.get"}
# 기록에서 "쓰기"로 세는 작업(거절된 시도 포함 — detail.refused). 점검기는 이것으로 판정한다.
WRITE_OPS = {"pulls.create", "pulls.update", "pulls.close", "pulls.merge", "issues.update", "issues.comments.create",
             "issues.labels.add", "statuses.create", "refs.create", "refs.update", "refs.delete", "git.push",
             "pulls.reviews.create", "pulls.comments.create", "pulls.requested_reviewers.create"}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ApiError(Exception):
    def __init__(self, status: int, message: str, op: str | None = None, **extra):
        super().__init__(message)
        self.status, self.message, self.op, self.extra = status, message, op, extra


# ── 레포 · git ──────────────────────────────────────────────────────────────────────────────

class Repos:
    """`<root>/git/<owner>/<repo>.git` bare 레포들. 이름 비교는 GitHub처럼 대소문자를 가리지 않는다."""

    def __init__(self, root: Path):
        self.root = root / "git"
        self.lock = threading.RLock()

    def path(self, full: str) -> Path | None:
        owner, _, name = full.partition("/")
        if not owner or not name:
            return None
        name = name[:-4] if name.endswith(".git") else name
        for cand in (self.root / owner / f"{name}.git", self.root / owner / name):
            if cand.is_dir():
                return cand
        if self.root.is_dir():  # 대소문자 무시
            for o in self.root.iterdir():
                if o.name.lower() != owner.lower():
                    continue
                for r in o.iterdir():
                    if r.name.lower() in (f"{name.lower()}.git", name.lower()):
                        return r
        return None

    def canonical(self, full: str) -> str | None:
        p = self.path(full)
        if p is None:
            return None
        return f"{p.parent.name}/{p.name[:-4] if p.name.endswith('.git') else p.name}"

    def all(self) -> list[str]:
        if not self.root.is_dir():
            return []
        out = []
        for o in sorted(self.root.iterdir()):
            if o.is_dir():
                out += [f"{o.name}/{r.name[:-4] if r.name.endswith('.git') else r.name}"
                        for r in sorted(o.iterdir()) if r.is_dir() or r.is_symlink()]
        return out

    def git(self, full: str, *args: str, check: bool = True, input: bytes | None = None) -> str:
        p = self.path(full)
        if p is None:
            raise ApiError(404, "Not Found")
        r = subprocess.run(["git", "--git-dir", str(p), *args], capture_output=True, input=input)
        if check and r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
        return r.stdout.decode("utf-8", "replace").strip() if r.returncode == 0 else ""

    def rev(self, full: str, ref: str) -> str | None:
        out = self.git(full, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
        return out or None

    def branch_sha(self, full: str, branch: str) -> str | None:
        return self.rev(full, f"refs/heads/{branch}")

    def default_branch(self, full: str) -> str:
        head = self.git(full, "symbolic-ref", "--short", "HEAD", check=False)
        return head or "main"

    def branches(self, full: str) -> list[tuple[str, str]]:
        out = self.git(full, "for-each-ref", "--format=%(refname:short)%09%(objectname)", "refs/heads")
        return [tuple(line.split("\t", 1)) for line in out.splitlines() if "\t" in line]  # type: ignore[misc]

    def refs(self, full: str) -> dict[str, str]:
        out = self.git(full, "for-each-ref", "--format=%(refname)%09%(objectname)", "refs/heads", "refs/tags")
        return dict(line.split("\t", 1) for line in out.splitlines() if "\t" in line)

    def is_ancestor(self, full: str, old: str, new: str) -> bool:
        p = self.path(full)
        return subprocess.run(["git", "--git-dir", str(p), "merge-base", "--is-ancestor", old, new],
                              capture_output=True).returncode == 0

    def merge_tree(self, full: str, base: str, head: str) -> str | None:
        """충돌 없이 합쳐지면 결과 tree, 충돌이면 None (git merge-tree --write-tree, git ≥ 2.38)."""
        p = self.path(full)
        r = subprocess.run(["git", "--git-dir", str(p), "merge-tree", "--write-tree", base, head],
                           capture_output=True, text=True)
        return r.stdout.split()[0] if r.returncode == 0 and r.stdout.strip() else None


# ── 상태 ────────────────────────────────────────────────────────────────────────────────────

class State:
    def __init__(self, repos: Repos, log_path: Path | None, pr_base: int = DEFAULT_PR_BASE,
                 rules: dict | None = None, synthetic_ci: bool | str = True,
                 human_status_prefixes: tuple[str, ...] = ("review/",)):
        self.repos = repos
        if synthetic_ci is True or synthetic_ci is False:
            synthetic_ci = "success" if synthetic_ci else "off"
        if synthetic_ci not in SYNTHETIC_CI_MODES:
            raise ValueError(f"synthetic_ci는 {SYNTHETIC_CI_MODES} 중 하나: {synthetic_ci!r}")
        self.synthetic_ci = synthetic_ci
        self.ci_heads: dict[tuple[str, int], int] = {}  # (repo, PR 번호) → 합성 CI를 붙인 head 수(fail-first용)
        self.human_status_prefixes = tuple(human_status_prefixes)
        self.ci_runs: dict[tuple[str, str], list[dict]] = {}  # (repo, sha) → 합성 체크 런
        self.lock = threading.RLock()
        self.tokens: dict[str, dict] = {}
        self.prs: dict[str, dict[int, dict]] = {}   # repo → number → PR(이 서버가 만든 것 + 손댄 실제 PR)
        self.comments: dict[tuple[str, int], list] = {}
        self.statuses: dict[tuple[str, str], list] = {}
        self.pr_seq: dict[str, itertools.count] = {}
        self.pr_base = pr_base
        self.rules = rules or {}  # "owner/repo" → {"branch": {"required_status_checks": [...], ...}}
        self.ids = itertools.count(1)
        self.log_path = log_path
        self.seq = itertools.count(1)
        self.log_lock = threading.Lock()

    # 기록
    def record(self, **entry) -> None:
        entry = {"seq": next(self.seq), "ts": now_iso(), **{k: v for k, v in entry.items() if v is not None}}
        if self.log_path is None:
            return
        with self.log_lock, self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # 토큰
    def mint(self, repositories, permissions) -> dict:
        repos = None
        if repositories:
            if not isinstance(repositories, list) or not all(isinstance(r, str) for r in repositories):
                raise ApiError(422, "repositories must be a list of repository names")
            repos = sorted({r.split("/")[-1].lower() for r in repositories})
        perms = None
        if permissions:
            if not isinstance(permissions, dict) or any(v not in ("read", "write", "admin") for v in permissions.values()):
                raise ApiError(422, "permissions must map permission names to read|write")
            perms = dict(permissions)
        token = "ghs_" + secrets.token_urlsafe(27).replace("-", "a").replace("_", "b")[:36]
        tid = f"t{len(self.tokens) + 1}"
        expires = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).replace(microsecond=0)
        info = {"id": tid, "repositories": repos, "permissions": perms, "expires_at": expires.isoformat().replace("+00:00", "Z")}
        with self.lock:
            self.tokens[token] = info
        self.record(source="admin", op="token.mint", token=tid, detail={"repositories": repos, "permissions": perms})
        return {"token": token, **{k: info[k] for k in ("expires_at", "repositories", "permissions")}}

    def authorize(self, token: dict | None, repo: str | None, perm: str, write: bool) -> None:
        if token is None:
            raise ApiError(401, "Requires authentication")
        if repo is not None:
            name = repo.split("/")[-1].lower()
            if token["repositories"] is not None and name not in token["repositories"]:
                raise ApiError(404, "Not Found")
        perms = token["permissions"]
        if perms is None or perm == "metadata" and not write:
            return
        level = perms.get(perm)
        if perm == "issues" and level is None:  # PR 코멘트는 pull_requests 권한으로도 된다
            level = perms.get("pull_requests")
        if level is None or (write and level == "read"):
            raise ApiError(403, "Resource not accessible by integration")

    # PR
    def next_pr_number(self, repo: str) -> int:
        with self.lock:
            if repo not in self.pr_seq:
                self.pr_seq[repo] = itertools.count(self.pr_base)
            return next(self.pr_seq[repo])

    def get_pr(self, repo: str, number: int) -> dict | None:
        return self.prs.get(repo, {}).get(number)

    def required_contexts(self, repo: str, branch: str) -> list[str]:
        return list((self.rules.get(repo.lower(), {}).get(branch) or {}).get("required_status_checks") or [])

    def is_human_context(self, context: str) -> bool:
        return any(context.startswith(p) for p in self.human_status_prefixes)

    def ensure_synthetic_ci(self, repo: str, sha: str, base: str, pr_number: int) -> None:
        """대역 PR의 head 커밋에 합성 CI를 한 번 붙인다(결론은 synthetic_ci 모드). 사람 승인 context는 빼고,
        필수 체크가 없으면 `ci`."""
        if self.synthetic_ci == "off" or not sha:
            return
        with self.lock:
            if (repo, sha) in self.ci_runs:
                return
            nth = self.ci_heads.get((repo, pr_number), 0)
            self.ci_heads[(repo, pr_number)] = nth + 1
            failed = self.synthetic_ci == "failure" or (self.synthetic_ci == "fail-first" and nth == 0)
            conclusion = "failure" if failed else "success"
            names = [c for c in self.required_contexts(repo, base) if not self.is_human_context(c)] or ["ci"]
            ts = now_iso()
            if failed:  # 실제 Actions 실패와 구별되지 않게 — 합성임은 기록에만 남긴다
                app = {"slug": "github-actions", "name": "GitHub Actions"}
                output = {"title": f"{{name}} failed", "summary": "Process completed with exit code 1.",
                          "text": None, "annotations_count": 1}
                marker = {}
            else:
                app = {"slug": SYNTHETIC_APP_SLUG, "name": "reconciler sandbox (synthetic CI)"}
                output = {"title": "sandbox: synthetic success — CI was not run",
                          "summary": "이 PR은 GitHub 샌드박스(대역)에만 있어 실제 CI가 돌지 않는다. 대역이 붙인 합성 성공 결과다.",
                          "text": None, "annotations_count": 0}
                marker = {"external_id": "reconciler-sandbox-synthetic", "synthetic": True}
            runs = []
            for name in names:
                rid = next(self.ids)
                out = {**output, "title": output["title"].format(name=name)}
                runs.append({"id": rid, "name": name, "head_sha": sha, "status": "completed",
                             "conclusion": conclusion, "started_at": ts, "completed_at": ts,
                             "html_url": f"https://github.com/{repo}/runs/{rid}",
                             "details_url": f"https://github.com/{repo}/pull/{pr_number}/checks",
                             "app": app, "output": out, "check_suite": {"id": next(self.ids)}, **marker})
            self.ci_runs[(repo, sha)] = runs
        self.record(source="stub", op="ci.synthetic", repo=repo, write=False,
                    detail={"sha": sha, "number": pr_number, "contexts": names, "conclusion": conclusion})

    def synthetic_runs(self, repo: str, sha: str) -> list[dict]:
        return list(self.ci_runs.get((repo, sha), []))

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "tokens": [{k: v for k, v in t.items()} for t in self.tokens.values()],
                "pulls": {repo: [pr_public(self, repo, pr) for pr in prs.values()] for repo, prs in self.prs.items()},
                "statuses": [{"repository": r, "sha": s, "statuses": v} for (r, s), v in self.statuses.items()],
                "comments": [{"repository": r, "number": n, "comments": v} for (r, n), v in self.comments.items()],
                "refs": {repo: self.repos.refs(repo) for repo in self.repos.all()},
            }


def repo_min(state: State, full: str) -> dict:
    owner, name = full.split("/", 1)
    return {"id": abs(hash(full)) % 10**9, "node_id": node_repo(full), "name": name, "full_name": full,
            "private": True, "owner": {"login": owner, "type": "User"},
            "html_url": f"https://github.com/{full}", "clone_url": f"https://github.com/{full}.git",
            "url": f"https://api.github.com/repos/{full}", "default_branch": state.repos.default_branch(full),
            "fork": False, "archived": False, "visibility": "private",
            "permissions": {"admin": False, "maintain": False, "push": True, "triage": True, "pull": True},
            "allow_merge_commit": True, "allow_squash_merge": True, "allow_rebase_merge": True,
            "delete_branch_on_merge": False, "has_issues": True}


def node_repo(full: str) -> str:
    return "R_sbx_" + base64.urlsafe_b64encode(full.encode()).decode().rstrip("=")


def node_pr(full: str, number: int) -> str:
    return "PR_sbx_" + base64.urlsafe_b64encode(f"{full}#{number}".encode()).decode().rstrip("=")


def parse_node(node_id: str) -> tuple[str, str]:
    for prefix, kind in (("PR_sbx_", "pr"), ("R_sbx_", "repo")):
        if node_id.startswith(prefix):
            raw = node_id[len(prefix):]
            return kind, base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
    raise ApiError(404, f"Could not resolve to a node with the global id of '{node_id}'")


def refresh_pr(state: State, repo: str, pr: dict) -> None:
    """열린 PR의 head는 브랜치를 따라간다(push하면 head sha가 바뀐다). mergeable은 지금 계산한다."""
    if pr["state"] == "open":
        sha = state.repos.branch_sha(repo, pr["head"]["ref"])
        if sha:
            pr["head"]["sha"] = sha
        base_sha = state.repos.branch_sha(repo, pr["base"]["ref"])
        if base_sha:
            pr["base"]["sha"] = base_sha
        tree = state.repos.merge_tree(repo, pr["base"]["sha"], pr["head"]["sha"])
        pr["mergeable"] = tree is not None
        pr["mergeable_state"] = "clean" if tree is not None else "dirty"
        # 실제 PR의 실제 head에는 진짜 CI가 있다 — 대역 PR과, 실제 PR에 대역에서 push한 새 head에만 붙인다.
        if pr.get("origin") == "sandbox" or pr["head"]["sha"] != pr.get("real_head_sha", pr["head"]["sha"]):
            state.ensure_synthetic_ci(repo, pr["head"]["sha"], pr["base"]["ref"], pr["number"])


def pr_public(state: State, repo: str, pr: dict) -> dict:
    refresh_pr(state, repo, pr)
    n = pr["number"]
    out = dict(pr)
    out.update({
        "url": f"https://api.github.com/repos/{repo}/pulls/{n}", "id": n, "node_id": node_pr(repo, n),
        "html_url": f"https://github.com/{repo}/pull/{n}",
        "diff_url": f"https://github.com/{repo}/pull/{n}.diff",
        "issue_url": f"https://api.github.com/repos/{repo}/issues/{n}",
        "comments_url": f"https://api.github.com/repos/{repo}/issues/{n}/comments",
        "statuses_url": f"https://api.github.com/repos/{repo}/statuses/{pr['head']['sha']}",
    })
    for side in ("head", "base"):
        out[side] = dict(pr[side], label=f"{repo.split('/')[0]}:{pr[side]['ref']}", repo=repo_min(state, repo),
                         user={"login": repo.split("/")[0]})
    try:
        stats = state.repos.git(repo, "diff", "--shortstat", f"{pr['base']['sha']}...{pr['head']['sha']}", check=False)
        files = int(m.group(1)) if (m := re.search(r"(\d+) file", stats)) else 0
        adds = int(m.group(1)) if (m := re.search(r"(\d+) insertion", stats)) else 0
        dels = int(m.group(1)) if (m := re.search(r"(\d+) deletion", stats)) else 0
        commits = int(state.repos.git(repo, "rev-list", "--count", f"{pr['base']['sha']}..{pr['head']['sha']}",
                                      check=False) or 0)
        out.update(changed_files=files, additions=adds, deletions=dels, commits=commits)
    except (ApiError, RuntimeError, ValueError):
        pass
    return out


# ── 실제 GitHub 읽기 중계 ─────────────────────────────────────────────────────────────────────

class Passthrough:
    """모델링하지 않은 GET만 실제 api.github.com으로 보낸다. /etc/hosts가 127.0.0.1로 바뀌기 전에 실제 주소를
    풀어 두고(시작 시), 그 주소로 직접 연결하면서 SNI·인증서 검증은 api.github.com으로 한다."""

    def __init__(self, token: str, host: str = API_HOST, timeout: float = 30.0, addresses: list[str] | None = None):
        self.token, self.host, self.timeout = token, host, timeout
        self.addresses = addresses or sorted({a[4][0] for a in socket.getaddrinfo(host, 443, socket.AF_INET,
                                                                                  socket.SOCK_STREAM)})
        self.ctx = ssl.create_default_context()

    def connect(self, addr: str) -> http.client.HTTPConnection:
        raw = socket.create_connection((addr, 443), timeout=self.timeout)
        conn = http.client.HTTPConnection(self.host, timeout=self.timeout)
        conn.sock = self.ctx.wrap_socket(raw, server_hostname=self.host)
        return conn

    def request(self, method: str, path_qs: str, body: bytes | None, headers: dict) -> tuple[int, dict, bytes]:
        assert method in ("GET", "POST"), "passthrough는 읽기 전용이다"
        last: Exception | None = None
        for addr in self.addresses:
            try:
                conn = self.connect(addr)
                auth = {"Authorization": f"Bearer {self.token}"} if self.token else {}  # 공개 웹은 자격 증명 없이
                conn.request(method, path_qs, body=body, headers={
                    "Host": self.host, "User-Agent": "reconciler-sandbox", "X-GitHub-Api-Version": "2022-11-28",
                    **auth, **headers})
                resp = conn.getresponse()
                data = resp.read()
                kept = {k: v for k, v in resp.getheaders() if k.lower() in ("content-type", "link", "etag", "location")}
                conn.close()
                return resp.status, kept, data
            except OSError as exc:
                last = exc
        raise ApiError(502, f"passthrough failed: {last}")

    def get(self, path_qs: str, accept: str | None = None) -> tuple[int, dict, bytes]:
        return self.request("GET", path_qs, None, {"Accept": accept or "application/vnd.github+json"})

    def graphql(self, query: str, variables: dict | None) -> dict:
        """GraphQL **질의**만(호출하는 쪽이 mutation이 아님을 확인한다)."""
        if MUTATION.search(query):
            raise ApiError(400, "mutation is never passed through")
        _, _, data = self.request("POST", "/graphql", json.dumps({"query": query, "variables": variables or {}}).encode(),
                                  {"Content-Type": "application/json"})
        return json.loads(data or b"{}")


# ── REST ────────────────────────────────────────────────────────────────────────────────────

class Api:
    """api.github.com 라우팅. 각 핸들러는 (status, json body, op, repo, detail)을 돌려준다."""

    def __init__(self, state: State, passthrough: Passthrough | None):
        self.s, self.pt = state, passthrough
        R = r"(?P<owner>[^/]+)/(?P<repo>[^/]+)"
        routes = [
            ("GET", r"/installation/repositories", self.installation_repos),
            ("GET", r"/rate_limit", self.rate_limit),
            ("GET", rf"/repos/{R}", self.repo_get),
            ("GET", rf"/repos/{R}/branches", self.branches),
            ("GET", rf"/repos/{R}/branches/(?P<branch>.+)", self.branch_get),
            ("GET", rf"/repos/{R}/git/(?:ref|refs)/heads/(?P<branch>.+)", self.ref_get),
            ("DELETE", rf"/repos/{R}/git/refs/heads/(?P<branch>.+)", self.ref_delete),
            ("PATCH", rf"/repos/{R}/git/refs/heads/(?P<branch>.+)", self.ref_update),
            ("POST", rf"/repos/{R}/git/refs", self.ref_create),
            ("GET", rf"/repos/{R}/commits/(?P<ref>[^/]+)/statuses", self.statuses_list),
            ("GET", rf"/repos/{R}/commits/(?P<ref>[^/]+)/status", self.status_combined),
            ("GET", rf"/repos/{R}/commits/(?P<ref>[^/]+)/check-runs", self.check_runs),
            ("GET", rf"/repos/{R}/commits/(?P<ref>[^/]+)/check-suites", self.check_suites),
            ("GET", rf"/repos/{R}/check-runs/(?P<run_id>\d+)", self.check_run_get),
            ("GET", rf"/repos/{R}/commits/(?P<ref>[^/]+)", self.commit_get),
            ("GET", rf"/repos/{R}/commits", self.commits_list),
            ("GET", rf"/repos/{R}/git/commits/(?P<sha>[0-9a-fA-F]{{40}})", self.git_commit_get),
            ("POST", rf"/repos/{R}/statuses/(?P<sha>[0-9a-fA-F]{{40}})", self.status_create),
            ("GET", rf"/repos/{R}/contents/?(?P<path>.*)", self.contents),
            ("GET", rf"/repos/{R}/compare/(?P<spec>.+)", self.compare),
            ("GET", rf"/repos/{R}/pulls", self.pulls_list),
            ("POST", rf"/repos/{R}/pulls", self.pulls_create),
            ("GET", rf"/repos/{R}/pulls/(?P<number>\d+)", self.pulls_get),
            ("PATCH", rf"/repos/{R}/pulls/(?P<number>\d+)", self.pulls_update),
            ("GET", rf"/repos/{R}/pulls/(?P<number>\d+)/files", self.pulls_files),
            ("GET", rf"/repos/{R}/pulls/(?P<number>\d+)/commits", self.pulls_commits),
            ("GET", rf"/repos/{R}/pulls/(?P<number>\d+)/merge", self.pulls_merged),
            ("PUT", rf"/repos/{R}/pulls/(?P<number>\d+)/merge", self.pulls_merge),
            ("GET", rf"/repos/{R}/pulls/(?P<number>\d+)/(?P<sub>reviews|comments|requested_reviewers)", self.pulls_sub),
            ("GET", rf"/repos/{R}/issues/(?P<number>\d+)/comments", self.comments_list),
            ("POST", rf"/repos/{R}/issues/(?P<number>\d+)/comments", self.comments_create),
            ("POST", rf"/repos/{R}/issues/(?P<number>\d+)/labels", self.labels_add),
            ("PATCH", rf"/repos/{R}/issues/(?P<number>\d+)", self.issue_update),
            ("POST", rf"/repos/{R}/pulls/(?P<number>\d+)/(?P<sub>reviews|requested_reviewers|comments)", self.pulls_sub_write),
        ]
        self.routes = [(m, re.compile(p + r"/?$"), h) for m, p, h in routes]

    # 공용
    def repo(self, kw) -> str:
        full = self.s.repos.canonical(f"{kw['owner']}/{kw['repo']}")
        if full is None:
            raise ApiError(404, "Not Found")
        return full

    def pr_or_real(self, repo: str, number: int) -> dict:
        """이 서버가 아는 PR, 아니면 실제 PR을 읽어 와 덮어쓰기 대상으로 등록한다(머지·닫기·코멘트용)."""
        pr = self.s.get_pr(repo, number)
        if pr is not None:
            return pr
        if self.pt is None:
            raise ApiError(404, "Not Found")
        status, _, body = self.pt.get(f"/repos/{repo}/pulls/{number}")
        if status != 200:
            raise ApiError(404, "Not Found")
        real = json.loads(body)
        pr = {"number": number, "title": real.get("title"), "body": real.get("body"), "state": real.get("state"),
              "draft": real.get("draft", False), "merged": real.get("merged", False),
              "merged_at": real.get("merged_at"), "closed_at": real.get("closed_at"),
              "merge_commit_sha": real.get("merge_commit_sha"), "created_at": real.get("created_at"),
              "updated_at": real.get("updated_at"), "user": real.get("user"), "labels": real.get("labels") or [],
              "head": {"ref": real["head"]["ref"], "sha": real["head"]["sha"]},
              "base": {"ref": real["base"]["ref"], "sha": real["base"]["sha"]},
              "origin": "real", "real_head_sha": real["head"]["sha"]}
        # 실제 PR head가 미러의 브랜치에 없으면(삭제됨) refs/pull/N/head를 쓴다.
        if not self.s.repos.branch_sha(repo, pr["head"]["ref"]):
            sha = self.s.repos.rev(repo, f"refs/pull/{number}/head")
            if sha and pr["state"] == "open":
                self.s.repos.git(repo, "update-ref", f"refs/heads/{pr['head']['ref']}", sha)
        with self.s.lock:
            self.s.prs.setdefault(repo, {})[number] = pr
        return pr

    def passthrough(self, path_qs: str, accept: str | None, repo: str | None):
        if self.pt is None:
            raise ApiError(404, "Not Found", op="unsupported")
        status, headers, body = self.pt.get(path_qs, accept)
        return status, body, headers

    # 라우트
    def installation_repos(self, tok, kw, q, body):
        names = self.s.repos.all()
        if tok["repositories"] is not None:
            names = [n for n in names if n.split("/")[1].lower() in tok["repositories"]]
        return 200, {"total_count": len(names), "repositories": [repo_min(self.s, n) for n in names]}, "repos.list", None, None

    def rate_limit(self, tok, kw, q, body):
        core = {"limit": 5000, "remaining": 4999, "reset": int(time.time()) + 3600, "used": 1}
        return 200, {"resources": {"core": core, "graphql": core}, "rate": core}, "rate_limit", None, None

    def repo_get(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "metadata", False)
        return 200, repo_min(self.s, repo), "repos.get", repo, None

    def branches(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "contents", False)
        out = [{"name": n, "commit": {"sha": sha, "url": f"https://api.github.com/repos/{repo}/commits/{sha}"},
                "protected": bool(self.s.rules.get(repo.lower(), {}).get(n))} for n, sha in self.s.repos.branches(repo)]
        return 200, out, "branches.list", repo, None

    def branch_get(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "contents", False)
        sha = self.s.repos.branch_sha(repo, kw["branch"])
        if not sha:
            raise ApiError(404, "Branch not found")
        return 200, {"name": kw["branch"], "commit": self.commit_obj(repo, sha),
                     "protected": bool(self.s.rules.get(repo.lower(), {}).get(kw["branch"]))}, "branches.get", repo, None

    def ref_get(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "contents", False)
        sha = self.s.repos.branch_sha(repo, kw["branch"])
        if not sha:
            raise ApiError(404, "Not Found")
        return 200, {"ref": f"refs/heads/{kw['branch']}", "object": {"sha": sha, "type": "commit"}}, "refs.get", repo, None

    def ref_create(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "contents", True)
        ref, sha = (body or {}).get("ref", ""), (body or {}).get("sha", "")
        if not ref.startswith("refs/heads/") or not self.s.repos.rev(repo, sha):
            raise ApiError(422, "Reference update failed")
        if self.s.repos.rev(repo, ref):
            raise ApiError(422, "Reference already exists")
        self.check_push_rules(repo, ref[len("refs/heads/"):], NULL_SHA, sha)
        self.s.repos.git(repo, "update-ref", ref, sha)
        return 201, {"ref": ref, "object": {"sha": sha, "type": "commit"}}, "refs.create", repo, {"ref": ref, "sha": sha}

    def ref_update(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "contents", True)
        branch, sha = kw["branch"], (body or {}).get("sha", "")
        old = self.s.repos.branch_sha(repo, branch)
        if not old or not self.s.repos.rev(repo, sha):
            raise ApiError(422, "Reference does not exist")
        forced = not self.s.repos.is_ancestor(repo, old, sha)
        if forced and not (body or {}).get("force"):
            raise ApiError(422, "Update is not a fast forward")
        self.check_push_rules(repo, branch, old, sha)
        self.s.repos.git(repo, "update-ref", f"refs/heads/{branch}", sha)
        return 200, {"ref": f"refs/heads/{branch}", "object": {"sha": sha, "type": "commit"}}, "refs.update", repo, \
            {"ref": f"refs/heads/{branch}", "old": old, "new": sha, "forced": forced}

    def ref_delete(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "contents", True)
        branch = kw["branch"]
        old = self.s.repos.branch_sha(repo, branch)
        if not old:
            raise ApiError(422, "Reference does not exist")
        if branch == self.s.repos.default_branch(repo):
            raise ApiError(422, "Cannot delete the default branch")
        self.check_push_rules(repo, branch, old, NULL_SHA)
        self.s.repos.git(repo, "update-ref", "-d", f"refs/heads/{branch}")
        return 204, None, "refs.delete", repo, {"ref": f"refs/heads/{branch}", "old": old}

    def check_push_rules(self, repo: str, branch: str, old: str, new: str) -> None:
        rules = self.s.rules.get(repo.lower(), {}).get(branch) or {}
        if new == NULL_SHA and rules.get("deletion"):
            raise ApiError(422, "Repository rule violations found\n\nCannot delete this branch")
        if rules.get("blocks_direct_push"):
            raise ApiError(422, "Repository rule violations found\n\nChanges must be made through a pull request.")

    def commit_obj(self, repo: str, sha: str) -> dict:
        fmt = "%H%x00%T%x00%P%x00%an%x00%ae%x00%aI%x00%B"
        raw = self.s.repos.git(repo, "show", "-s", f"--format={fmt}", sha)
        h, tree, parents, an, ae, ad, msg = (raw.split("\x00") + [""] * 7)[:7]
        return {"sha": h, "node_id": f"C_sbx_{h}", "url": f"https://api.github.com/repos/{repo}/commits/{h}",
                "html_url": f"https://github.com/{repo}/commit/{h}",
                "commit": {"message": msg.strip(), "tree": {"sha": tree},
                           "author": {"name": an, "email": ae, "date": ad},
                           "committer": {"name": an, "email": ae, "date": ad}},
                "parents": [{"sha": p} for p in parents.split()]}

    def commit_get(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "contents", False)
        sha = self.s.repos.rev(repo, urllib.parse.unquote(kw["ref"]))
        if not sha:
            raise ApiError(422, f"No commit found for SHA: {kw['ref']}")
        out = self.commit_obj(repo, sha)
        names = self.s.repos.git(repo, "show", "--format=", "--name-status", sha, check=False)
        out["files"] = [{"filename": line.split("\t")[-1], "status": {"A": "added", "M": "modified", "D": "removed"}
                         .get(line[:1], "modified")} for line in names.splitlines() if "\t" in line]
        return 200, out, "commits.get", repo, None

    def commits_list(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "contents", False)
        ref = (q.get("sha") or [self.s.repos.default_branch(repo)])[0]
        tip = self.s.repos.rev(repo, ref) or self.s.repos.rev(repo, f"refs/heads/{ref}")
        if not tip:
            raise ApiError(404, f"No commit found for SHA: {ref}")
        per_page = min(int((q.get("per_page") or ["30"])[0]), 100)
        args = ["rev-list", f"--max-count={per_page}", tip]
        if q.get("path"):
            args += ["--", q["path"][0]]
        shas = self.s.repos.git(repo, *args).split()
        return 200, [self.commit_obj(repo, c) for c in shas], "commits.list", repo, None

    def git_commit_get(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "contents", False)
        if not self.s.repos.rev(repo, kw["sha"]):
            raise ApiError(404, "Not Found")
        c = self.commit_obj(repo, kw["sha"].lower())
        out = dict(c["commit"], sha=c["sha"], node_id=c["node_id"], parents=c["parents"],
                   url=f"https://api.github.com/repos/{repo}/git/commits/{c['sha']}",
                   html_url=c["html_url"], verification={"verified": False, "reason": "unsigned"})
        return 200, out, "git.commits.get", repo, None

    def local_statuses(self, repo: str, sha: str) -> list:
        return list(reversed(self.s.statuses.get((repo, sha), [])))

    def real_list(self, path: str, key: str | None = None) -> list:
        if self.pt is None:
            return []
        try:
            status, _, body = self.pt.get(path)
        except ApiError:
            return []
        if status != 200:
            return []
        data = json.loads(body)
        return (data.get(key) or []) if key else (data if isinstance(data, list) else [])

    def real_ci(self, repo: str, sha: str, path: str, key: str) -> list:
        """실제 GitHub의 체크 런·스위트 중계. 대역이 CI를 맡은 커밋(합성 런이 있는 head)이면 섞지 않는다 — 시드로 실제 커밋 위에
        세운 대역 PR에서 그 커밋의 실제 CI 결과가 합성 결과(예: 실패)를 가리지 않게."""
        if self.s.synthetic_runs(repo, sha):
            return []
        return self.real_list(path, key)

    def statuses_list(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "statuses", False)
        sha = self.s.repos.rev(repo, urllib.parse.unquote(kw["ref"])) or kw["ref"]
        out = self.local_statuses(repo, sha) + self.real_list(f"/repos/{repo}/commits/{sha}/statuses?per_page=100")
        return 200, out, "statuses.list", repo, None

    def status_combined(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "statuses", False)
        sha = self.s.repos.rev(repo, urllib.parse.unquote(kw["ref"])) or kw["ref"]
        latest: dict[str, dict] = {}
        for st in self.local_statuses(repo, sha) + self.real_list(f"/repos/{repo}/commits/{sha}/statuses?per_page=100"):
            latest.setdefault(st["context"], st)
        states = [st["state"] for st in latest.values()]
        overall = ("failure" if any(s in ("failure", "error") for s in states) else
                   "pending" if not states or any(s == "pending" for s in states) else "success")
        return 200, {"state": overall, "sha": sha, "total_count": len(latest), "statuses": list(latest.values())}, \
            "statuses.combined", repo, None

    def check_runs(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "checks", False)
        sha = self.s.repos.rev(repo, urllib.parse.unquote(kw["ref"])) or kw["ref"]
        runs = self.s.synthetic_runs(repo, sha) + \
            self.real_ci(repo, sha, f"/repos/{repo}/commits/{sha}/check-runs?per_page=100", "check_runs")
        return 200, {"total_count": len(runs), "check_runs": runs}, "checks.list", repo, None

    def check_run_get(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "checks", False)
        rid = int(kw["run_id"])
        for (r, _), runs in list(self.s.ci_runs.items()):
            for run in runs:
                if r == repo and run["id"] == rid:
                    return 200, run, "checks.get", repo, None
        status, data, _ = self.passthrough(f"/repos/{repo}/check-runs/{rid}", None, repo)  # 대역 런이 아니면 실제 읽기
        return status, data, "checks.get", repo, {"passthrough": True}

    def check_suites(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "checks", False)
        sha = self.s.repos.rev(repo, urllib.parse.unquote(kw["ref"])) or kw["ref"]
        suites = [{"id": r["check_suite"]["id"], "head_sha": sha, "status": "completed", "conclusion": r["conclusion"],
                   "app": r["app"], "synthetic": True} for r in self.s.synthetic_runs(repo, sha)] + \
            self.real_ci(repo, sha, f"/repos/{repo}/commits/{sha}/check-suites?per_page=100", "check_suites")
        return 200, {"total_count": len(suites), "check_suites": suites}, "checks.suites", repo, None

    def add_status(self, repo: str, sha: str, body: dict, source: str) -> dict:
        state = body.get("state")
        if state not in ("error", "failure", "pending", "success"):
            raise ApiError(422, "Validation Failed: state")
        if not self.s.repos.rev(repo, sha):
            raise ApiError(422, f"No commit found for SHA: {sha}")
        st = {"id": next(self.s.ids), "state": state, "context": body.get("context") or "default",
              "description": body.get("description"), "target_url": body.get("target_url"),
              "creator": {"login": BOT_LOGIN}, "created_at": now_iso(), "updated_at": now_iso()}
        with self.s.lock:
            self.s.statuses.setdefault((repo, sha), []).append(st)
        return st

    def status_create(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "statuses", True)
        st = self.add_status(repo, kw["sha"].lower(), body or {}, "api")
        return 201, st, "statuses.create", repo, {"sha": kw["sha"].lower(), "context": st["context"], "state": st["state"]}

    def contents(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "contents", False)
        ref = (q.get("ref") or [self.s.repos.default_branch(repo)])[0]
        sha = self.s.repos.rev(repo, ref) or self.s.repos.rev(repo, f"refs/heads/{ref}")
        if not sha:
            raise ApiError(404, f"No commit found for the ref {ref}")
        path = urllib.parse.unquote(kw.get("path") or "").strip("/")
        spec = f"{sha}:{path}" if path else f"{sha}^{{tree}}"
        kind = self.s.repos.git(repo, "cat-file", "-t", spec, check=False)
        if kind == "blob":
            p = self.s.repos.path(repo)
            data = subprocess.run(["git", "--git-dir", str(p), "cat-file", "blob", spec], capture_output=True).stdout
            blob = self.s.repos.git(repo, "rev-parse", spec)
            return 200, {"type": "file", "encoding": "base64", "size": len(data), "name": path.split("/")[-1],
                         "path": path, "sha": blob, "content": base64.encodebytes(data).decode(),
                         "html_url": f"https://github.com/{repo}/blob/{ref}/{path}"}, "contents.get", repo, None
        if kind == "tree":
            out = []
            for line in self.s.repos.git(repo, "ls-tree", "-l", spec).splitlines():
                meta, name = line.split("\t", 1)
                _, typ, osha, size = meta.split()
                out.append({"type": "dir" if typ == "tree" else "file", "name": name,
                            "path": f"{path}/{name}".strip("/"), "sha": osha,
                            "size": 0 if size == "-" else int(size)})
            return 200, out, "contents.list", repo, None
        raise ApiError(404, "Not Found")

    def compare(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "contents", False)
        base_ref, _, head_ref = urllib.parse.unquote(kw["spec"]).partition("...")
        base, head = self.s.repos.rev(repo, base_ref.split(":")[-1]), self.s.repos.rev(repo, head_ref.split(":")[-1])
        if not base or not head:
            raise ApiError(404, "Not Found")
        ahead = int(self.s.repos.git(repo, "rev-list", "--count", f"{base}..{head}") or 0)
        behind = int(self.s.repos.git(repo, "rev-list", "--count", f"{head}..{base}") or 0)
        names = self.s.repos.git(repo, "diff", "--name-status", f"{base}...{head}", check=False)
        files = [{"filename": line.split("\t")[-1], "status": {"A": "added", "M": "modified", "D": "removed"}
                  .get(line[:1], "modified")} for line in names.splitlines() if "\t" in line]
        commits = [self.commit_obj(repo, c) for c in self.s.repos.git(repo, "rev-list", "--reverse",
                                                                    f"{base}..{head}").split()]
        status = "identical" if not ahead and not behind else "ahead" if not behind else "behind" if not ahead else "diverged"
        return 200, {"status": status, "ahead_by": ahead, "behind_by": behind, "total_commits": ahead,
                     "commits": commits, "files": files}, "compare", repo, None

    # PR
    def pulls_list(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "pull_requests", False)
        state = (q.get("state") or ["open"])[0]
        head = (q.get("head") or [""])[0].split(":")[-1]
        base = (q.get("base") or [""])[0]
        local = [pr_public(self.s, repo, pr) for pr in sorted(self.s.prs.get(repo, {}).values(),
                                                              key=lambda p: -p["number"])]
        known = {p["number"] for p in local}
        qs = urllib.parse.urlencode({k: v[0] for k, v in q.items()})
        real = [p for p in self.real_list(f"/repos/{repo}/pulls?{qs}") if p.get("number") not in known]
        out = [p for p in local
               if (state == "all" or p["state"] == state) and (not head or p["head"]["ref"] == head)
               and (not base or p["base"]["ref"] == base)] + real
        return 200, out, "pulls.list", repo, None

    def create_pr(self, repo: str, title: str, head: str, base: str, body: str | None, draft: bool) -> dict:
        head = (head or "").split(":")[-1]
        if not title:
            raise ApiError(422, "Validation Failed: title is missing")
        if not self.s.repos.branch_sha(repo, base or ""):
            raise ApiError(422, "Validation Failed: base is invalid")
        head_sha = self.s.repos.branch_sha(repo, head)
        if not head_sha:
            raise ApiError(422, "Validation Failed: head is invalid (push the branch first)")
        if head == base:
            raise ApiError(422, "Validation Failed: head and base must be different")
        base_sha = self.s.repos.branch_sha(repo, base)
        if self.s.repos.git(repo, "rev-list", "--count", f"{base_sha}..{head_sha}") == "0":
            raise ApiError(422, f"Validation Failed: No commits between {base} and {head}")
        for pr in self.s.prs.get(repo, {}).values():
            if pr["state"] == "open" and pr["head"]["ref"] == head and pr["base"]["ref"] == base:
                raise ApiError(422, f"Validation Failed: A pull request already exists for {repo.split('/')[0]}:{head}.")
        if self.pt is not None:  # 실제 레포에 같은 head의 열린 PR이 있으면 실제 GitHub도 거절한다
            for real in self.real_list(f"/repos/{repo}/pulls?state=open&head={repo.split('/')[0]}:{head}"):
                if real.get("base", {}).get("ref") == base:
                    raise ApiError(422, f"Validation Failed: A pull request already exists for {repo.split('/')[0]}:{head}.")
        number = self.s.next_pr_number(repo)
        ts = now_iso()
        pr = {"number": number, "title": title, "body": body, "state": "open", "draft": bool(draft),
              "merged": False, "merged_at": None, "closed_at": None, "merge_commit_sha": None,
              "created_at": ts, "updated_at": ts, "user": {"login": BOT_LOGIN, "type": "Bot"}, "labels": [],
              "head": {"ref": head, "sha": head_sha}, "base": {"ref": base, "sha": base_sha}, "origin": "sandbox"}
        with self.s.lock:
            self.s.prs.setdefault(repo, {})[number] = pr
        return pr

    def pulls_create(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "pull_requests", True)
        b = body or {}
        pr = self.create_pr(repo, b.get("title"), b.get("head"), b.get("base"), b.get("body"), b.get("draft"))
        out = pr_public(self.s, repo, pr)
        return 201, out, "pulls.create", repo, {"number": pr["number"], "html_url": out["html_url"],
                                                 "head": pr["head"]["ref"], "base": pr["base"]["ref"],
                                                 "head_sha": pr["head"]["sha"], "title": pr["title"]}

    def pulls_get(self, tok, kw, q, body, accept=None):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "pull_requests", False)
        pr = self.s.get_pr(repo, int(kw["number"]))
        if pr is None:
            status, data, headers = self.passthrough(f"/repos/{repo}/pulls/{kw['number']}", accept, repo)
            if status == 200 and not self.real_pr_moved(repo, data):
                return status, data, "pulls.get", repo, {"passthrough": True}
            if status != 200:
                return status, data, "pulls.get", repo, {"passthrough": True}
            # 대역에서 PR 브랜치에 push했다 — 실제 PR을 등록해 대역의 head(와 그 합성 CI)로 보여 준다.
            pr = self.pr_or_real(repo, int(kw["number"]))
        return 200, pr_public(self.s, repo, pr), "pulls.get", repo, None

    def real_pr_moved(self, repo: str, data) -> bool:
        """실제 PR 응답의 head 브랜치가 대역 미러에서 다른 커밋을 가리키나(대역에서 push됨)."""
        try:
            real = json.loads(data) if isinstance(data, (bytes, str)) else data
            ref, sha = real["head"]["ref"], real["head"]["sha"]
        except (ValueError, KeyError, TypeError):
            return False
        if real.get("state") != "open":
            return False
        mirrored = self.s.repos.branch_sha(repo, ref)
        return bool(mirrored) and mirrored != sha

    def update_pr(self, repo: str, number: int, b: dict) -> tuple[dict, dict]:
        pr = self.pr_or_real(repo, number)
        changes = {}
        for key in ("title", "body"):
            if key in b and b[key] != pr.get(key):
                pr[key] = b[key]
                changes[key] = "changed"
        if b.get("state") in ("open", "closed") and b["state"] != pr["state"]:
            if pr.get("merged"):
                raise ApiError(422, "Validation Failed: cannot change state of a merged pull request")
            pr["state"] = b["state"]
            pr["closed_at"] = now_iso() if b["state"] == "closed" else None
            changes["state"] = b["state"]
        if b.get("base") and b["base"] != pr["base"]["ref"]:
            if not self.s.repos.branch_sha(repo, b["base"]):
                raise ApiError(422, "Validation Failed: base is invalid")
            pr["base"]["ref"] = b["base"]
            changes["base"] = b["base"]
        pr["updated_at"] = now_iso()
        return pr, changes

    def pulls_update(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "pull_requests", True)
        pr, changes = self.update_pr(repo, int(kw["number"]), body or {})
        op = "pulls.close" if changes.get("state") == "closed" else "pulls.update"
        return 200, pr_public(self.s, repo, pr), op, repo, {"number": pr["number"], "changes": changes,
                                                            "origin": pr.get("origin")}

    def issue_update(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "issues", True)
        number = int(kw["number"])
        if self.s.get_pr(repo, number) is None and self.pt is None:
            raise ApiError(404, "Not Found")
        pr, changes = self.update_pr(repo, number, body or {})
        op = "pulls.close" if changes.get("state") == "closed" else "issues.update"
        return 200, pr_public(self.s, repo, pr), op, repo, {"number": number, "changes": changes}

    def pulls_files(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "pull_requests", False)
        pr = self.s.get_pr(repo, int(kw["number"]))
        if pr is None:
            status, data, _ = self.passthrough(f"/repos/{repo}/pulls/{kw['number']}/files?per_page=100", None, repo)
            return status, data, "pulls.files", repo, {"passthrough": True}
        refresh_pr(self.s, repo, pr)
        diff_range = f"{pr['base']['sha']}...{pr['head']['sha']}"
        out = []
        for line in self.s.repos.git(repo, "diff", "--numstat", diff_range, check=False).splitlines():
            adds, dels, name = line.split("\t", 2)
            patch = self.s.repos.git(repo, "diff", diff_range, "--", name, check=False)
            out.append({"filename": name, "additions": int(adds) if adds.isdigit() else 0,
                        "deletions": int(dels) if dels.isdigit() else 0, "status": "modified",
                        "patch": "@@" + patch.split("@@", 1)[1] if "@@" in patch else ""})
        return 200, out, "pulls.files", repo, None

    def pulls_commits(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "pull_requests", False)
        pr = self.s.get_pr(repo, int(kw["number"]))
        if pr is None:
            status, data, _ = self.passthrough(f"/repos/{repo}/pulls/{kw['number']}/commits?per_page=100", None, repo)
            return status, data, "pulls.commits", repo, {"passthrough": True}
        refresh_pr(self.s, repo, pr)
        shas = self.s.repos.git(repo, "rev-list", "--reverse", f"{pr['base']['sha']}..{pr['head']['sha']}").split()
        return 200, [self.commit_obj(repo, c) for c in shas], "pulls.commits", repo, None

    def pulls_merged(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "pull_requests", False)
        pr = self.s.get_pr(repo, int(kw["number"]))
        if pr is None:
            status, data, _ = self.passthrough(f"/repos/{repo}/pulls/{kw['number']}/merge", None, repo)
            return status, data, "pulls.merged", repo, {"passthrough": True}
        return (204 if pr.get("merged") else 404), None, "pulls.merged", repo, None

    def merge_pr(self, repo: str, number: int, b: dict) -> tuple[dict, dict]:
        pr = self.pr_or_real(repo, number)
        refresh_pr(self.s, repo, pr)
        if pr.get("merged"):
            raise ApiError(405, "Pull Request is not mergeable (already merged)")
        if pr["state"] != "open":
            raise ApiError(405, "Pull Request is not mergeable (closed)")
        if pr.get("draft"):
            raise ApiError(405, "Pull Request is still a draft")
        if b.get("sha") and b["sha"] != pr["head"]["sha"]:
            raise ApiError(409, "Head branch was modified. Review and try the merge again.")
        latest: dict[str, str] = {}
        for st in self.local_statuses(repo, pr["head"]["sha"]) + \
                self.real_list(f"/repos/{repo}/commits/{pr['head']['sha']}/statuses?per_page=100"):
            latest.setdefault(st["context"], st["state"])
        for run in self.s.synthetic_runs(repo, pr["head"]["sha"]) + \
                self.real_ci(repo, pr["head"]["sha"],
                             f"/repos/{repo}/commits/{pr['head']['sha']}/check-runs?per_page=100", "check_runs"):
            latest.setdefault(run.get("name"), "success" if run.get("conclusion") in ("success", "neutral", "skipped")
                              else "failure" if run.get("conclusion") in ("failure", "timed_out", "cancelled",
                                                                          "action_required")
                              else "pending")
        missing = [c for c in self.s.required_contexts(repo, pr["base"]["ref"]) if latest.get(c) != "success"]
        if missing:
            raise ApiError(405, "Repository rule violations found\n\n" +
                           "\n".join(f'Required status check "{c}" is expected.' for c in missing),
                           required=missing)
        tree = self.s.repos.merge_tree(repo, pr["base"]["sha"], pr["head"]["sha"])
        if tree is None:
            raise ApiError(405, "Pull Request is not mergeable (merge conflict)")
        method = b.get("merge_method") or "merge"
        if method not in ("merge", "squash", "rebase"):
            raise ApiError(422, "Validation Failed: merge_method")
        title = b.get("commit_title") or (f"{pr['title']} (#{number})" if method == "squash" else
                                          f"Merge pull request #{number} from {pr['head']['ref']}")
        message = title + ("\n\n" + b["commit_message"] if b.get("commit_message") else "")
        parents = ["-p", pr["base"]["sha"]] + (["-p", pr["head"]["sha"]] if method == "merge" else [])
        env = dict(os.environ, GIT_AUTHOR_NAME="GitHub", GIT_AUTHOR_EMAIL="noreply@github.com",
                   GIT_COMMITTER_NAME="GitHub", GIT_COMMITTER_EMAIL="noreply@github.com")
        p = self.s.repos.path(repo)
        r = subprocess.run(["git", "--git-dir", str(p), "commit-tree", tree, *parents, "-m", message],
                           capture_output=True, text=True, env=env)
        if r.returncode != 0:
            raise ApiError(500, f"merge failed: {r.stderr.strip()}")
        merged_sha = r.stdout.strip()
        self.s.repos.git(repo, "update-ref", f"refs/heads/{pr['base']['ref']}", merged_sha, pr["base"]["sha"])
        ts = now_iso()
        pr.update(state="closed", merged=True, merged_at=ts, closed_at=ts, merge_commit_sha=merged_sha,
                  updated_at=ts, merged_by={"login": BOT_LOGIN})
        return pr, {"number": number, "method": method, "merge_commit_sha": merged_sha,
                    "base": pr["base"]["ref"], "head_sha": pr["head"]["sha"], "origin": pr.get("origin")}

    def pulls_merge(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "contents", True)
        try:
            pr, detail = self.merge_pr(repo, int(kw["number"]), body or {})
        except ApiError as exc:
            exc.op, exc.extra = "pulls.merge", dict(exc.extra, number=int(kw["number"]), refused=True)
            raise
        return 200, {"sha": pr["merge_commit_sha"], "merged": True, "message": "Pull Request successfully merged"}, \
            "pulls.merge", repo, detail

    def pulls_sub(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "pull_requests", False)
        number = int(kw["number"])
        pr = self.s.get_pr(repo, number)
        if pr is None or pr.get("origin") == "real":
            if self.pt is None:
                return 200, [] if kw["sub"] != "requested_reviewers" else {"users": [], "teams": []}, \
                    f"pulls.{kw['sub']}", repo, None
            status, data, _ = self.passthrough(f"/repos/{repo}/pulls/{number}/{kw['sub']}?per_page=100", None, repo)
            return status, data, f"pulls.{kw['sub']}", repo, {"passthrough": True}
        empty = {"users": [], "teams": []} if kw["sub"] == "requested_reviewers" else []
        return 200, empty, f"pulls.{kw['sub']}", repo, None

    def pulls_sub_write(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "pull_requests", True)
        number = int(kw["number"])
        self.pr_or_real(repo, number)
        item = {"id": next(self.s.ids), "user": {"login": BOT_LOGIN}, "body": (body or {}).get("body"),
                "state": (body or {}).get("event") or "COMMENTED", "submitted_at": now_iso()}
        return 201 if kw["sub"] != "reviews" else 200, item, f"pulls.{kw['sub']}.create", repo, \
            {"number": number, "event": (body or {}).get("event")}

    def comments_list(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "issues", False)
        number = int(kw["number"])
        local = self.s.comments.get((repo, number), [])
        pr = self.s.get_pr(repo, number)
        real = [] if pr is not None and pr.get("origin") == "sandbox" else \
            self.real_list(f"/repos/{repo}/issues/{number}/comments?per_page=100")
        return 200, real + local, "issues.comments.list", repo, None

    def comments_create(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "issues", True)
        number = int(kw["number"])
        self.pr_or_real(repo, number)
        text = (body or {}).get("body")
        if not text:
            raise ApiError(422, "Validation Failed: body is missing")
        c = self.add_comment(repo, number, text)
        return 201, c, "issues.comments.create", repo, {"number": number, "length": len(text)}

    def add_comment(self, repo: str, number: int, text: str) -> dict:
        c = {"id": next(self.s.ids), "node_id": f"IC_sbx_{next(self.s.ids)}", "body": text,
             "user": {"login": BOT_LOGIN, "type": "Bot"}, "created_at": now_iso(), "updated_at": now_iso(),
             "html_url": f"https://github.com/{repo}/pull/{number}#issuecomment-sbx"}
        with self.s.lock:
            self.s.comments.setdefault((repo, number), []).append(c)
        return c

    def labels_add(self, tok, kw, q, body):
        repo = self.repo(kw)
        self.s.authorize(tok, repo, "issues", True)
        pr = self.pr_or_real(repo, int(kw["number"]))
        labels = (body or {}).get("labels") or []
        names = [label if isinstance(label, str) else label.get("name") for label in labels]
        pr["labels"] = [{"name": n} for n in dict.fromkeys([lb["name"] for lb in pr.get("labels", [])] + names)]
        return 200, pr["labels"], "issues.labels.add", repo, {"number": pr["number"], "labels": names}

    # 디스패치
    def handle(self, method: str, path: str, query: dict, tok: dict | None, body, accept: str | None):
        if method == "HEAD":
            method = "GET"
        for m, rx, handler in self.routes:
            if m != method:
                continue
            match = rx.match(path)
            if match:
                try:
                    return handler(tok, match.groupdict(), query, body)
                except ApiError as exc:  # 권한·검증으로 거절돼도 무엇을 하려 했는지 남긴다
                    if exc.op is None:
                        exc.op = HANDLER_OPS.get(handler.__name__, handler.__name__)
                        if method not in READ_METHODS:
                            exc.extra = dict(exc.extra, refused=True)
                    raise
        # 모르는 경로: 읽기만 실제로 묻는다(레포 범위는 지킨다). 쓰기는 절대 내보내지 않는다.
        if method == "GET" and self.pt is not None:
            m = re.match(r"/repos/([^/]+)/([^/]+)", path)
            repo = self.s.repos.canonical(f"{m.group(1)}/{m.group(2)}") if m else None
            if m and repo is None:
                raise ApiError(404, "Not Found")
            self.s.authorize(tok, repo, "metadata", False)
            qs = urllib.parse.urlencode({k: v[0] for k, v in query.items()})
            status, data, _ = self.passthrough(path + (f"?{qs}" if qs else ""), accept, repo)
            return status, data, "passthrough", repo, None
        raise ApiError(501 if method != "GET" else 404, f"Not implemented by this server: {method} {path}",
                       op="unsupported")



# ── GraphQL 선택 집합 파서 · 투영 ──────────────────────────────────────────────────────────────
# 응답을 질의가 고른 필드 그대로의 모양으로 깎는다(별칭·인라인 프래그먼트·이름 붙은 프래그먼트 포함). gh의 일부 경로는
# 응답에 질의하지 않은 필드가 있으면 디코딩에 실패한다(strict) — 그래서 상위 집합을 만든 뒤 여기서 투영한다.

_GQL_TOKEN = re.compile(r'"""(?:.|\n)*?"""|"(?:\\.|[^"\\])*"|\.\.\.|[A-Za-z_][A-Za-z0-9_]*|-?\d+(?:\.\d+)?|[{}()\[\]:!$=@,|&]')


class Sel:
    __slots__ = ("alias", "name", "children", "spread", "fragment", "on")

    def __init__(self, alias=None, name=None, children=None, spread=False, fragment=None, on=None):
        self.alias, self.name, self.children, self.spread, self.fragment = alias, name, children, spread, fragment
        self.on = on


def gql_tokens(text: str) -> list[str]:
    text = re.sub(r"#[^\n]*", "", text)
    return [t for t in _GQL_TOKEN.findall(text) if t != ","]


class GqlDoc:
    def __init__(self, text: str):
        self.t, self.i = gql_tokens(text), 0
        self.operation: list[Sel] | None = None
        self.op_type = "query"
        self.fragments: dict[str, tuple[str, list[Sel]]] = {}
        while self.i < len(self.t):
            tok = self.t[self.i]
            if tok == "fragment":
                name, on = self.t[self.i + 1], self.t[self.i + 3]
                self.i += 4  # fragment Name on Type
                self.skip_directives()
                self.fragments[name] = (on, self.selection_set())
            elif tok in ("query", "mutation", "subscription"):
                self.op_type = tok
                self.i += 1
                if self.i < len(self.t) and self.t[self.i] not in ("(", "{", "@"):
                    self.i += 1
                if self.i < len(self.t) and self.t[self.i] == "(":
                    self.skip_balanced("(", ")")
                self.skip_directives()
                sels = self.selection_set()
                self.operation = self.operation or sels
            elif tok == "{":
                sels = self.selection_set()
                self.operation = self.operation or sels
            else:
                self.i += 1

    def skip_balanced(self, open_, close):
        depth = 0
        while self.i < len(self.t):
            tok = self.t[self.i]
            self.i += 1
            if tok == open_:
                depth += 1
            elif tok == close:
                depth -= 1
                if depth == 0:
                    return

    def skip_directives(self):
        while self.i < len(self.t) and self.t[self.i] == "@":
            self.i += 2
            if self.i < len(self.t) and self.t[self.i] == "(":
                self.skip_balanced("(", ")")

    def selection_set(self) -> list[Sel]:
        out: list[Sel] = []
        if self.i >= len(self.t) or self.t[self.i] != "{":
            return out
        self.i += 1
        while self.i < len(self.t) and self.t[self.i] != "}":
            tok = self.t[self.i]
            if tok == "...":
                self.i += 1
                if self.t[self.i] == "on":
                    on = self.t[self.i + 1]
                    self.i += 2
                    self.skip_directives()
                    out.append(Sel(spread=True, children=self.selection_set(), on=on))
                elif self.t[self.i] in ("{", "@"):
                    self.skip_directives()
                    out.append(Sel(spread=True, children=self.selection_set()))
                else:
                    out.append(Sel(spread=True, fragment=self.t[self.i]))
                    self.i += 1
                    self.skip_directives()
                continue
            name = tok
            self.i += 1
            alias = name
            if self.i < len(self.t) and self.t[self.i] == ":":
                name = self.t[self.i + 1]
                self.i += 2
            if self.i < len(self.t) and self.t[self.i] == "(":
                self.skip_balanced("(", ")")
            self.skip_directives()
            children = self.selection_set() if self.i < len(self.t) and self.t[self.i] == "{" else None
            out.append(Sel(alias, name, children))
        self.i += 1
        return out

    def expand(self, sels: list[Sel], typename: str | None = None, seen=()) -> list[Sel]:
        """프래그먼트를 펼친다. 값에 __typename이 있으면 타입 조건이 맞는 프래그먼트만."""
        out: list[Sel] = []
        for sel in sels:
            if sel.spread and sel.fragment:
                on, children = self.fragments.get(sel.fragment, (None, []))
                if sel.fragment not in seen and (typename is None or on in (None, typename)):
                    out += self.expand(children, typename, (*seen, sel.fragment))
            elif sel.spread:
                if typename is None or sel.on in (None, typename):
                    out += self.expand(sel.children or [], typename, seen)
            else:
                out.append(sel)
        return out

    def project(self, sels: list[Sel] | None, value):
        if sels is None or value is None:
            return value
        if isinstance(value, list):
            return [self.project(sels, v) for v in value]
        if not isinstance(value, dict):
            return value
        out: dict = {}
        for sel in self.expand(sels, value.get("__typename")):
            sub = value.get(sel.name)
            projected = self.project(sel.children, sub) if sel.children is not None else sub
            if sel.alias in out and isinstance(out[sel.alias], dict) and isinstance(projected, dict):
                out[sel.alias].update(projected)  # 같은 필드를 여러 프래그먼트가 고른 경우
            else:
                out[sel.alias] = projected
        return out

# ── GraphQL ─────────────────────────────────────────────────────────────────────────────────

MUTATION = re.compile(r"\bmutation\b")
MUTATION_FIELDS = ("createPullRequest", "mergePullRequest", "closePullRequest", "reopenPullRequest",
                   "updatePullRequest", "addComment", "markPullRequestReadyForReview", "enablePullRequestAutoMerge",
                   "addLabelsToLabelable", "requestReviews", "addPullRequestReview", "updateRef", "createRef",
                   "deleteRef", "createCommitOnBranch")


INTROSPECTION = {
    "PullRequest": ("id", "number", "title", "body", "state", "url", "isDraft", "headRefName", "baseRefName",
                    "headRefOid", "mergeable", "mergeStateStatus", "author", "labels", "commits", "merged", "closed"),
    "StatusCheckRollupContextConnection": ("nodes", "pageInfo", "totalCount", "edges"),
    "WorkflowRun": ("id", "databaseId", "url"),
}


def gql_rollup(state: State, repo: str, sha: str) -> dict:
    latest: dict[str, dict] = {}
    for st in reversed(state.statuses.get((repo, sha), [])):
        latest.setdefault(st["context"], st)
    nodes = [{"__typename": "StatusContext", "context": c, "state": st["state"].upper(),
              "targetUrl": st.get("target_url"), "description": st.get("description"), "createdAt": st["created_at"],
              "isRequired": c in state.required_contexts(repo, state.repos.default_branch(repo))}
             for c, st in latest.items()]
    required = state.required_contexts(repo, state.repos.default_branch(repo))
    nodes += [{"__typename": "CheckRun", "name": r["name"], "status": "COMPLETED", "conclusion": r["conclusion"].upper(),
               "detailsUrl": r["html_url"], "startedAt": r["started_at"], "completedAt": r["completed_at"],
               "isRequired": r["name"] in required, "checkSuite": {"workflowRun": None},
               "title": r["output"]["title"]} for r in state.synthetic_runs(repo, sha)]
    states = [n.get("state") or n.get("conclusion") for n in nodes]
    overall = ("FAILURE" if any(x in ("FAILURE", "ERROR") for x in states) else
               "PENDING" if not states or "PENDING" in states else "SUCCESS")
    return {"state": overall, "contexts": {"nodes": nodes, "totalCount": len(nodes),
                                           "pageInfo": {"hasNextPage": False, "endCursor": None}}}


def gql_pr(state: State, repo: str, pr: dict) -> dict:
    p = pr_public(state, repo, pr)
    owner = repo.split("/")[0]
    commit_nodes = {"totalCount": p.get("commits", 0), "nodes": [{"commit": {
        "oid": pr["head"]["sha"], "statusCheckRollup": gql_rollup(state, repo, pr["head"]["sha"])}}]}
    return {"__typename": "PullRequest", "id": node_pr(repo, pr["number"]), "number": pr["number"], "url": p["html_url"],
            "title": pr["title"], "body": pr.get("body") or "", "state": "MERGED" if pr.get("merged") else pr["state"].upper(),
            "isDraft": bool(pr.get("draft")), "merged": bool(pr.get("merged")), "closed": pr["state"] == "closed",
            "headRefName": pr["head"]["ref"], "baseRefName": pr["base"]["ref"], "headRefOid": pr["head"]["sha"],
            "baseRefOid": pr["base"]["sha"], "isCrossRepository": False, "maintainerCanModify": False,
            "mergeable": "MERGEABLE" if p.get("mergeable") else "CONFLICTING",
            "mergeStateStatus": "CLEAN" if p.get("mergeable") else "DIRTY",
            "headRepositoryOwner": {"login": owner}, "headRepository": {"name": repo.split("/")[1], "id": node_repo(repo)},
            "author": {"login": BOT_LOGIN}, "createdAt": pr.get("created_at"), "updatedAt": pr.get("updated_at"),
            "mergedAt": pr.get("merged_at"), "closedAt": pr.get("closed_at"),
            "mergeCommit": {"oid": pr["merge_commit_sha"]} if pr.get("merge_commit_sha") else None,
            "additions": p.get("additions", 0), "deletions": p.get("deletions", 0), "changedFiles": p.get("changed_files", 0),
            "labels": {"nodes": pr.get("labels") or [], "totalCount": len(pr.get("labels") or [])},
            "assignees": {"nodes": [], "totalCount": 0}, "reviewRequests": {"nodes": [], "totalCount": 0},
            "reviews": {"nodes": [], "totalCount": 0}, "comments": {"nodes": [], "totalCount": 0},
            "commits": commit_nodes, "statusCheckRollup": commit_nodes, "milestone": None, "projectCards": {"nodes": []},
            "projectItems": {"nodes": []}, "reviewDecision": None, "autoMergeRequest": None,
            "repository": gql_repo(state, repo)}


def gql_repo(state: State, repo: str) -> dict:
    owner, name = repo.split("/", 1)
    branch = state.repos.default_branch(repo)
    return {"__typename": "Repository", "id": node_repo(repo), "name": name, "nameWithOwner": repo,
            "owner": {"login": owner, "id": f"U_sbx_{owner}"}, "url": f"https://github.com/{repo}",
            "isPrivate": True, "isFork": False, "isArchived": False, "isTemplate": False, "isEmpty": False,
            "hasIssuesEnabled": True, "hasWikiEnabled": False, "hasProjectsEnabled": False,
            "hasDiscussionsEnabled": False, "viewerPermission": "WRITE", "viewerCanAdminister": False,
            "description": "", "parent": None, "mergeCommitAllowed": True, "rebaseMergeAllowed": True,
            "squashMergeAllowed": True, "deleteBranchOnMerge": False, "visibility": "PRIVATE",
            "defaultBranchRef": {"name": branch, "target": {"oid": state.repos.branch_sha(repo, branch)}}}


class GraphQL:
    """gh CLI가 PR을 만들고·보고·머지할 때 쓰는 GraphQL. 이 서버가 만든 PR·레포를 아는 응답은 직접 답하고,
    그 밖의 **질의(query)**는 실제 GitHub에 읽기 전용으로 묻는다. **변경(mutation)**은 아는 것만 여기서 처리하고
    나머지는 오류 + unsupported 기록 — 실제로 내보내지 않는다.

    응답은 필드를 고르지 않고 흔히 쓰는 필드를 다 담은 상위 집합으로 돌려준다(클라이언트는 남는 필드를 무시한다)."""

    def __init__(self, state: State, api: Api, passthrough: Passthrough | None):
        self.s, self.api, self.pt = state, api, passthrough

    def handle(self, tok: dict | None, payload: dict):
        if tok is None:
            raise ApiError(401, "This endpoint requires you to be authenticated.")
        query = payload.get("query") or ""
        variables = payload.get("variables") or {}
        result = self.mutation(tok, query, variables) if MUTATION.search(query) else self.query(tok, query, variables)
        status, data, op, repo, detail = result
        if op not in ("graphql.passthrough", "graphql.introspection") and isinstance(data, dict) and data.get("data"):
            try:
                doc = GqlDoc(query)
                if doc.operation:
                    data = dict(data, data=doc.project(doc.operation, data["data"]))
            except (IndexError, KeyError):  # 파서가 못 읽는 질의는 상위 집합 그대로
                pass
        return status, data, op, repo, detail

    def _repo_from(self, query: str, variables: dict) -> str | None:
        owner = variables.get("owner") or variables.get("repoOwner")
        name = variables.get("name") or variables.get("repo") or variables.get("repoName")
        if not (owner and name):
            m = re.search(r'repository\s*\(\s*owner\s*:\s*"([^"]+)"\s*,\s*name\s*:\s*"([^"]+)"', query)
            if m:
                owner, name = m.groups()
        return self.s.repos.canonical(f"{owner}/{name}") if owner and name else None

    def query(self, tok, query, variables):
        types = re.findall(r'(\w+)\s*:\s*__type\s*\(\s*name\s*:\s*"(\w+)"\s*\)', query)
        if types:  # gh의 기능 감지(introspection) — 기본 필드만 있다고 답해 옛 경로를 쓰게 한다
            data = {alias: {"fields": [{"name": f} for f in INTROSPECTION.get(name, ("id",))]} for alias, name in types}
            return 200, {"data": data}, "graphql.introspection", None, None
        node_id = variables.get("id") or variables.get("pullRequestId")
        if node_id and re.search(r"\bnode\s*\(", query):
            try:
                kind, value = parse_node(str(node_id))
            except ApiError:
                kind = value = None
            if kind == "pr":
                repo, _, number = value.rpartition("#")
                self.s.authorize(tok, repo, "pull_requests", False)
                pr = self.s.get_pr(repo, int(number))
                if pr is None:
                    raise ApiError(404, "Not Found")
                return 200, {"data": {"node": gql_pr(self.s, repo, pr)}}, "graphql.query", repo, None
            if kind == "repo":
                self.s.authorize(tok, value, "metadata", False)
                return 200, {"data": {"node": gql_repo(self.s, value)}}, "graphql.query", value, None
        if re.search(r"\bviewer\s*\{", query) and "repository" not in query:
            return 200, {"data": {"viewer": {"login": BOT_LOGIN, "id": "BOT_sbx", "databaseId": 1}}}, "graphql.viewer", None, None
        repo = self._repo_from(query, variables)
        if repo is not None:
            self.s.authorize(tok, repo, "metadata", False)
            data = gql_repo(self.s, repo)
            number = variables.get("number") or variables.get("pr_number") or (
                int(m.group(1)) if (m := re.search(r"pullRequest\s*\(\s*number\s*:\s*(\d+)", query)) else None)
            head = variables.get("headRefName") or variables.get("head")
            if number is not None:
                pr = self.s.get_pr(repo, int(number))
                if pr is None:
                    return self._passthrough(tok, repo, query, variables)
                data["pullRequest"] = gql_pr(self.s, repo, pr)
            if "pullRequests" in query:
                states = variables.get("states") or ["OPEN"]
                states = [states] if isinstance(states, str) else states
                nodes = [gql_pr(self.s, repo, pr) for pr in sorted(self.s.prs.get(repo, {}).values(),
                                                                   key=lambda p: -p["number"])]
                nodes = [n for n in nodes if n["state"] in states and (not head or n["headRefName"] == head)]
                real = self._real_prs(repo, query, variables) if self.pt is not None else []
                nodes += [n for n in real if n.get("number") not in {x["number"] for x in nodes}]
                data["pullRequests"] = {"totalCount": len(nodes), "nodes": nodes,
                                        "pageInfo": {"hasNextPage": False, "endCursor": None}}
            for key in ("ref", "object"):  # 브랜치 존재 확인류
                if re.search(rf"\b{key}\s*\(", query):
                    q = variables.get("qualifiedName") or variables.get("ref") or variables.get("expression") or ""
                    sha = self.s.repos.rev(repo, q) or self.s.repos.branch_sha(repo, q.replace("refs/heads/", ""))
                    data[key] = {"name": q.replace("refs/heads/", ""), "target": {"oid": sha}, "oid": sha} if sha else None
            return 200, {"data": {"repository": data}}, "graphql.query", repo, None
        if self.pt is None:
            return 200, {"errors": [{"message": "unsupported query", "type": "UNSUPPORTED"}]}, "unsupported", None, \
                {"query": " ".join(query.split())[:400], "variables": sorted(variables)}
        return self._passthrough(tok, None, query, variables)

    def _real_prs(self, repo, query, variables) -> list:
        try:
            data = self.pt.graphql(query, variables)  # type: ignore[union-attr]
            return (((data.get("data") or {}).get("repository") or {}).get("pullRequests") or {}).get("nodes") or []
        except (OSError, ValueError, ApiError):
            return []

    def _passthrough(self, tok, repo, query, variables):
        try:
            data = self.pt.graphql(query, variables)  # type: ignore[union-attr]
        except (OSError, ValueError) as exc:
            raise ApiError(502, f"passthrough failed: {exc}")
        return 200, data, "graphql.passthrough", repo, None

    def _pr_target(self, tok, node_id: str, perm: str) -> tuple[str, int]:
        kind, value = parse_node(node_id)
        if kind != "pr":
            raise ApiError(422, "expected a pull request id")
        repo, _, number = value.rpartition("#")
        self.s.authorize(tok, repo, perm, True)
        return repo, int(number)

    def mutation(self, tok, query, variables):
        field = next((f for f in MUTATION_FIELDS if re.search(rf"\b{f}\s*\(", query)), None)
        inp = variables.get("input") or {}
        try:
            if field == "createPullRequest":
                kind, repo = parse_node(inp.get("repositoryId", ""))
                if kind != "repo":
                    raise ApiError(422, "repositoryId is invalid")
                self.s.authorize(tok, repo, "pull_requests", True)
                pr = self.api.create_pr(repo, inp.get("title"), inp.get("headRefName"), inp.get("baseRefName"),
                                        inp.get("body"), inp.get("draft"))
                g = gql_pr(self.s, repo, pr)
                return 200, {"data": {field: {"pullRequest": g, "clientMutationId": None}}}, "pulls.create", repo, \
                    {"number": pr["number"], "html_url": g["url"], "head": pr["head"]["ref"], "base": pr["base"]["ref"],
                     "head_sha": pr["head"]["sha"], "title": pr["title"], "via": "graphql"}
            if field in ("closePullRequest", "reopenPullRequest", "updatePullRequest", "markPullRequestReadyForReview"):
                repo, number = self._pr_target(tok, inp.get("pullRequestId", ""), "pull_requests")
                change = {"closePullRequest": {"state": "closed"}, "reopenPullRequest": {"state": "open"},
                          "markPullRequestReadyForReview": {}, "updatePullRequest": {
                              k: v for k, v in (("title", inp.get("title")), ("body", inp.get("body")),
                                                ("base", inp.get("baseRefName"))) if v is not None}}[field]
                pr, changes = self.api.update_pr(repo, number, change)
                if field == "markPullRequestReadyForReview":
                    pr["draft"] = False
                op = "pulls.close" if changes.get("state") == "closed" else "pulls.update"
                return 200, {"data": {field: {"pullRequest": gql_pr(self.s, repo, pr), "clientMutationId": None}}}, op, repo, \
                    {"number": number, "changes": changes, "via": "graphql"}
            if field == "mergePullRequest":
                repo, number = self._pr_target(tok, inp.get("pullRequestId", ""), "contents")
                method = {"MERGE": "merge", "SQUASH": "squash", "REBASE": "rebase"}.get(inp.get("mergeMethod", "MERGE"), "merge")
                try:
                    pr, detail = self.api.merge_pr(repo, number, {"merge_method": method,
                                                                  "sha": inp.get("expectedHeadOid"),
                                                                  "commit_title": inp.get("commitHeadline"),
                                                                  "commit_message": inp.get("commitBody")})
                except ApiError as exc:
                    exc.op, exc.extra = "pulls.merge", dict(exc.extra, number=number, refused=True, via="graphql",
                                                            repo=repo)
                    raise
                return 200, {"data": {field: {"pullRequest": gql_pr(self.s, repo, pr), "clientMutationId": None}}}, "pulls.merge", repo, \
                    dict(detail, via="graphql")
            if field == "addComment":
                repo, number = self._pr_target(tok, inp.get("subjectId", ""), "issues")
                c = self.api.add_comment(repo, number, inp.get("body") or "")
                return 200, {"data": {field: {"commentEdge": {"node": {"id": c["node_id"], "url": c["html_url"]}}}}}, \
                    "issues.comments.create", repo, {"number": number, "via": "graphql"}
        except ApiError as exc:
            if exc.status in (401,):
                raise
            entry_op = exc.op or (f"graphql.{field}" if field else "unsupported")
            extra = dict(exc.extra)
            repo = extra.pop("repo", None)
            return 200, {"errors": [{"message": exc.message, "type": "UNPROCESSABLE"}], "data": None}, entry_op, repo, \
                dict(extra, error=exc.message, refused=True)
        return 200, {"errors": [{"message": f"mutation not supported by this server: {field or '?'}",
                                 "type": "UNSUPPORTED"}], "data": None}, "unsupported", None, {"mutation": field}


# ── HTTP 서버 ────────────────────────────────────────────────────────────────────────────────

def read_body(handler: BaseHTTPRequestHandler) -> bytes:
    if handler.headers.get("Transfer-Encoding", "").lower() == "chunked":
        chunks = []
        while True:
            size = int(handler.rfile.readline().split(b";")[0].strip() or b"0", 16)
            if size == 0:
                while handler.rfile.readline() not in (b"\r\n", b"\n", b""):
                    pass
                break
            chunks.append(handler.rfile.read(size))
            handler.rfile.readline()
        return b"".join(chunks)
    length = int(handler.headers.get("Content-Length") or 0)
    return handler.rfile.read(length) if length else b""


def parse_auth(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() in ("token", "bearer"):
        return value.strip()
    if scheme.lower() == "basic":
        try:
            user, _, pw = base64.b64decode(value.strip()).decode().partition(":")
        except (ValueError, UnicodeDecodeError):
            return None
        return pw or user
    return None


def make_server_handler(state: State, api: Api, gql: GraphQL, root: Path, web: Passthrough | None = None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "GitHub.com"

        def log_message(self, *a):
            pass

        def host(self) -> str:
            return (self.headers.get("Host") or "").split(":")[0].lower()

        def token(self):
            raw = parse_auth(self.headers.get("Authorization"))
            info = state.tokens.get(raw) if raw else None
            return raw, info

        def send(self, status: int, body, headers: dict | None = None, ctype="application/json; charset=utf-8"):
            data = b"" if body is None else body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            if body is not None:
                self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-GitHub-Request-Id", f"SBX:{next(state.ids)}")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def dispatch(self):
            host = self.host()
            url = urllib.parse.urlsplit(self.path)
            try:
                if host == GIT_HOST and re.search(r"/(info/refs|git-upload-pack|git-receive-pack)$", url.path):
                    return self.git(url)
                if host == API_HOST:
                    return self.api(url)
                if host == RAW_HOST:
                    return self.raw(url)
                if host == GIT_HOST and self.command in READ_METHODS and web is not None:
                    return self.public_web(url)
                self.fail(404, "Not Found", op="unsupported", path=url.path)
            except Exception as exc:  # noqa: BLE001 — 대역 버그가 요청을 끊지 않게 500으로 답하고 기록한다
                self.fail(500, f"internal error: {exc}", op="error", path=url.path)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = dispatch

        def fail(self, status, message, op=None, repo=None, path=None, token=None, **extra):
            state.record(host=self.host(), method=self.command, path=path or self.path, status=status,
                         op=op or "error", repo=repo, token=token,
                         write=(op in WRITE_OPS) or (self.command not in READ_METHODS and "/graphql" not in (path or "")),
                         detail=dict(extra, message=message))
            hdr = {"WWW-Authenticate": 'Basic realm="GitHub"'} if status == 401 and self.host() == GIT_HOST else None
            if self.host() in (GIT_HOST, RAW_HOST):
                self.send(status, message.encode() + b"\n", hdr, ctype="text/plain")
            else:
                self.send(status, {"message": message, "documentation_url": "https://docs.github.com/rest",
                                   "status": str(status)}, hdr)

        # api.github.com
        def api(self, url):
            raw, tok = self.token()
            if raw and tok is None:
                return self.fail(401, "Bad credentials", op="auth")
            body = read_body(self)
            payload = None
            if body:
                try:
                    if self.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    payload = json.loads(body)
                except ValueError:
                    return self.fail(400, "Problems parsing JSON", op="error")
            path = url.path.rstrip("/") or "/"
            if path.startswith("/api/v3"):
                path = path[len("/api/v3"):] or "/"
            tid = tok["id"] if tok else None
            try:
                if path == "/graphql" and self.command == "POST":
                    status, data, op, repo, detail = gql.handle(tok, payload or {})
                else:
                    if tok is None:
                        raise ApiError(401, "Requires authentication")
                    status, data, op, repo, detail = api.handle(self.command, path, urllib.parse.parse_qs(url.query),
                                                                tok, payload, self.headers.get("Accept"))
            except ApiError as exc:
                return self.fail(exc.status, exc.message, op=exc.op or "error", path=url.path, token=tid,
                                 repo=self.repo_of(path), **exc.extra)
            write = op in WRITE_OPS or (path != "/graphql" and self.command not in READ_METHODS) or \
                (op == "unsupported" and isinstance(detail, dict) and "mutation" in detail)
            state.record(host=API_HOST, method=self.command, path=url.path, status=status, op=op, repo=repo,
                         token=tid, write=write, detail=detail)
            if isinstance(data, (bytes, bytearray)):
                return self.send(status, bytes(data))
            self.send(status, data)

        @staticmethod
        def repo_of(path: str) -> str | None:
            m = re.match(r"/repos/([^/]+/[^/]+)", path)
            return state.repos.canonical(m.group(1)) if m else None

        # github.com의 git 밖 GET(릴리스 내려받기·아카이브 등): 자격 증명 없이 실제 github.com에 묻고 그대로 돌려준다.
        # 공개 자료만 보인다. 릴리스는 objects.githubusercontent.com으로 리다이렉트되고, 그쪽은 대역이 아니다.
        def public_web(self, url):
            status, headers, body = web.request("GET", self.path, None, {"Accept": self.headers.get("Accept", "*/*")})
            state.record(host=GIT_HOST, method=self.command, path=url.path, status=status, op="web.passthrough",
                         write=False)
            self.send(status, body, {k: v for k, v in headers.items() if k.lower() == "location"},
                      ctype=headers.get("Content-Type", headers.get("content-type", "application/octet-stream")))

        # raw.githubusercontent.com/<owner>/<repo>/<ref>/<path>
        def raw(self, url):
            raw_tok, tok = self.token()
            parts = urllib.parse.unquote(url.path).strip("/").split("/", 3)
            if len(parts) < 4:
                return self.fail(404, "404: Not Found", op="raw")
            repo = state.repos.canonical(f"{parts[0]}/{parts[1]}")
            try:
                if repo is None:
                    raise ApiError(404, "404: Not Found")
                state.authorize(tok, repo, "contents", False)
            except ApiError as exc:
                return self.fail(404 if exc.status in (401, 403) else exc.status, "404: Not Found", op="raw", repo=repo)
            # 브랜치 이름에 /가 있을 수 있다(reconcile/fix) — 실제처럼 앞에서부터 가장 긴 ref를 찾는다.
            segs = (parts[2] + "/" + parts[3]).split("/")
            p = state.repos.path(repo)
            r = None
            for i in range(len(segs) - 1, 0, -1):
                ref, path = "/".join(segs[:i]), "/".join(segs[i:])
                sha = state.repos.rev(repo, f"refs/heads/{ref}") or state.repos.rev(repo, ref)
                if sha:
                    r = subprocess.run(["git", "--git-dir", str(p), "cat-file", "blob", f"{sha}:{path}"],
                                       capture_output=True)
                    break
            if r is None or r.returncode != 0:
                return self.fail(404, "404: Not Found", op="raw", repo=repo)
            state.record(host=RAW_HOST, method=self.command, path=url.path, status=200, op="raw", repo=repo,
                         token=tok["id"] if tok else None, write=False)
            self.send(200, r.stdout, ctype="text/plain; charset=utf-8")

        # github.com git smart HTTP → git http-backend
        def git(self, url):
            m = re.match(r"^/([^/]+)/([^/]+?)(?:\.git)?/(info/refs|git-upload-pack|git-receive-pack)$", url.path)
            if not m:
                return self.fail(404, "Not Found", op="unsupported")
            owner, name, endpoint = m.groups()
            q = urllib.parse.parse_qs(url.query)
            service = q.get("service", [""])[0] if endpoint == "info/refs" else endpoint
            push = service == "git-receive-pack"
            repo = state.repos.canonical(f"{owner}/{name}")
            raw_tok, tok = self.token()
            op = "git.push" if push else "git.fetch"
            if raw_tok is None:
                return self.fail(401, "Authentication required", op="git.auth", repo=repo)
            if tok is None:
                return self.fail(401, "Invalid username or token. Password authentication is not supported.",
                                 op="git.auth", repo=repo)
            try:
                if repo is None:
                    raise ApiError(404, "Repository not found.")
                state.authorize(tok, repo, "contents", push)
            except ApiError as exc:
                msg = "Repository not found." if exc.status == 404 else \
                    f"Permission to {owner}/{name}.git denied to {BOT_LOGIN}."
                return self.fail(exc.status if exc.status != 401 else 401, msg, op=op, repo=repo, token=tok["id"])
            body = read_body(self)
            before = state.repos.refs(repo) if push and endpoint != "info/refs" else None
            git_dir = state.repos.path(repo)
            env = dict(os.environ,
                       GIT_PROJECT_ROOT=str(git_dir.parent), GIT_HTTP_EXPORT_ALL="1",
                       PATH_INFO=f"/{git_dir.name}/{endpoint}", QUERY_STRING=url.query,
                       REQUEST_METHOD=self.command, CONTENT_TYPE=self.headers.get("Content-Type", ""),
                       CONTENT_LENGTH=str(len(body)), REMOTE_USER=BOT_LOGIN, REMOTE_ADDR="127.0.0.1",
                       GIT_PROTOCOL=self.headers.get("Git-Protocol", ""),
                       HTTP_CONTENT_ENCODING=self.headers.get("Content-Encoding", ""))
            r = subprocess.run(["git", "http-backend"], input=body, capture_output=True, env=env)
            if r.returncode != 0 and not r.stdout:
                return self.fail(500, "git http-backend failed", op=op, repo=repo, token=tok["id"],
                                 stderr=r.stderr.decode("utf-8", "replace")[-400:])
            head, _, out = r.stdout.partition(b"\r\n\r\n")
            if not _:
                head, _, out = r.stdout.partition(b"\n\n")
            status, headers = 200, {}
            for line in head.decode("latin-1").splitlines():
                k, _, v = line.partition(":")
                if k.lower() == "status":
                    status = int(v.strip().split()[0])
                elif k:
                    headers[k.strip()] = v.strip()
            ctype = headers.pop("Content-Type", "application/octet-stream")
            detail = None
            if before is not None:
                after = state.repos.refs(repo)
                updates = []
                for ref in sorted(set(before) | set(after)):
                    old, new = before.get(ref, NULL_SHA), after.get(ref, NULL_SHA)
                    if old != new:
                        forced = old != NULL_SHA and new != NULL_SHA and not state.repos.is_ancestor(repo, old, new)
                        updates.append({"ref": ref, "old": old, "new": new, "forced": forced})
                rejected = r.stderr.decode("utf-8", "replace").strip()[-400:] if r.returncode else None
                detail = {"updates": updates, "default_branch": state.repos.default_branch(repo)}
                if rejected:
                    detail["stderr"] = rejected
                if b"remote rejected" in out or b"pre-receive hook declined" in out:
                    detail["rejected"] = True
            state.record(host=GIT_HOST, method=self.command, path=url.path, status=status,
                         op=op if endpoint != "info/refs" else f"{op}.advertise", repo=repo, token=tok["id"],
                         write=bool(push and endpoint != "info/refs"), detail=detail)
            self.send(status, out, headers, ctype=ctype)

    return Handler


def apply_seed(state: State, api: Api, seed: dict) -> None:
    """무대가 미리 갖춰 둔 브랜치·PR·status. 스킬의 쓰기와 구분되게 seed.* (write false)로 기록한다.

    branches: [{repository, name, sha}] — 미러에 이미 있는 커밋(refs/pull/* 포함)에 브랜치를 건다. 실제 PR의 head 커밋을
    대역 PR로 다시 세울 때 쓴다(실제 PR과 같은 head 브랜치 이름이면 실제 GitHub처럼 중복 PR로 거절되므로 다른 이름)."""
    for spec in seed.get("branches") or []:
        repo = state.repos.canonical(spec["repository"])
        if repo is None:
            raise SystemExit(f"seed: 레포 없음 {spec['repository']}")
        sha = state.repos.rev(repo, spec["sha"])
        if not sha:
            raise SystemExit(f"seed: {repo}에 커밋 {spec['sha']}이 없음")
        state.repos.git(repo, "update-ref", f"refs/heads/{spec['name']}", sha)
        state.record(source="seed", op="seed.branch", repo=repo, write=False,
                     detail={"name": spec["name"], "sha": sha})
    for spec in seed.get("pulls") or []:
        repo = state.repos.canonical(spec["repository"])
        if repo is None:
            raise SystemExit(f"seed: 레포 없음 {spec['repository']}")
        pr = api.create_pr(repo, spec["title"], spec["head"], spec.get("base") or "main", spec.get("body"),
                           spec.get("draft", False))
        if spec.get("number") and pr["number"] != spec["number"]:
            raise SystemExit(f"seed: PR 번호 {pr['number']} ≠ 기대 {spec['number']}")
        refresh_pr(state, repo, pr)
        state.record(source="seed", op="seed.pull", repo=repo, write=False,
                     detail={"number": pr["number"], "head": pr["head"]["ref"], "head_sha": pr["head"]["sha"]})
    for spec in seed.get("statuses") or []:
        repo = state.repos.canonical(spec["repository"])
        if repo is None:
            raise SystemExit(f"seed: 레포 없음 {spec['repository']}")
        st = api.add_status(repo, spec["sha"].lower(), spec, "seed")
        state.record(source="seed", op="seed.status", repo=repo, write=False,
                     detail={"sha": spec["sha"], "context": st["context"], "state": st["state"]})


def make_admin_handler(state: State, api: Api):
    class Admin(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def send(self, status, body):
            data = json.dumps(body, ensure_ascii=False, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/_sandbox/health":
                return self.send(200, {"ok": True, "repos": state.repos.all()})
            if self.path == "/_sandbox/state":
                return self.send(200, state.snapshot())
            self.send(404, {"message": "Not Found"})

        def do_POST(self):
            try:
                payload = json.loads(read_body(self) or b"{}")
                if self.path == "/_sandbox/tokens":
                    return self.send(200, state.mint(payload.get("repositories"), payload.get("permissions")))
                if self.path == "/_sandbox/statuses":  # MCP github_commit_status_create (owner = 설치 계정)
                    owners = sorted({r.split("/")[0] for r in state.repos.all()})
                    name = str(payload.get("repository") or "")
                    repo = next((c for o in owners if (c := state.repos.canonical(f"{o}/{name}"))), None)
                    if repo is None:
                        raise ApiError(404, f"repository {name!r} is not installed for the App")
                    st = api.add_status(repo, str(payload.get("sha", "")).lower(), payload, "mcp")
                    state.record(source="mcp", op="statuses.create", repo=repo, write=True, status=201,
                                 detail={"sha": payload.get("sha"), "context": st["context"], "state": st["state"],
                                         "via": "mcp:github_commit_status_create"})
                    return self.send(201, dict(st, repository=repo, sha=payload.get("sha")))
            except ApiError as exc:
                return self.send(exc.status, {"message": exc.message})
            except ValueError:
                return self.send(400, {"message": "bad json"})
            self.send(404, {"message": "Not Found"})

    return Admin


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", type=Path, required=True, help="샌드박스 루트(git/<owner>/<repo>.git, rules.json)")
    p.add_argument("--cert", type=Path, help="TLS 인증서(github.com·api.github.com·raw 이름 포함)")
    p.add_argument("--key", type=Path)
    p.add_argument("--port", type=int, default=443)
    p.add_argument("--admin-port", type=int, default=8766)
    p.add_argument("--log", type=Path, help="요청 기록 JSONL")
    p.add_argument("--passthrough-token-file", type=Path,
                   help="read passthrough용 실제 읽기 토큰 파일(읽은 뒤 지운다). 없으면 모르는 읽기는 404")
    p.add_argument("--pr-number-base", type=int, default=DEFAULT_PR_BASE)
    p.add_argument("--seed", type=Path, help="시작 때 심을 PR·status(JSON, 머리말 「시드」)")
    p.add_argument("--plain", action="store_true", help="TLS 없이(테스트용)")
    p.add_argument("--no-public-web", action="store_true", help="github.com의 git 밖 GET을 실제로 묻지 않는다")
    p.add_argument("--synthetic-ci", choices=SYNTHETIC_CI_MODES, default="success",
                   help="대역 PR 합성 CI 결론: success · failure(매 head) · fail-first(첫 head만) · off")
    p.add_argument("--no-synthetic-ci", action="store_true", help="--synthetic-ci off와 같다")
    p.add_argument("--human-status-prefixes", default="review/",
                   help="합성하지 않을 사람 승인 status context 접두어(쉼표 구분)")
    args = p.parse_args(argv)

    rules = {}
    rules_file = args.root / "rules.json"
    if rules_file.is_file():
        rules = {k.lower(): v for k, v in json.loads(rules_file.read_text(encoding="utf-8")).items()}
    state = State(Repos(args.root), args.log, args.pr_number_base, rules,
                  synthetic_ci="off" if args.no_synthetic_ci else args.synthetic_ci,
                  human_status_prefixes=tuple(x.strip() for x in args.human_status_prefixes.split(",") if x.strip()))
    passthrough = None
    if args.passthrough_token_file:
        token = args.passthrough_token_file.read_text(encoding="utf-8").strip()
        args.passthrough_token_file.unlink()  # 환경 변수·파일 어디에도 남기지 않는다
        if token:
            passthrough = Passthrough(token)  # 실제 주소는 지금(hosts가 바뀌기 전) 푼다
    api = Api(state, passthrough)
    gql = GraphQL(state, api, passthrough)
    if args.seed:
        apply_seed(state, api, json.loads(args.seed.read_text(encoding="utf-8")))
    web = None
    if not args.no_public_web:
        try:
            web = Passthrough("", host=GIT_HOST)  # 공개 github.com 읽기(자격 증명 없음) — 실제 주소는 지금 푼다
        except OSError as exc:
            print(f"github-stub: public web passthrough off ({exc})", flush=True)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_server_handler(state, api, gql, args.root, web))
    if not args.plain:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(args.cert), str(args.key))
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    admin = ThreadingHTTPServer(("127.0.0.1", args.admin_port), make_admin_handler(state, api))
    threading.Thread(target=admin.serve_forever, daemon=True).start()
    print(f"github-stub: listening on {'http' if args.plain else 'https'}://127.0.0.1:{args.port} "
          f"(admin http://127.0.0.1:{args.admin_port}) repos={state.repos.all()} "
          f"passthrough={'on' if passthrough else 'off'} public_web={'on' if web else 'off'} "
          f"synthetic_ci={state.synthetic_ci} rules={sorted(rules)}",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
