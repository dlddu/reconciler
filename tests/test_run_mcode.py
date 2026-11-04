"""`.github/scripts/run_mcode.sh` 테스트 (python3 -m unittest discover -s tests).

PATH 앞에 가짜 `mcode`를 두고, 재시도 가능한 오류면 같은 세션으로 한 번 더 돌고 아니면 멈추는지 본다.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".github" / "scripts" / "run_mcode.sh"

FAKE = r"""#!/usr/bin/env bash
# 호출마다 인자·stdin을 기록하고, FAKE_PLAN의 n번째 줄(retryable|fatal|ok)대로 끝난다.
n=$(( $(cat "$FAKE_DIR/count" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$FAKE_DIR/count"
echo "$*" > "$FAKE_DIR/args-$n"; cat > "$FAKE_DIR/stdin-$n"
case "$(sed -n "${n}p" "$FAKE_DIR/plan")" in
  retryable) echo '{"type":"exec.completed","result":{"status":"failed","sessionId":"mvs_1","error":{"retryable":true}}}'; exit 4 ;;
  fatal) echo '{"type":"exec.completed","result":{"status":"failed","sessionId":"mvs_1","error":{"retryable":false}}}'; exit 4 ;;
  *) echo '{"type":"exec.completed","result":{"status":"succeeded","sessionId":"mvs_1"}}'; exit 0 ;;
esac
"""


class RunMcodeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "mcode"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        self.fake_dir = self.tmp / "fake"
        self.fake_dir.mkdir()
        (self.tmp / "prompt.md").write_text("first prompt\n")
        (self.tmp / "resume.md").write_text("resume prompt\n")
        self.out = self.tmp / "out"
        self.env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_DIR": str(self.fake_dir),
                    "GITHUB_OUTPUT": str(self.tmp / "gh_out"), "MCODE_UNSET": "SECRET_X", "SECRET_X": "leak"}

    def tearDown(self):
        self._tmp.cleanup()

    def run_script(self, plan):
        (self.fake_dir / "plan").write_text("\n".join(plan) + "\n")
        proc = subprocess.run([str(SCRIPT), str(self.tmp / "prompt.md"), str(self.tmp / "resume.md"), str(self.out),
                               str(self.tmp), "4200"], env=self.env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        outputs = dict(line.split("=", 1) for line in (self.tmp / "gh_out").read_text().splitlines())
        return proc, outputs

    def test_retryable_error_resumes_same_session_once(self):
        _, outputs = self.run_script(["retryable", "ok"])
        self.assertEqual(outputs, {"exit_code": "0", "attempts": "2"})
        self.assertNotIn("--session", (self.fake_dir / "args-1").read_text())
        self.assertIn("--session mvs_1", (self.fake_dir / "args-2").read_text())
        self.assertEqual((self.fake_dir / "stdin-2").read_text(), "resume prompt\n")
        self.assertTrue((self.out / "transcript-attempt1.jsonl").exists())
        self.assertIn("succeeded", (self.out / "transcript.jsonl").read_text())

    def test_non_retryable_error_stops(self):
        _, outputs = self.run_script(["fatal", "ok"])
        self.assertEqual(outputs, {"exit_code": "4", "attempts": "1"})
        self.assertFalse((self.fake_dir / "args-2").exists())

    def test_retries_only_once(self):
        _, outputs = self.run_script(["retryable", "retryable", "ok"])
        self.assertEqual(outputs, {"exit_code": "4", "attempts": "2"})
        self.assertFalse((self.fake_dir / "args-3").exists())

    def test_unset_env_is_removed_from_mcode(self):
        (self.fake_dir / "plan").write_text("ok\n")
        probe = self.tmp / "bin" / "mcode"
        probe.write_text('#!/usr/bin/env bash\necho "SECRET_X=${SECRET_X:-unset}" > "$FAKE_DIR/env"; cat >/dev/null\n'
                         'echo \'{"type":"exec.completed","result":{"status":"succeeded"}}\'\n')
        subprocess.run([str(SCRIPT), str(self.tmp / "prompt.md"), str(self.tmp / "resume.md"), str(self.out),
                        str(self.tmp)], env=self.env, check=True, capture_output=True)
        self.assertEqual((self.fake_dir / "env").read_text().strip(), "SECRET_X=unset")


if __name__ == "__main__":
    unittest.main()
