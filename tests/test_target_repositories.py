"""`.github/scripts/target_repositories.py` 테스트 (python3 -m unittest discover -s tests)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import target_repositories as tr  # noqa: E402


class TargetRepositoriesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        (self.repo / "data").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, models):
        (self.repo / "data" / "to-be-models.json").write_text(json.dumps(models))

    def test_collects_nested_repositories_of_owner(self):
        self.write([
            {"id": "tbm_a", "asIs": {"dataSources": [{"type": "github", "repository": "dlddu/Pocket-Aide", "ref": "main"}]},
             "toBe": {"dataSources": [{"type": "github", "repository": "dlddu/pocket-aide"}]}},
            {"id": "tbm_b", "checkPolicy": {"enabled": False},
             "asIs": {"dataSources": [{"type": "github", "repository": "dlddu/tessera"},
                                      {"type": "github", "repository": "someone/else"},
                                      {"type": "kubernetes", "namespace": "x"}]}},
            {"id": "tbm_c", "toBe": {"dataSources": [{"type": "github", "repository": "dlddu/reconciler"}]},
             "definition": "repository: dlddu/feature-doc 는 본문이라 세지 않는다"},
        ])
        self.assertEqual(tr.target_repositories(self.repo, "dlddu", {"reconciler"}), ["pocket-aide", "tessera"])

    def test_main_prints_comma_list_and_fails_when_empty(self):
        self.write([{"id": "tbm_a", "asIs": {"dataSources": [{"repository": "dlddu/dear-baby"}, {"repository": "dlddu/feature-doc"}]}}])
        self.assertEqual(tr.main([str(self.repo), "--exclude", "feature-doc"]), 0)
        self.write([{"id": "tbm_a", "asIs": {"dataSources": [{"repository": "dlddu/reconciler"}]}}])
        self.assertEqual(tr.main([str(self.repo)]), 1)

    def test_live_data_has_targets(self):
        live = tr.target_repositories(ROOT, "dlddu", {"reconciler"})
        self.assertIn("pocket-aide", live)
        self.assertNotIn("reconciler", live)


if __name__ == "__main__":
    unittest.main()
