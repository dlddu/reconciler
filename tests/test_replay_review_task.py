"""`.github/scripts/replay_review_task.py` 테스트 (python3 -m unittest discover -s tests).

이력: base(planned) → `review(...): claim`(reviewing) → `review(...): approved` 를 만들고, replay가 점유 직전
레코드를 되돌려 샌드박스 origin에 push하는지 본다. PR 조회는 가짜 lookup으로 대신한다(네트워크 없음).
"""

import json
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
TID2 = "rct_20261025-0002"
PR2 = "https://github.com/dlddu/demo/pull/8"
HEAD = "c" * 40


def info(state, head_ref="reconcile/x", head_sha=HEAD):
    return {"state": state, "head_sha": head_sha, "head_ref": head_ref, "base_ref": "main",
            "title": "real title", "body": "real body"}


def reviewed_history(tmp: Path, models=None):
    """TID 하나: planned → claim → approved(→ succeeded)."""
    repo = ReviewRepo(tmp, {MID: [planned_task()]}, models=models)
    claim = repo.commit({MID: [planned_task(status="reviewing")]}, f"review({MID}/{TID}): claim")
    repo.commit({MID: [planned_task(status="succeeded", review=APPROVED)]}, f"review({MID}/{TID}): approved")
    git(repo.path, "push", "-q", "origin", "main")
    return repo, claim


def two_task_history(tmp: Path):
    """TID2(PR 8)가 먼저, TID(PR 7)가 나중에 리뷰됨 — 최근 후보는 TID."""
    t2 = lambda status, review=None: planned_task(TID2, status=status, pr=PR2, review=review)  # noqa: E731
    t1 = lambda status, review=None: planned_task(TID, status=status, review=review)  # noqa: E731
    repo = ReviewRepo(tmp, {MID: [t1("planned"), t2("planned")]})
    c2 = repo.commit({MID: [t1("planned"), t2("reviewing")]}, f"review({MID}/{TID2}): claim")
    repo.commit({MID: [t1("planned"), t2("succeeded", APPROVED)]}, f"review({MID}/{TID2}): approved")
    c1 = repo.commit({MID: [t1("reviewing"), t2("succeeded", APPROVED)]}, f"review({MID}/{TID}): claim")
    repo.commit({MID: [t1("approved", APPROVED), t2("succeeded", APPROVED)]}, f"review({MID}/{TID}): approved")
    git(repo.path, "push", "-q", "origin", "main")
    return repo, c1, c2


class ReplayReviewTaskTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def main(self, repo, *extra, states=None, token="tok"):
        self.out = self.tmp / "out.txt"
        self.out.write_text("")
        env = {"REPLAY_TOKEN": token} if token else {}
        lookup = (lambda url, tok: (states or {}).get(url))
        old = dict(rrt.os.environ)
        rrt.os.environ.update(env)
        try:
            return rrt.main(["--repo", str(repo.path), "--github-output", str(self.out), "--summary-file",
                             str(self.tmp / "s.md"), "--token-env", "REPLAY_TOKEN", *extra], lookup=lookup)
        finally:
            rrt.os.environ.clear()
            rrt.os.environ.update(old)

    def outputs(self):
        return dict(line.split("=", 1) for line in self.out.read_text().splitlines())

    # ── merged ────────────────────────────────────────────────────────────────

    def test_merged_mode_prefers_merged_pr_over_more_recent_open_one(self):
        repo, _, c2 = two_task_history(self.tmp)
        self.assertEqual(self.main(repo, states={PR: info("open"), PR2: info("merged")}), 0)
        out = self.outputs()
        self.assertEqual((out["target"], out["original_claim"]), (f"{MID}/{TID2}", c2))
        self.assertEqual((out["pr_state"], out["expect_statuses"]), ("merged", "review_rejected,cancelled"))
        self.assertEqual(repo.tasks(rev="origin/main")[1]["status"], "planned")
        self.assertIn("sandbox only", git(repo.path, "log", "-1", "--format=%s", "origin/main"))

    def test_merged_mode_falls_back_without_expectation(self):
        repo, c1, _ = two_task_history(self.tmp)
        self.assertEqual(self.main(repo, states={PR: info("open"), PR2: info("open")}), 0)
        out = self.outputs()
        self.assertEqual((out["target"], out["expect_statuses"]), (f"{MID}/{TID}", ""))
        self.assertIn("머지·종료된 PR 건을 찾지 못함", (self.tmp / "s.md").read_text())
        repo2, claim = reviewed_history(self.tmp / "b")
        self.assertEqual(self.main(repo2, token=None), 0)  # 토큰 없음 — 조회 없이 최근 후보
        self.assertEqual((self.outputs()["original_claim"], self.outputs()["expect_statuses"]), (claim, ""))

    def test_max_lookups(self):
        repo, c1, _ = two_task_history(self.tmp)
        self.assertEqual(self.main(repo, "--max-lookups", "1", states={PR: info("open"), PR2: info("merged")}), 0)
        self.assertEqual(self.outputs()["expect_statuses"], "")  # 두 번째(머지된) 후보까지 보지 않음

    # ── ci-failure ────────────────────────────────────────────────────────────

    def test_ci_failure_rehosts_open_pr_as_sandbox_pr(self):
        repo, _, _ = two_task_history(self.tmp)
        sbx = self.tmp / "sandbox"
        self.assertEqual(self.main(repo, "--mode", "ci-failure", "--sandbox-root", str(sbx),
                                   states={PR: info("open"), PR2: info("merged")}), 0)
        out = self.outputs()
        new_url = "https://github.com/dlddu/demo/pull/90001"
        self.assertEqual((out["target"], out["mode"]), (f"{MID}/{TID}", "ci-failure"))
        self.assertEqual((out["pull_request_url"], out["original_pr"]), (new_url, PR))
        self.assertEqual(out["expect_statuses"], "review_rejected,cancelled")
        seed = json.loads((sbx / "seed.json").read_text())
        self.assertEqual(seed["branches"], [{"repository": "dlddu/demo", "name": "reconcile/x-2", "sha": HEAD}])
        self.assertEqual(seed["pulls"][0]["head"], "reconcile/x-2")
        self.assertEqual((seed["pulls"][0]["number"], seed["pulls"][0]["title"]), (90001, "real title"))
        rec = repo.tasks(rev="origin/main")[0]
        prep = rec["attempts"][-1]["preparation"]
        self.assertEqual((rec["status"], prep["pullRequestUrl"], prep["branch"]), ("planned", new_url, "reconcile/x-2"))

    def test_ci_failure_rewrites_old_references_in_last_attempt(self):
        repo, _ = reviewed_history(self.tmp)
        rp = rrt.Replay(MID, TID, planned_task(), "a" * 40, "", pull_request_url=PR, original_pr=PR)
        rp.record["attempts"][-1]["preparation"]["notes"] = "PR #7 (reconcile/x) 통과. #70 · reconcile/x-old 는 그대로"
        rp.record["attempts"][-1]["plan"]["executionGuide"] = f"1. {PR} 머지"
        rrt.rehost(rp, info("open"))
        last = rp.record["attempts"][-1]
        self.assertEqual(last["preparation"]["notes"], "PR #90001 (reconcile/x-2) 통과. #70 · reconcile/x-old 는 그대로")
        self.assertEqual(last["plan"]["executionGuide"], "1. https://github.com/dlddu/demo/pull/90001 머지")

    def test_ci_failure_needs_open_pr_and_token(self):
        repo, _, _ = two_task_history(self.tmp)
        sbx = self.tmp / "sandbox"
        self.assertEqual(self.main(repo, "--mode", "ci-failure", "--sandbox-root", str(sbx),
                                   states={PR: info("merged"), PR2: info("closed")}), 1)
        self.assertEqual(self.main(repo, "--mode", "ci-failure", "--sandbox-root", str(sbx), token=None), 1)
        self.assertFalse((sbx / "seed.json").exists())

    # ── 공통 ──────────────────────────────────────────────────────────────────

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
        self.assertEqual(self.main(repo, "--target", f"{MID}/{TID}", states={PR: info("merged")}), 0)
        self.assertEqual(self.outputs()["expect_statuses"], "review_rejected,cancelled")

    def test_is_local_url(self):
        self.assertTrue(rrt.is_local_url("/tmp/sandbox.git"))
        self.assertTrue(rrt.is_local_url("file:///tmp/sandbox.git"))
        self.assertTrue(rrt.is_local_url("../sandbox.git"))
        self.assertFalse(rrt.is_local_url("https://github.com/dlddu/reconciler"))
        self.assertFalse(rrt.is_local_url("git@github.com:dlddu/reconciler.git"))
        self.assertFalse(rrt.is_local_url(""))


if __name__ == "__main__":
    unittest.main()
