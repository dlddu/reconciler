"""`.github/scripts/check_llm_key_scope.py` 테스트 (python3 -m unittest discover -s tests)."""

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import check_llm_key_scope as ck  # noqa: E402


class CheckLlmKeyScopeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def problems(self, body: str) -> list[str]:
        f = self.dir / "wf.yml"
        f.write_text(textwrap.dedent(body))
        return ck.check_workflow(f)

    def test_repository_workflows_pass(self):
        files = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertTrue(files)
        for f in files:
            self.assertEqual(ck.check_workflow(f), [], f.name)

    def test_key_in_matching_environment_passes(self):
        self.assertEqual(self.problems("""
            jobs:
              a:
                runs-on: ubuntu-latest
                environment: llm-minimax
                steps:
                  - run: echo
                    env: {K: "${{ secrets.MINIMAX_SUBSCRIPTION_KEY }}"}
              b:
                runs-on: ubuntu-latest
                environment: {name: llm-claude}
                steps:
                  - run: echo
                    env: {K: "${{ secrets.ANTHROPIC_API_KEY }}", T: "${{ secrets.GITHUB_TOKEN }}"}
            """), [])

    def test_key_without_environment_fails(self):
        out = self.problems("""
            jobs:
              a:
                runs-on: ubuntu-latest
                steps:
                  - run: echo
                    env: {K: "${{ secrets.MINIMAX_SUBSCRIPTION_KEY }}"}
            """)
        self.assertEqual(len(out), 1)
        self.assertIn("environment 없음", out[0])

    def test_other_providers_key_in_environment_fails(self):
        out = self.problems("""
            jobs:
              a:
                runs-on: ubuntu-latest
                environment: llm-minimax
                steps:
                  - uses: ./setup
                    with: {key: "${{ secrets.MINIMAX_SUBSCRIPTION_KEY }}"}
                  - run: echo
                    env: {K: "${{ secrets.GLM_API_KEY }}"}
            """)
        self.assertEqual(len(out), 1)
        self.assertIn("GLM_API_KEY", out[0])
        self.assertIn("llm-glm", out[0])

    def test_workflow_level_env_and_bulk_forms_fail(self):
        out = self.problems("""
            env:
              K: "${{ secrets.ANTHROPIC_API_KEY }}"
            jobs:
              a:
                uses: ./.github/workflows/x.yml
                secrets: inherit
              b:
                runs-on: ubuntu-latest
                environment: llm-claude
                steps:
                  - run: echo '${{ toJSON(secrets) }}'
                  - run: echo "${{ secrets[inputs.name] }}"
            """)
        joined = "\n".join(out)
        self.assertIn("최상위 env", joined)
        self.assertIn("secrets: inherit", joined)
        self.assertEqual(sum("secret 전체" in p for p in out), 2)

    def test_commented_reference_is_ignored(self):
        self.assertEqual(self.problems("""
            # secrets.MINIMAX_SUBSCRIPTION_KEY 는 environment에 둔다
            jobs:
              a:
                runs-on: ubuntu-latest
                steps: [{run: echo}]
            """), [])


if __name__ == "__main__":
    unittest.main()
