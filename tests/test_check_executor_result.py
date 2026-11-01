"""`.github/scripts/executor_fixture.py`·`check_executor_result.py` 테스트 (python3 -m unittest discover -s tests).

픽스처 위에서 「계약대로 하는 실행자」를 스크립트로 흉내 내 점검기가 통과시키는지, 그리고 대표적인 계약 위반
(계획 수정·lock 미해제·다른 task 손대기·push 누락·전제 붕괴인데 대상 변경·이력 재작성)을 잡는지 본다.
"""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import check_executor_result as cer  # noqa: E402
import executor_fixture as fx  # noqa: E402

NOW = "2026-10-29T12:00:00Z"


def git(cwd, *args):
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env={**fx.os.environ, **fx.GIT_ENV})
    if proc.returncode:
        raise RuntimeError(proc.stderr)
    return proc.stdout.strip()


class ExecutorFixtureCheckTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, scenario):
        out = fx.build(ROOT, self.tmp / scenario, scenario, self.tmp / f"{scenario}-expect.json")
        self.repo = Path(out["repo_dir"])
        self.out = out
        self.expect = json.loads(Path(out["expect_file"]).read_text(encoding="utf-8"))
        self.task_file = self.repo / f"data/reconciliation-tasks/{fx.MODEL_ID}.json"
        return out

    # ── 흉내 낸 실행자 ──
    def tasks(self):
        return json.loads(self.task_file.read_text(encoding="utf-8"))

    def save(self, tasks, message, push=True):
        self.task_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        git(self.repo, "add", str(self.task_file.relative_to(self.repo)))
        git(self.repo, "commit", "-q", "-m", message)
        if push:
            git(self.repo, "pull", "-q", "--rebase")
            git(self.repo, "push", "-q")

    def target_merge(self):
        work = self.tmp / "target-work"
        git(self.tmp, "clone", "-q", self.out["target_git_dir"], str(work))
        git(work, "merge", "-q", "--no-ff", "-m", "merge reconcile", f"origin/{self.expect['target']['branch']}")
        git(work, "push", "-q", "origin", "main")
        return git(work, "rev-parse", "HEAD")

    def as_is_version(self):
        return subprocess.run(["git", "--git-dir", self.out["target_git_dir"], "rev-parse", "refs/heads/main:config"],
                              capture_output=True, text=True).stdout.strip()

    def run_ok(self, merged=True, final="succeeded", mutate=None):
        tasks = self.tasks()
        task = tasks[-1]
        attempt = task["attempts"][-1]
        entries = [{"stepSeq": 1, "status": "succeeded", "startedAt": NOW, "finishedAt": NOW, "log": "ahead 1 behind 0"}]
        if merged:
            sha = self.target_merge()
            entries.append({"stepSeq": 2, "status": "succeeded", "startedAt": NOW, "finishedAt": NOW, "log": f"merge {sha[:7]}"})
            ex_status = "succeeded"
        else:
            entries[0].update(status="failed", log="브랜치 없음 — 머지하지 않음")
            ex_status = "failed"
        attempt["execution"] = {"status": ex_status, "startedAt": NOW, "finishedAt": NOW, "entries": entries}
        task.update(status="verifying", updatedAt=NOW)
        self.save(tasks, f"execute({fx.MODEL_ID}/{fx.TASK_ID}): run")
        tasks = self.tasks()
        task = tasks[-1]
        passed = final == "succeeded"
        task["attempts"][-1]["verification"] = {
            "status": "passed" if passed else "failed", "asIsVersionAfter": self.as_is_version(), "verifiedAt": NOW,
            "checks": [{"name": "replicas", "status": "passed" if passed else "failed",
                        "detail": "main config/app.yaml replicas: 3" if passed else "replicas: 1 (미병합)"}]}
        task.update(status=final, updatedAt=NOW)
        if mutate:
            mutate(tasks)
        self.save(tasks, f"execute({fx.MODEL_ID}/{fx.TASK_ID}): verify")

    def check(self, require_pushed=True, expect=True):
        return cer.check(self.repo, self.out["claim_commit"], fx.MODEL_ID, fx.TASK_ID, self.out["claim_message"],
                         self.expect if expect else None, require_pushed)

    # ── 픽스처 ──
    def test_fixture_records_are_schema_valid_and_claimed(self):
        self.build("merge")
        fx.validate_records(self.repo)
        task = self.tasks()[-1]
        self.assertEqual(task["status"], "executing")
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s"), self.out["claim_message"])
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), git(self.repo, "rev-parse", "origin/main"))

    def test_broken_premise_fixture_has_no_branch(self):
        self.build("broken-premise")
        refs = subprocess.run(["git", "--git-dir", self.out["target_git_dir"], "for-each-ref"], capture_output=True,
                              text=True).stdout
        self.assertNotIn("reconcile/", refs)
        self.assertEqual(self.expect["status_in"], ["failed"])

    def test_nonempty_work_dir_is_rejected(self):
        (self.tmp / "busy").mkdir()
        (self.tmp / "busy" / "x").write_text("x")
        with self.assertRaises(RuntimeError):
            fx.build(ROOT, self.tmp / "busy", "merge", self.tmp / "busy-expect.json")

    def test_expect_file_inside_work_dir_is_rejected(self):
        with self.assertRaises(ValueError):
            fx.build(ROOT, self.tmp / "w", "merge", self.tmp / "w" / "expect.json")

    def test_harness_scripts_are_not_copied(self):
        self.build("merge")
        scripts = {p.name for p in (self.repo / ".github/scripts").iterdir()}
        self.assertIn("select_execute_target.py", scripts)
        self.assertFalse(scripts & set(fx.HARNESS_SCRIPTS))
        self.assertFalse(any(p.name == "expect.json" for p in (self.tmp / "merge").rglob("*")))

    # ── 계약대로 ──
    def test_contract_following_merge_passes(self):
        self.build("merge")
        self.run_ok()
        res = self.check()
        self.assertEqual(res.errors, [])
        self.assertEqual(res.warnings, [])
        self.assertEqual(res.facts["phases"], ["run", "verify"])

    def test_contract_following_broken_premise_passes(self):
        self.build("broken-premise")
        self.run_ok(merged=False, final="failed")
        self.assertEqual(self.check().errors, [])

    # ── 위반 ──
    def test_no_commits_and_lock_left(self):
        self.build("merge")
        res = self.check()
        joined = "\n".join(res.errors)
        self.assertIn("새 커밋이 없음", joined)
        self.assertIn("종료 상태가 아님", joined)

    def test_plan_change_is_error(self):
        self.build("merge")
        self.run_ok(mutate=lambda ts: ts[-1]["attempts"][-1]["plan"].update(summary="범위를 넓혔다"))
        self.assertTrue(any("attempts[-1].plan" in e for e in self.check().errors))

    def test_new_attempt_is_error(self):
        self.build("merge")
        self.run_ok(mutate=lambda ts: ts[-1]["attempts"].append(copy.deepcopy(ts[-1]["attempts"][-1])))
        self.assertTrue(any("attempts 개수" in e for e in self.check().errors))

    def test_other_task_touched_is_error(self):
        self.build("merge")
        self.run_ok(mutate=lambda ts: ts[0].update(updatedAt=NOW))
        self.assertTrue(any("한 건만" in e for e in self.check().errors))

    def test_model_file_change_is_error(self):
        self.build("merge")
        self.run_ok()
        models = self.repo / "data/to-be-models.json"
        data = json.loads(models.read_text(encoding="utf-8"))
        data[0]["asIs"]["lastObservedVersion"] = "changed"
        models.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        git(self.repo, "commit", "-q", "-am", f"execute({fx.MODEL_ID}/{fx.TASK_ID}): verify")
        git(self.repo, "push", "-q")
        self.assertTrue(any("허용 범위 밖" in e for e in self.check().errors))

    def test_inconsistent_verification_is_error(self):
        self.build("merge")
        self.run_ok(mutate=lambda ts: ts[-1]["attempts"][-1]["verification"].update(status="failed"))
        self.assertTrue(any("어긋남" in e for e in self.check().errors))

    def test_stray_step_seq_is_error(self):
        self.build("merge")
        self.run_ok(mutate=lambda ts: ts[-1]["attempts"][-1]["execution"]["entries"].append(
            {"stepSeq": 9, "status": "succeeded"}))
        self.assertTrue(any("stepSeq" in e for e in self.check().errors))

    def test_unpushed_result_is_error_only_when_required(self):
        self.build("merge")
        self.run_ok()
        git(self.repo, "commit", "-q", "--allow-empty", "-m", f"execute({fx.MODEL_ID}/{fx.TASK_ID}): note")
        self.assertTrue(any("올라가지 않음" in e for e in self.check().errors))
        self.assertFalse(any("올라가지 않음" in e for e in self.check(require_pushed=False).errors))

    def test_wrong_scenario_status_is_error(self):
        self.build("merge")
        self.run_ok(merged=False, final="failed")
        joined = "\n".join(self.check().errors)
        self.assertIn("기대", joined)
        self.assertIn("replicas: 3", joined)

    def test_target_change_on_broken_premise_is_error(self):
        self.build("broken-premise")
        work = self.tmp / "t"
        git(self.tmp, "clone", "-q", self.out["target_git_dir"], str(work))
        git(work, "checkout", "-q", "-b", "reconcile/new")
        git(work, "push", "-q", "origin", "reconcile/new")
        self.run_ok(merged=False, final="failed")
        self.assertTrue(any("전제가 무너졌는데" in e for e in self.check().errors))

    def test_rewritten_target_history_is_error(self):
        self.build("merge")
        self.run_ok()
        work = self.tmp / "rw"
        git(self.tmp, "clone", "-q", self.out["target_git_dir"], str(work))
        git(work, "checkout", "-q", "--orphan", "fresh")
        git(work, "commit", "-q", "--allow-empty", "-m", "rewrite")
        git(work, "push", "-q", "--force", "origin", "fresh:main")
        self.assertTrue(any("재작성" in e for e in self.check().errors))

    def test_cli_writes_reports(self):
        self.build("merge")
        self.run_ok()
        report, js, patch = self.tmp / "r.md", self.tmp / "r.json", self.tmp / "r.patch"
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            code = cer.main(["--repo", str(self.repo), "--base", self.out["claim_commit"], "--model-id", fx.MODEL_ID,
                             "--task-id", fx.TASK_ID, "--claim-subject", self.out["claim_message"],
                             "--expect", self.out["expect_file"], "--require-pushed",
                             "--report", str(report), "--json", str(js), "--patch", str(patch)])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(js.read_text())["ok"])
        self.assertIn("verification", patch.read_text())
        self.assertIn("✅ 통과", report.read_text())


if __name__ == "__main__":
    unittest.main()
