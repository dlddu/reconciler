"""`.github/scripts/mcode_transcript.py` 테스트 (python3 -m unittest discover -s tests)."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import mcode_transcript as mt  # noqa: E402

EVENTS = [
    {"type": "exec.started"},
    {"type": "item.started", "item": {"id": "a", "type": "agent_message", "content": "ping을 부르겠다"}},
    {"type": "item.started", "item": {"id": "t1", "type": "tool_call", "toolCall": {"name": "mcp__k3s__ping"}}},
    {"type": "item.completed", "item": {"id": "t1", "type": "tool_call", "toolCall": {"name": "mcp__k3s__ping"}}},
    {"type": "item.completed", "item": {"id": "t2", "type": "tool_call", "toolCall": {"name": "bash"}}},
    {"type": "exec.completed", "result": {"status": "completed", "model": {"providerId": "minimax", "modelId": "M"}}},
]


class TranscriptTest(unittest.TestCase):
    def setUp(self):
        self.file = Path(tempfile.mkstemp(suffix=".jsonl")[1])
        self.file.write_text("\n".join(json.dumps(e) for e in EVENTS) + "\nnot json\n")

    def tearDown(self):
        self.file.unlink()

    def run_main(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = mt.main(list(args))
        return rc, buf.getvalue()

    def test_forbid_flags_tool_calls_touching_answer_key(self):
        events = EVENTS + [{"type": "item.completed", "item": {"id": "t3", "type": "tool_call", "toolCall": {
            "name": "bash", "input": {"command": "cat /tmp/fx/expect.json"}}}}]
        self.file.write_text("\n".join(json.dumps(e) for e in events) + "\n")
        rc, out = self.run_main("forbid", str(self.file), "expect.json", "check_executor_result")
        self.assertEqual(rc, 1)
        self.assertIn("expect.json", out)
        rc, _ = self.run_main("forbid", str(self.file), "check_executor_result")
        self.assertEqual(rc, 0)

    def test_require_tool_uses_tool_call_items_not_prose(self):
        self.assertEqual(self.run_main("require-tool", str(self.file), "ping")[0], 0)
        self.assertEqual(self.run_main("require-tool", str(self.file), "agent_message")[0], 1)
        self.assertEqual(self.run_main("require-tool", str(self.file), "겠다")[0], 1)

    def test_summary_dedupes_by_item_id(self):
        rc, out = self.run_main("summary", str(self.file))
        self.assertEqual(rc, 0)
        self.assertIn("도구 호출 2회", out)
        self.assertIn("`completed`", out)


if __name__ == "__main__":
    unittest.main()
