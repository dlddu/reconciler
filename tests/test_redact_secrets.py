"""`.github/scripts/redact_secrets.py` 테스트 (python3 -m unittest discover -s tests)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import redact_secrets as rs  # noqa: E402

GH = "ghs_" + "A1b2C3d4" * 5
KEY = "sk-cp-" + "x9Y8z7W6" * 3


class RedactTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_jsonl_transcript_stays_valid_and_tokens_gone(self):
        event = {"item": {"toolCall": {"input": {"command": f"cat > t.env <<'E'\nGITHUB_TOKEN={GH}\nE"},
                                       "output": {"text": f"GITHUB_TOKEN={GH}"}}}}
        f = self.root / "logs" / "t.jsonl"
        f.parent.mkdir()
        f.write_text(json.dumps(event) + "\n" + json.dumps({"k": KEY}) + "\n")
        hits = rs.redact_dir(self.root, [])
        self.assertEqual(hits, {"logs/t.jsonl": 3})
        text = f.read_text()
        self.assertNotIn(GH, text)
        self.assertNotIn(KEY, text)
        for line in text.splitlines():
            json.loads(line)

    def test_basic_auth_url_credential_and_literal_env(self):
        b64 = "eC1hY2Nlc3MtdG9rZW46c2VjcmV0dmFsdWU="
        f = self.root / "a.log"
        f.write_text(f"AUTHORIZATION: basic {b64}\nhttps://x-access-token:supersecret1@github.com/a/b\nplain-literal-123\n")
        rs.redact_dir(self.root, ["plain-literal-123"])
        text = f.read_text()
        self.assertNotIn(b64, text)
        self.assertNotIn("supersecret1", text)
        self.assertNotIn("plain-literal-123", text)
        self.assertIn("https://x-access-token:<redacted:url-credential>@github.com", text)

    def test_binary_and_clean_files_untouched(self):
        (self.root / "b.bin").write_bytes(b"\0\1" + GH.encode())
        (self.root / "c.txt").write_text("nothing here")
        self.assertEqual(rs.redact_dir(self.root, []), {})


if __name__ == "__main__":
    unittest.main()
