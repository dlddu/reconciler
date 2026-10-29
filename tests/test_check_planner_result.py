"""`.github/scripts/check_planner_result.py` 테스트 (python3 -m unittest discover -s tests)."""

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import check_planner_result as cpr  # noqa: E402

MID, TID = "tbm_a", "rct_20261020-0001"
FILE = f"data/reconciliation-tasks/{MID}.json"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def claimed(attempts=None):
    t = {"id": TID, "toBeModelId": MID, "status": "planning", "createdAt": "2026-10-01T00:00:00Z",
         "updatedAt": "2026-10-27T00:00:00Z",
         "trigger": {"source": "manual", "detectedAt": "2026-10-01T00:00:00Z", "reason": "r"},
         "stateSummary": {"asIs": "a", "toBe": "b", "gap": "g"},
         "assessment": {"reason": "필요"}}
    if attempts:
        t["attempts"] = attempts
    return t


def attempt(reason=None, pr=None):
    a = {"plan": {"summary": "목업을 4×6으로 갱신. 범위: 목업만.", "riskLevel": "low",
                  "steps": [{"seq": 1, "action": "목업 수정", "expectedOutcome": "렌더 일치"},
                            {"seq": 2, "action": "PR", "expectedOutcome": "CI 통과"}],
                  "plannedAt": "2026-10-27T00:10:00Z",
                  "executionGuide": "## 순서\n1→2\n## 검증\n렌더 비교\n## 롤백\nrevert PR"},
         "preparation": {"repository": "dlddu/pocket-aide", "branch": "reconcile/x",
                         "pullRequestUrl": pr, "notes": "목업 2파일 변경"}}
    if reason:
        a["reason"] = reason
    return a


class CheckPlannerResultTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "r"
        (self.repo / "data/reconciliation-tasks").mkdir(parents=True)
        shutil.copytree(ROOT / "schemas", self.repo / "schemas")
        (self.repo / "data/to-be-models.json").write_text("[]\n")
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "b@e.com")
        git(self.repo, "config", "user.name", "b")

    def tearDown(self):
        self._tmp.cleanup()

    def base(self, task, others=()):
        self.write([task, *others])
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", f"plan({MID}/{TID}): claim")
        return git(self.repo, "rev-parse", "HEAD")

    def write(self, tasks, rel=FILE):
        (self.repo / rel).write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n")

    def commit(self, msg):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", msg)

    def run_check(self, base, from_status="action_required", **kw):
        return cpr.check(self.repo, base, MID, TID, from_status, **kw)

    def test_complete_plan_passes(self):
        base = self.base(claimed())
        t = claimed([attempt()])
        self.write([t]); self.commit(f"plan({MID}/{TID}): draft plan")  # noqa: E702
        t["status"] = "planned"
        self.write([t]); self.commit(f"plan({MID}/{TID}): ready for execution")  # noqa: E702
        res = self.run_check(base)
        self.assertEqual(res.errors, [])
        self.assertEqual(res.warnings, [])

    def test_rework_needs_reason_and_keeps_previous_attempts(self):
        prev = [{"plan": {"summary": "old", "steps": [{"seq": 1, "action": "x"}]},
                 "review": {"status": "rejected", "comment": "넓음"}}]
        base = self.base(claimed(copy.deepcopy(prev)))
        t = claimed(prev + [attempt()])  # reason 누락
        t["status"] = "planned"
        self.write([t]); self.commit(f"plan({MID}/{TID}): replan")  # noqa: E702
        res = self.run_check(base, from_status="review_rejected")
        self.assertEqual(res.errors, [])
        self.assertTrue(any("reason" in w for w in res.warnings))

        t["attempts"][0]["plan"]["summary"] = "고침"
        self.write([t]); self.commit(f"plan({MID}/{TID}): edit history")  # noqa: E702
        self.assertTrue(any("append-only" in e for e in self.run_check(base, "review_rejected").errors))

    def test_violations(self):
        other = {**claimed(), "id": "rct_20261020-0002", "status": "succeeded"}
        base = self.base(claimed(), [other])
        t = claimed([attempt(pr="https://github.com/dlddu/pocket-aide/pull/1")])
        t["status"] = "planned"
        t["stateSummary"]["gap"] = "바꿈"
        o = {**other, "updatedAt": "2026-10-27T01:00:00Z"}
        self.write([t, o])
        (self.repo / "data/to-be-models.json").write_text("[ ]\n")
        self.commit("wip")
        joined = "\n".join(self.run_check(base).errors)
        for needle in ("커밋 규약", "허용 범위 밖", "한 건만", "stateSummary"):
            self.assertIn(needle, joined)

    def test_left_planning_is_error(self):
        base = self.base(claimed())
        t = claimed([attempt()])
        self.write([t]); self.commit(f"plan({MID}/{TID}): draft")  # noqa: E702
        self.assertTrue(any("lock" in e for e in self.run_check(base).errors))

    def test_missing_preparation_and_guide(self):
        base = self.base(claimed())
        a = attempt()
        del a["preparation"]
        del a["plan"]["executionGuide"]
        t = claimed([a])
        t["status"] = "planned"
        self.write([t]); self.commit(f"plan({MID}/{TID}): ready")  # noqa: E702
        joined = "\n".join(self.run_check(base).errors)
        self.assertIn("executionGuide", joined)
        self.assertIn("preparation 없음", joined)

    def test_released_without_attempt_is_warning_with_attempt_is_error(self):
        base = self.base(claimed())
        t = claimed()
        t["status"] = "action_required"
        self.write([t]); self.commit(f"plan({MID}/{TID}): release lock")  # noqa: E702
        res = self.run_check(base)
        self.assertEqual(res.errors, [])
        self.assertTrue(any("lock 해제" in w for w in res.warnings))

        t = claimed([attempt()])
        t["status"] = "action_required"
        self.write([t]); self.commit(f"plan({MID}/{TID}): release with leftover")  # noqa: E702
        self.assertTrue(any("시도를 남기지 않는다" in e for e in self.run_check(base).errors))

    def test_pr_url_recorded_is_fine(self):
        base = self.base(claimed())
        t = claimed([attempt(pr="https://github.com/dlddu/pocket-aide/pull/1")])
        t["status"] = "planned"
        self.write([t]); self.commit(f"plan({MID}/{TID}): ready")  # noqa: E702
        res = self.run_check(base)
        self.assertEqual(res.errors, [])
        self.assertIn("preparation 기록", res.passed)

if __name__ == "__main__":
    unittest.main()
