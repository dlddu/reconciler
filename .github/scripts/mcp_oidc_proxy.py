#!/usr/bin/env python3
"""homelab-k3s-mcp를 GitHub Actions OIDC로 호출하는 로컬 중계 프록시.

GitHub OIDC ID 토큰은 약 5분 뒤 만료되는데, 에이전트(mcode) 실행은 수십 분 걸린다. 그래서
`.mcp.json`에 토큰을 박지 않고 이 프록시(`http://127.0.0.1:<port>/mcp`)를 가리키게 하고, 프록시가
요청마다 유효한 토큰을 `Authorization: Bearer`로 붙여 실제 MCP로 넘긴다. 만료가 가까우면
(`--refresh-before`초 이내) 러너의 토큰 엔드포인트에서 새로 받는다.

- 토큰은 프로세스 메모리에만 있다. 에이전트 환경·설정 파일·로그 어디에도 나가지 않는다.
- 127.0.0.1에만 바인드한다(러너 밖에서 접근 불가).
- 응답 본문은 받는 대로 흘려보낸다(JSON이든 SSE든). HTTP/1.0 방식으로 연결 종료가 본문 끝이다.

필요한 환경 변수: ACTIONS_ID_TOKEN_REQUEST_URL, ACTIONS_ID_TOKEN_REQUEST_TOKEN
(job에 `permissions: id-token: write`가 있어야 러너가 넣어 준다).

샌드박스 모드(`--sandbox-admin`, 스킬 빌드 test 전용): GitHub에 닿는 도구를 실제 MCP로 보내지 않고
GitHub 대역(github_stub.py)이 받게 한다. 스킬은 평소처럼 도구를 부르고, 자기가 test 중인지 모른다.

- `github_app_installation_token` → 대역이 발급한 가짜 토큰(같은 `.env` 모양). 진짜 토큰은 에이전트에 닿지 않는다.
- `github_commit_status_create` → 대역의 commit status로 기록.
- `--sandbox-allow-tools`에 적은 도구만 실제 MCP로 보낸다(관측용 읽기 도구). 나머지 도구 호출은 isError로 막는다 —
  허용 목록은 fail-closed다.

오프라인 샌드박스 모드(`--sandbox-admin` + `--offline`, 실제 MCP·OIDC 없음 — 실행 빌드의 격리 무대): 프록시가 MCP 서버
자체가 되어 initialize·tools/list에 직접 답하고, GitHub 도구 두 개(대역으로)와 `ping`만 노출한다. 실제 MCP로는 아무것도
보내지 않는다. `--offline-tools`로 노출할 도구를 그중 일부로 줄일 수 있다 — 운영 워크플로의 OIDC 규칙이 주지 않는 도구
(예: 실행 단계의 `github_commit_status_create`)를 시험에서도 보이지 않게 해, 시험이 운영의 도구 구성을 따르게 한다.
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FORWARD_REQUEST_HEADERS = ("content-type", "accept", "mcp-session-id", "mcp-protocol-version",
                           "last-event-id", "x-session-platform-session-id")
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
              "trailers", "transfer-encoding", "upgrade", "content-length"}


def jwt_exp(token: str) -> float:
    """서명 검증 없이 payload의 exp만 읽는다(갱신 시점 계산용 — 검증은 MCP 서버 몫)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except (IndexError, KeyError, ValueError, TypeError) as exc:
        raise ValueError(f"OIDC 토큰에서 exp를 읽지 못함: {exc}") from exc


class OidcTokenSource:
    """러너 토큰 엔드포인트에서 audience 토큰을 받아 캐시하고, 만료가 가까우면 다시 받는다."""

    def __init__(self, request_url: str, request_token: str, audience: str,
                 refresh_before: float = 90.0, clock=time.time, opener=urllib.request.urlopen):
        if not request_url or not request_token:
            raise ValueError("ACTIONS_ID_TOKEN_REQUEST_URL/TOKEN이 없음 — job에 id-token: write 권한이 필요")
        self._url = request_url
        self._request_token = request_token
        self._audience = audience
        self._refresh_before = refresh_before
        self._clock = clock
        self._open = opener
        self._lock = threading.Lock()
        self._token: str | None = None
        self._exp = 0.0
        self.fetch_count = 0

    def _fetch(self) -> None:
        sep = "&" if "?" in self._url else "?"
        url = f"{self._url}{sep}audience={urllib.parse.quote(self._audience, safe='')}"
        req = urllib.request.Request(url, headers={"Authorization": f"bearer {self._request_token}",
                                                   "Accept": "application/json"})
        with self._open(req, timeout=30) as resp:
            value = json.loads(resp.read().decode("utf-8"))["value"]
        self._exp = jwt_exp(value)
        self._token = value
        self.fetch_count += 1

    def get(self) -> str:
        with self._lock:
            if self._token is None or self._exp - self._clock() <= self._refresh_before:
                self._fetch()
            return self._token  # type: ignore[return-value]


