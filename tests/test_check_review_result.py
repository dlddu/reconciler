"""`.github/scripts/check_review_result.py` 테스트 (python3 -m unittest discover -s tests).

기준 = 러너의 점유 커밋(planned → reviewing). 스킬이 했을 법한 변경을 커밋한 뒤 점검기가 계약 위반을 잡는지 본다.
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import check_review_result as crr  # noqa: E402
from review_fixture import MID, TID, ReviewRepo, git, planned_task  # noqa: E402

SHA = "a" * 40
APPROVE = {"status": "approved", "reviewedAt": "2026-10-25T02:00:00Z", "reason": "PR 열림·CI 통과. 롤백 가능."}
REJECT = {"status": "rejected", "reviewedAt": "2026-10-25T02:00:00Z", "reason": "PR 머지됨.",
          "comment": "새 PR로 다시 준비할 것"}


def judged(status, review, **extra):
    t = planned_task(status=status, review=review)
    t.update(extra)
    return t


class CheckReviewResultTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = ReviewRepo(Path(self._tmp.name), {MID: [planned_task(status="reviewing")]},
                               message=f"review({MID}/{TID}): claim")
        self.base = git(self.repo.path, "rev-parse", "HEAD")

    def tearDown(self):
        self._tmp.cleanup()

    def check(self, **kw):
        return crr.check(self.repo.path, self.base, MID, TID, **kw)

    def test_approved_passes(self):
        self.repo.commit({MID: [judged("approved", APPROVE)]}, f"review({MID}/{TID}): approved")
        res = self.check()
        self.assertEqual(res.errors, [])
        self.assertEqual(res.facts["status"], "approved")

    def test_manual_approval_passes_and_only_on_approved(self):
        ma = dict(APPROVE, manualApproval={"sha": SHA, "context": "review/manual-approval"})
        self.repo.commit({MID: [judged("approved", ma)]}, f"review({MID}/{TID}): approved (manual approval required)")
        self.assertEqual(self.check().errors, [])
        bad = dict(REJECT, manualApproval={"sha": SHA, "context": "review/manual-approval"})
        self.repo.commit({MID: [judged("review_rejected", bad)]}, f"review({MID}/{TID}): rejected")
        self.assertTrue(any("manualApproval" in e for e in self.check().errors))

    def test_rejected_needs_comment_and_matching_review_status(self):
        no_comment = {k: v for k, v in REJECT.items() if k != "comment"}
        self.repo.commit({MID: [judged("review_rejected", no_comment)]}, f"review({MID}/{TID}): rejected")
        self.assertTrue(any("comment" in e for e in self.check().errors))
        self.repo.commit({MID: [judged("review_rejected", APPROVE)]}, f"review({MID}/{TID}): rejected")
        self.assertTrue(any("review.status" in e for e in self.check().errors))

    def test_cancelled_counts_as_rejection(self):
        self.repo.commit({MID: [judged("cancelled", REJECT)]}, f"review({MID}/{TID}): cancel after repeated rejection")
        self.assertEqual(self.check().errors, [])

    def test_lock_left_or_released_without_verdict_is_error(self):
        self.repo.commit({MID: [judged("reviewing", APPROVE)]}, f"review({MID}/{TID}): note")
        self.assertTrue(any("lock" in e for e in self.check().errors))
        self.repo.commit({MID: [planned_task()]}, f"review({MID}/{TID}): release")
        self.assertTrue(any("판정 없이" in e for e in self.check().errors))

    def test_editing_plan_or_previous_attempt_is_error(self):
        t = judged("approved", APPROVE)
        t["attempts"][-1]["plan"]["summary"] = "바꿈"
        self.repo.commit({MID: [t]}, f"review({MID}/{TID}): approved")
        self.assertTrue(any("review 밖 키" in e for e in self.check().errors))

    def test_previous_attempts_append_only(self):
        base = planned_task(status="reviewing")
        first = copy.deepcopy(base["attempts"][0])
        first["review"] = REJECT
        base["attempts"] = [first, copy.deepcopy(planned_task()["attempts"][0])]
        self.repo.commit({MID: [base]}, f"review({MID}/{TID}): claim")
        self.base = git(self.repo.path, "rev-parse", "HEAD")
        after = copy.deepcopy(base)
        after["status"] = "approved"
        after["attempts"][0]["review"] = dict(REJECT, comment="고침")
        after["attempts"][1]["review"] = APPROVE
        self.repo.commit({MID: [after]}, f"review({MID}/{TID}): approved")
        self.assertTrue(any("append-only" in e for e in self.check().errors))

    def test_preserved_fields_and_scope(self):
        t = judged("approved", APPROVE, stateSummary={"asIs": "x", "toBe": "y", "gap": "z"})
        self.repo.commit({MID: [t], "tbm_other": [planned_task(mid="tbm_other")]}, f"review({MID}/{TID}): approved")
        errors = self.check().errors
        self.assertTrue(any("stateSummary" in e for e in errors))
        self.assertTrue(any("허용 범위 밖" in e for e in errors))

    def test_bad_commit_subject_and_no_commit(self):
        self.assertTrue(any("새 커밋이 없음" in e for e in self.check().errors))
        self.repo.commit({MID: [judged("approved", APPROVE)]}, "chore: approve")
        self.assertTrue(any("커밋 규약" in e for e in self.check().errors))

    def test_expectation(self):
        self.repo.commit({MID: [judged("approved", APPROVE)]}, f"review({MID}/{TID}): approved")
        self.assertTrue(any("기대 status" in e for e in self.check(expect=["review_rejected", "cancelled"]).errors))
        self.assertEqual(self.check(expect=["approved"]).errors, [])

    def test_transcript_target_write_is_error(self):
        self.repo.commit({MID: [judged("approved", APPROVE)]}, f"review({MID}/{TID}): approved")
        path = Path(self._tmp.name) / "t.jsonl"
        call = {"type": "item.completed", "item": {"id": "1", "type": "tool_call",
                                                   "toolCall": {"name": "mcp__k3s__github_commit_status_create",
                                                                "arguments": {"state": "success"}}}}
        path.write_text(json.dumps(call) + "\n")
        self.assertTrue(any("대상 레포 쓰기" in e for e in self.check(transcript=path).errors))
        call["item"]["toolCall"] = {"name": "Bash", "arguments": {"command": "gh api repos/o/r/pulls/3"}}
        path.write_text(json.dumps(call) + "\n")
        self.assertEqual(self.check(transcript=path).errors, [])

    def test_main_writes_task_and_report(self):
        self.repo.commit({MID: [judged("approved", APPROVE)]}, f"review({MID}/{TID}): approved")
        out = Path(self._tmp.name)
        code = crr.main(["--repo", str(self.repo.path), "--base", self.base, "--model-id", MID, "--task-id", TID,
                         "--report", str(out / "r.md"), "--json", str(out / "r.json"), "--patch", str(out / "p.diff"),
                         "--task-out", str(out / "task.json")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((out / "task.json").read_text())["status"], "approved")
        self.assertIn("✅ 통과", (out / "r.md").read_text())
        self.assertIn('"approved"', (out / "p.diff").read_text())
        self.assertNotIn("task", json.loads((out / "r.json").read_text())["facts"])


if __name__ == "__main__":
    unittest.main()
