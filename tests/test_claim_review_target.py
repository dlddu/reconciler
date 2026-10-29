"""`.github/scripts/claim_review_target.py` 테스트 (python3 -m unittest discover -s tests).

경쟁은 push 직전 훅에서 "다른 워커"가 같은 origin에 먼저 커밋을 밀어 넣는 것으로 재현한다.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import claim_review_target as crt  # noqa: E402
from review_fixture import MID, PR, TID, ReviewRepo, git, model, planned_task  # noqa: E402


def flip(worker: Path, mid: str, tid: str, status: str, msg: str):
    path = worker / "data" / "reconciliation-tasks" / f"{mid}.json"
    tasks = json.loads(path.read_text())
    next(t for t in tasks if t["id"] == tid)["status"] = status
    path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n")
    git(worker, "commit", "-qam", msg)
    git(worker, "push", "-q")


class ClaimReviewTargetTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_claim(self, repo, explicit=None, before_push=None):
        return crt.run(repo.path, explicit=explicit, remote="origin", branch="main", before_push=before_push)

    def test_claims_oldest_planned_and_pushes_status_only(self):
        repo = ReviewRepo(self.tmp, {MID: [planned_task("rct_20261025-0002", updated="2026-10-25T05:00:00Z"),
                                           planned_task(TID, updated="2026-10-25T01:00:00Z")]})
        before = repo.tasks()
        out = self.run_claim(repo)
        self.assertEqual(out.claim.status, "claimed")
        self.assertEqual(out.selection.target_id, TID)
        self.assertEqual(out.claim.message, f"review({MID}/{TID}): claim")
        self.assertEqual(git(repo.path, "rev-parse", "origin/main"), out.claim.commit)
        after = repo.tasks(rev="origin/main")
        changed = [a["id"] for a, b in zip(after, before) if a != b]
        self.assertEqual(changed, [TID])
        diff = {k for k in after[1] if after[1][k] != before[1][k]}
        self.assertEqual(diff, {"status"})
        self.assertEqual(after[1]["status"], "reviewing")
        self.assertEqual(after[0]["status"], "planned")  # 한 건만

    def test_no_planned_target(self):
        repo = ReviewRepo(self.tmp, {MID: [planned_task(status="approved")]})
        out = self.run_claim(repo)
        self.assertIsNone(out.claim)
        self.assertFalse(out.selection.found)

    def test_lost_race_moves_to_next_candidate(self):
        second = "rct_20261025-0002"
        repo = ReviewRepo(self.tmp, {MID: [planned_task(TID), planned_task(second, updated="2026-10-25T09:00:00Z")]})
        worker = repo.other_worker()

        def race(attempt):
            if attempt == 1 and not getattr(race, "done", False):
                race.done = True
                flip(worker, MID, TID, "reviewing", f"review({MID}/{TID}): claim")

        out = self.run_claim(repo, before_push=race)
        self.assertEqual(out.lost[0][0], f"{MID}/{TID}")
        self.assertIn("다른 워커", out.lost[0][1])
        self.assertEqual(out.selection.target_id, second)
        statuses = {t["id"]: t["status"] for t in repo.tasks(rev="origin/main")}
        self.assertEqual(statuses, {TID: "reviewing", second: "reviewing"})

    def test_explicit_target_lost_race_stops(self):
        second = "rct_20261025-0002"
        repo = ReviewRepo(self.tmp, {MID: [planned_task(TID), planned_task(second)]})
        worker = repo.other_worker()
        out = self.run_claim(repo, explicit=f"{MID}/{TID}",
                             before_push=lambda a: a == 1 and flip(worker, MID, TID, "reviewing", "w claim"))
        self.assertIsNone(out.claim)
        self.assertEqual(len(out.lost), 1)
        self.assertEqual(repo.tasks(rev="origin/main")[1]["status"], "planned")

    def test_unrelated_commit_is_retried(self):
        repo = ReviewRepo(self.tmp, {MID: [planned_task()], "tbm_other": [planned_task(status="approved", mid="tbm_other")]})
        worker = repo.other_worker()
        out = self.run_claim(repo, before_push=lambda a: a == 1 and flip(
            worker, "tbm_other", TID, "executing", f"execute(tbm_other/{TID}): claim"))
        self.assertEqual(out.claim.status, "claimed")
        self.assertEqual(repo.tasks(rev="origin/main")[0]["status"], "reviewing")
        subjects = git(repo.path, "log", "--format=%s", "-2", "origin/main").splitlines()
        self.assertEqual(subjects[0], f"review({MID}/{TID}): claim")

    def test_disabled_model_is_parked(self):
        repo = ReviewRepo(self.tmp, models=[model(enabled=False)])
        self.assertIsNone(self.run_claim(repo).claim)

    def test_main_outputs(self):
        repo = ReviewRepo(self.tmp)
        out_file = self.tmp / "out.txt"
        code = crt.main(["--repo", str(repo.path), "--github-output", str(out_file), "--summary-file", str(self.tmp / "s.md")])
        self.assertEqual(code, 0)
        outputs = dict(line.split("=", 1) for line in out_file.read_text().splitlines())
        self.assertEqual(outputs["claimed"], "true")
        self.assertEqual(outputs["task_id"], TID)
        self.assertEqual(outputs["pull_request_url"], PR)
        self.assertEqual(outputs["claim_message"], f"review({MID}/{TID}): claim")

    def test_bad_target_format(self):
        repo = ReviewRepo(self.tmp)
        self.assertEqual(crt.main(["--repo", str(repo.path), "--target", "nope", "--github-output", "/dev/null",
                                   "--summary-file", "/dev/null"]), 2)


if __name__ == "__main__":
    unittest.main()
