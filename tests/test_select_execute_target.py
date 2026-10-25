"""`.github/scripts/select_execute_target.py` 테스트 (python3 -m unittest discover -s tests).

GitHub API는 로컬 HTTP 서버(가짜 pulls/statuses 엔드포인트)로 대신해, 실제 urllib 요청 경로를
그대로 탄다. 네트워크·토큰 없이 돈다.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import select_execute_target as sxt  # noqa: E402

SHA = "a" * 40
SHA2 = "b" * 40
CTX = "review/manual-approval"


class FakeGitHub:
    """pulls/<n>, commits/<sha>/statuses만 흉내 낸다. 등록 안 된 경로는 404."""

    def __init__(self):
        self.routes = {}   # path -> (code, body)
        self.requests = []  # (path, Authorization 헤더)
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                fake.requests.append((self.path, self.headers.get("Authorization")))
                code, body = fake.routes.get(self.path, (404, {"message": "Not Found"}))
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def pr(self, repo, number, *, head=SHA, state="open", merged=False, code=200):
        body = {"state": state, "merged": merged, "merged_at": "2026-10-25T00:00:00Z" if merged else None,
                "head": {"sha": head}}
        self.routes[f"/repos/{repo}/pulls/{number}"] = (code, body)

    def statuses(self, repo, sha, items, code=200):
        self.routes[f"/repos/{repo}/commits/{sha}/statuses?per_page=100"] = (code, items)

    def paths(self):
        return [p for p, _ in self.requests]


def status(state, created, context=CTX):
    return {"context": context, "state": state, "created_at": created}


class Fixture:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.repo = tmp / "reconciler"
        (self.repo / "data" / "reconciliation-tasks").mkdir(parents=True)
        self.tasks = {}

    def task(self, mid, tid, status="approved", *, reviewed_at="2026-10-20T00:00:00Z", pr=None,
             manual=None, decision=None, steps=True, guide=True, prepared=True, attempts=None):
        attempt = {"seq": 1, "plan": {}, "preparation": {}, "review": {"status": "approved"}}
        if steps:
            attempt["plan"]["steps"] = [{"seq": 1, "action": "merge"}]
        if guide:
            attempt["plan"]["executionGuide"] = "merge then verify"
        if prepared:
            attempt["preparation"]["preparedAt"] = "2026-10-19T00:00:00Z"
        if pr:
            attempt["preparation"]["pullRequestUrl"] = f"https://github.com/{pr}"
        if reviewed_at:
            attempt["review"]["reviewedAt"] = reviewed_at
        if manual:
            attempt["review"]["manualApproval"] = manual
        if decision is not None:
            attempt["decision"] = decision
        t = {"id": tid, "toBeModelId": mid, "status": status, "createdAt": "2026-10-18T00:00:00Z",
             "attempts": [attempt] if attempts is None else attempts}
        self.tasks.setdefault(mid, []).append(t)
        return t

    def write(self):
        for mid, tasks in self.tasks.items():
            (self.repo / "data" / "reconciliation-tasks" / f"{mid}.json").write_text(json.dumps(tasks))


class SelectExecuteTargetTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.fx = Fixture(self.tmp)
        self.gh = FakeGitHub()
        env = {k: v for k, v in os.environ.items() if k not in ("SOURCE_GITHUB_TOKEN", "GITHUB_TOKEN")}
        self._env = mock.patch.dict(os.environ, env, clear=True)
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self.gh.close()
        self._tmp.cleanup()

    def run_main(self, *extra):
        self.fx.write()
        out_file = self.tmp / "gh_output"
        out_file.write_text("")
        summary = self.tmp / "summary.md"
        summary.write_text("")
        argv = ["--repo", str(self.fx.repo), "--api-url", self.gh.url,
                "--github-output", str(out_file), "--summary-file", str(summary), *extra]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = sxt.main(argv)
        outputs = dict(line.split("=", 1) for line in out_file.read_text().splitlines())
        return code, outputs, buf.getvalue()

    # ── 대상 없음 ──

    def test_no_approved_tasks(self):
        self.fx.task("tbm_a", "rct_1", "planned")
        self.fx.task("tbm_a", "rct_2", "succeeded")
        self.fx.task("tbm_b", "rct_1", "review_rejected")
        code, out, stdout = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(out["found"], "false")
        self.assertEqual(out["target_id"], "")
        self.assertEqual(out["approved_count"], "0")
        self.assertIn("planned 1건(reconciler-work-review 판정 대기)", stdout)
        self.assertIn("review_rejected 1건(reconciler-work-planner 재계획 대기)", stdout)
        self.assertNotIn("succeeded", stdout)
        self.assertEqual(self.gh.requests, [])

    def test_never_picks_pre_review_or_locked_statuses(self):
        for i, st in enumerate(["planned", "reviewing", "executing", "verifying", "awaiting_review"]):
            self.fx.task("tbm_a", f"rct_{i}", st)
        code, out, _ = self.run_main()
        self.assertEqual((code, out["found"]), (0, "false"))

    def test_empty_tasks_dir(self):
        code, out, _ = self.run_main()
        self.assertEqual((code, out["found"]), (0, "false"))

    # ── 준비 미완 ──

    def test_not_ready_when_plan_or_preparation_missing(self):
        self.fx.task("tbm_a", "rct_1", steps=False)
        self.fx.task("tbm_b", "rct_1", guide=False)
        self.fx.task("tbm_c", "rct_1", prepared=False)
        self.fx.task("tbm_d", "rct_1", attempts=[])
        code, out, stdout = self.run_main()
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertEqual(out["approved_count"], "4")
        self.assertEqual(stdout.count("준비 미완"), 4)
        self.assertIn("preparedAt", stdout)

    # ── 사람 승인 불필요 ──

    def test_picks_approved_without_manual_approval_and_calls_no_api(self):
        self.fx.task("tbm_a", "rct_1", pr="dlddu/alpha/pull/3")
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(out["found"], "true")
        self.assertEqual(out["target_id"], "tbm_a/rct_1")
        self.assertEqual(out["task_id"], "rct_1")
        self.assertEqual(out["model_id"], "tbm_a")
        self.assertEqual(out["reason"], "oldest_approval")
        self.assertEqual(out["pull_request_url"], "https://github.com/dlddu/alpha/pull/3")
        self.assertEqual(self.gh.requests, [])

    def test_oldest_approval_first_and_rest_deferred(self):
        self.fx.task("tbm_a", "rct_new", reviewed_at="2026-10-22T00:00:00Z")
        self.fx.task("tbm_b", "rct_old", reviewed_at="2026-10-20T00:00:00Z")
        self.fx.task("tbm_c", "rct_none", reviewed_at=None)
        code, out, stdout = self.run_main()
        self.assertEqual(out["target_id"], "tbm_b/rct_old")
        self.assertEqual(out["approved_count"], "3")
        self.assertIn("다음 실행에 넘김: `tbm_a/rct_new`, `tbm_c/rct_none`", stdout)

    def test_skips_non_executable_older_ones_until_first_executable(self):
        self.fx.task("tbm_a", "rct_1", reviewed_at="2026-10-19T00:00:00Z", prepared=False)
        self.fx.task("tbm_b", "rct_1", reviewed_at="2026-10-20T00:00:00Z",
                     pr="dlddu/beta/pull/1", manual={"sha": SHA, "context": CTX})
        self.gh.pr("dlddu/beta", 1)
        self.gh.statuses("dlddu/beta", SHA, [])
        self.fx.task("tbm_c", "rct_1", reviewed_at="2026-10-21T00:00:00Z")
        code, out, stdout = self.run_main()
        self.assertEqual(out["target_id"], "tbm_c/rct_1")
        self.assertIn("준비 미완 · `tbm_a/rct_1`", stdout)
        self.assertIn("승인 대기 · `tbm_b/rct_1`", stdout)

    def test_stops_judging_after_first_executable(self):
        self.fx.task("tbm_a", "rct_1", reviewed_at="2026-10-19T00:00:00Z")
        self.fx.task("tbm_b", "rct_1", reviewed_at="2026-10-20T00:00:00Z",
                     pr="dlddu/beta/pull/1", manual={"sha": SHA, "context": CTX})
        code, out, _ = self.run_main()
        self.assertEqual(out["target_id"], "tbm_a/rct_1")
        self.assertEqual(self.gh.requests, [])

    # ── 사람 승인(manualApproval) ──

    def manual_task(self, mid="tbm_a", tid="rct_1", pr_number=7):
        return self.fx.task(mid, tid, pr=f"dlddu/alpha/pull/{pr_number}", manual={"sha": SHA, "context": CTX})

    def test_manual_approval_success_is_executable(self):
        self.manual_task()
        self.gh.pr("dlddu/alpha", 7)
        self.gh.statuses("dlddu/alpha", SHA, [status("success", "2026-10-21T00:00:00Z"),
                                              status("failure", "2026-10-21T00:00:00Z", context="ci")])
        code, out, stdout = self.run_main()
        self.assertEqual((code, out["found"], out["target_id"]), (0, "true", "tbm_a/rct_1"))
        self.assertEqual(self.gh.paths(), ["/repos/dlddu/alpha/pulls/7",
                                           f"/repos/dlddu/alpha/commits/{SHA}/statuses?per_page=100"])
        self.assertIn("API 호출 2회", stdout)

    def test_manual_approval_without_status_waits(self):
        self.manual_task()
        self.gh.pr("dlddu/alpha", 7)
        self.gh.statuses("dlddu/alpha", SHA, [status("success", "2026-10-21T00:00:00Z", context="ci")])
        code, out, stdout = self.run_main()
        self.assertEqual((code, out["found"], out["error_count"]), (0, "false", "0"))
        self.assertIn("승인 대기 · `tbm_a/rct_1`", stdout)
        self.assertIn(f"https://github.com/dlddu/alpha/pull/7 에 `{CTX}` 필요", stdout)

    def test_manual_approval_latest_status_wins(self):
        self.manual_task()
        self.gh.pr("dlddu/alpha", 7)
        # API는 최신이 앞이지만 created_at이 기준이다: 나중에 pending으로 되돌린 경우.
        self.gh.statuses("dlddu/alpha", SHA, [status("success", "2026-10-21T00:00:00Z"),
                                              status("pending", "2026-10-22T00:00:00Z")])
        code, out, stdout = self.run_main()
        self.assertEqual(out["found"], "false")
        self.assertIn("'pending'", stdout)

    def test_manual_approval_success_after_failure(self):
        self.manual_task()
        self.gh.pr("dlddu/alpha", 7)
        self.gh.statuses("dlddu/alpha", SHA, [status("success", "2026-10-22T00:00:00Z"),
                                              status("failure", "2026-10-21T00:00:00Z")])
        self.assertEqual(self.run_main()[1]["found"], "true")

    def test_manual_approval_head_moved_is_stale(self):
        self.manual_task()
        self.gh.pr("dlddu/alpha", 7, head=SHA2)
        code, out, stdout = self.run_main()
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertIn("승인 무효 · `tbm_a/rct_1`", stdout)
        self.assertIn("head가 bbbbbbbbbbbb로 바뀜", stdout)
        # head가 바뀌면 statuses는 조회하지 않는다.
        self.assertEqual(self.gh.paths(), ["/repos/dlddu/alpha/pulls/7"])

    def test_manual_approval_merged_or_closed_is_stale(self):
        self.manual_task("tbm_a", "rct_1", 7)
        self.gh.pr("dlddu/alpha", 7, state="closed", merged=True)
        self.manual_task("tbm_b", "rct_1", 8)
        self.gh.pr("dlddu/alpha", 8, state="closed")
        code, out, stdout = self.run_main()
        self.assertEqual(out["found"], "false")
        self.assertIn("이미 머지됨", stdout)
        self.assertIn("'closed' (open 아님)", stdout)

    def test_manual_approval_api_error_is_fail_closed(self):
        self.manual_task()
        self.gh.pr("dlddu/alpha", 7, code=403)
        code, out, stdout = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual((out["found"], out["error_count"]), ("false", "1"))
        self.assertIn("::warning::tbm_a/rct_1: GET /repos/dlddu/alpha/pulls/7 → HTTP 403", stdout)
        self.assertIn("::error::1건의 승인을 확인하지 못해", stdout)

    def test_statuses_api_error_is_fail_closed(self):
        self.manual_task()
        self.gh.pr("dlddu/alpha", 7)
        self.gh.statuses("dlddu/alpha", SHA, {"message": "boom"}, code=500)
        code, out, _ = self.run_main()
        self.assertEqual((code, out["found"], out["error_count"]), (1, "false", "1"))

    def test_error_does_not_block_another_executable_task(self):
        self.manual_task("tbm_a", "rct_1", 7)
        self.gh.pr("dlddu/alpha", 7, code=500)
        self.fx.task("tbm_b", "rct_1", reviewed_at="2026-10-23T00:00:00Z")
        code, out, stdout = self.run_main()
        self.assertEqual((code, out["target_id"], out["error_count"]), (0, "tbm_b/rct_1", "1"))
        self.assertIn("::warning::tbm_a/rct_1", stdout)

    def test_manual_approval_bad_pr_url(self):
        self.fx.task("tbm_a", "rct_1", pr="dlddu/alpha/issues/7", manual={"sha": SHA, "context": CTX})
        self.fx.task("tbm_b", "rct_1", manual={"sha": SHA, "context": CTX})
        code, out, stdout = self.run_main()
        self.assertEqual((code, out["error_count"]), (1, "2"))
        self.assertIn("PR URL을 해석할 수 없음", stdout)
        self.assertIn("pullRequestUrl이 없음", stdout)
        self.assertEqual(self.gh.requests, [])

    def test_manual_approval_missing_context(self):
        self.fx.task("tbm_a", "rct_1", pr="dlddu/alpha/pull/7", manual={"sha": SHA})
        self.gh.pr("dlddu/alpha", 7)
        code, out, stdout = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("sha 또는 context가 없음", stdout)

    # ── 사람 결정(decision) ──

    def test_decision_without_verdict_waits_without_api(self):
        self.fx.task("tbm_a", "rct_1", pr="dlddu/alpha/pull/7", decision={"sha": SHA})
        code, out, stdout = self.run_main()
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertIn("사람 결정 대기", stdout)
        self.assertEqual(self.gh.requests, [])

    def test_decision_approved_with_bound_pr_is_executable(self):
        self.fx.task("tbm_a", "rct_1", pr="dlddu/alpha/pull/7", decision={"sha": SHA, "verdict": "approved"})
        self.gh.pr("dlddu/alpha", 7)
        code, out, _ = self.run_main()
        self.assertEqual(out["found"], "true")
        self.assertEqual(self.gh.paths(), ["/repos/dlddu/alpha/pulls/7"])

    def test_decision_rejected_is_stale(self):
        self.fx.task("tbm_a", "rct_1", pr="dlddu/alpha/pull/7", decision={"sha": SHA, "verdict": "rejected"})
        code, out, stdout = self.run_main()
        self.assertEqual(out["found"], "false")
        self.assertIn("승인 무효", stdout)

    def test_decision_and_manual_both_required(self):
        self.fx.task("tbm_a", "rct_1", pr="dlddu/alpha/pull/7",
                     manual={"sha": SHA, "context": CTX}, decision={"sha": SHA, "verdict": "approved"})
        self.gh.pr("dlddu/alpha", 7)
        self.gh.statuses("dlddu/alpha", SHA, [])
        code, out, stdout = self.run_main()
        self.assertEqual(out["found"], "false")
        self.assertIn("사람 승인 대기", stdout)
        # PR은 두 게이트가 공유해 한 번만 가져온다.
        self.assertEqual(self.gh.paths().count("/repos/dlddu/alpha/pulls/7"), 1)

    # ── 지목 ──

    def test_explicit_qualified_task(self):
        self.fx.task("tbm_a", "rct_1", reviewed_at="2026-10-19T00:00:00Z")
        self.fx.task("tbm_b", "rct_1", reviewed_at="2026-10-22T00:00:00Z")
        code, out, _ = self.run_main("--target", "tbm_b/rct_1")
        self.assertEqual((code, out["target_id"], out["reason"]), (0, "tbm_b/rct_1", "explicit"))

    def test_explicit_bare_task_unique(self):
        self.fx.task("tbm_a", "rct_9")
        self.fx.task("tbm_b", "rct_1")
        code, out, _ = self.run_main("--target", "rct_9")
        self.assertEqual(out["target_id"], "tbm_a/rct_9")

    def test_explicit_bare_task_ambiguous_is_refused(self):
        self.fx.task("tbm_a", "rct_1")
        self.fx.task("tbm_b", "rct_1", "succeeded")
        code, out, stdout = self.run_main("--target", "rct_1")
        self.assertEqual(code, 2)
        self.assertEqual(out, {})
        self.assertIn("모호함(tbm_a, tbm_b)", stdout)

    def test_explicit_not_found(self):
        self.fx.task("tbm_a", "rct_1")
        for target in ("tbm_a/rct_2", "rct_2", "tbm_zzz"):
            code, out, stdout = self.run_main("--target", target)
            self.assertEqual(code, 2, target)
            self.assertIn("::error::", stdout)

    def test_explicit_task_not_approved_is_not_picked(self):
        self.fx.task("tbm_a", "rct_1", "planned")
        code, out, stdout = self.run_main("--target", "tbm_a/rct_1")
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertIn("status=planned — 실행 단계 대상이 아님", stdout)

    def test_explicit_task_waiting_is_not_picked(self):
        self.manual_task()
        self.gh.pr("dlddu/alpha", 7)
        self.gh.statuses("dlddu/alpha", SHA, [])
        code, out, _ = self.run_main("--target", "tbm_a/rct_1")
        self.assertEqual((code, out["found"]), (0, "false"))

    def test_explicit_model_picks_its_oldest_executable(self):
        self.fx.task("tbm_a", "rct_1", reviewed_at="2026-10-19T00:00:00Z")
        self.fx.task("tbm_b", "rct_2", reviewed_at="2026-10-22T00:00:00Z")
        self.fx.task("tbm_b", "rct_3", reviewed_at="2026-10-21T00:00:00Z")
        code, out, _ = self.run_main("--target", "tbm_b")
        self.assertEqual((out["target_id"], out["reason"]), ("tbm_b/rct_3", "explicit"))

    def test_explicit_model_without_approved(self):
        self.fx.task("tbm_a", "rct_1", "succeeded")
        code, out, stdout = self.run_main("--target", "tbm_a")
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertIn("approved task가 없음", stdout)

    def test_invalid_target_format(self):
        code, _, stdout = self.run_main("--target", "foo")
        self.assertEqual(code, 2)
        self.assertIn("::error::target_id", stdout)

    # ── 데이터 오류 · 토큰 ──

    def test_broken_task_file_is_fatal(self):
        self.fx.write()
        (self.fx.repo / "data" / "reconciliation-tasks" / "tbm_x.json").write_text("{not json")
        code, out, stdout = self.run_main()
        self.assertEqual((code, out), (2, {}))
        self.assertIn("::error::tbm_x.json", stdout)

    def test_missing_tasks_dir_is_fatal(self):
        (self.fx.repo / "data" / "reconciliation-tasks").rmdir()
        code, _, _ = self.run_main()
        self.assertEqual(code, 2)

    def test_source_token_preferred_and_not_printed(self):
        self.manual_task()
        self.gh.pr("dlddu/alpha", 7)
        self.gh.statuses("dlddu/alpha", SHA, [status("success", "2026-10-21T00:00:00Z")])
        os.environ["GITHUB_TOKEN"] = "workflow-tok"
        os.environ["SOURCE_GITHUB_TOKEN"] = "source-tok"
        code, out, stdout = self.run_main()
        self.assertEqual(out["found"], "true")
        self.assertEqual({a for _, a in self.gh.requests}, {"Bearer source-tok"})
        self.assertNotIn("source-tok", stdout)

    def test_workflow_token_fallback(self):
        self.manual_task()
        self.gh.pr("dlddu/alpha", 7)
        self.gh.statuses("dlddu/alpha", SHA, [])
        os.environ["GITHUB_TOKEN"] = "workflow-tok"
        self.run_main()
        self.assertEqual({a for _, a in self.gh.requests}, {"Bearer workflow-tok"})

    def test_anonymous_without_tokens(self):
        self.manual_task()
        self.gh.pr("dlddu/alpha", 7)
        self.gh.statuses("dlddu/alpha", SHA, [])
        self.run_main()
        self.assertEqual({a for _, a in self.gh.requests}, {None})

    def test_summary_file_written(self):
        self.fx.task("tbm_a", "rct_1")
        self.run_main()
        text = (self.tmp / "summary.md").read_text()
        self.assertTrue(text.startswith("#### Select target"))
        self.assertIn("`tbm_a/rct_1`", text)


if __name__ == "__main__":
    unittest.main()