class SandboxPolicy:
    """샌드박스 모드의 tools/call 처리. intercept()가 dict를 돌려주면 그 JSON-RPC result로 바로 답하고,
    None이면 실제 MCP로 중계한다."""

    FAKED = ("github_app_installation_token", "github_commit_status_create")

    def __init__(self, admin_url: str, allow_tools: set[str], timeout: float = 30.0,
                 opener=urllib.request.urlopen):
        self.admin_url = admin_url.rstrip("/")
        self.allow_tools = set(allow_tools)
        self._timeout = timeout
        self._open = opener

    def _admin(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(f"{self.admin_url}{path}", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self._open(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            try:
                detail = json.loads(detail).get("message", detail)
            except ValueError:
                pass
            raise RuntimeError(detail) from exc

    @staticmethod
    def _text(text: str, is_error: bool = False) -> dict:
        result: dict = {"content": [{"type": "text", "text": text}]}
        if is_error:
            result["isError"] = True
        return result

    def intercept(self, msg) -> dict | None:
        if not isinstance(msg, dict) or msg.get("method") != "tools/call":
            return None
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "github_app_installation_token":
                return self._token(args)
            if name == "github_commit_status_create":
                return self._status(args)
        except RuntimeError as exc:
            return self._text(f"{name} failed: {exc}", is_error=True)
        if name in self.allow_tools:
            return None
        return self._text(f"tool {name!r} is not available in this environment", is_error=True)

    def _token(self, args: dict) -> dict:
        minted = self._admin("/_sandbox/tokens", {"repositories": args.get("repositories"),
                                                  "permissions": args.get("permissions")})
        repos = minted.get("repositories")
        perms = minted.get("permissions")
        lines = [f"# Expires at: {minted['expires_at']}",
                 f"# Repository selection: {'selected' if repos else 'all'}"]
        if repos:
            lines.append("# Repositories: " + ", ".join(repos))
        if perms:
            lines.append("# Permissions: " + ", ".join(f"{k}={v}" for k, v in sorted(perms.items())))
        lines.append(f"GITHUB_TOKEN={minted['token']}")
        return {"content": [{"type": "resource", "resource": {  # 실제 서버와 같은 embedded resource 모양
            "uri": "file:///github-token.env", "mimeType": "text/plain", "text": "\n".join(lines) + "\n"}}]}

    def _status(self, args: dict) -> dict:
        missing = [k for k in ("repository", "sha", "state", "context") if not args.get(k)]
        if missing:
            raise RuntimeError("missing required argument(s): " + ", ".join(missing))
        if not re.fullmatch(r"[0-9a-f]{40}", str(args["sha"])):
            raise RuntimeError("sha must be a full 40-character hex commit SHA")
        created = self._admin("/_sandbox/statuses", {k: args.get(k) for k in
                                                     ("repository", "sha", "state", "context", "description",
                                                      "target_url")})
        return self._text(f"Created commit status {created['context']}={created['state']} on "
                          f"{created['repository']}@{created['sha']} (id {created['id']})")


OFFLINE_TOOLS = [
    {"name": "github_app_installation_token",
     "description": "Mint a short-lived GitHub App installation access token (sandbox: issued by the GitHub test double).",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "repositories": {"type": "array", "items": {"type": "string"}},
         "permissions": {"type": "object", "additionalProperties": {"type": "string"}}}}},
    {"name": "github_commit_status_create",
     "description": "Write one commit status on a commit (sandbox: recorded by the GitHub test double).",
     "inputSchema": {"type": "object", "additionalProperties": False,
                     "required": ["repository", "sha", "state", "context"], "properties": {
                         "repository": {"type": "string"}, "sha": {"type": "string"},
                         "state": {"type": "string", "enum": ["error", "failure", "pending", "success"]},
                         "context": {"type": "string"}, "description": {"type": "string"},
                         "target_url": {"type": "string"}}}},
    {"name": "ping", "description": "Health check.", "inputSchema": {"type": "object", "properties": {}}},
]
OFFLINE_PROTOCOL = "2025-06-18"


def offline_answer(msg: dict, sandbox: "SandboxPolicy", tools: list[dict]) -> dict | None:
    """오프라인 모드의 JSON-RPC 응답 본문(result 또는 error). 알림(id 없음)은 None."""
    if "id" not in msg:
        return None
    method = msg.get("method")
    if method == "initialize":
        version = (msg.get("params") or {}).get("protocolVersion") or OFFLINE_PROTOCOL
        return {"result": {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                           "serverInfo": {"name": "homelab-k3s-mcp", "version": "sandbox-offline"}}}
    if method == "ping":
        return {"result": {}}
    if method == "tools/list":
        return {"result": {"tools": tools}}
    if method == "tools/call":
        name = (msg.get("params") or {}).get("name")
        if name == "ping":
            return {"result": {"content": [{"type": "text", "text": "pong"}]}}
        if name not in {t["name"] for t in tools}:
            return {"error": {"code": -32602, "message": f"unknown tool: {name}"}}
        result = sandbox.intercept(msg)
        if result is None:  # 허용 도구라도 오프라인에는 보낼 곳이 없다
            result = sandbox._text(f"tool {name!r} is not available in this environment", is_error=True)
        return {"result": result}
    return {"error": {"code": -32601, "message": f"method not found: {method}"}}


def offline_tools(spec: str) -> list[dict]:
    """`--offline-tools` 값(쉼표 구분)을 노출할 도구 정의로. 비우면 전부, 모르는 이름이면 ValueError."""
    names = [n.strip() for n in (spec or "").split(",") if n.strip()]
    if not names:
        return list(OFFLINE_TOOLS)
    known = {t["name"] for t in OFFLINE_TOOLS}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise ValueError(f"--offline-tools에 모르는 도구: {', '.join(unknown)} (가능: {', '.join(sorted(known))})")
    return [t for t in OFFLINE_TOOLS if t["name"] in names]


def make_offline_handler(sandbox: "SandboxPolicy", tools: list[dict] | None = None, log=print):
    tools = tools or OFFLINE_TOOLS

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"
        server_version = "mcp-oidc-proxy"

        def log_message(self, fmt, *args):
            pass

        def _send(self, status: int, payload: dict | list | None, headers: dict | None = None) -> None:
            data = b"" if payload is None else json.dumps(payload).encode()
            self.send_response(status)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            if payload is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                msg = json.loads(self.rfile.read(length) or b"null")
            except ValueError:
                return self._send(400, {"jsonrpc": "2.0", "id": None,
                                        "error": {"code": -32700, "message": "parse error"}})
            batch = isinstance(msg, list)
            out = []
            for m in (msg if batch else [msg]):
                if not isinstance(m, dict):
                    continue
                ans = offline_answer(m, sandbox, tools)
                if ans is not None:
                    out.append({"jsonrpc": "2.0", "id": m.get("id"), **ans})
                    if m.get("method") == "tools/call":
                        log(f"mcp-oidc-proxy: offline tools/call {(m.get('params') or {}).get('name')} -> "
                            f"{'error' if 'error' in ans or ans['result'].get('isError') else 'ok'}", flush=True)
            if not out:
                return self._send(202, None)
            self._send(200, out if batch else out[0], {"Mcp-Session-Id": "sandbox-offline"})

        def do_GET(self):  # 서버 발신 SSE 스트림은 없다(스펙상 405 허용)
            self._send(405, {"error": "no server-initiated stream"}, {"Allow": "POST, DELETE"})

        def do_DELETE(self):
            self._send(200, {})

    return Handler


def make_handler(upstream: str, tokens: OidcTokenSource, timeout: float, log=print,
                 sandbox: SandboxPolicy | None = None):
    target = urllib.parse.urlsplit(upstream)
    if target.scheme not in ("http", "https") or not target.hostname:
        raise ValueError(f"upstream URL이 올바르지 않음: {upstream}")
    upstream_path = target.path or "/"

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"
        server_version = "mcp-oidc-proxy"

        def log_message(self, fmt, *args):  # 기본 로그(클라이언트 주소 등) 대신 아래 한 줄만 남긴다
            pass

        def _relay(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            if sandbox is not None and body and self._sandboxed(body):
                return
            headers = {k: v for k, v in self.headers.items() if k.lower() in FORWARD_REQUEST_HEADERS}
            try:
                headers["Authorization"] = f"Bearer {tokens.get()}"
            except Exception as exc:  # 토큰 발급 실패는 502로 돌려 에이전트가 원인을 보게 한다
                self._error(502, f"OIDC token request failed: {exc}")
                return
            path = upstream_path
            query = urllib.parse.urlsplit(self.path).query
            if query:
                path += "?" + query
            conn_cls = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
            conn = conn_cls(target.hostname, target.port, timeout=timeout)
            started = time.monotonic()
            try:
                conn.request(self.command, path, body=body, headers=headers)
                resp = conn.getresponse()
                self.send_response(resp.status, resp.reason)
                for key, value in resp.getheaders():
                    if key.lower() not in HOP_BY_HOP:
                        self.send_header(key, value)
                self.end_headers()
                while True:
                    chunk = resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                log(f"mcp-oidc-proxy: {self.command} {resp.status} {int((time.monotonic() - started) * 1000)}ms",
                    flush=True)
            except (OSError, http.client.HTTPException) as exc:
                self._error(502, f"upstream request failed: {exc}")
            finally:
                conn.close()

        def _sandboxed(self, body: bytes) -> bool:
            """샌드박스가 직접 답했으면 True. 배치(JSON 배열) 안의 tools/call은 가로챌 수 없으니 거절한다."""
            try:
                msg = json.loads(body)
            except ValueError:
                return False
            if isinstance(msg, list):
                if any(isinstance(m, dict) and m.get("method") == "tools/call" for m in msg):
                    self._error(400, "batched tools/call is not supported")
                    return True
                return False
            result = sandbox.intercept(msg)
            if result is None:
                return False
            name = (msg.get("params") or {}).get("name")
            log(f"mcp-oidc-proxy: sandbox tools/call {name} -> {'error' if result.get('isError') else 'ok'}",
                flush=True)
            payload = json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": result}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return True

        def _error(self, status: int, message: str) -> None:
            log(f"mcp-oidc-proxy: {self.command} {status} {message}", flush=True)
            payload = json.dumps({"error": message}).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload)
            except OSError:
                pass

        do_POST = do_GET = do_DELETE = _relay

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--upstream", default="", help="실제 MCP 엔드포인트(예: https://.../mcp) — --offline이 아니면 필수")
    parser.add_argument("--audience", default="", help="OIDC 토큰 audience (서버의 MCP_GITHUB_OIDC_AUDIENCE)")
    parser.add_argument("--offline", action="store_true",
                        help="실제 MCP·OIDC 없이 샌드박스 GitHub 도구만 노출(--sandbox-admin 필요)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--refresh-before", type=float, default=90.0, help="만료 몇 초 전에 갱신할지")
    parser.add_argument("--timeout", type=float, default=600.0, help="upstream 요청 타임아웃(초)")
    parser.add_argument("--sandbox-admin", default="",
                        help="샌드박스 모드: GitHub 대역(github_stub.py)의 관리 URL(예: http://127.0.0.1:8766)")
    parser.add_argument("--sandbox-allow-tools", default="",
                        help="샌드박스 모드에서 실제 MCP로 보낼 도구(쉼표 구분). 나머지는 막는다")
    parser.add_argument("--offline-tools", default="",
                        help="오프라인 모드에서 노출할 도구(쉼표 구분, "
                             + ", ".join(t["name"] for t in OFFLINE_TOOLS) + " 중). 비우면 전부")
    args = parser.parse_args(argv)
    sandbox = None
    if args.sandbox_admin:
        allow = {t.strip() for t in args.sandbox_allow_tools.split(",") if t.strip()}
        sandbox = SandboxPolicy(args.sandbox_admin, allow - set(SandboxPolicy.FAKED))
    if args.offline:
        if sandbox is None:
            parser.error("--offline에는 --sandbox-admin이 필요하다")
        try:
            tools = offline_tools(args.offline_tools)
        except ValueError as exc:
            parser.error(str(exc))
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_offline_handler(sandbox, tools))
        print(f"mcp-oidc-proxy: listening on http://127.0.0.1:{args.port}/mcp (offline sandbox: github -> "
              f"{args.sandbox_admin}, tools {[t['name'] for t in tools]})", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0
    if not args.upstream or not args.audience:
        parser.error("--upstream·--audience가 필요하다(--offline이 아니면)")

    tokens = OidcTokenSource(os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", ""),
                             os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", ""),
                             args.audience, refresh_before=args.refresh_before)
    tokens.get()  # 시작 시 한 번 받아 설정 오류를 즉시 드러낸다
    server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                 make_handler(args.upstream, tokens, args.timeout, sandbox=sandbox))
    mode = f" (sandbox: github -> {args.sandbox_admin}, allow {sorted(sandbox.allow_tools)})" if sandbox else ""
    print(f"mcp-oidc-proxy: listening on http://127.0.0.1:{args.port}/mcp -> {args.upstream}{mode}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
