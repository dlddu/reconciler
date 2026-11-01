"""`.github/scripts/mcp_oidc_proxy.py` · `mcp_call.py` 테스트 (python3 -m unittest discover -s tests).

가짜 러너 토큰 엔드포인트와 가짜 MCP 서버를 로컬에 띄워, 프록시가 토큰을 붙여 중계하고 만료 전에
갱신하는지, mcp_call이 그 프록시를 통해 tools/list·tools/call을 하는지 본다. 네트워크 없이 돈다.
"""

import base64
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import mcp_call  # noqa: E402
import mcp_oidc_proxy as proxy  # noqa: E402


def fake_jwt(exp: float, n: int) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{enc({'alg': 'none'})}.{enc({'exp': exp, 'n': n})}.sig"


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def serve(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class FakeWorld:
    """토큰 엔드포인트 + MCP 서버. MCP는 Authorization을 기록하고 JSON-RPC에 응답한다."""

    def __init__(self, clock: Clock, lifetime=300):
        self.clock, self.lifetime = clock, lifetime
        self.issued, self.seen_auth, self.seen_audience = 0, [], []
        world = self

        class TokenHandler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                assert self.headers["Authorization"] == "bearer req-token"
                world.seen_audience.append(self.path.split("audience=")[-1])
                world.issued += 1
                body = json.dumps({"value": fake_jwt(world.clock() + world.lifetime, world.issued)}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        class McpHandler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                world.seen_auth.append(self.headers.get("Authorization"))
                msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if "id" not in msg:
                    self.send_response(202)
                    self.end_headers()
                    return
                method = msg["method"]
                if method == "initialize":
                    result = {"protocolVersion": "2025-06-18", "capabilities": {}}
                elif method == "tools/list":
                    result = {"tools": [{"name": "ping"}, {"name": "github_app_installation_token"}]}
                elif msg["params"]["name"] == "github_app_installation_token":
                    result = {"content": [{"type": "resource", "resource": {  # 실제 서버와 같은 embedded resource 모양
                        "uri": "file:///github-token.env", "mimeType": "text/plain",
                        "text": "# expires soon\nGITHUB_TOKEN=ghs_fake123\n"}}]}
                else:
                    result = {"content": [{"type": "text", "text": "pong"}]}
                body = json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.token_server, self.token_url = serve(TokenHandler)
        self.mcp_server, self.mcp_url = serve(McpHandler)

    def close(self):
        for server in (self.token_server, self.mcp_server):
            server.shutdown()
            server.server_close()


class ProxyTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.world = FakeWorld(self.clock)
        self.tokens = proxy.OidcTokenSource(f"{self.world.token_url}/token?api-version=2.0", "req-token",
                                            "homelab-k3s-mcp", refresh_before=90, clock=self.clock)
        handler = proxy.make_handler(f"{self.world.mcp_url}/mcp", self.tokens, 10, log=lambda *a, **k: None)
        self.proxy_server, base = serve(handler)
        self.client = mcp_call.McpClient(f"{base}/mcp")

    def tearDown(self):
        self.proxy_server.shutdown()
        self.proxy_server.server_close()
        self.world.close()

    def test_relays_with_bearer_token_and_audience(self):
        self.client.initialize()
        names = sorted(t["name"] for t in self.client.list_tools())
        self.assertEqual(names, ["github_app_installation_token", "ping"])
        self.assertEqual(self.world.seen_audience, ["homelab-k3s-mcp"])
        self.assertTrue(all(a and a.startswith("Bearer ") for a in self.world.seen_auth))
        self.assertEqual(self.world.issued, 1)  # 유효한 동안은 캐시

    def test_refreshes_before_expiry(self):
        self.client.initialize()
        self.clock.now += 300 - 89  # 만료 89초 전 → 갱신 구간
        self.assertEqual(self.client.call_tool("ping", {}), "pong")
        self.assertEqual(self.world.issued, 2)
        first, last = self.world.seen_auth[0], self.world.seen_auth[-1]
        self.assertNotEqual(first, last)

    def test_github_token_is_masked_and_exported(self):
        env_file = Path(tempfile.mkstemp()[1])
        try:
            os.environ["GITHUB_ENV"] = str(env_file)
            import contextlib, io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = mcp_call.main(["--url", self.client.url, "github-token", "--env-name", "SRC_TOKEN"])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("::add-mask::ghs_fake123", out)
            self.assertEqual(out.count("ghs_fake123"), 1)  # 마스킹 지시 외에는 값이 출력되지 않는다
            self.assertEqual(env_file.read_text(), "SRC_TOKEN=ghs_fake123\n")
        finally:
            os.environ.pop("GITHUB_ENV", None)
            env_file.unlink()


class FakeSandboxAdmin:
    """github_stub.py의 관리 API 흉내 — 받은 요청을 기록하고 정해진 답을 돌려준다."""

    def __init__(self):
        self.calls = []
        admin = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                admin.calls.append((self.path, payload))
                if self.path == "/_sandbox/tokens":
                    status, body = 200, {"token": "ghs_sandboxAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                                         "expires_at": "2026-11-01T13:00:00Z",
                                         "repositories": payload.get("repositories"),
                                         "permissions": payload.get("permissions")}
                elif payload.get("context", "").startswith("bad/"):
                    status, body = 422, {"message": "context not allowed"}
                else:
                    status, body = 201, dict(payload, id=1)
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server, self.url = serve(Handler)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class SandboxProxyTest(unittest.TestCase):
    """샌드박스 모드: GitHub 도구는 대역이 받고, 허용 목록 밖 도구는 막고, 허용된 도구만 실제 MCP로 간다."""

    def setUp(self):
        self.clock = Clock()
        self.world = FakeWorld(self.clock)
        self.admin = FakeSandboxAdmin()
        tokens = proxy.OidcTokenSource(f"{self.world.token_url}/token", "req-token", "aud", clock=self.clock)
        policy = proxy.SandboxPolicy(self.admin.url, {"ping"})
        handler = proxy.make_handler(f"{self.world.mcp_url}/mcp", tokens, 10, log=lambda *a, **k: None,
                                     sandbox=policy)
        self.proxy_server, base = serve(handler)
        self.client = mcp_call.McpClient(f"{base}/mcp")
        self.client.initialize()

    def tearDown(self):
        self.proxy_server.shutdown()
        self.proxy_server.server_close()
        self.admin.close()
        self.world.close()

    def upstream_calls(self):
        return len(self.world.seen_auth)

    def test_token_comes_from_sandbox_not_upstream(self):
        before = self.upstream_calls()
        text = self.client.call_tool("github_app_installation_token",
                                     {"repositories": ["pocket-aide"], "permissions": {"contents": "write"}})
        self.assertEqual(self.upstream_calls(), before)  # 실제 MCP에는 가지 않는다
        self.assertEqual(mcp_call.extract_env_value(text, "GITHUB_TOKEN"), "ghs_sandboxAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
        self.assertIn("# Permissions: contents=write", text)
        self.assertEqual(self.admin.calls, [("/_sandbox/tokens", {"repositories": ["pocket-aide"],
                                                                  "permissions": {"contents": "write"}})])

    def test_commit_status_goes_to_sandbox(self):
        sha = "a" * 40
        text = self.client.call_tool("github_commit_status_create",
                                     {"repository": "pocket-aide", "sha": sha, "state": "success",
                                      "context": "review/manual-approval"})
        self.assertIn("review/manual-approval=success", text)
        self.assertEqual(self.admin.calls[0][0], "/_sandbox/statuses")
        with self.assertRaises(mcp_call.McpError):  # 짧은 sha는 실제 도구처럼 거절
            self.client.call_tool("github_commit_status_create",
                                  {"repository": "x", "sha": "abc", "state": "success", "context": "c"})
        with self.assertRaises(mcp_call.McpError):  # 대역의 거절은 isError로 전달
            self.client.call_tool("github_commit_status_create",
                                  {"repository": "x", "sha": sha, "state": "success", "context": "bad/x"})

    def test_allowlist_is_fail_closed(self):
        self.assertEqual(self.client.call_tool("ping", {}), "pong")  # 허용 → 실제 MCP
        before = self.upstream_calls()
        with self.assertRaises(mcp_call.McpError):
            self.client.call_tool("resource_delete", {"kind": "Pod"})
        self.assertEqual(self.upstream_calls(), before)

    def test_non_tool_calls_pass_through(self):
        names = sorted(t["name"] for t in self.client.list_tools())
        self.assertEqual(names, ["github_app_installation_token", "ping"])

    def test_batched_tool_call_rejected(self):
        req = urllib.request.Request(self.client.url, method="POST", headers={"Content-Type": "application/json"},
                                     data=json.dumps([{"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                                                       "params": {"name": "resource_delete"}}]).encode())
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 400)


class HelpersTest(unittest.TestCase):
    def test_jwt_exp(self):
        self.assertEqual(proxy.jwt_exp(fake_jwt(1234, 1)), 1234)
        with self.assertRaises(ValueError):
            proxy.jwt_exp("not-a-jwt")

    def test_missing_runner_env_is_rejected(self):
        with self.assertRaises(ValueError):
            proxy.OidcTokenSource("", "", "aud")

    def test_parse_sse_picks_matching_id(self):
        body = 'event: message\ndata: {"jsonrpc":"2.0","method":"note"}\n\n' \
               'event: message\ndata: {"jsonrpc":"2.0","id":7,"result":{"ok":true}}\n\n'
        self.assertEqual(mcp_call.parse_sse(body, 7)["result"], {"ok": True})

    def test_extract_env_value(self):
        self.assertEqual(mcp_call.extract_env_value("# c\nGITHUB_TOKEN='abc'\n", "GITHUB_TOKEN"), "abc")
        with self.assertRaises(mcp_call.McpError):
            mcp_call.extract_env_value("nothing", "GITHUB_TOKEN")


if __name__ == "__main__":
    unittest.main()
