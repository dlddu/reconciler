"""`.github/scripts/claude_transcript.py` 테스트 (python3 -m unittest discover -s tests)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import claude_transcript as ct  # noqa: E402

INIT = {"type": "system", "subtype": "init", "model": "claude-opus-5-5",
        "mcp_servers": [{"name": "k3s", "status": "connected"}]}
TOOL_USE = {"type": "assistant", "message": {"content": [
    {"type": "text", "text": "레포 확보"},
    {"type": "tool_use", "id": "t1", "name": "mcp__k3s__github_app_installation_token", "input": {}},
    {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "git clone ..."}},
    {"type": "tool_use", "id": "t3", "name": "Skill", "input": {"skill": "reconciler-data-plane:reconciler-repo-access"}},
]}}
TOOL_RESULT = {"type": "user", "message": {"content": [
    {"type": "tool_result", "tool_use_id": "t2", "is_error": True, "content": "fatal"},
]}}
RESULT_OK = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 7,
             "duration_ms": 180000, "total_cost_usd": 1.234, "result": "감지 완료: no_action_needed"}


class TranscriptTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, *events, extra=""):
        f = self.dir / "t.jsonl"
        f.write_text("\n".join(json.dumps(e) for e in events) + "\n" + extra)
        return f

    def test_summary_counts_tools_and_result(self):
        tr = ct.load(self.write(INIT, TOOL_USE, TOOL_RESULT, RESULT_OK, extra="not json\n"))
        self.assertEqual(tr.tool_calls["Bash"], 1)
        self.assertEqual(tr.tool_errors, 1)
        self.assertEqual(tr.skills, ["reconciler-data-plane:reconciler-repo-access"])
        text = ct.summary(tr)
        self.assertIn("k3s=connected", text)
        self.assertIn("7턴", text)
        self.assertIn("$1.23", text)
        self.assertIn("해석 못 한 줄 1개", text)

    def test_summary_shows_mcp_server_errors(self):
        init = dict(INIT, mcp_server_errors=[{"name": "k3s", "error": "invalid url"}])
        self.assertIn("invalid url", ct.summary(ct.load(self.write(init, RESULT_OK))))

    def test_check_passes_on_success_with_connected_mcp(self):
        tr = ct.load(self.write(INIT, RESULT_OK))
        self.assertEqual(ct.problems(tr, ["k3s"]), [])

    def test_check_fails_without_result_or_on_error(self):
        self.assertTrue(ct.problems(ct.load(self.write(INIT, TOOL_USE)), []))
        err = dict(RESULT_OK, subtype="error_max_turns", is_error=True)
        self.assertTrue(ct.problems(ct.load(self.write(INIT, err)), []))

    def test_check_fails_when_mcp_not_connected(self):
        init = dict(INIT, mcp_servers=[{"name": "k3s", "status": "failed"}])
        found = ct.problems(ct.load(self.write(init, RESULT_OK)), ["k3s"])
        self.assertEqual(len(found), 1)
        self.assertIn("failed", found[0])

    def test_final_writes_result_text_and_missing_file_is_empty(self):
        out = self.dir / "final.md"
        self.assertEqual(ct.main(["final", str(self.write(INIT, RESULT_OK)), "--out", str(out)]), 0)
        self.assertEqual(out.read_text(), "감지 완료: no_action_needed")
        self.assertIsNone(ct.load(self.dir / "missing.jsonl").result)


class UsageLimitTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def load(self, *events, extra=""):
        f = self.dir / "t.jsonl"
        f.write_text("\n".join(json.dumps(e) for e in events) + "\n" + extra)
        return ct.load(f)

    @staticmethod
    def rate(status, kind="five_hour", resets=1793079000, util=1.0):
        return {"type": "rate_limit_event",
                "rate_limit_info": {"status": status, "rateLimitType": kind, "resetsAt": resets, "utilization": util}}

    LIMIT_RESULT = dict(RESULT_OK, is_error=True, num_turns=1, total_cost_usd=0,
                        result="You've hit your session limit · resets 3:50pm (Asia/Seoul)")

    def test_rejected_rate_limit_event(self):
        tr = self.load(INIT, self.rate("allowed_warning", util=0.9), self.rate("rejected"), self.LIMIT_RESULT)
        limit = ct.usage_limit(tr)
        self.assertEqual(limit["source"], "rate_limit_event")
        self.assertEqual(limit["label"], "5시간 세션 한도")
        self.assertEqual(ct.format_reset(limit["resets_at"], "Asia/Seoul"), "10-27 14:30 KST")
        self.assertEqual(len(ct.problems(tr, [])), 1)
        self.assertIn("한도 초과", ct.problems(tr, [])[0])
        self.assertIn("⛔", ct.summary(tr))

    def test_resets_at_in_milliseconds(self):
        tr = self.load(INIT, self.rate("rejected", kind="seven_day", resets=1793079000000), self.LIMIT_RESULT)
        limit = ct.usage_limit(tr)
        self.assertEqual(limit["label"], "주간 한도")
        self.assertEqual(ct.format_reset(limit["resets_at"], "Asia/Seoul"), "10-27 14:30 KST")

    def test_result_text_only(self):
        for text in ("You've hit your session limit · resets 3:50pm", "API Error: Rate limit reached",
                     "Claude AI usage limit reached|1793079000", "You've hit your weekly limit"):
            tr = self.load(INIT, dict(RESULT_OK, is_error=True, result=text))
            self.assertEqual(ct.usage_limit(tr)["source"], "result", text)

    def test_rejected_inside_corrupted_line(self):
        broken = '{"type":"assistant","message":{"content":[{"type":"te{"type":"rate_limit_event","rate_limit_info":{"status":"rejected"}}xt"}]}}'
        tr = self.load(INIT, extra=broken + "\n")
        self.assertEqual(ct.usage_limit(tr)["source"], "rate_limit_event(깨진 줄)")

    def test_not_a_limit(self):
        cases = [
            (INIT, self.rate("allowed_warning", util=0.95), RESULT_OK),  # 경고만
            (INIT, dict(RESULT_OK, is_error=True, result="Usage credits are required for this model.")),
            (INIT, dict(RESULT_OK, result="완료 — rate limit 관련 대상 레포 설정은 이상 없음")),  # 정상 보고 속 단어
            (INIT, dict(RESULT_OK, subtype="error_max_turns", is_error=True, result="")),
        ]
        for events in cases:
            self.assertIsNone(ct.usage_limit(self.load(*events)), events)

    def test_limit_outputs_and_notify_payload(self):
        f = self.dir / "t.jsonl"
        f.write_text("\n".join(json.dumps(e) for e in (INIT, self.rate("rejected"), self.LIMIT_RESULT)) + "\n")
        out = self.dir / "gh_output"
        self.assertEqual(ct.main(["limit", str(f), "--github-output", str(out)]), 0)
        values = dict(line.split("=", 1) for line in out.read_text().splitlines())
        self.assertEqual(values["limited"], "true")
        self.assertEqual(values["resets_local"], "10-27 14:30 KST")
        payload = ct.notify_payload(ct.usage_limit(ct.load(f)), "reconciler-work-planner",
                                    "rct_20261013-0006 (tbm_x)", "https://github.com/r/actions/runs/1", "Asia/Seoul")
        self.assertEqual(payload["title"], "reconciler work-planner — Claude 한도 초과로 중단")
        self.assertIn("5시간 세션 한도 · 재설정 10-27 14:30 KST", payload["body"])
        self.assertIn("rct_20261013-0006 (tbm_x)", payload["body"])
        self.assertLessEqual(len(payload["title"]), 120)

    def test_limit_output_false_when_clean(self):
        f = self.dir / "t.jsonl"
        f.write_text(json.dumps(INIT) + "\n" + json.dumps(RESULT_OK) + "\n")
        out = self.dir / "gh_output"
        ct.main(["limit", str(f), "--github-output", str(out)])
        self.assertEqual(out.read_text(), "limited=false\n")


if __name__ == "__main__":
    unittest.main()
