"""`.github/scripts/claim_drift_target.py` 테스트 (python3 -m unittest discover -s tests).

reconciler checkout은 로컬 bare origin을 둔 git 레포로, 대상 레포는 file:// 로 대신한다(네트워크 없음).
경쟁은 push 직전 훅에서 "다른 워커"가 같은 origin에 먼저 커밋을 밀어 넣는 것으로 재현한다.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import claim_drift_target as cdt  # noqa: E402
import select_drift_target as sdt  # noqa: E402
from test_select_drift_target import NOW, Fixture  # noqa: E402

NOW_DT = sdt.parse_time(NOW)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def task(mid, tid, status="assessing", recheck_after=None):
    t = {"id": tid, "toBeModelId": mid, "status": status, "createdAt": "2026-10-20T00:00:00Z",
         "trigger": {"source": "manual", "detectedAt": "2026-10-20T00:00:00Z", "reason": "r"}}
    if status == "assessing":
        t["assessment"] = {"reason": "유예", "recheckAfter": recheck_after}
    return t


class ClaimFixture(Fixture):
    """Fixture + reconciler checkout을 git 레포로 만들고 bare origin을 붙인다."""

    def publish(self):
        self.write()
        shutil.copytree(ROOT / "schemas", self.repo / "schemas", dirs_exist_ok=True)
        for name in ("to-be-models.json",):
            p = self.repo / "data" / name
            p.write_text(json.dumps(json.loads(p.read_text()), ensure_ascii=False, indent=2) + "\n")
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "bot@example.com")
        git(self.repo, "config", "user.name", "bot")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        self.origin = self.tmp / "origin.git"
        git(self.tmp, "clone", "-q", "--bare", str(self.repo), str(self.origin))
        git(self.repo, "remote", "add", "origin", str(self.origin))
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "branch", "-q", "-u", "origin/main")

    def other_worker(self, name="other"):
        """같은 origin을 보는 다른 워커의 클론."""
        path = self.tmp / name
        if not path.exists():
            git(self.tmp, "clone", "-q", str(self.origin), str(path))
            git(path, "config", "user.email", "w@example.com")
            git(path, "config", "user.name", "w")
        git(path, "pull", "-q", "--rebase")
        (path / "data" / "reconciliation-tasks").mkdir(parents=True, exist_ok=True)  # 빈 디렉터리는 git에 없다
        return path

    def computer(self):
        return sdt.VersionComputer(work_dir=self.tmp / "work", url_template=f"file://{self.sources}/{{repository}}")

    def run_claim(self, explicit=None, dry_run=False, before_push=None, reason="지목 사유"):
        return cdt.run(self.repo, NOW_DT, self.computer(), explicit=explicit, remote="origin", branch="main",
                       dry_run=dry_run, explicit_reason=reason, before_push=before_push)

    def origin_json(self, rel):
        return json.loads(git(self.repo, "show", f"origin/main:{rel}"))


def edit_json(path: Path, fn):
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


class ClaimDriftTargetTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = ClaimFixture(Path(self._tmp.name))
        self.repo_a = self.fx.source("alpha", {"src/a.py": "a=1\n", "docs/a.md": "# a\n"})
        self.repo_b = self.fx.source("beta", {"src/b.py": "b=1\n", "docs/b.md": "# b\n"})

    def tearDown(self):
        self._tmp.cleanup()

    def unchanged(self, mid, repository, **kw):
        as_is, to_be = self.fx.current(repository)
        return self.fx.model(mid, repository, as_is=as_is, to_be=to_be, **kw)

    def changed(self, mid, repository, observed_at="2026-10-20T00:00:00Z", **kw):
        as_is, _ = self.fx.current(repository)
        return self.fx.model(mid, repository, as_is=as_is, to_be="stale-tree", observed_at=observed_at, **kw)

    def model_on_origin(self, mid):
        return next(m for m in self.fx.origin_json("data/to-be-models.json") if m["id"] == mid)

    # ── 정상 점유 ──

    def test_version_change_claim_creates_task_and_moves_baseline_in_one_pushed_commit(self):
        self.changed("tbm_a", self.repo_a)
        self.unchanged("tbm_b", self.repo_b)
        self.fx.publish()
        out = self.fx.run_claim()
        self.assertEqual(out.claim.status, "claimed")
        self.assertEqual(out.claim.task_id, "rct_20261025-0001")
        self.assertEqual(git(self.fx.repo, "log", "-1", "--format=%s", "origin/main"),
                         "detect(tbm_a/rct_20261025-0001): claim")
        self.assertEqual(git(self.fx.repo, "show", "--name-only", "--format=", "origin/main").split(),
                         ["data/reconciliation-tasks/tbm_a.json", "data/to-be-models.json"])
        t = self.fx.origin_json("data/reconciliation-tasks/tbm_a.json")[0]
        tree = self.fx.tree(self.repo_a, "docs")
        self.assertEqual(t["status"], "assessing")
        self.assertEqual(t["trigger"], {"detectedAt": NOW, "source": "version_change",
                                        "toBe": {"previousVersion": "stale-tree", "currentVersion": tree}})
        m = self.model_on_origin("tbm_a")
        self.assertEqual((m["toBe"]["lastObservedVersion"], m["toBe"]["lastObservedAt"]), (tree, NOW))
        self.assertEqual(m["asIs"]["lastObservedAt"], "2026-10-20T00:00:00Z")  # 안 바뀐 side는 그대로

    def test_manual_trigger_copies_reason_and_clears_pair(self):
        self.unchanged("tbm_a", self.repo_a, check_policy={
            "manualTriggerRequestedAt": "2026-10-24T00:00:00Z", "manualTriggerReason": "문서 다시 봐줘"})
        self.fx.publish()
        out = self.fx.run_claim()
        t = self.fx.origin_json("data/reconciliation-tasks/tbm_a.json")[0]
        self.assertEqual(t["trigger"], {"detectedAt": NOW, "source": "manual", "reason": "문서 다시 봐줘"})
        self.assertEqual(self.model_on_origin("tbm_a")["checkPolicy"],
                         {"manualTriggerRequestedAt": None, "manualTriggerReason": None})
        self.assertTrue(out.claim.message.endswith(": claim manual"))

    def test_manual_trigger_with_version_change_records_side_and_baseline(self):
        self.changed("tbm_a", self.repo_a, check_policy={
            "manualTriggerRequestedAt": "2026-10-24T00:00:00Z", "manualTriggerReason": "확인"})
        self.fx.publish()
        self.fx.run_claim()
        t = self.fx.origin_json("data/reconciliation-tasks/tbm_a.json")[0]
        self.assertEqual(t["trigger"]["source"], "manual")
        self.assertEqual(t["trigger"]["toBe"]["previousVersion"], "stale-tree")
        self.assertEqual(self.model_on_origin("tbm_a")["toBe"]["lastObservedVersion"],
                         self.fx.tree(self.repo_a, "docs"))

    def test_recheck_expired_reenters_existing_task(self):
        self.unchanged("tbm_a", self.repo_a)
        self.fx.tasks["tbm_a"] = [task("tbm_a", "rct_20261024-0001", recheck_after="2026-10-25T09:00:00Z")]
        self.fx.publish()
        out = self.fx.run_claim()
        self.assertEqual(out.claim.task_id, "rct_20261024-0001")
        t = self.fx.origin_json("data/reconciliation-tasks/tbm_a.json")
        self.assertEqual(len(t), 1)
        self.assertIsNone(t[0]["assessment"]["recheckAfter"])
        self.assertEqual(t[0]["updatedAt"], NOW)
        self.assertTrue(out.claim.message.endswith(": claim recheck"))

    def test_explicit_model_without_change_opens_manual_task_with_given_reason(self):
        self.unchanged("tbm_a", self.repo_a)
        self.fx.publish()
        self.fx.run_claim(explicit="tbm_a", reason="사용자 지목")
        t = self.fx.origin_json("data/reconciliation-tasks/tbm_a.json")[0]
        self.assertEqual(t["trigger"], {"detectedAt": NOW, "source": "manual", "reason": "사용자 지목"})

    def test_dry_run_commits_without_push(self):
        self.changed("tbm_a", self.repo_a)
        self.fx.publish()
        before = git(self.fx.repo, "rev-parse", "origin/main")
        out = self.fx.run_claim(dry_run=True)
        self.assertEqual(out.claim.status, "claimed")
        git(self.fx.repo, "fetch", "-q", "origin")
        self.assertEqual(git(self.fx.repo, "rev-parse", "origin/main"), before)
        self.assertEqual(git(self.fx.repo, "rev-parse", "HEAD"), out.claim.commit)

    def test_nothing_to_claim(self):
        self.unchanged("tbm_a", self.repo_a)
        self.fx.publish()
        out = self.fx.run_claim()
        self.assertIsNone(out.claim)
        self.assertEqual(out.lost, [])

    # ── 경쟁 ──

    def test_unrelated_commit_ahead_is_retried_not_lost(self):
        self.changed("tbm_a", self.repo_a)
        self.unchanged("tbm_b", self.repo_b)
        self.fx.publish()

        def unrelated(attempt):
            if attempt == 1:
                w = self.fx.other_worker()
                (w / "data" / "reconciliation-tasks" / "tbm_b.json").write_text("[]\n")
                git(w, "add", "-A")
                git(w, "commit", "-q", "-m", "plan(tbm_b/x): unrelated")
                git(w, "push", "-q")

        out = self.fx.run_claim(before_push=unrelated)
        self.assertEqual(out.claim.status, "claimed")
        self.assertEqual(out.lost, [])
        log = git(self.fx.repo, "log", "--format=%s", "-2", "origin/main").splitlines()
        self.assertEqual(log, ["detect(tbm_a/rct_20261025-0001): claim", "plan(tbm_b/x): unrelated"])

    def test_lost_race_moves_to_next_candidate(self):
        self.changed("tbm_a", self.repo_a, observed_at="2026-10-01T00:00:00Z")  # 더 오래됨 → 먼저 선정
        self.changed("tbm_b", self.repo_b, observed_at="2026-10-10T00:00:00Z")
        self.fx.publish()

        def rival_claims_a(attempt):
            w = self.fx.other_worker()
            models_path = w / "data" / "to-be-models.json"
            if json.loads(models_path.read_text())[0]["toBe"]["lastObservedVersion"] != "stale-tree":
                return
            edit_json(models_path, lambda ms: ms[0]["toBe"].update(lastObservedVersion="rival"))
            (w / "data" / "reconciliation-tasks" / "tbm_a.json").write_text(
                json.dumps([task("tbm_a", "rct_20261025-0001")], ensure_ascii=False, indent=2) + "\n")
            git(w, "add", "-A")
            git(w, "commit", "-q", "-m", "detect(tbm_a/rct_20261025-0001): claim")
            git(w, "push", "-q")

        out = self.fx.run_claim(before_push=rival_claims_a)
        self.assertEqual([m for m, _ in out.lost], ["tbm_a"])
        self.assertIn("이미 assessing", out.lost[0][1])
        self.assertEqual(out.selection.model_id, "tbm_b")
        self.assertEqual(out.claim.status, "claimed")
        tasks_a = self.fx.origin_json("data/reconciliation-tasks/tbm_a.json")
        self.assertEqual(len(tasks_a), 1)  # 경쟁자의 task만 — 중복 task 없음

    def test_explicit_target_lost_does_not_fall_through(self):
        self.changed("tbm_a", self.repo_a)
        self.changed("tbm_b", self.repo_b)
        self.fx.publish()

        def rival(attempt):
            w = self.fx.other_worker()
            if (w / "data" / "reconciliation-tasks" / "tbm_a.json").exists():
                return
            (w / "data" / "reconciliation-tasks" / "tbm_a.json").write_text(
                json.dumps([task("tbm_a", "rct_20261025-0001")], ensure_ascii=False, indent=2) + "\n")
            git(w, "add", "-A")
            git(w, "commit", "-q", "-m", "detect(tbm_a/rct_20261025-0001): claim")
            git(w, "push", "-q")

        out = self.fx.run_claim(explicit="tbm_a", before_push=rival)
        self.assertIsNone(out.claim)
        self.assertEqual([m for m, _ in out.lost], ["tbm_a"])

    def test_recheck_reentry_lost_when_rival_cleared_it(self):
        self.unchanged("tbm_a", self.repo_a)
        self.fx.tasks["tbm_a"] = [task("tbm_a", "rct_20261024-0001", recheck_after="2026-10-25T09:00:00Z")]
        self.fx.publish()

        def rival(attempt):
            w = self.fx.other_worker()
            p = w / "data" / "reconciliation-tasks" / "tbm_a.json"
            if json.loads(p.read_text())[0]["assessment"]["recheckAfter"] is None:
                return
            edit_json(p, lambda ts: ts[0]["assessment"].update(recheckAfter=None))
            git(w, "add", "-A")
            git(w, "commit", "-q", "-m", "detect(tbm_a/rct_20261024-0001): claim recheck")
            git(w, "push", "-q")

        out = self.fx.run_claim(before_push=rival)
        self.assertIsNone(out.claim)
        self.assertIn("recheckAfter", out.lost[0][1])

    def test_schema_violation_is_error_not_commit(self):
        self.changed("tbm_a", self.repo_a)
        self.fx.publish()
        bad = self.fx.repo / "schemas" / "reconciliation-task.schema.json"
        edit_json(bad, lambda s: s["properties"]["trigger"]["properties"].pop("source"))
        git(self.fx.repo, "commit", "-qam", "schema tighten")
        git(self.fx.repo, "push", "-q", "origin", "main")
        head = git(self.fx.repo, "rev-parse", "origin/main")
        with self.assertRaises(cdt.ClaimError):
            self.fx.run_claim()
        self.assertEqual(git(self.fx.repo, "rev-parse", "origin/main"), head)


if __name__ == "__main__":
    unittest.main()
