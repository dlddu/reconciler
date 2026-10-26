#!/usr/bin/env python3
"""MCP 서버(streamable HTTP, JSON-RPC)를 직접 부르는 작은 클라이언트.

워크플로의 사전 점검·토큰 발급용이다. 인증은 붙이지 않는다 — mcp_oidc_proxy.py를 거쳐 부르면
프록시가 OIDC 토큰을 붙인다.

  tools                      노출된 도구 이름을 한 줄에 하나씩 (--json이면 JSON 배열)
  call <tool> [--args JSON]  도구 호출 결과의 text content를 출력
  github-token               github_app_installation_token으로 토큰을 받아 마스킹한 뒤
                             $GITHUB_ENV에 <--env-name>=<token>으로 내보낸다(값은 출력하지 않는다)
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import sys
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2025-06-18"


class McpError(Exception):
    pass


class McpClient:
    def __init__(self, url: str, timeout: float = 120.0):
        self.url = url
        self.timeout = timeout
        self.session_id: str | None = None
        self._ids = itertools.count(1)

    def _post(self, payload: dict) -> dict | None:
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL_VERSION}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers=headers,
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self.session_id = resp.headers.get("Mcp-Session-Id") or self.session_id
                body = resp.read().decode("utf-8")
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise McpError(f"HTTP {exc.code} from MCP: {detail}") from exc
        if "id" not in payload:  # notification
            return None
        if "text/event-stream" in ctype:
            return parse_sse(body, payload["id"])
        if not body.strip():
            raise McpError("MCP가 빈 응답을 돌려줌")
        return json.loads(body)

    def request(self, method: str, params: dict | None = None) -> dict:
        msg = self._post({"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or {}})
        if msg is None:
            raise McpError(f"{method}: 응답 없음")
        if "error" in msg:
            err = msg["error"]
            raise McpError(f"{method}: {err.get('code')} {err.get('message')}")
        return msg.get("result") or {}

    def initialize(self) -> dict:
        result = self.request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                             "clientInfo": {"name": "reconciler-workflow", "version": "1"}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def list_tools(self) -> list[dict]:
        tools, cursor = [], None
        while True:
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools.extend(result.get("tools") or [])
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        text = "\n".join(content_text(c) for c in result.get("content") or [])
        if result.get("isError"):
            raise McpError(f"{name}: {text.strip()[:500]}")
        return text


def content_text(content: dict) -> str:
    """text content와 embedded resource(text)를 같은 방식으로 읽는다.

    github_app_installation_token은 토큰을 `{"type":"resource","resource":{"text":...}}`로 돌려준다.
    """
    if content.get("type") == "text":
        return content.get("text", "")
    if content.get("type") == "resource":
        return (content.get("resource") or {}).get("text", "")
    return ""


def parse_sse(body: str, want_id) -> dict:
    for event in re.split(r"\r?\n\r?\n", body):
        data = "\n".join(line[5:].lstrip() for line in event.splitlines() if line.startswith("data:"))
        if not data:
            continue
        msg = json.loads(data)
        if msg.get("id") == want_id:
            return msg
    raise McpError("SSE 응답에서 결과 메시지를 찾지 못함")


def extract_env_value(text: str, key: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise McpError(f"응답에 {key}= 줄이 없음")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=os.environ.get("MCP_URL", "http://127.0.0.1:8765/mcp"))
    parser.add_argument("--timeout", type=float, default=120.0)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_tools = sub.add_parser("tools")
    p_tools.add_argument("--json", action="store_true")
    p_call = sub.add_parser("call")
    p_call.add_argument("tool")
    p_call.add_argument("--args", default="{}")
    p_tok = sub.add_parser("github-token")
    p_tok.add_argument("--env-name", default="SOURCE_GITHUB_TOKEN")
    p_tok.add_argument("--repositories", default="", help="쉼표 구분 레포 이름(owner 없이). 비우면 설치된 전체")
    p_tok.add_argument("--permissions", default='{"contents":"read","metadata":"read"}')
    args = parser.parse_args(argv)

    client = McpClient(args.url, timeout=args.timeout)
    try:
        client.initialize()
        if args.cmd == "tools":
            names = sorted(t["name"] for t in client.list_tools())
            print(json.dumps(names) if args.json else "\n".join(names))
        elif args.cmd == "call":
            print(client.call_tool(args.tool, json.loads(args.args)))
        else:
            params: dict = {"permissions": json.loads(args.permissions)}
            repos = [r.strip() for r in args.repositories.split(",") if r.strip()]
            if repos:
                params["repositories"] = repos
            token = extract_env_value(client.call_tool("github_app_installation_token", params), "GITHUB_TOKEN")
            print(f"::add-mask::{token}")
            env_file = os.environ.get("GITHUB_ENV")
            if not env_file:
                raise McpError("GITHUB_ENV가 없어 토큰을 내보낼 곳이 없음")
            with open(env_file, "a", encoding="utf-8") as fh:
                fh.write(f"{args.env_name}={token}\n")
            print(f"{args.env_name} exported ({params['permissions']})")
    except (McpError, OSError, ValueError) as exc:
        print(f"::error::MCP 호출 실패: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
