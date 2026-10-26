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
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import sys
import threading
import time
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


def make_handler(upstream: str, tokens: OidcTokenSource, timeout: float, log=print):
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
    parser.add_argument("--upstream", required=True, help="실제 MCP 엔드포인트(예: https://.../mcp)")
    parser.add_argument("--audience", required=True, help="OIDC 토큰 audience (서버의 MCP_GITHUB_OIDC_AUDIENCE)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--refresh-before", type=float, default=90.0, help="만료 몇 초 전에 갱신할지")
    parser.add_argument("--timeout", type=float, default=600.0, help="upstream 요청 타임아웃(초)")
    args = parser.parse_args(argv)

    tokens = OidcTokenSource(os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", ""),
                             os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", ""),
                             args.audience, refresh_before=args.refresh_before)
    tokens.get()  # 시작 시 한 번 받아 설정 오류를 즉시 드러낸다
    server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                 make_handler(args.upstream, tokens, args.timeout))
    print(f"mcp-oidc-proxy: listening on http://127.0.0.1:{args.port}/mcp -> {args.upstream}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
