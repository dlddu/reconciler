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


if __name__ == "__main__":
    unittest.main()
