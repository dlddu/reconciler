"""`.github/scripts/claim_plan_target.py` 테스트 (python3 -m unittest discover -s tests).

reconciler checkout은 로컬 bare origin을 둔 git 레포다(네트워크 없음). 경쟁은 push 직전 훅에서
"다른 워커"가 같은 origin에 먼저 커밋을 밀어 넣는 것으로 재현한다.
"""

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import claim_plan_target as cpt  # noqa: E402
import select_plan_target as spt  # noqa: E402

NOW = "2026-10-27T00:00:00Z"
NOW_DT = spt.parse_time(NOW)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def task(mid, tid, status, updated="2026-10-20T00:00:00Z", attempts=None):
    t = {"id": tid, "toBeModelId": mid, "status": status, "createdAt": "2026-10-01T00:00:00Z",
         "updatedAt": updated, "trigger": {"source": "manual", "detectedAt": "2026-10-01T00:00:00Z", "reason": "r"}}
    if attempts:
        t["attempts"] = attempts
    return t


class Fixture:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.repo = tmp / "reconciler"
        (self.repo / "data" / "reconciliation-tasks").mkdir(parents=True)
        self.models, self.tasks = [], {}

    def model(self, mid, enabled=None):
        m = {"id": mid, "metadata": {"name": mid}, "definition": "# def"}
        if enabled is not None:
            m["checkPolicy"] = {"enabled": enabled}
        self.models.append(m)

    def add(self, t):
        self.tasks.setdefault(t["toBeModelId"], []).append(t)

    def publish(self):
        dump = lambda p, d: p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")  # noqa: E731
        dump(self.repo / "data" / "to-be-models.json", self.models)
        for mid, tasks in self.tasks.items():
            dump(self.repo / "data" / "reconciliation-tasks" / f"{mid}.json", tasks)
        shutil.copytree(ROOT / "schemas", self.repo / "schemas")
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "bot@example.com")
        git(self.repo, "config", "user.name", "bot")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        self.origin = self.tmp / "origin.git"
        git(self.tmp, "clone", "-q", "--bare", str(self.repo), str(self.origin))
        git(self.repo, "remote", "add", "origin", str(self.origin))
        git(self.repo, "fetch", "-q", "origin")

    def other_worker(self):
        path = self.tmp / "other"
        if not path.exists():
            git(self.tmp, "clone", "-q", str(self.origin), str(path))
            git(path, "config", "user.email", "w@example.com")
            git(path, "config", "user.name", "w")
        git(path, "pull", "-q", "--rebase")
        return path

    def run(self, explicit=None, before_push=None):
        return cpt.run(self.repo, NOW_DT, explicit=explicit, remote="origin", branch="main",
                       before_push=before_push)

    def origin_task(self, mid, tid):
        tasks = json.loads(git(self.repo, "show", f"origin/main:data/reconciliation-tasks/{mid}.json"))
        return next(t for t in tasks if t["id"] == tid)


def edit(path: Path, fn):
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


class ClaimPlanTargetTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = Fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_claims_oldest_ready_to_planning_in_one_pushed_commit(self):
        self.fx.model("tbm_a")
        self.fx.model("tbm_b")
        self.fx.add(task("tbm_a", "rct_20261020-0001", "action_required", updated="2026-10-21T00:00:00Z"))
        self.fx.add(task("tbm_b", "rct_20261020-0001", "action_required", updated="2026-10-20T00:00:00Z"))
        self.fx.publish()
        out = self.fx.run()
        self.assertEqual(out.claim.status, "claimed")
        self.assertEqual((out.selection.model_id, out.selection.target_id), ("tbm_b", "rct_20261020-0001"))
        self.assertEqual(git(self.fx.repo, "log", "-1", "--format=%s", "origin/main"),
                         "plan(tbm_b/rct_20261020-0001): claim")
        self.assertEqual(git(self.fx.repo, "show", "--name-only", "--format=", "origin/main").split(),
                         ["data/reconciliation-tasks/tbm_b.json"])
        t = self.fx.origin_task("tbm_b", "rct_20261020-0001")
        self.assertEqual((t["status"], t["updatedAt"]), ("planning", NOW))
        self.assertNotIn("attempts", t)  # 시도 항목은 스킬 몫
        self.assertEqual(self.fx.origin_task("tbm_a", "rct_20261020-0001")["status"], "action_required")

    def test_rework_claim_keeps_attempts_and_reports_from_status(self):
        self.fx.model("tbm_a")
        prev = [{"plan": {"summary": "s", "steps": [{"seq": 1, "action": "a"}]}, "review": {"status": "rejected", "comment": "범위가 넓음"}}]
        self.fx.add(task("tbm_a", "rct_20261020-0001", "review_rejected", attempts=prev))
        self.fx.publish()
        out = self.fx.run()
        self.assertEqual(out.selection.from_status, "review_rejected")
        self.assertEqual(out.selection.attempt_count, 1)
        self.assertEqual(self.fx.origin_task("tbm_a", "rct_20261020-0001")["attempts"], prev)

    def test_claim_commit_is_pushed_head(self):
        self.fx.model("tbm_a")
        self.fx.add(task("tbm_a", "rct_20261020-0001", "action_required"))
        self.fx.publish()
        out = self.fx.run()
        self.assertEqual(out.claim.status, "claimed")
        self.assertEqual(git(self.fx.repo, "rev-parse", "HEAD"), out.claim.commit)
        self.assertEqual(git(self.fx.repo, "rev-parse", "origin/main"), out.claim.commit)

    def test_nothing_ready(self):
        self.fx.model("tbm_a")
        self.fx.model("tbm_off", enabled=False)
        self.fx.add(task("tbm_a", "rct_20261020-0001", "planned"))
        self.fx.add(task("tbm_off", "rct_20261020-0001", "action_required"))
        self.fx.publish()
        out = self.fx.run()
        self.assertIsNone(out.claim)
        self.assertFalse(out.selection.found)

    def test_lost_race_moves_to_next_candidate(self):
        self.fx.model("tbm_a")
        self.fx.model("tbm_b")
        self.fx.add(task("tbm_a", "rct_20261020-0001", "action_required", updated="2026-10-19T00:00:00Z"))
        self.fx.add(task("tbm_b", "rct_20261020-0001", "action_required"))
        self.fx.publish()

        fired = []

        def other_claims_a(attempt):
            if not fired:  # 첫 후보(tbm_a)의 push 직전에만 — 다음 후보 점유 때는 끼어들지 않는다
                fired.append(attempt)
                w = self.fx.other_worker()
                edit(w / "data/reconciliation-tasks/tbm_a.json",
                     lambda ts: ts[0].update(status="planning"))
                git(w, "commit", "-qam", "plan(tbm_a/rct_20261020-0001): claim")
                git(w, "push", "-q")

        out = self.fx.run(before_push=other_claims_a)
        self.assertEqual(out.claim.status, "claimed")
        self.assertEqual(out.selection.model_id, "tbm_b")
        self.assertEqual(len(out.lost), 1)
        self.assertIn("tbm_a/rct_20261020-0001", out.lost[0][0])
        self.assertEqual(self.fx.origin_task("tbm_b", "rct_20261020-0001")["status"], "planning")

    def test_unrelated_push_is_retried_not_lost(self):
        self.fx.model("tbm_a")
        self.fx.model("tbm_b")
        self.fx.add(task("tbm_a", "rct_20261020-0001", "action_required"))
        self.fx.add(task("tbm_b", "rct_20261020-0001", "succeeded"))
        self.fx.publish()

        def unrelated(attempt):
            if attempt == 1:
                w = self.fx.other_worker()
                edit(w / "data/reconciliation-tasks/tbm_b.json", lambda ts: ts[0].update(updatedAt=NOW))
                git(w, "commit", "-qam", "unrelated")
                git(w, "push", "-q")

        out = self.fx.run(before_push=unrelated)
        self.assertEqual(out.claim.status, "claimed")
        self.assertEqual(out.lost, [])
        self.assertEqual(git(self.fx.repo, "log", "-2", "--format=%s", "origin/main").splitlines(),
                         ["plan(tbm_a/rct_20261020-0001): claim", "unrelated"])

    def test_explicit_lost_does_not_fall_through(self):
        self.fx.model("tbm_a")
        self.fx.add(task("tbm_a", "rct_20261020-0001", "action_required"))
        self.fx.add(task("tbm_a", "rct_20261020-0002", "action_required", updated="2026-10-25T00:00:00Z"))
        self.fx.publish()

        def other(attempt):
            w = self.fx.other_worker()
            edit(w / "data/reconciliation-tasks/tbm_a.json", lambda ts: ts[0].update(status="planning"))
            git(w, "commit", "-qam", "other claim")
            git(w, "push", "-q")

        out = self.fx.run(explicit="tbm_a/rct_20261020-0001", before_push=other)
        self.assertIsNone(out.claim)
        self.assertEqual(len(out.lost), 1)

    def test_main_writes_outputs(self):
        self.fx.model("tbm_a")
        self.fx.add(task("tbm_a", "rct_20261020-0001", "failed"))
        self.fx.publish()
        gh = self.fx.tmp / "gh_output"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cpt.main(["--repo", str(self.fx.repo), "--now", NOW,
                             "--github-output", str(gh), "--summary-file", str(self.fx.tmp / "s.md")])
        self.assertEqual(code, 0)
        outs = dict(line.split("=", 1) for line in gh.read_text().splitlines())
        self.assertEqual(outs["claimed"], "true")
        self.assertEqual(outs["from_status"], "failed")
        self.assertEqual(outs["claim_message"], "plan(tbm_a/rct_20261020-0001): claim")
        self.assertEqual(outs["claim_commit"], git(self.fx.repo, "rev-parse", "HEAD"))

    def test_bad_target_is_usage_error(self):
        self.fx.model("tbm_a")
        self.fx.publish()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cpt.main(["--repo", str(self.fx.repo), "--target", "nope",
                                       "--github-output", str(self.fx.tmp / "o")]), 2)


if __name__ == "__main__":
    unittest.main()
