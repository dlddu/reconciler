"""`.github/scripts/replay_review_task.py` 테스트 (python3 -m unittest discover -s tests).

이력: base(planned) → `review(...): claim`(reviewing) → `review(...): approved` 를 만들고, replay가 점유 직전
레코드를 되돌려 샌드박스 origin에 push하는지 본다. PR 상태 조회는 가짜 lookup으로 대신한다(네트워크 없음).
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import replay_review_task as rrt  # noqa: E402
from review_fixture import MID, PR, TID, ReviewRepo, git, model, planned_task  # noqa: E402

APPROVED = {"status": "approved", "reviewedAt": "2026-10-25T02:00:00Z", "reason": "근거"}


def reviewed_history(tmp: Path, models=None):
    repo = ReviewRepo(tmp, {MID: [planned_task()]}, models=models)
    claim = repo.commit({MID: [planned_task(status="reviewing")]}, f"review({MID}/{TID}): claim")
    repo.commit({MID: [planned_task(status="succeeded", review=APPROVED)]}, f"review({MID}/{TID}): approved")
    git(repo.path, "push", "-q", "origin", "main")
    return repo, claim


class ReplayReviewTaskTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def main(self, repo, *extra, lookup=lambda url, token: ""):
        self.out = self.tmp / "out.txt"
        self.out.write_text("")
        return rrt.main(["--repo", str(repo.path), "--github-output", str(self.out), "--summary-file",
                         str(self.tmp / "s.md"), *extra], lookup=lookup)

    def outputs(self):
        return dict(line.split("=", 1) for line in self.out.read_text().splitlines())

    def test_rewinds_latest_claim_to_planned_and_pushes_to_sandbox(self):
        repo, claim = reviewed_history(self.tmp)
        self.assertEqual(self.main(repo), 0)
        out = self.outputs()
        self.assertEqual(out["target"], f"{MID}/{TID}")
        self.assertEqual(out["original_claim"], claim)
        self.assertIn("review approved", out["original_verdict"])
        self.assertEqual(out["pull_request_url"], PR)
        self.assertEqual(out["expect_statuses"], "")
        origin = repo.tasks(rev="origin/main")[0]
        self.assertEqual(origin, planned_task())
        self.assertIn("sandbox only", git(repo.path, "log", "-1", "--format=%s", "origin/main"))

    def test_merged_pr_expects_rejection(self):
        repo, _ = reviewed_history(self.tmp)
        self.assertEqual(self.main(repo, lookup=lambda url, token: "merged"), 0)
        self.assertEqual(self.outputs()["pr_state"], "merged")
        self.assertEqual(self.outputs()["expect_statuses"], "review_rejected,cancelled")

    def test_refuses_non_local_remote(self):
        repo, _ = reviewed_history(self.tmp)
        git(repo.path, "remote", "set-url", "--push", "origin", "https://github.com/dlddu/reconciler.git")
        head = git(repo.path, "rev-parse", "HEAD")
        self.assertEqual(self.main(repo), 1)
        self.assertEqual(git(repo.path, "rev-parse", "HEAD"), head)  # 아무것도 쓰지 않음

    def test_skips_live_and_disabled(self):
        repo, _ = reviewed_history(self.tmp, models=[model(enabled=False), model("tbm_other")])
        self.assertEqual(self.main(repo), 1)
        live = ReviewRepo(self.tmp / "live")
        live.commit({MID: [planned_task(status="reviewing")]}, f"review({MID}/{TID}): claim")
        live.commit({MID: [planned_task(status="planned")]}, "revert claim")
        self.assertEqual(self.main(live), 1)

    def test_explicit_target(self):
        repo, _ = reviewed_history(self.tmp)
        self.assertEqual(self.main(repo, "--target", f"tbm_other/{TID}"), 1)
        self.assertEqual(self.main(repo, "--target", f"{MID}/{TID}"), 0)

    def test_is_local_url(self):
        self.assertTrue(rrt.is_local_url("/tmp/sandbox.git"))
        self.assertTrue(rrt.is_local_url("file:///tmp/sandbox.git"))
        self.assertTrue(rrt.is_local_url("../sandbox.git"))
        self.assertFalse(rrt.is_local_url("https://github.com/dlddu/reconciler"))
        self.assertFalse(rrt.is_local_url("git@github.com:dlddu/reconciler.git"))
        self.assertFalse(rrt.is_local_url(""))


if __name__ == "__main__":
    unittest.main()
