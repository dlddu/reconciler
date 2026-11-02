#!/usr/bin/env python3
"""스킬 빌드 test의 GitHub 샌드박스 준비·해제 — 스킬이 닿는 GitHub를 러너 안의 대역(github_stub.py)으로 바꾼다.

  repos-for-model <reconciler> <model_id> [--owner dlddu]
        그 ToBeModel 데이터 소스가 가리키는 대상 레포(owner/name)를 쉼표로 출력한다(미러링·읽기 토큰 범위).
  mirror --root R --repos o/a,o/b --token-env NAME [--reconciler-bare PATH --reconciler-repo o/reconciler]
        대상 레포를 `R/git/<owner>/<repo>.git`에 bare 미러로 받는다(refs/pull/* 포함 — 실제 PR 머지용).
        미러의 원격은 지운다: 대역이 받은 push가 어디로도 다시 나가지 않는다. 기본 브랜치의 ruleset을 읽어
        `R/rules.json`과 pre-receive 훅으로 옮긴다(실제처럼 기본 브랜치 직접 push 거절). reconciler는
        러너가 이미 만든 샌드박스 원격(bare)을 같은 자리에 링크한다 — 새로 clone해도 샌드박스로 간다.
  certs --root R
        자체 CA와 github.com · api.github.com · raw.githubusercontent.com 인증서를 만든다.
  start --root R --log L [--token-env NAME] [--port 443] [--admin-port 8766] [--no-synthetic-ci]
        대역을 띄우고 준비될 때까지 기다린다. 기본으로 대역 PR에 합성 CI(성공)를 붙인다(github_stub.py 머리말). 읽기 토큰은 환경 변수가 아니라 0600 파일로 넘기고 대역이 읽은 뒤 지운다.
  enable --root R [--env-file $GITHUB_ENV]
        CA를 시스템 신뢰 목록에 넣고 /etc/hosts에서 세 호스트를 127.0.0.1로 돌린다(sudo). 에이전트용 CA 환경 변수
        (NODE_EXTRA_CA_CERTS · REQUESTS_CA_BUNDLE · SSL_CERT_FILE)를 env 파일에 쓴다.
  disable --root R
        hosts·CA를 원래대로 돌린다(대역 기록은 남긴다).
  summary --log L [--markdown OUT]
        대역 기록을 쓰기 위주로 요약한다(작업 요약·아티팩트용).

이 순서가 중요하다: mirror·start(실제 주소 풀이)는 hosts를 바꾸기 **전**에, enable은 에이전트 실행 직전에.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HOSTS = ("github.com", "api.github.com", "raw.githubusercontent.com")
MARK_BEGIN = "# >>> reconciler github sandbox >>>"
MARK_END = "# <<< reconciler github sandbox <<<"
CA_DEST = Path("/usr/local/share/ca-certificates/reconciler-github-sandbox.crt")
SYSTEM_BUNDLE = "/etc/ssl/certs/ca-certificates.crt"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BLOCKING_RULES = ("pull_request", "update", "required_status_checks")
# 대역 프로세스에 넘기지 않을 환경 변수(토큰·키). GIT_CONFIG_KEY_<n> 같은 설정 변수는 남긴다.
SECRET_ENV = re.compile(r"(^|_)(TOKEN|SECRET|PASSWORD|CREDENTIALS?)(_|$)|_KEY$|^GH_|^ACTIONS_ID_TOKEN")


def sudo() -> list[str]:
    return [] if os.geteuid() == 0 else ["sudo", "-n"]


def sbin(name: str) -> str:
    """update-ca-certificates·sysctl은 /usr/sbin에 있다 — PATH에 sbin이 없어도 찾는다."""
    return shutil.which(name) or shutil.which(name, path="/usr/local/sbin:/usr/sbin:/sbin") or name


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


# ── 대상 레포 ────────────────────────────────────────────────────────────────────────────────

def collect_repos(node, found: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "repository" and isinstance(value, str) and REPO_RE.match(value):
                found.append(value)
            else:
                collect_repos(value, found)
    elif isinstance(node, list):
        for item in node:
            collect_repos(item, found)


def repos_for_model(reconciler: Path, model_id: str, owner: str | None = None) -> list[str]:
    models = json.loads((reconciler / "data" / "to-be-models.json").read_text(encoding="utf-8"))
    model = next((m for m in models if m.get("id") == model_id), None)
    if model is None:
        raise SystemExit(f"모델 {model_id}를 찾지 못함")
    found: list[str] = []
    collect_repos(model, found)
    out = []
    for full in found:
        if owner and full.split("/")[0].lower() != owner.lower():
            continue
        if full.split("/")[1].lower() == "reconciler":
            continue
        if full.lower() not in {o.lower() for o in out}:
            out.append(full)
    return out


# ── 미러 · 규칙 ───────────────────────────────────────────────────────────────────────────────

def github_get(path: str, token: str):
    req = urllib.request.Request(f"https://api.github.com{path}", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "reconciler-sandbox"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        print(f"::warning::{path}: HTTP {exc.code} — 규칙 없이 진행", file=sys.stderr)
        return None


def parse_rules(rules: list) -> dict:
    out: dict = {"required_status_checks": [], "types": []}
    for rule in rules or []:
        typ = rule.get("type")
        out["types"].append(typ)
        if typ == "required_status_checks":
            for check in (rule.get("parameters") or {}).get("required_status_checks") or []:
                if check.get("context") and check["context"] not in out["required_status_checks"]:
                    out["required_status_checks"].append(check["context"])
        if typ == "deletion":
            out["deletion"] = True
        if typ == "non_fast_forward":
            out["non_fast_forward"] = True
    out["types"] = sorted(set(out["types"]))
    out["blocks_direct_push"] = any(t in BLOCKING_RULES for t in out["types"])
    return out


PRE_RECEIVE = """#!/bin/sh
# 샌드박스: 실제 레포의 ruleset을 옮긴 것 — 보호 브랜치에 직접 push·삭제·강제 push를 거절한다.
rules="$(dirname "$0")/sandbox-rules"
zero=0000000000000000000000000000000000000000
status=0
while read old new ref; do
  branch=${ref#refs/heads/}
  line=$(grep -F -x -e "block $branch" -e "nonff $branch" -e "nodelete $branch" "$rules" 2>/dev/null)
  [ -z "$line" ] && continue
  if [ "$new" = "$zero" ] && echo "$line" | grep -q "^nodelete "; then
    echo "error: GH013: Repository rule violations found for $ref. Cannot delete this branch"; status=1; continue
  fi
  if echo "$line" | grep -q "^block "; then
    echo "error: GH013: Repository rule violations found for $ref."
    echo "- Changes must be made through a pull request."; status=1; continue
  fi
  if [ "$old" != "$zero" ] && [ "$new" != "$zero" ] && ! git merge-base --is-ancestor "$old" "$new" 2>/dev/null \\
     && echo "$line" | grep -q "^nonff "; then
    echo "error: GH013: Repository rule violations found for $ref. Cannot force-push to this branch"; status=1
  fi
done
exit $status
"""


def install_hook(bare: Path, branch_rules: dict) -> None:
    lines = []
    for branch, rule in branch_rules.items():
        if rule.get("blocks_direct_push"):
            lines.append(f"block {branch}")
        if rule.get("non_fast_forward"):
            lines.append(f"nonff {branch}")
        if rule.get("deletion"):
            lines.append(f"nodelete {branch}")
    (bare / "hooks").mkdir(exist_ok=True)
    (bare / "hooks" / "sandbox-rules").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    hook = bare / "hooks" / "pre-receive"
    hook.write_text(PRE_RECEIVE, encoding="utf-8")
    hook.chmod(0o755)


def mirror(root: Path, repos: list[str], token: str | None, reconciler_bare: Path | None,
           reconciler_repo: str | None) -> dict:
    gitroot = root / "git"
    gitroot.mkdir(parents=True, exist_ok=True)
    rules_file = root / "rules.json"  # 무대가 미리 둔 규칙(실행 빌드 픽스처)은 지우지 않고 합친다
    all_rules: dict = json.loads(rules_file.read_text(encoding="utf-8")) if rules_file.is_file() else {}
    for full in repos:
        owner, name = full.split("/", 1)
        dest = gitroot / owner / f"{name}.git"
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["git"]
        if token:
            basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            cmd += ["-c", f"http.extraHeader=Authorization: Basic {basic}"]
        cmd += ["clone", "--mirror", "--quiet", f"https://github.com/{full}.git", str(dest)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            err = r.stderr.replace(token or "\0", "***") if token else r.stderr
            raise SystemExit(f"미러 실패 {full}: {err.strip()[-300:]}")
        # 원격을 지운다 — 미러는 이제 대역의 레포다. 대역이 받은 push가 어디로도 나가지 않는다.
        subprocess.run(["git", "--git-dir", str(dest), "remote", "remove", "origin"], capture_output=True)
        default = subprocess.run(["git", "--git-dir", str(dest), "symbolic-ref", "--short", "HEAD"],
                                 capture_output=True, text=True).stdout.strip() or "main"
        branch_rules = {}
        if token:
            rules = github_get(f"/repos/{full}/rules/branches/{default}", token)
            if isinstance(rules, list):
                branch_rules[default] = parse_rules(rules)
        install_hook(dest, branch_rules)
        if branch_rules:
            all_rules[full] = branch_rules
        print(f"mirrored {full} (default {default}; rules {branch_rules.get(default, {}).get('types', [])})")
    if reconciler_bare and reconciler_repo:
        owner, name = reconciler_repo.split("/", 1)
        link = gitroot / owner / f"{name}.git"
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.exists():
            link.unlink() if link.is_symlink() else shutil.rmtree(link)
        link.symlink_to(reconciler_bare.resolve(), target_is_directory=True)
        print(f"linked {reconciler_repo} -> {reconciler_bare}")
    rules_file.write_text(json.dumps(all_rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return all_rules


# ── 인증서 · 호스트 ────────────────────────────────────────────────────────────────────────────

def certs(root: Path) -> Path:
    tls = root / "tls"
    tls.mkdir(parents=True, exist_ok=True)
    ca_key, ca_crt = tls / "ca.key", tls / "ca.crt"
    key, csr, crt, ext = tls / "server.key", tls / "server.csr", tls / "server.crt", tls / "server.ext"
    run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-keyout", str(ca_key),
         "-out", str(ca_crt), "-subj", "/CN=reconciler github sandbox CA",
         "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign"])
    run(["openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(csr),
         "-subj", "/CN=github.com"])
    ext.write_text("basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n"
                   "extendedKeyUsage=serverAuth\nsubjectAltName=" + ",".join(f"DNS:{h}" for h in HOSTS) + "\n")
    run(["openssl", "x509", "-req", "-in", str(csr), "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial",
         "-days", "2", "-out", str(crt), "-extfile", str(ext)])
    for f in (ca_key, key):
        f.chmod(0o600)
    return ca_crt


def strip_block(text: str) -> str:
    return re.sub(rf"\n?{re.escape(MARK_BEGIN)}.*?{re.escape(MARK_END)}\n?", "\n", text, flags=re.S).rstrip("\n") + "\n"


def write_root_file(path: str, content: str) -> None:
    subprocess.run([*sudo(), "tee", path], input=content, text=True, check=True, stdout=subprocess.DEVNULL)


def enable(root: Path, env_file: str | None, hosts_file: str = "/etc/hosts") -> None:
    ca = root / "tls" / "ca.crt"
    if not ca.is_file():
        raise SystemExit("CA가 없음 — certs 먼저")
    subprocess.run([*sudo(), "cp", str(ca), str(CA_DEST)], check=True)
    subprocess.run([*sudo(), sbin("update-ca-certificates")], check=True, capture_output=True)
    current = Path(hosts_file).read_text(encoding="utf-8")
    block = "\n".join([MARK_BEGIN, *(f"127.0.0.1 {h}" for h in HOSTS), MARK_END])
    write_root_file(hosts_file, strip_block(current) + block + "\n")
    env = {"NODE_EXTRA_CA_CERTS": str(ca), "REQUESTS_CA_BUNDLE": SYSTEM_BUNDLE, "SSL_CERT_FILE": SYSTEM_BUNDLE,
           "CURL_CA_BUNDLE": SYSTEM_BUNDLE, "GIT_SSL_CAINFO": SYSTEM_BUNDLE}
    if env_file:
        with open(env_file, "a", encoding="utf-8") as fh:
            fh.writelines(f"{k}={v}\n" for k, v in env.items())
    print("enabled: " + ", ".join(HOSTS) + " -> 127.0.0.1")


def disable(root: Path, hosts_file: str = "/etc/hosts") -> None:
    current = Path(hosts_file).read_text(encoding="utf-8")
    if MARK_BEGIN in current:
        write_root_file(hosts_file, strip_block(current))
    if CA_DEST.exists():
        subprocess.run([*sudo(), "rm", "-f", str(CA_DEST)], check=False)
        subprocess.run([*sudo(), sbin("update-ca-certificates"), "--fresh"], check=False, capture_output=True)
    print("disabled")


# ── 대역 기동 ─────────────────────────────────────────────────────────────────────────────────

def start(root: Path, log: Path, token: str | None, port: int, admin_port: int, stub_log: Path,
          synthetic_ci: bool = True) -> int:
    if port < 1024 and os.geteuid() != 0:  # 대역은 러너 사용자로 돈다 — 443에 바인드하도록 낮은 포트를 연다
        subprocess.run([*sudo(), sbin("sysctl"), "-q", "-w", f"net.ipv4.ip_unprivileged_port_start={port}"], check=True)
    args = [sys.executable, str(Path(__file__).with_name("github_stub.py")), "--root", str(root),
            "--cert", str(root / "tls" / "server.crt"), "--key", str(root / "tls" / "server.key"),
            "--port", str(port), "--admin-port", str(admin_port), "--log", str(log)]
    if not synthetic_ci:
        args.append("--no-synthetic-ci")
    if (root / "seed.json").is_file():  # 무대가 심어 둔 PR·status(실행 빌드 픽스처)
        args += ["--seed", str(root / "seed.json")]
    if token:
        fd, path = tempfile.mkstemp(prefix="pt-", dir=str(root))
        os.write(fd, token.encode())
        os.close(fd)
        os.chmod(path, 0o600)
        args += ["--passthrough-token-file", path]
    log.parent.mkdir(parents=True, exist_ok=True)
    log.touch()
    env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}
    with stub_log.open("a") as out:
        proc = subprocess.Popen(args, stdout=out, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    for _ in range(60):
        if proc.poll() is not None:
            raise SystemExit("대역 기동 실패:\n" + stub_log.read_text()[-2000:])
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{admin_port}/_sandbox/health", timeout=2) as resp:
                print("stub ready:", resp.read().decode())
                (root / "stub.pid").write_text(str(proc.pid))
                return proc.pid
        except OSError:
            time.sleep(0.5)
    raise SystemExit("대역이 준비되지 않음:\n" + stub_log.read_text()[-2000:])


# ── 요약 ─────────────────────────────────────────────────────────────────────────────────────

def load_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(entries: list[dict]) -> str:
    writes = [e for e in entries if e.get("write") or e.get("op") in ("statuses.create",)]
    unsupported = [e for e in entries if e.get("op") == "unsupported"]
    reads = [e for e in entries if not e.get("write") and e.get("op") not in ("unsupported", "token.mint")]
    passthrough = [e for e in reads if e.get("op") in ("passthrough", "graphql.passthrough")
                   or (e.get("detail") or {}).get("passthrough")]
    mints = [e for e in entries if e.get("op") == "token.mint"]
    synthetic = [e for e in entries if e.get("op") == "ci.synthetic"]
    out = ["### GitHub 샌드박스 기록",
           f"- 요청 {len(entries)}건 · 쓰기 {len(writes)}건 · 읽기 {len(reads)}건(실제 GitHub 읽기 중계 {len(passthrough)}건) · "
           f"토큰 발급 {len(mints)}건 · 미지원 {len(unsupported)}건"]
    for m in mints:
        d = m.get("detail") or {}
        out.append(f"  - 토큰 `{m.get('token')}` repos={d.get('repositories') or '전체'} perms={d.get('permissions') or '전체'}")
    for e in synthetic:
        d = e.get("detail") or {}
        out.append(f"  - 합성 CI(성공, 실제로 돌지 않음) {e.get('repo')} #{d.get('number')} @ `{str(d.get('sha'))[:7]}`: "
                   + ", ".join(d.get("contexts") or []))
    if writes:
        out.append("\n| # | 작업 | 레포 | 결과 | 내용 |\n| --- | --- | --- | --- | --- |")
        for e in writes:
            d = e.get("detail") or {}
            what = d.get("html_url") or d.get("merge_commit_sha") or d.get("context") or ""
            if e.get("op") == "git.push":
                what = "; ".join(f"{u['ref']} {u['old'][:7]}→{u['new'][:7]}{' (force)' if u.get('forced') else ''}"
                                 for u in d.get("updates") or []) or "(변경 없음)"
            if d.get("message"):
                what = (what + " " if what else "") + str(d["message"]).splitlines()[0][:120]
            if d.get("refused") or d.get("rejected"):
                what = ("**거절됨** " + what).strip()
            out.append(f"| {e.get('seq')} | `{e.get('op')}` | {e.get('repo') or '-'} | {e.get('status')} | {what} |")
    if unsupported:
        out.append("\n**대역이 모르는 요청** (대역을 넓혀야 할 수 있음)")
        out += [f"- `{e.get('method')} {e.get('host')}{e.get('path')}` → {e.get('status')}" for e in unsupported[:20]]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("repos-for-model")
    s.add_argument("reconciler", type=Path)
    s.add_argument("model_id")
    s.add_argument("--owner", default="dlddu")
    s = sub.add_parser("mirror")
    s.add_argument("--root", type=Path, required=True)
    s.add_argument("--repos", default="")
    s.add_argument("--token-env", default="")
    s.add_argument("--reconciler-bare", type=Path)
    s.add_argument("--reconciler-repo", default="dlddu/reconciler")
    s = sub.add_parser("certs")
    s.add_argument("--root", type=Path, required=True)
    s = sub.add_parser("start")
    s.add_argument("--root", type=Path, required=True)
    s.add_argument("--log", type=Path, required=True)
    s.add_argument("--token-env", default="")
    s.add_argument("--port", type=int, default=443)
    s.add_argument("--admin-port", type=int, default=8766)
    s.add_argument("--stub-log", type=Path)
    s.add_argument("--no-synthetic-ci", action="store_true")
    s = sub.add_parser("enable")
    s.add_argument("--root", type=Path, required=True)
    s.add_argument("--env-file", default=os.environ.get("GITHUB_ENV"))
    s = sub.add_parser("disable")
    s.add_argument("--root", type=Path, required=True)
    s = sub.add_parser("summary")
    s.add_argument("--log", type=Path, required=True)
    s.add_argument("--markdown", type=Path)
    args = p.parse_args(argv)

    if args.cmd == "repos-for-model":
        print(",".join(repos_for_model(args.reconciler, args.model_id, args.owner)))
    elif args.cmd == "mirror":
        token = os.environ.get(args.token_env) if args.token_env else None
        repos = [r.strip() for r in args.repos.split(",") if r.strip()]
        bad = [r for r in repos if not REPO_RE.match(r)]
        if bad:
            raise SystemExit(f"owner/name 형식이 아님: {bad}")
        mirror(args.root, repos, token, args.reconciler_bare, args.reconciler_repo)
    elif args.cmd == "certs":
        print(certs(args.root))
    elif args.cmd == "start":
        token = os.environ.get(args.token_env) if args.token_env else None
        start(args.root, args.log, token, args.port, args.admin_port, args.stub_log or args.root / "stub.log",
              synthetic_ci=not args.no_synthetic_ci)
    elif args.cmd == "enable":
        enable(args.root, args.env_file)
    elif args.cmd == "disable":
        disable(args.root)
    else:
        text = summarize(load_log(args.log))
        print(text, end="")
        if args.markdown:
            args.markdown.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
