"""`.github/scripts/claim_execute_target.py` 테스트 (python3 -m unittest discover -s tests).

경쟁은 push 직전 훅에서 "다른 워커"가 같은 origin에 먼저 커밋을 밀어 넣는 것으로 재현한다(리뷰 점유 테스트와 같은 방식).
GitHub 조회는 경로 → 응답 표로 흉내 낸다 — 네트워크 없음.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import claim_execute_target as cet  # noqa: E402
import select_execute_target as setg  # noqa: E402
from review_fixture import MID, PR, TID, ReviewRepo, git, model, planned_task  # noqa: E402

SHA = "a" * 40
SHA2 = "b" * 40
CTX = "review/manual-approval"


def approved_task(tid=TID, mid=MID, reviewed="2026-10-25T02:00:00Z", manual=False, status="approved"):
    review = {"status": "approved", "reviewedAt": reviewed, "reason": "승인"}
    if manual:
        review["manualApproval"] = {"sha": SHA, "context": CTX}
    return planned_task(tid, mid, status=status, review=review)


class StubGitHub:
    """select_execute_target.GitHub.get 흉내 — 경로별 응답, 없는 경로는 ApprovalCheckError(fail-closed 확인용)."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = 0

    def get(self, path):
        self.calls += 1
        if path not in self.routes:
            raise setg.ApprovalCheckError(f"GET {path} → HTTP 404")
        return self.routes[path]

    def approve(self, head=SHA, state="success"):
        self.routes["/repos/dlddu/demo/pulls/7"] = {"state": "open", "merged": False, "head": {"sha": head}}
        self.routes[f"/repos/dlddu/demo/commits/{SHA}/statuses?per_page=100"] = [
            {"context": CTX, "state": state, "created_at": "2026-10-25T03:00:00Z"}]
        return self


def flip(worker: Path, mid: str, tid: str, status: str, msg: str):
    path = worker / "data" / "reconciliation-tasks" / f"{mid}.json"
    tasks = json.loads(path.read_text())
    next(t for t in tasks if t["id"] == tid)["status"] = status
    path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n")
    git(worker, "commit", "-qam", msg)
    git(worker, "push", "-q")


class ClaimExecuteTargetTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_claim(self, repo, gh=None, explicit=None, before_push=None):
        return cet.run(repo.path, gh or StubGitHub(), explicit=explicit, remote="origin", branch="main",
                       before_push=before_push)

    def test_claims_oldest_approval_and_pushes_status_only(self):
        newer = "rct_20261025-0002"
        repo = ReviewRepo(self.tmp, {MID: [approved_task(newer, reviewed="2026-10-25T05:00:00Z"), approved_task()]})
        before = repo.tasks()
        out = self.run_claim(repo)
        self.assertEqual(out.claim.status, "claimed")
        self.assertEqual(out.selection.task_id, TID)
        self.assertEqual(out.claim.message, f"execute({MID}/{TID}): claim")
        self.assertEqual(git(repo.path, "rev-parse", "origin/main"), out.claim.commit)
        after = repo.tasks(rev="origin/main")
        self.assertEqual([a["id"] for a, b in zip(after, before) if a != b], [TID])
        self.assertEqual({k for k in after[1] if after[1][k] != before[1][k]}, {"status"})
        self.assertEqual(after[1]["status"], "executing")
        self.assertEqual(after[0]["status"], "approved")  # 한 건만

    def test_only_approved_is_an_entrance(self):
        repo = ReviewRepo(self.tmp, {MID: [planned_task(), approved_task("rct_20261025-0002", status="reviewing")]})
        out = self.run_claim(repo)
        self.assertIsNone(out.claim)
        self.assertFalse(out.selection.found)
        self.assertEqual(git(repo.path, "rev-list", "--count", "origin/main"), "1")  # 쓰지 않음

    def test_manual_approval_waiting_is_not_claimed(self):
        repo = ReviewRepo(self.tmp, {MID: [approved_task(manual=True)]})
        out = self.run_claim(repo, StubGitHub().approve(state="pending"))
        self.assertIsNone(out.claim)
        self.assertEqual(out.selection.judged[0][1], setg.WAITING)

    def test_manual_approval_done_is_claimed(self):
        repo = ReviewRepo(self.tmp, {MID: [approved_task(manual=True)]})
        out = self.run_claim(repo, StubGitHub().approve())
        self.assertEqual(out.claim.status, "claimed")
        self.assertIn("사람 승인 완료", out.claim.detail)

    def test_api_failure_is_fail_closed(self):
        repo = ReviewRepo(self.tmp, {MID: [approved_task(manual=True)]})
        out = self.run_claim(repo, StubGitHub())
        self.assertIsNone(out.claim)
        self.assertEqual(len(out.selection.errors), 1)
        code = cet.main(["--repo", str(repo.path), "--api-url", "http://127.0.0.1:9",
                         "--github-output", "/dev/null", "--summary-file", "/dev/null"])
        self.assertEqual(code, 1)  # 대상 없음으로 단정할 수 없음

    def test_gate_rechecked_right_before_claim(self):
        # 선정 때는 통과, 점유 직전에 PR head가 바뀜 → 점유하지 않고 다음 후보로
        second = "rct_20261025-0002"
        repo = ReviewRepo(self.tmp, {MID: [approved_task(manual=True), approved_task(second, reviewed="2026-10-25T09:00:00Z")]})
        gh = StubGitHub().approve()
        real_judge = setg.judge
        seen = {"n": 0}

        def judge(task, g):
            if task["id"] == TID:
                seen["n"] += 1
                if seen["n"] == 2:  # 첫 호출은 선정, 두 번째가 점유 직전 재확인
                    gh.approve(head=SHA2)
            return real_judge(task, g)

        cet.setg.judge = judge
        try:
            out = self.run_claim(repo, gh)
        finally:
            cet.setg.judge = real_judge
        self.assertEqual(out.lost[0][0], f"{MID}/{TID}")
        self.assertIn("게이트 재확인 실패", out.lost[0][1])
        self.assertEqual(out.selection.task_id, second)
        statuses = {t["id"]: t["status"] for t in repo.tasks(rev="origin/main")}
        self.assertEqual(statuses, {TID: "approved", second: "executing"})

    def test_lost_race_moves_to_next_candidate(self):
        second = "rct_20261025-0002"
        repo = ReviewRepo(self.tmp, {MID: [approved_task(), approved_task(second, reviewed="2026-10-25T09:00:00Z")]})
        worker = repo.other_worker()

        def race(attempt):
            if attempt == 1 and not getattr(race, "done", False):
                race.done = True
                flip(worker, MID, TID, "executing", f"execute({MID}/{TID}): claim")

        out = self.run_claim(repo, before_push=race)
        self.assertIn("다른 워커", out.lost[0][1])
        self.assertEqual(out.selection.task_id, second)
        statuses = {t["id"]: t["status"] for t in repo.tasks(rev="origin/main")}
        self.assertEqual(statuses, {TID: "executing", second: "executing"})

    def test_explicit_target_lost_race_stops(self):
        repo = ReviewRepo(self.tmp, {MID: [approved_task(), approved_task("rct_20261025-0002")]})
        worker = repo.other_worker()
        out = self.run_claim(repo, explicit=f"{MID}/{TID}",
                             before_push=lambda a: a == 1 and flip(worker, MID, TID, "executing", "w claim"))
        self.assertIsNone(out.claim)
        self.assertEqual(len(out.lost), 1)
        self.assertEqual(repo.tasks(rev="origin/main")[1]["status"], "approved")

    def test_unrelated_commit_is_retried(self):
        repo = ReviewRepo(self.tmp, {MID: [approved_task()], "tbm_other": [planned_task(mid="tbm_other")]})
        worker = repo.other_worker()
        out = self.run_claim(repo, before_push=lambda a: a == 1 and flip(
            worker, "tbm_other", TID, "reviewing", f"review(tbm_other/{TID}): claim"))
        self.assertEqual(out.claim.status, "claimed")
        self.assertEqual(repo.tasks(rev="origin/main")[0]["status"], "executing")
        self.assertEqual(git(repo.path, "log", "-1", "--format=%s", "origin/main"), f"execute({MID}/{TID}): claim")

    def test_disabled_model_is_parked(self):
        repo = ReviewRepo(self.tmp, {MID: [approved_task()]}, models=[model(enabled=False)])
        self.assertIsNone(self.run_claim(repo).claim)

    def test_main_outputs(self):
        repo = ReviewRepo(self.tmp, {MID: [approved_task()]})
        out_file = self.tmp / "out.txt"
        code = cet.main(["--repo", str(repo.path), "--github-output", str(out_file), "--summary-file", str(self.tmp / "s.md")])
        self.assertEqual(code, 0)
        outputs = dict(line.split("=", 1) for line in out_file.read_text().splitlines())
        self.assertEqual(outputs["claimed"], "true")
        self.assertEqual((outputs["model_id"], outputs["task_id"]), (MID, TID))
        self.assertEqual(outputs["pull_request_url"], PR)
        self.assertEqual(outputs["claim_message"], f"execute({MID}/{TID}): claim")
        self.assertIn("점유", (self.tmp / "s.md").read_text())

    def test_bad_target_format(self):
        repo = ReviewRepo(self.tmp, {MID: [approved_task()]})
        self.assertEqual(cet.main(["--repo", str(repo.path), "--target", "nope", "--github-output", "/dev/null",
                                   "--summary-file", "/dev/null"]), 2)

    def test_release_reverts_unexecuted_claim(self):
        repo = ReviewRepo(self.tmp, {MID: [approved_task()]})
        self.run_claim(repo)
        self.assertEqual(cet.release(repo.path, f"{MID}/{TID}", remote="origin", branch="main"), "released")
        self.assertEqual(repo.tasks(rev="origin/main")[0]["status"], "approved")
        self.assertEqual(git(repo.path, "log", "-1", "--format=%s", "origin/main"), f"execute({MID}/{TID}): release")

    def test_release_keeps_started_or_moved_task(self):
        repo = ReviewRepo(self.tmp, {MID: [approved_task()]})
        self.run_claim(repo)
        worker = repo.other_worker()
        path = worker / "data" / "reconciliation-tasks" / f"{MID}.json"
        tasks = json.loads(path.read_text())
        tasks[0]["attempts"][-1]["execution"] = {"status": "running", "startedAt": "2026-10-25T04:00:00Z", "entries": []}
        path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n")
        git(worker, "commit", "-qam", f"execute({MID}/{TID}): run")
        git(worker, "push", "-q")
        self.assertIn("execution", cet.release(repo.path, f"{MID}/{TID}", remote="origin", branch="main"))
        flip(worker, MID, TID, "failed", f"execute({MID}/{TID}): verify")
        self.assertTrue(cet.release(repo.path, f"{MID}/{TID}", remote="origin", branch="main").startswith("skipped"))
        self.assertEqual(repo.tasks(rev="origin/main")[0]["status"], "failed")

    def test_release_main(self):
        repo = ReviewRepo(self.tmp, {MID: [approved_task()]})
        self.run_claim(repo)
        self.assertEqual(cet.main(["--repo", str(repo.path), "--release", f"{MID}/{TID}", "--summary-file", "/dev/null"]), 0)
        self.assertEqual(repo.tasks(rev="origin/main")[0]["status"], "approved")
        self.assertEqual(cet.main(["--repo", str(repo.path), "--release", "bad", "--summary-file", "/dev/null"]), 2)


if __name__ == "__main__":
    unittest.main()
