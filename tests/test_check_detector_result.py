"""`.github/scripts/check_detector_result.py` 테스트 (python3 -m unittest discover -s tests).

실제 schemas/를 복사한 임시 git 레포에 "스킬 실행 전" 커밋을 만들고, 스킬이 했을 법한 변경을 커밋한 뒤
점검기가 계약 위반을 잡는지 본다. jsonschema가 필요하다.
"""

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

import check_detector_result as cdr  # noqa: E402

MID = "tbm_demo"
SCRIPT = {"runtime": "bash", "code": "git rev-parse HEAD\n"}


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def model(mid=MID, as_is="v1", to_be="t1", check_policy=None):
    def side(version):
        return {"dataSource": {"type": "github", "repository": "dlddu/demo", "ref": "main"},
                "versionScript": SCRIPT, "lastObservedVersion": version, "lastObservedAt": "2026-10-20T00:00:00Z"}
    m = {"id": mid, "metadata": {"name": mid, "createdAt": "2026-10-01T00:00:00Z"},
         "definition": "# def", "asIs": side(as_is), "toBe": side(to_be)}
    if check_policy is not None:
        m["checkPolicy"] = check_policy
    return m


def finished_task(tid="rct_20261025-0001", status="action_required", trigger=None, **extra):
    t = {"id": tid, "toBeModelId": MID, "status": status, "createdAt": "2026-10-25T00:00:00Z",
         "trigger": trigger or {"detectedAt": "2026-10-25T00:00:00Z",
                                "asIs": {"previousVersion": "v1", "currentVersion": "v2"}},
         "stateSummary": {"asIs": "실제 상태", "toBe": "목표 상태", "gap": "차이",
                          "summarizedAt": "2026-10-25T00:01:00Z"},
         "assessment": {"reason": "근거", "assessedAt": "2026-10-25T00:02:00Z"}}
    t.update(extra)
    return t


class Repo:
    def __init__(self, tmp: Path, models, tasks=None):
        self.path = tmp / "reconciler"
        (self.path / "data" / "reconciliation-tasks").mkdir(parents=True)
        shutil.copytree(ROOT / "schemas", self.path / "schemas")
        git(self.path, "init", "-q", "-b", "main")
        git(self.path, "config", "user.email", "t@example.com")
        git(self.path, "config", "user.name", "t")
        self.write(models, tasks or {})
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", "base")
        self.base = git(self.path, "rev-parse", "HEAD")

    def write(self, models, tasks):
        (self.path / "data" / "to-be-models.json").write_text(json.dumps(models, ensure_ascii=False, indent=2))
        for mid, items in tasks.items():
            (self.path / "data" / "reconciliation-tasks" / f"{mid}.json").write_text(
                json.dumps(items, ensure_ascii=False, indent=2))

    def commit(self, models, tasks, msg):
        self.write(models, tasks)
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", msg)

    def check(self, target_id=MID, kind="model", reason="version_changed"):
        return cdr.check(self.path, self.base, MID, target_id, kind, reason)


class CheckDetectorResultTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_version_change_claim_and_assess_passes(self):
        repo = Repo(self.tmp, [model(), model("tbm_other")])
        claimed = finished_task(status="assessing")
        claimed.pop("stateSummary"); claimed.pop("assessment")
        repo.commit([model(as_is="v2"), model("tbm_other")], {MID: [claimed]},
                    f"detect({MID}/rct_20261025-0001): claim")
        repo.commit([model(as_is="v2"), model("tbm_other")], {MID: [finished_task()]},
                    f"detect({MID}/rct_20261025-0001): assess action")
        res = repo.check()
        self.assertEqual(res.errors, [])
        self.assertEqual(res.facts["status"], "action_required")
        self.assertEqual(len(res.facts["commits"]), 2)

    def test_lastObservedVersion_not_updated_is_error(self):
        repo = Repo(self.tmp, [model()])
        repo.commit([model()], {MID: [finished_task()]}, f"detect({MID}/rct_20261025-0001): assess")
        res = repo.check()
        self.assertTrue(any("lastObservedVersion" in e for e in res.errors), res.errors)

    def test_touching_other_model_and_schema_file_is_error(self):
        repo = Repo(self.tmp, [model(), model("tbm_other")])
        (repo.path / "schemas" / "reconciliation-task.schema.json").write_text(
            (ROOT / "schemas" / "reconciliation-task.schema.json").read_text() + "\n")
        repo.commit([model(as_is="v2"), model("tbm_other", as_is="zzz")], {MID: [finished_task()]},
                    f"detect({MID}/rct_20261025-0001): assess")
        res = repo.check()
        joined = "\n".join(res.errors)
        self.assertIn("허용 범위 밖", joined)
        self.assertIn("tbm_other", joined)

    def test_parked_without_recheck_after_is_error(self):
        repo = Repo(self.tmp, [model()])
        t = finished_task(status="assessing")
        repo.commit([model(as_is="v2")], {MID: [t]}, f"detect({MID}/rct_20261025-0001): park")
        res = repo.check()
        self.assertTrue(any("recheckAfter" in e for e in res.errors), res.errors)

    def test_parked_with_recheck_after_passes(self):
        repo = Repo(self.tmp, [model()])
        t = finished_task(status="assessing")
        t["assessment"]["recheckAfter"] = "2026-10-25T03:00:00Z"
        repo.commit([model(as_is="v2")], {MID: [t]}, f"detect({MID}/rct_20261025-0001): park")
        self.assertEqual(repo.check().errors, [])

    def test_bad_commit_message_and_schema_violation(self):
        repo = Repo(self.tmp, [model()])
        t = finished_task(status="action_required")
        t["unknownField"] = 1
        repo.commit([model(as_is="v2")], {MID: [t]}, "update data")
        joined = "\n".join(repo.check().errors)
        self.assertIn("커밋 메시지 규약 위반", joined)
        self.assertIn("task 스키마 위반", joined)

    def test_two_tasks_touched_is_error(self):
        repo = Repo(self.tmp, [model()])
        repo.commit([model(as_is="v2")], {MID: [finished_task(), finished_task("rct_20261025-0002")]},
                    f"detect({MID}/rct_20261025-0001): assess")
        self.assertTrue(any("정확히 1건" in e for e in repo.check().errors))

    def test_manual_trigger_must_copy_reason_and_clear_request(self):
        cp = {"manualTriggerRequestedAt": "2026-10-24T00:00:00Z", "manualTriggerReason": "문서 다시 봐줘"}
        repo = Repo(self.tmp, [model(check_policy=cp)])
        trig = {"source": "manual", "detectedAt": "2026-10-25T00:00:00Z", "reason": "요약된 사유"}
        repo.commit([model(check_policy=copy.deepcopy(cp))], {MID: [finished_task(trigger=trig)]},
                    f"detect({MID}/rct_20261025-0001): claim manual")
        joined = "\n".join(repo.check(reason="manual_trigger").errors)
        self.assertIn("manualTriggerReason을 그대로", joined)
        self.assertIn("지워지지 않음", joined)

    def test_manual_trigger_passes(self):
        cp = {"manualTriggerRequestedAt": "2026-10-24T00:00:00Z", "manualTriggerReason": "문서 다시 봐줘"}
        repo = Repo(self.tmp, [model(check_policy=cp)])
        trig = {"source": "manual", "detectedAt": "2026-10-25T00:00:00Z", "reason": "문서 다시 봐줘"}
        cleared = {"manualTriggerRequestedAt": None, "manualTriggerReason": None}
        repo.commit([model(check_policy=cleared)], {MID: [finished_task(status="no_action_needed", trigger=trig)]},
                    f"detect({MID}/rct_20261025-0001): claim manual")
        self.assertEqual(repo.check(reason="manual_trigger").errors, [])

    def test_recheck_expired_must_resume_existing_task(self):
        old = finished_task(status="assessing")
        old["assessment"]["recheckAfter"] = "2026-10-24T00:00:00Z"
        repo = Repo(self.tmp, [model()], {MID: [old]})
        new = finished_task("rct_20261025-0002", status="action_required")
        repo.commit([model()], {MID: [old, new]}, f"detect({MID}/rct_20261025-0002): assess")
        joined = "\n".join(repo.check(target_id="rct_20261025-0001", kind="task", reason="recheck_expired").errors)
        self.assertIn("rct_20261025-0001", joined)

    def test_no_commits_is_error(self):
        repo = Repo(self.tmp, [model()])
        self.assertTrue(any("새 커밋이 없음" in e for e in repo.check().errors))

    def _transcript(self, calls):
        path = self.tmp / "t.jsonl"
        lines = [json.dumps({"type": "item.completed", "timestampMs": ts,
                             "item": {"id": f"c{i}", "type": "tool_call",
                                      "toolCall": {"name": name, "input": {"command": cmd}}}})
                 for i, (ts, name, cmd) in enumerate(calls)]
        path.write_text("\n".join(lines) + "\n")
        return path

    def _claimed_repo(self):
        repo = Repo(self.tmp, [model()])
        repo.commit([model(as_is="v2")], {MID: [finished_task()]}, f"detect({MID}/rct_20261025-0001): claim")
        claim_ms = int(git(repo.path, "log", "-1", "--format=%ct")) * 1000
        return repo, claim_ms

    def test_collection_before_claim_is_error(self):
        repo, claim = self._claimed_repo()
        tr = self._transcript([(claim - 60000, "mcp__k3s__github_app_installation_token", ""),
                               (claim - 50000, "bash", "git clone --depth 1 https://x /tmp/w/demo"),
                               (claim - 40000, "bash", "C=/tmp/w/demo\ngit -C $C diff -U0 a b"),
                               (claim - 30000, "bash", "cd /tmp/w/demo && npm install jsdom"),
                               (claim + 5000, "bash", "git -C /tmp/w/demo show HEAD:docs/a.md")])
        res = repo.check()
        cdr.check_claim_order(repo.path, repo.base, tr, res)
        joined = "\n".join(res.errors)
        self.assertIn("점유 커밋 전에 수집", joined)
        self.assertIn("diff/내용 읽기 1회", joined)
        self.assertIn("하네스·의존성 실행 1회", joined)
        self.assertEqual(res.facts["pre_claim_tool_calls"], 4)

    def test_version_only_before_claim_passes(self):
        repo, claim = self._claimed_repo()
        own = str(repo.path.resolve())
        tr = self._transcript([(claim - 50000, "bash", "git clone --depth 1 https://x /tmp/w/demo"),
                               (claim - 40000, "bash", "cd /tmp/w/demo && bash /tmp/version.sh"),
                               (claim - 30000, "bash", f"git -C {own} diff --name-only"),
                               (claim + 5000, "bash", "git -C /tmp/w/demo diff a b")])
        res = repo.check()
        cdr.check_claim_order(repo.path, repo.base, tr, res)
        self.assertFalse([e for e in res.errors if "점유" in e], res.errors)
        self.assertTrue(any("점유 순서" in p for p in res.passed))

    def test_patch_includes_uncommitted(self):
        repo = Repo(self.tmp, [model()])
        repo.write([model(as_is="v2")], {MID: [finished_task()]})
        patch = self.tmp / "r.patch"
        rc = cdr.main(["--repo", str(repo.path), "--base", repo.base, "--model-id", MID, "--target-id", MID,
                       "--target-kind", "model", "--reason", "version_changed", "--patch", str(patch)])
        self.assertEqual(rc, 1)  # 커밋이 없으니 실패
        self.assertIn(f"{MID}.json", patch.read_text())


if __name__ == "__main__":
    unittest.main()
