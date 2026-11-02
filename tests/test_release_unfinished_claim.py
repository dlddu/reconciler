"""`.github/scripts/release_unfinished_claim.py` 테스트 (python3 -m unittest discover -s tests).

러너 checkout과 「다른 워커」를 같은 bare origin의 두 클론으로 두고, 판정 없이 끝난 점유가 재확인 유예로
풀리는지, 판정이 이미 있거나 유예 중이면 손대지 않는지, push 경쟁에서 조건을 다시 보는지 확인한다.
"""

import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import release_unfinished_claim as ruc  # noqa: E402

MID, TID = "tbm_demo", "rct_20261102-0001"
NOW = dt.datetime(2026, 11, 2, 7, 0, tzinfo=dt.timezone.utc)
GRACE = dt.timedelta(minutes=30)
REL = f"data/reconciliation-tasks/{MID}.json"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def claimed(**extra):
    t = {"id": TID, "toBeModelId": MID, "status": "assessing", "createdAt": "2026-11-02T06:00:00Z",
         "trigger": {"source": "version_change", "detectedAt": "2026-11-02T06:00:00Z",
                     "asIs": {"previousVersion": "v1", "currentVersion": "v2"}}}
    t.update(extra)
    return t


def judged():
    return claimed(status="no_action_needed", updatedAt="2026-11-02T06:10:00Z",
                   stateSummary={"asIs": "a", "toBe": "b", "gap": "없음", "summarizedAt": "2026-11-02T06:05:00Z"},
                   assessment={"reason": "근거", "assessedAt": "2026-11-02T06:10:00Z"})


class Fixture:
    def __init__(self, tmp: Path, tasks):
        seed = tmp / "seed"
        (seed / "data" / "reconciliation-tasks").mkdir(parents=True)
        shutil.copytree(ROOT / "schemas", seed / "schemas")
        (seed / REL).write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n")
        git(seed, "init", "-q", "-b", "main")
        git(seed, "-c", "user.name=s", "-c", "user.email=s@x", "add", "-A")
        git(seed, "-c", "user.name=s", "-c", "user.email=s@x", "commit", "-q", "-m", "claim")
        self.origin = tmp / "origin.git"
        git(tmp, "clone", "-q", "--bare", str(seed), str(self.origin))
        self.runner = self._clone(tmp / "runner")
        self.other = self._clone(tmp / "other")

    def _clone(self, path):
        git(path.parent, "clone", "-q", str(self.origin), str(path))
        git(path, "config", "user.email", "bot@x")
        git(path, "config", "user.name", "bot")
        return path

    def other_commits(self, tasks, msg):
        git(self.other, "pull", "-q", "--rebase")
        (self.other / REL).write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n")
        git(self.other, "commit", "-q", "-am", msg)
        git(self.other, "push", "-q", "origin", "HEAD:main")

    def origin_tasks(self):
        git(self.runner, "fetch", "-q", "origin")
        return {t["id"]: t for t in json.loads(git(self.runner, "show", f"origin/main:{REL}"))}

    def release(self, before_push=None):
        return ruc.release(self.runner, MID, TID, NOW, remote="origin", branch="main", grace=GRACE,
                           note="러너 정리", before_push=before_push)


class ReleaseUnfinishedClaimTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_unfinished_claim_is_parked_with_recheck_after(self):
        fx = Fixture(self.tmp, [claimed()])
        status, _ = fx.release()
        self.assertEqual(status, "parked")
        t = fx.origin_tasks()[TID]
        self.assertEqual(t["status"], "assessing")
        self.assertEqual(t["assessment"]["recheckAfter"], "2026-11-02T07:30:00Z")
        self.assertIn("러너 정리", t["assessment"]["reason"])
        self.assertEqual(t["trigger"], claimed()["trigger"])  # 점유 기록은 그대로
        self.assertEqual(git(fx.runner, "log", "-1", "--format=%s", "origin/main"),
                         f"detect({MID}/{TID}): park unfinished")

    def test_partial_summary_is_kept_and_previous_reason_quoted(self):
        partial = claimed(stateSummary={"asIs": "a", "toBe": "b", "gap": "g", "summarizedAt": "2026-11-02T06:05:00Z"},
                          assessment={"reason": "쓰다 만 근거"})
        fx = Fixture(self.tmp, [partial])
        self.assertEqual(fx.release()[0], "parked")
        t = fx.origin_tasks()[TID]
        self.assertEqual(t["stateSummary"], partial["stateSummary"])
        self.assertIn("(이전 기록) 쓰다 만 근거", t["assessment"]["reason"])

    def test_judged_task_is_left_alone(self):
        fx = Fixture(self.tmp, [judged()])
        head = git(fx.runner, "rev-parse", "origin/main")
        self.assertEqual(fx.release()[0], "noop")
        git(fx.runner, "fetch", "-q", "origin")
        self.assertEqual(git(fx.runner, "rev-parse", "origin/main"), head)

    def test_already_parked_task_is_left_alone(self):
        parked = claimed(assessment={"reason": "유예", "recheckAfter": "2026-11-02T09:00:00Z"})
        fx = Fixture(self.tmp, [parked])
        status, detail = fx.release()
        self.assertEqual(status, "noop")
        self.assertIn("이미 재확인 유예", detail)

    def test_missing_task_is_noop(self):
        fx = Fixture(self.tmp, [])
        self.assertEqual(fx.release()[0], "noop")

    def test_local_unpushed_commits_are_discarded_before_deciding(self):
        # 스킬이 로컬에서 판정을 커밋했지만 push하지 못한 채 끝난 경우: 원격 기준으로 풀어야 한다.
        fx = Fixture(self.tmp, [claimed()])
        (fx.runner / REL).write_text(json.dumps([judged()], ensure_ascii=False, indent=2) + "\n")
        git(fx.runner, "commit", "-q", "-am", f"detect({MID}/{TID}): 판정")
        self.assertEqual(fx.release()[0], "parked")
        self.assertIn("recheckAfter", fx.origin_tasks()[TID]["assessment"])

    def test_push_race_with_unrelated_commit_retries(self):
        fx = Fixture(self.tmp, [claimed(), judged() | {"id": "rct_20261101-0001"}])

        def unrelated(attempt):
            if attempt == 1:
                other = judged() | {"id": "rct_20261101-0001", "updatedAt": "2026-11-02T06:59:00Z"}
                fx.other_commits([claimed(), other], "plan(tbm_demo/rct_20261101-0001): x")

        self.assertEqual(fx.release(before_push=unrelated)[0], "parked")
        tasks = fx.origin_tasks()
        self.assertIn("recheckAfter", tasks[TID]["assessment"])
        self.assertEqual(tasks["rct_20261101-0001"]["updatedAt"], "2026-11-02T06:59:00Z")

    def test_push_race_where_verdict_lands_first_is_noop(self):
        fx = Fixture(self.tmp, [claimed()])

        def verdict_lands(attempt):
            if attempt == 1:
                fx.other_commits([judged()], f"detect({MID}/{TID}): 판정")

        self.assertEqual(fx.release(before_push=verdict_lands)[0], "noop")
        self.assertEqual(fx.origin_tasks()[TID]["status"], "no_action_needed")

    def test_main_writes_summary(self):
        fx = Fixture(self.tmp, [claimed()])
        summary = self.tmp / "release.md"
        rc = ruc.main(["--repo", str(fx.runner), "--model-id", MID, "--task-id", TID, "--now", "2026-11-02T07:00:00Z",
                       "--run-exit", "124", "--run-url", "https://example/run/1", "--summary-file", str(summary)])
        self.assertEqual(rc, 0)
        self.assertIn("재확인 유예로 돌림", summary.read_text())
        self.assertIn("mcode exit 124", fx.origin_tasks()[TID]["assessment"]["reason"])


if __name__ == "__main__":
    unittest.main()
