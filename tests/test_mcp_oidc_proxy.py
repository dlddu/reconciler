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
