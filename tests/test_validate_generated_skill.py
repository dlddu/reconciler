"""`.github/scripts/validate_generated_skill.py` 테스트 (python3 -m unittest discover -s tests)."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import validate_generated_skill as vgs  # noqa: E402

BODY = """
# reconciler-drift-detector

대상 선정과 점유는 러너가 끝냈다. 넘겨받은 `task_id` 한 건만 판정한다.

1. task가 `assessing`인지 확인한다. 그 task의 `trigger`·`createdAt`과 `to-be-models.json`은 그대로 둔다.
2. `stateSummary`와 `assessment`를 채우고 `schemas/reconciliation-task.schema.json`으로 jsonschema 검증.
3. `data/reconciliation-tasks/<model>.json`에 기록하고 커밋 `detect(<tbm>/<rct>): assess`.
4. `no_action_needed` 또는 `action_required`, 유예면 `assessment.recheckAfter`.
5. `git pull --rebase` 후 push. `RECONCILER_DRY_RUN=1`이면 push를 건너뛴다. 스키마는 절대 수정하지 않는다.
6. 대상 레포는 `github_app_installation_token`(contents:read)으로 읽는다.
"""


def skill_text(name="reconciler-drift-detector", desc="감지 단계 스킬", body=BODY, pad=1600):
    return f"---\nname: {name}\ndescription: \"{desc}\"\n---\n{body}\n" + ("관측 사실을 적는다. " * (pad // 10))


class ValidateGeneratedSkillTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "reconciler-drift-detector"
        self.dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, text, extra=None):
        (self.dir / "SKILL.md").write_text(text, encoding="utf-8")
        for rel, content in (extra or {}).items():
            p = self.dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return vgs.validate(self.dir)

    def test_complete_skill_passes_without_warnings(self):
        rep = self.write(skill_text())
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.warnings, [])

    def test_missing_file(self):
        self.assertTrue(vgs.validate(self.dir).errors)

    def test_wrong_name_and_missing_frontmatter(self):
        self.assertTrue(any("name" in e for e in self.write(skill_text(name="drift")).errors))
        self.assertTrue(any("frontmatter" in e for e in self.write(BODY * 5).errors))

    def test_folded_description_is_parsed(self):
        text = "---\nname: reconciler-drift-detector\ndescription: >\n  여러 줄\n  설명\n---\n" + BODY + "x" * 1600
        rep = self.write(text)
        self.assertEqual(rep.errors, [])
        self.assertGreater(rep.meta["description_chars"], 0)

    def test_missing_contract_items_are_errors(self):
        rep = self.write(skill_text(body=BODY.replace("recheckAfter", "재확인시각").replace("RECONCILER_DRY_RUN", "DRY")))
        joined = "\n".join(rep.errors)
        self.assertIn("recheckAfter", joined)
        self.assertIn("RECONCILER_DRY_RUN", joined)

    def test_missing_runner_claim_note_is_warning(self):
        body = BODY.replace("대상 선정과 점유는 러너가 끝냈다. ", "")
        rep = self.write(skill_text(body=body))
        self.assertEqual(rep.errors, [])
        self.assertTrue(any("점유는 러너 몫" in w for w in rep.warnings))

    def test_contract_covered_by_bundled_script(self):
        body = BODY.replace("`schemas/reconciliation-task.schema.json`으로 ", "")
        rep = self.write(skill_text(body=body))
        self.assertTrue(any("task 스키마 참조" in e for e in rep.errors))
        rep = self.write(skill_text(body=body), {"scripts/rec.py": 'SCHEMA = "reconciliation-task.schema.json"\n'})
        self.assertEqual(rep.errors, [])

    def test_short_body_is_error(self):
        self.assertTrue(any("짧음" in e for e in self.write(skill_text(pad=0)).errors))

    def test_forbidden_patterns(self):
        bad = BODY + "\n```\ngit push --force origin main\necho $GITHUB_TOKEN\n" \
                     "sed -i 's/a/b/' schemas/reconciliation-task.schema.json\n```\n"
        joined = "\n".join(self.write(skill_text(body=bad)).errors)
        self.assertIn("강제 push", joined)
        self.assertIn("토큰 출력", joined)
        self.assertIn("스키마 파일 쓰기", joined)

    def test_prohibition_lines_are_not_usage(self):
        ok = BODY + "\n- **강제 push 금지**(`git push --force`, `--force-with-lease` 사용 금지).\n" \
                    "- `echo $GITHUB_TOKEN` 같은 출력은 절대 하지 않는다.\n"
        self.assertEqual(self.write(skill_text(body=ok)).errors, [])
        bad = BODY + "\n```\ngit push --force origin main\n```\n"
        self.assertTrue(any("강제 push" in e for e in self.write(skill_text(body=bad)).errors))

    def test_scripts_are_checked(self):
        rep = self.write(skill_text(), {"scripts/ok.py": "print(1)\n", "scripts/bad.py": "def (:\n",
                                         "scripts/bad.sh": "if then\n"})
        joined = "\n".join(rep.errors)
        self.assertIn("bad.py", joined)
        self.assertIn("bad.sh", joined)
        self.assertNotIn("ok.py", joined)


if __name__ == "__main__":
    unittest.main()
