"""`.github/scripts/github_stub.py` · `github_sandbox.py` 테스트 (python3 -m unittest discover -s tests).

대역을 평문 HTTP로 띄우고 Host 헤더로 github.com · api.github.com을 흉내 낸다. 실제 git 클라이언트로 clone·push하고,
REST·GraphQL로 PR을 만들고 머지하며, 기록이 점검기가 기대하는 모양인지 본다. 실제 GitHub 대신 가짜 상류를 두고
read passthrough가 읽기만 중계하는지도 본다. 네트워크 없이 돈다.
"""

import base64
import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import github_sandbox as sbx  # noqa: E402
import github_stub as stub  # noqa: E402

GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
GIT_ENV.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e",
               GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", HOME=tempfile.gettempdir())


def git(*args, cwd=None, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=GIT_ENV)
    if check and r.returncode:
        raise AssertionError(r.stderr)
    return r


class FakeUpstream:
    """실제 api.github.com 자리. 받은 요청을 기록한다."""

    def __init__(self):
        self.seen = []
        up = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, body):
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                up.seen.append(("GET", self.path, self.headers.get("Authorization")))
                if self.path.startswith("/repos/dlddu/demo/pulls/7"):
                    return self._reply({"number": 7, "title": "real", "state": "open", "body": "",
                                        "head": {"ref": "real-branch", "sha": "f" * 40},
                                        "base": {"ref": "main", "sha": "e" * 40}})
                if "/pulls?" in self.path or self.path.endswith("/statuses?per_page=100") \
                        or "/check-runs" in self.path or "/comments" in self.path:
                    return self._reply([] if "/check-runs" not in self.path else {"check_runs": []})
                self._reply({"real": True, "path": self.path})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                up.seen.append(("POST", self.path, self.rfile.read(length).decode()))
                self._reply({"data": {"real": True}})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class PlainPassthrough(stub.Passthrough):
    def __init__(self, port, token="ghs_REALREADONLYTOKENxxxxxxxxxxxxxxxx"):
        super().__init__(token, addresses=["127.0.0.1"])
        self.port = port

    def connect(self, addr):
        return http.client.HTTPConnection(addr, self.port, timeout=10)


class StubFixture(unittest.TestCase):
    passthrough = False
    required = ["review/manual-approval"]
    synthetic_ci = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        src = tmp / "src"
        src.mkdir()
        git("init", "-q", "-b", "main", cwd=src)
        (src / "README.md").write_text("hello\n")
        git("add", ".", cwd=src)
        git("commit", "-qm", "init", cwd=src)
        self.root = tmp / "root"
        bare = self.root / "git" / "dlddu" / "demo.git"
        bare.parent.mkdir(parents=True)
        git("clone", "-q", "--bare", str(src), str(bare))
        rules = {"main": {"blocks_direct_push": True, "required_status_checks": list(self.required)}}
        sbx.install_hook(bare, rules)
        self.bare = bare
        self.log = tmp / "log.jsonl"
        self.state = stub.State(stub.Repos(self.root), self.log, rules={"dlddu/demo": rules},
                                synthetic_ci=self.synthetic_ci)
        self.upstream = FakeUpstream() if self.passthrough else None
        pt = PlainPassthrough(self.upstream.port) if self.upstream else None
        api = stub.Api(self.state, pt)
        gql = stub.GraphQL(self.state, api, pt)
        web = PlainPassthrough(self.upstream.port, token="") if self.upstream else None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0),
                                          stub.make_server_handler(self.state, api, gql, self.root, web))
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.admin = ThreadingHTTPServer(("127.0.0.1", 0), stub.make_admin_handler(self.state, api))
        self.admin_port = self.admin.server_address[1]
        threading.Thread(target=self.admin.serve_forever, daemon=True).start()
        self.tmp = tmp

    def tearDown(self):
        for srv in (self.server, self.admin):
            srv.shutdown()
            srv.server_close()
        if self.upstream:
            self.upstream.close()
        self._tmp.cleanup()

    # helpers
    def mint(self, repositories=None, permissions=None):
        return self.admin_call("POST", "/_sandbox/tokens",
                               {"repositories": repositories, "permissions": permissions})[1]["token"]

    def admin_call(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.admin_port, timeout=10)
        conn.request(method, path, body=json.dumps(body).encode() if body is not None else None)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, json.loads(data or b"null")

    def call(self, method, path, token=None, body=None, host="api.github.com"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        headers = {"Host": host, "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        try:
            return resp.status, json.loads(data) if data else None
        except ValueError:
            return resp.status, data.decode()

    def gql(self, token, query, variables=None):
        return self.call("POST", "/graphql", token, {"query": query, "variables": variables or {}})[1]

    def entries(self):
        return sbx.load_log(self.log)

    def git_remote(self, token, name="demo"):
        auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        return ["-c", "http.extraHeader=Host: github.com", "-c", f"http.extraHeader=Authorization: Basic {auth}"], \
            f"http://127.0.0.1:{self.port}/dlddu/{name}.git"

    def push_branch(self, token, branch="reconcile/fix", content="fix\n"):
        cfg, url = self.git_remote(token)
        work = self.tmp / f"w-{branch.replace('/', '_')}"
        git(*cfg, "clone", "-q", url, str(work))
        git("checkout", "-qb", branch, cwd=work)
        (work / "fix.txt").write_text(content)
        git("add", ".", cwd=work)
        git("commit", "-qm", "fix", cwd=work)
        return git(*cfg, "push", "-q", "origin", branch, cwd=work, check=False), work, cfg


class AuthTest(StubFixture):
    def test_scope_and_credentials(self):
        tok = self.mint(["demo"], {"contents": "read", "metadata": "read"})
        self.assertEqual(self.call("GET", "/repos/dlddu/demo")[0], 401)
        self.assertEqual(self.call("GET", "/repos/dlddu/demo", "ghs_unknown")[0], 401)
        self.assertEqual(self.call("GET", "/repos/dlddu/demo", tok)[0], 200)
        other = self.mint(["elsewhere"])
        self.assertEqual(self.call("GET", "/repos/dlddu/demo", other)[0], 404)  # 범위 밖 레포는 404
        status, body = self.call("POST", "/repos/dlddu/demo/pulls", tok, {"title": "t", "head": "x", "base": "main"})
        self.assertEqual((status, body["message"]), (403, "Resource not accessible by integration"))

    def test_git_push_needs_contents_write(self):
        read = self.mint(["demo"], {"contents": "read"})
        result, _, _ = self.push_branch(read)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(stub.Repos(self.root).branch_sha("dlddu/demo", "reconcile/fix"))


class GitTest(StubFixture):
    def test_push_branch_and_rule_rejects_default_branch(self):
        tok = self.mint(["demo"], {"contents": "write"})
        result, work, cfg = self.push_branch(tok)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(stub.Repos(self.root).branch_sha("dlddu/demo", "reconcile/fix"))
        git("checkout", "-q", "main", cwd=work)
        (work / "README.md").write_text("direct\n")
        git("commit", "-qam", "direct", cwd=work)
        rejected = git(*cfg, "push", "origin", "main", cwd=work, check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("Changes must be made through a pull request", rejected.stderr)
        pushes = [e for e in self.entries() if e["op"] == "git.push"]
        self.assertEqual([u["ref"] for u in pushes[0]["detail"]["updates"]], ["refs/heads/reconcile/fix"])
        self.assertTrue(pushes[1]["detail"].get("rejected"))
        self.assertEqual(pushes[1]["detail"]["updates"], [])


class PullRequestTest(StubFixture):
    def test_rest_create_merge_with_required_status(self):
        tok = self.mint(["demo"])
        self.push_branch(tok)
        status, pr = self.call("POST", "/repos/dlddu/demo/pulls", tok,
                               {"title": "제안: fix", "head": "dlddu:reconcile/fix", "base": "main", "body": "b"})
        self.assertEqual(status, 201)
        self.assertEqual(pr["number"], stub.DEFAULT_PR_BASE)
        self.assertEqual(pr["html_url"], f"https://github.com/dlddu/demo/pull/{stub.DEFAULT_PR_BASE}")
        self.assertTrue(pr["mergeable"])
        n = pr["number"]
        dup = self.call("POST", "/repos/dlddu/demo/pulls", tok, {"title": "x", "head": "reconcile/fix", "base": "main"})
        self.assertEqual(dup[0], 422)
        self.assertEqual([p["number"] for p in self.call("GET", "/repos/dlddu/demo/pulls?state=open", tok)[1]], [n])

        status, body = self.call("PUT", f"/repos/dlddu/demo/pulls/{n}/merge", tok, {})
        self.assertEqual(status, 405)
        self.assertIn('Required status check "review/manual-approval" is expected.', body["message"])

        sha = pr["head"]["sha"]
        st = self.admin_call("POST", "/_sandbox/statuses", {"repository": "demo", "sha": sha, "state": "success",
                                                            "context": "review/manual-approval"})
        self.assertEqual(st[0], 201)
        combined = self.call("GET", f"/repos/dlddu/demo/commits/{sha}/status", tok)[1]
        self.assertEqual(combined["state"], "success")
        status, body = self.call("PUT", f"/repos/dlddu/demo/pulls/{n}/merge", tok, {"merge_method": "squash"})
        self.assertEqual((status, body["merged"]), (200, True))
        main = stub.Repos(self.root).branch_sha("dlddu/demo", "main")
        self.assertEqual(main, body["sha"])
        self.assertTrue(self.call("GET", f"/repos/dlddu/demo/pulls/{n}", tok)[1]["merged"])

        ops = [(e["op"], e.get("write"), bool((e.get("detail") or {}).get("refused"))) for e in self.entries()
               if e.get("write")]
        self.assertIn(("pulls.create", True, False), ops)
        self.assertIn(("pulls.merge", True, True), ops)   # 거절된 시도도 쓰기로 남는다
        self.assertIn(("pulls.merge", True, False), ops)
        self.assertIn(("statuses.create", True, False), ops)

    def test_graphql_create_and_projection(self):
        tok = self.mint(["demo"])
        self.push_branch(tok)
        repo = self.gql(tok, 'query R($owner:String!,$name:String!){repository(owner:$owner,name:$name){id '
                             'defaultBranchRef{name}}}', {"owner": "dlddu", "name": "demo"})
        self.assertEqual(set(repo["data"]["repository"]), {"id", "defaultBranchRef"})  # 고른 필드만
        created = self.gql(tok, "mutation C($input:CreatePullRequestInput!){createPullRequest(input:$input)"
                                "{pullRequest{id url number}}}",
                           {"input": {"repositoryId": repo["data"]["repository"]["id"], "baseRefName": "main",
                                      "headRefName": "reconcile/fix", "title": "t", "body": "b"}})
        pr = created["data"]["createPullRequest"]["pullRequest"]
        self.assertEqual(set(pr), {"id", "url", "number"})
        merged = self.gql(tok, "mutation M($input:MergePullRequestInput!){mergePullRequest(input:$input)"
                               "{clientMutationId}}", {"input": {"pullRequestId": pr["id"], "mergeMethod": "MERGE"}})
        self.assertIn("errors", merged)  # 필수 status 없음 → 거절
        rollup = self.gql(tok, "query S($id:ID!){node(id:$id){...on PullRequest{statusCheckRollup:commits(last:1)"
                               "{nodes{commit{statusCheckRollup{state}}}}}}}", {"id": pr["id"]})
        # 필수 체크가 사람 승인뿐이라 합성 CI는 일반 `ci` 하나 — rollup은 실제 GitHub처럼 SUCCESS지만
        # 사람 승인 status가 없어 머지는 위에서 거절됐다.
        self.assertEqual(rollup["data"]["node"]["statusCheckRollup"]["nodes"][0]["commit"]["statusCheckRollup"],
                         {"state": "SUCCESS"})
        unknown = self.gql(tok, "mutation{deleteRepository(input:{}){clientMutationId}}")
        self.assertIn("errors", unknown)
        self.assertTrue(any(e["op"] == "unsupported" and e.get("write") for e in self.entries()))

    def test_unknown_write_is_not_implemented(self):
        tok = self.mint(["demo"])
        status, _ = self.call("POST", "/repos/dlddu/demo/releases", tok, {"tag_name": "v1"})
        self.assertEqual(status, 501)
        self.assertEqual(self.entries()[-1]["op"], "unsupported")


class SyntheticCiTest(StubFixture):
    """대역 PR에는 CI가 돌지 않으니 합성 성공 체크 런을 붙인다 — 사람 승인 context는 절대 아니다."""
    required = ["ci-success", "review/manual-approval"]

    def open_pr(self, tok):
        self.push_branch(tok)
        status, pr = self.call("POST", "/repos/dlddu/demo/pulls", tok,
                               {"title": "t", "head": "reconcile/fix", "base": "main"})
        self.assertEqual(status, 201)
        return pr

    def test_ci_is_synthesized_but_human_approval_is_not(self):
        tok = self.mint(["demo"])
        pr = self.open_pr(tok)
        sha, n = pr["head"]["sha"], pr["number"]
        runs = self.call("GET", f"/repos/dlddu/demo/commits/{sha}/check-runs", tok)[1]["check_runs"]
        self.assertEqual([(r["name"], r["conclusion"]) for r in runs], [("ci-success", "success")])
        self.assertIn("synthetic", runs[0]["output"]["title"])
        self.assertEqual(runs[0]["app"]["slug"], stub.SYNTHETIC_APP_SLUG)
        # 커밋 status(사람 승인)는 합성하지 않는다 → combined status는 아직 pending
        self.assertEqual(self.call("GET", f"/repos/dlddu/demo/commits/{sha}/status", tok)[1]["state"], "pending")
        # 머지 게이트: CI는 합성으로 충족, 사람 승인만 남는다
        status, body = self.call("PUT", f"/repos/dlddu/demo/pulls/{n}/merge", tok, {})
        self.assertEqual(status, 405)
        self.assertIn('"review/manual-approval"', body["message"])
        self.assertNotIn('"ci-success"', body["message"])
        self.admin_call("POST", "/_sandbox/statuses", {"repository": "demo", "sha": sha, "state": "success",
                                                       "context": "review/manual-approval"})
        self.assertEqual(self.call("PUT", f"/repos/dlddu/demo/pulls/{n}/merge", tok, {})[0], 200)
        synth = [e for e in self.entries() if e["op"] == "ci.synthetic"]
        self.assertEqual(len(synth), 1)
        self.assertEqual(synth[0]["detail"]["contexts"], ["ci-success"])
        self.assertFalse(synth[0]["write"])

    def test_new_push_gets_its_own_ci_and_graphql_rollup_shows_it(self):
        tok = self.mint(["demo"])
        pr = self.open_pr(tok)
        self.push_branch(tok, branch="other", content="other\n")  # 다른 브랜치·다른 커밋 — 대역 PR 아님
        cfg2, url = self.git_remote(tok)
        w2 = self.tmp / "w2"
        git(*cfg2, "clone", "-q", "-b", "reconcile/fix", url, str(w2))
        (w2 / "more.txt").write_text("more\n")
        git("add", ".", cwd=w2)
        git("commit", "-qm", "more", cwd=w2)
        git(*cfg2, "push", "-q", "origin", "reconcile/fix", cwd=w2)
        head = self.call("GET", f"/repos/dlddu/demo/pulls/{pr['number']}", tok)[1]["head"]["sha"]
        self.assertNotEqual(head, pr["head"]["sha"])
        runs = self.call("GET", f"/repos/dlddu/demo/commits/{head}/check-runs", tok)[1]["check_runs"]
        self.assertEqual([r["name"] for r in runs], ["ci-success"])
        other = stub.Repos(self.root).branch_sha("dlddu/demo", "other")  # PR이 아닌 커밋에는 없다
        self.assertEqual(self.call("GET", f"/repos/dlddu/demo/commits/{other}/check-runs", tok)[1]["check_runs"], [])
        # gh pr checks/view처럼 owner·name·number 변수로 묻는다
        node = self.gql(tok, 'query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name)'
                             '{pullRequest(number:$number){statusCheckRollup:commits(last:1){nodes{commit{'
                             'statusCheckRollup{state contexts(first:10){nodes{__typename ...on CheckRun{name '
                             'conclusion} ...on StatusContext{context state}}}}}}}}}}',
                        {"owner": "dlddu", "name": "demo", "number": pr["number"]})
        rollup = node["data"]["repository"]["pullRequest"]["statusCheckRollup"]["nodes"][0]["commit"]["statusCheckRollup"]
        self.assertEqual(rollup["contexts"]["nodes"], [{"__typename": "CheckRun", "name": "ci-success",
                                                         "conclusion": "SUCCESS"}])
        self.assertEqual(rollup["state"], "SUCCESS")

    def test_repo_without_required_checks_gets_generic_ci(self):
        self.state.rules = {}
        tok = self.mint(["demo"])
        pr = self.open_pr(tok)
        runs = self.call("GET", f"/repos/dlddu/demo/commits/{pr['head']['sha']}/check-runs", tok)[1]["check_runs"]
        self.assertEqual([r["name"] for r in runs], ["ci"])


class SyntheticCiOffTest(StubFixture):
    required = ["ci-success"]
    synthetic_ci = False

    def test_disabled(self):
        tok = self.mint(["demo"])
        self.push_branch(tok)
        pr = self.call("POST", "/repos/dlddu/demo/pulls", tok, {"title": "t", "head": "reconcile/fix",
                                                                "base": "main"})[1]
        self.assertEqual(self.call("GET", f"/repos/dlddu/demo/commits/{pr['head']['sha']}/check-runs",
                                   tok)[1]["check_runs"], [])
        self.assertEqual(self.call("PUT", f"/repos/dlddu/demo/pulls/{pr['number']}/merge", tok, {})[0], 405)


class PassthroughTest(StubFixture):
    passthrough = True

    def test_unknown_reads_are_relayed_with_read_token_only(self):
        tok = self.mint(["demo"])
        status, body = self.call("GET", "/repos/dlddu/demo/rulesets", tok)
        self.assertEqual((status, body["real"]), (200, True))
        method, path, auth = self.upstream.seen[-1]
        self.assertEqual((method, path), ("GET", "/repos/dlddu/demo/rulesets"))
        self.assertEqual(auth, "Bearer ghs_REALREADONLYTOKENxxxxxxxxxxxxxxxx")  # 스킬 토큰이 아니라 러너의 읽기 토큰
        before = len(self.upstream.seen)
        self.assertEqual(self.call("POST", "/repos/dlddu/demo/rulesets", tok, {})[0], 501)
        self.assertEqual(self.call("GET", "/repos/dlddu/other/rulesets", tok)[0], 404)  # 미러하지 않은 레포
        self.assertEqual(len(self.upstream.seen), before)  # 쓰기·범위 밖은 상류에 가지 않는다

    def test_real_pr_gets_no_synthetic_ci(self):
        tok = self.mint(["demo"])
        self.call("PATCH", "/repos/dlddu/demo/pulls/7", tok, {"title": "touched"})  # 실제 PR을 손대 등록시킨다
        self.assertEqual(self.call("GET", f"/repos/dlddu/demo/commits/{'f' * 40}/check-runs", tok)[1]["check_runs"], [])
        self.assertFalse([e for e in self.entries() if e["op"] == "ci.synthetic"])

    def test_closing_a_real_pr_stays_local(self):
        tok = self.mint(["demo"])
        status, pr = self.call("PATCH", "/repos/dlddu/demo/pulls/7", tok, {"state": "closed"})
        self.assertEqual((status, pr["state"]), (200, "closed"))
        self.assertFalse([s for s in self.upstream.seen if s[0] != "GET"])
        close = [e for e in self.entries() if e["op"] == "pulls.close"]
        self.assertEqual(close[0]["detail"]["origin"], "real")

    def test_public_web_get_is_relayed_without_credentials(self):
        status, body = self.call("GET", "/WiseLibs/better-sqlite3/releases/download/v1/x.tar.gz", host="github.com")
        self.assertEqual(status, 200)
        method, path, auth = self.upstream.seen[-1]
        self.assertEqual((method, path, auth), ("GET", "/WiseLibs/better-sqlite3/releases/download/v1/x.tar.gz", None))
        self.assertEqual(self.entries()[-1]["op"], "web.passthrough")
        before = len(self.upstream.seen)
        self.assertEqual(self.call("POST", "/login", body={}, host="github.com")[0], 404)  # 웹 쓰기는 중계 안 함
        self.assertEqual(len(self.upstream.seen), before)

    def test_graphql_mutation_never_relayed(self):
        with self.assertRaises(stub.ApiError):
            PlainPassthrough(self.upstream.port).graphql("mutation{x}", {})


class SandboxHelpersTest(unittest.TestCase):
    def test_parse_rules(self):
        rules = sbx.parse_rules([
            {"type": "pull_request", "parameters": {}},
            {"type": "required_status_checks", "parameters": {"required_status_checks": [
                {"context": "review/manual-approval"}, {"context": "ci"}]}},
            {"type": "non_fast_forward"}, {"type": "deletion"}])
        self.assertTrue(rules["blocks_direct_push"])
        self.assertEqual(rules["required_status_checks"], ["review/manual-approval", "ci"])
        self.assertTrue(rules["deletion"] and rules["non_fast_forward"])
        self.assertFalse(sbx.parse_rules([{"type": "deletion"}])["blocks_direct_push"])

    def test_hosts_block_roundtrip(self):
        base = "127.0.0.1 localhost\n"
        with_block = sbx.strip_block(base) + "\n".join([sbx.MARK_BEGIN, "127.0.0.1 github.com", sbx.MARK_END]) + "\n"
        self.assertIn("github.com", with_block)
        self.assertEqual(sbx.strip_block(with_block), base)

    def test_repos_for_model_skips_reconciler(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "data").mkdir()
            (Path(d) / "data" / "to-be-models.json").write_text(json.dumps([
                {"id": "tbm_a", "toBe": {"dataSource": {"repository": "dlddu/pocket-aide"}},
                 "asIs": {"x": [{"repository": "dlddu/reconciler"}, {"repository": "dlddu/pocket-aide"}]}},
                {"id": "tbm_b", "toBe": {"repository": "dlddu/other"}}]))
            self.assertEqual(sbx.repos_for_model(Path(d), "tbm_a"), ["dlddu/pocket-aide"])

    def test_secret_env_filter(self):
        for name in ("GITHUB_TOKEN", "SOURCE_GITHUB_TOKEN", "MINIMAX_SUBSCRIPTION_KEY", "GH_TOKEN",
                     "ACTIONS_ID_TOKEN_REQUEST_URL", "AWS_SECRET_ACCESS_KEY"):
            self.assertTrue(sbx.SECRET_ENV.search(name), name)
        for name in ("GIT_CONFIG_KEY_0", "PATH", "HOME", "RUNNER_TEMP"):
            self.assertFalse(sbx.SECRET_ENV.search(name), name)

    def test_summary_lists_writes_and_unsupported(self):
        text = sbx.summarize([
            {"seq": 1, "op": "token.mint", "token": "t1", "detail": {"repositories": ["demo"]}},
            {"seq": 2, "op": "git.push", "write": True, "repo": "dlddu/demo", "status": 200,
             "detail": {"updates": [{"ref": "refs/heads/x", "old": "0" * 40, "new": "a" * 40, "forced": False}]}},
            {"seq": 3, "op": "unsupported", "method": "POST", "host": "api.github.com", "path": "/x", "status": 501}])
        self.assertIn("refs/heads/x 0000000→aaaaaaa", text)
        self.assertIn("POST api.github.com/x", text)


if __name__ == "__main__":
    unittest.main()
