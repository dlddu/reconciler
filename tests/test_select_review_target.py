"""`.github/scripts/select_review_target.py` 테스트 (python3 -m unittest discover -s tests).

임시 reconciler checkout(data/to-be-models.json + data/reconciliation-tasks/*.json)을 만들어
CLI(main)를 그대로 돌리고 GITHUB_OUTPUT/종료 코드/요약을 검사한다. 네트워크·토큰 없이 돈다.
"""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".github" / "scripts" / "select_review_target.py"
sys.path.insert(0, str(SCRIPT.parent))

import select_review_target as srt  # noqa: E402


def prepared_attempt(pr="https://github.com/dlddu/app/pull/1", notes=None, prepared_at="2026-10-20T00:00:00Z"):
    prep = {"repository": "dlddu/app", "pullRequestUrl": pr, "preparedAt": prepared_at}
    if notes is not None:
        prep["notes"] = notes
    return {"reason": "r", "plan": {"summary": "s", "steps": ["a"], "executionGuide": "g"},
            "preparation": prep}


class Fixture:
    def __init__(self, tmp: Path):
        self.repo = tmp / "reconciler"
        (self.repo / "data" / "reconciliation-tasks").mkdir(parents=True)
        self.models = []
        self.tasks = {}

    def model(self, mid, enabled=None):
        m = {"id": mid}
        if enabled is not None:
            m["checkPolicy"] = {"enabled": enabled}
        self.models.append(m)

    def task(self, mid, tid, status, *, updated="2026-10-20T00:00:00Z", attempts="prepared", **extra):
        if mid not in {m["id"] for m in self.models}:
            self.model(mid)
        t = {"id": tid, "toBeModelId": mid, "status": status,
             "createdAt": "2026-10-01T00:00:00Z", "updatedAt": updated}
        if attempts == "prepared":
            t["attempts"] = [prepared_attempt()]
        elif attempts is not None:
            t["attempts"] = attempts
        if updated is None:
            del t["updatedAt"]
        t.update(extra)
        self.tasks.setdefault(mid, []).append(t)
        return t

    def write(self):
        (self.repo / "data" / "to-be-models.json").write_text(json.dumps(self.models))
        for mid, tasks in self.tasks.items():
            (self.repo / "data" / "reconciliation-tasks" / f"{mid}.json").write_text(json.dumps(tasks))

    def run(self, target=""):
        self.write()
        out = self.repo.parent / "out.txt"
        summary = self.repo.parent / "summary.md"
        out.write_text("")
        summary.write_text("")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = srt.main(["--repo", str(self.repo), "--target", target,
                           "--github-output", str(out), "--summary-file", str(summary)])
        outputs = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
        return rc, outputs, summary.read_text(), buf.getvalue()


class SelectReviewTargetTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.f = Fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    # ── 자동 선정 ──

    def test_no_tasks_found_false(self):
        self.f.model("tbm_a")
        rc, out, summary, _ = self.f.run()
        self.assertEqual(rc, 0)
        self.assertEqual(out["found"], "false")
        self.assertEqual(out["target_id"], "")
        self.assertEqual(out["target_kind"], "")
        self.assertIn("판정할 대상 없음", summary)

    def test_picks_single_planned(self):
        self.f.task("tbm_a", "rct_1", "planned")
        rc, out, summary, _ = self.f.run()
        self.assertEqual(rc, 0)
        self.assertEqual(out["found"], "true")
        self.assertEqual(out["target_id"], "rct_1")
        self.assertEqual(out["target_kind"], "task")
        self.assertEqual(out["model_id"], "tbm_a")
        self.assertEqual(out["reason"], "oldest_planned")
        self.assertEqual(out["pull_request_url"], "https://github.com/dlddu/app/pull/1")
        self.assertEqual(out["ready_count"], "1")
        self.assertEqual(out["error_count"], "0")

    def test_oldest_updated_wins_across_models(self):
        self.f.task("tbm_a", "rct_new", "planned", updated="2026-10-22T00:00:00Z")
        self.f.task("tbm_b", "rct_old", "planned", updated="2026-10-21T00:00:00Z")
        self.f.task("tbm_c", "rct_mid", "planned", updated="2026-10-21T12:00:00Z")
        rc, out, summary, _ = self.f.run()
        self.assertEqual((rc, out["target_id"], out["model_id"]), (0, "rct_old", "tbm_b"))
        self.assertEqual(out["ready_count"], "3")
        # 나머지는 점유하지 않고 planned로 남긴다고 알린다.
        self.assertIn("planned 2건", summary)
        self.assertIn("tbm_c/rct_mid", summary)
        self.assertIn("tbm_a/rct_new", summary)

    def test_tie_broken_by_id(self):
        self.f.task("tbm_a", "rct_b", "planned")
        self.f.task("tbm_a", "rct_a", "planned")
        _, out, _, _ = self.f.run()
        self.assertEqual(out["target_id"], "rct_a")

    def test_missing_updated_falls_back_to_created(self):
        self.f.task("tbm_a", "rct_upd", "planned", updated="2026-10-05T00:00:00Z")
        self.f.task("tbm_a", "rct_crt", "planned", updated=None)  # createdAt 2026-10-01
        _, out, _, _ = self.f.run()
        self.assertEqual(out["target_id"], "rct_crt")

    def test_timezone_offsets_compared_in_utc(self):
        self.f.task("tbm_a", "rct_kst", "planned", updated="2026-10-21T08:00:00+09:00")  # 23:00Z 전날
        self.f.task("tbm_a", "rct_utc", "planned", updated="2026-10-21T00:00:00Z")
        _, out, _, _ = self.f.run()
        self.assertEqual(out["target_id"], "rct_kst")

    def test_non_planned_statuses_never_selected(self):
        for i, status in enumerate(["assessing", "no_action_needed", "action_required", "planning",
                                    "reviewing", "approved", "executing", "verifying",
                                    "review_rejected", "failed", "succeeded", "cancelled"]):
            self.f.task("tbm_a", f"rct_{i:02d}", status)
        rc, out, summary, _ = self.f.run()
        self.assertEqual((rc, out["found"], out["error_count"]), (0, "false", "0"))
        self.assertIn("reviewing 1건", summary)
        self.assertIn("회수하지 않음", summary)
        self.assertIn("executor 몫", summary)
        self.assertIn("planner 재계획 몫", summary)

    def test_stale_reviewing_lock_not_reclaimed(self):
        self.f.task("tbm_a", "rct_lock", "reviewing", updated="2020-01-01T00:00:00Z")
        self.f.task("tbm_a", "rct_p", "planned", updated="2026-10-22T00:00:00Z")
        _, out, summary, _ = self.f.run()
        self.assertEqual(out["target_id"], "rct_p")
        self.assertIn("tbm_a/rct_lock", summary)

    def test_nested_status_history_ignored(self):
        attempt = prepared_attempt()
        attempt["execution"] = {"status": "planned"}
        self.f.task("tbm_a", "rct_done", "succeeded", attempts=[attempt])
        _, out, _, _ = self.f.run()
        self.assertEqual(out["found"], "false")

    def test_disabled_model_is_parked(self):
        # 꺼진 모델의 planned task는 주차된 것 — 오래 기다렸어도 고르지 않고 켜진 모델의 것을 고른다.
        self.f.model("tbm_off", enabled=False)
        self.f.task("tbm_off", "rct_1", "planned", updated="2026-09-01T00:00:00Z")
        self.f.task("tbm_a", "rct_2", "planned")
        rc, out, summary, _ = self.f.run()
        self.assertEqual((rc, out["model_id"], out["target_id"]), (0, "tbm_a", "rct_2"))
        self.assertIn("주차됨", summary)

    def test_disabled_model_alone_finds_nothing(self):
        self.f.model("tbm_off", enabled=False)
        self.f.task("tbm_off", "rct_1", "planned")
        rc, out, summary, _ = self.f.run()
        self.assertEqual((rc, out["found"]), (0, "false"))
        self.assertIn("tbm_off/rct_1", summary)

    def test_disabled_model_explicit_is_parked(self):
        self.f.model("tbm_off", enabled=False)
        self.f.task("tbm_off", "rct_1", "planned")
        for target in ("tbm_off/rct_1", "rct_1", "tbm_off"):
            rc, out, summary, _ = self.f.run(target)
            self.assertEqual((rc, out["found"]), (0, "false"), target)
            self.assertIn("주차됨", summary, target)

    def test_direct_action_with_notes_is_ready(self):
        self.f.task("tbm_a", "rct_1", "planned", attempts=[prepared_attempt(pr=None, notes="직접 실행")])
        rc, out, summary, _ = self.f.run()
        self.assertEqual((rc, out["target_id"], out["pull_request_url"]), (0, "rct_1", ""))
        self.assertIn("직접 액션", summary)

    def test_uses_last_attempt_only(self):
        broken = {"reason": "r", "plan": {"summary": "s", "steps": []}}
        self.f.task("tbm_a", "rct_1", "planned", attempts=[broken, prepared_attempt(pr="https://x/pull/9")])
        _, out, _, _ = self.f.run()
        self.assertEqual((out["target_id"], out["pull_request_url"]), ("rct_1", "https://x/pull/9"))

    # ── 전제 미충족 planned ──

    def assert_unready(self, attempts, needle):
        self.f.task("tbm_a", "rct_bad", "planned", attempts=attempts)
        rc, out, summary, stdout = self.f.run()
        self.assertEqual(rc, 1, stdout)
        self.assertEqual(out["found"], "false")
        self.assertEqual(out["error_count"], "1")
        self.assertIn(needle, summary)
        self.assertIn("::error::", stdout)

    def test_unready_no_attempts(self):
        self.assert_unready(None, "attempts[]가 없음")

    def test_unready_no_steps(self):
        a = prepared_attempt()
        a["plan"]["steps"] = []
        self.assert_unready([a], "plan.steps")

    def test_unready_no_execution_guide(self):
        a = prepared_attempt()
        del a["plan"]["executionGuide"]
        self.assert_unready([a], "plan.executionGuide")

    def test_unready_not_prepared(self):
        a = prepared_attempt()
        del a["preparation"]
        self.assert_unready([a], "preparedAt")

    def test_unready_direct_action_without_notes(self):
        self.assert_unready([prepared_attempt(pr=None, notes="  ")], "notes")

    def test_unready_skipped_but_ready_one_still_selected(self):
        self.f.task("tbm_a", "rct_bad", "planned", attempts=None, updated="2026-10-01T00:00:00Z")
        self.f.task("tbm_b", "rct_ok", "planned", updated="2026-10-22T00:00:00Z")
        rc, out, summary, stdout = self.f.run()
        self.assertEqual((rc, out["target_id"], out["error_count"]), (0, "rct_ok", "1"))
        self.assertIn("::warning::tbm_a/rct_bad", stdout)
        self.assertNotIn("::error::", stdout)

    # ── 지목 ──

    def test_explicit_task_planned(self):
        self.f.task("tbm_a", "rct_old", "planned", updated="2026-10-01T00:00:00Z")
        self.f.task("tbm_b", "rct_pick", "planned", updated="2026-10-22T00:00:00Z")
        rc, out, _, _ = self.f.run("rct_pick")
        self.assertEqual((rc, out["target_id"], out["model_id"], out["reason"]),
                         (0, "rct_pick", "tbm_b", "explicit"))

    def test_explicit_task_wrong_status_skips(self):
        self.f.task("tbm_a", "rct_1", "approved")
        rc, out, summary, _ = self.f.run("rct_1")
        self.assertEqual((rc, out["found"]), (0, "false"))
        self.assertIn("status=approved", summary)
        self.assertIn("executor 몫", summary)

    def test_explicit_task_reviewing_not_reclaimed(self):
        self.f.task("tbm_a", "rct_1", "reviewing")
        rc, out, summary, _ = self.f.run("rct_1")
        self.assertEqual((rc, out["found"]), (0, "false"))
        self.assertIn("회수하지 않음", summary)

    def test_explicit_task_unready_fails(self):
        self.f.task("tbm_a", "rct_1", "planned", attempts=None)
        rc, out, _, _ = self.f.run("rct_1")
        self.assertEqual((rc, out["found"], out["error_count"]), (1, "false", "1"))

    def test_explicit_task_unknown(self):
        self.f.task("tbm_a", "rct_1", "planned")
        rc, out, _, stdout = self.f.run("rct_nope")
        self.assertEqual(rc, 2)
        self.assertEqual(out, {})
        self.assertIn("찾을 수 없음", stdout)

    def test_explicit_model_restricts_scope(self):
        self.f.task("tbm_a", "rct_older", "planned", updated="2026-10-01T00:00:00Z")
        self.f.task("tbm_b", "rct_b2", "planned", updated="2026-10-23T00:00:00Z")
        self.f.task("tbm_b", "rct_b1", "planned", updated="2026-10-22T00:00:00Z")
        rc, out, summary, _ = self.f.run("tbm_b")
        self.assertEqual((rc, out["target_id"], out["model_id"], out["reason"]),
                         (0, "rct_b1", "tbm_b", "explicit"))
        self.assertNotIn("rct_older", summary)

    def test_explicit_model_without_planned(self):
        self.f.task("tbm_a", "rct_1", "succeeded")
        rc, out, _, _ = self.f.run("tbm_a")
        self.assertEqual((rc, out["found"]), (0, "false"))

    def test_explicit_model_without_task_file(self):
        self.f.model("tbm_empty")
        rc, out, _, _ = self.f.run("tbm_empty")
        self.assertEqual((rc, out["found"]), (0, "false"))

    def test_explicit_model_unknown(self):
        self.f.model("tbm_a")
        rc, _, _, stdout = self.f.run("tbm_nope")
        self.assertEqual(rc, 2)
        self.assertIn("찾을 수 없음", stdout)

    def test_bad_target_forms(self):
        self.f.model("tbm_a")
        for bad in ["foo", "rct_1/tbm_a", "tbm_a/", "tbm_a/tbm_b", "tbm_a/rct_1/x"]:
            with self.subTest(bad=bad):
                rc, _, _, stdout = self.f.run(bad)
                self.assertEqual(rc, 2)
                self.assertIn("tbm_.../rct_", stdout)

    # ── task id는 모델 안에서만 유일하다(실데이터: 450개 중 368개가 여러 모델에 걸침) ──

    def test_shared_id_bare_picks_the_planned_one(self):
        # 파일 정렬상 앞선 모델(tbm_a)의 같은 id가 먼저 보여도 planned인 쪽을 고른다.
        self.f.task("tbm_a", "rct_x", "no_action_needed")
        self.f.task("tbm_b", "rct_x", "succeeded")
        self.f.task("tbm_c", "rct_x", "planned")
        rc, out, summary, _ = self.f.run("rct_x")
        self.assertEqual((rc, out["target_id"], out["model_id"]), (0, "rct_x", "tbm_c"))
        self.assertIn("다른 모델 task 2건", summary)

    def test_shared_id_bare_none_planned_reports_each(self):
        self.f.task("tbm_a", "rct_x", "no_action_needed")
        self.f.task("tbm_b", "rct_x", "review_rejected")
        rc, out, summary, _ = self.f.run("rct_x")
        self.assertEqual((rc, out["found"]), (0, "false"))
        self.assertIn("tbm_a/rct_x: status=no_action_needed", summary)
        self.assertIn("tbm_b/rct_x: status=review_rejected", summary)

    def test_shared_id_bare_two_planned_is_ambiguous(self):
        self.f.task("tbm_a", "rct_x", "planned")
        self.f.task("tbm_b", "rct_x", "planned")
        rc, out, _, stdout = self.f.run("rct_x")
        self.assertEqual((rc, out), (2, {}))
        self.assertIn("tbm_a, tbm_b", stdout)
        self.assertIn("모델까지 지목", stdout)

    def test_qualified_target_exact_model(self):
        self.f.task("tbm_a", "rct_x", "planned", updated="2026-10-01T00:00:00Z")
        self.f.task("tbm_b", "rct_x", "planned", updated="2026-10-22T00:00:00Z")
        rc, out, _, _ = self.f.run("tbm_b/rct_x")
        self.assertEqual((rc, out["target_id"], out["model_id"], out["reason"]),
                         (0, "rct_x", "tbm_b", "explicit"))

    def test_qualified_target_wrong_status_even_if_other_model_planned(self):
        self.f.task("tbm_a", "rct_x", "planned")
        self.f.task("tbm_b", "rct_x", "approved")
        rc, out, summary, _ = self.f.run("tbm_b/rct_x")
        self.assertEqual((rc, out["found"]), (0, "false"))
        self.assertIn("tbm_b/rct_x: status=approved", summary)
        self.assertNotIn("tbm_a", summary)

    def test_qualified_target_unknown(self):
        self.f.task("tbm_a", "rct_x", "planned")
        for target in ["tbm_b/rct_x", "tbm_a/rct_y"]:
            with self.subTest(target=target):
                rc, _, _, stdout = self.f.run(target)
                self.assertEqual(rc, 2)
                self.assertIn("찾을 수 없음", stdout)

    def test_whitespace_target_means_auto(self):
        self.f.task("tbm_a", "rct_1", "planned")
        _, out, _, _ = self.f.run("   ")
        self.assertEqual(out["reason"], "oldest_planned")

    # ── 깨진 데이터 ──

    def test_corrupt_task_file(self):
        self.f.task("tbm_a", "rct_1", "planned")
        self.f.write()
        (self.f.repo / "data" / "reconciliation-tasks" / "tbm_a.json").write_text("{not json")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = srt.main(["--repo", str(self.f.repo), "--github-output", "/dev/null", "--summary-file", ""])
        self.assertEqual(rc, 2)
        self.assertIn("::error::", buf.getvalue())

    def test_task_file_not_array(self):
        self.f.model("tbm_a")
        self.f.write()
        (self.f.repo / "data" / "reconciliation-tasks" / "tbm_a.json").write_text("{}")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = srt.main(["--repo", str(self.f.repo), "--github-output", "/dev/null", "--summary-file", ""])
        self.assertEqual(rc, 2)

    def test_not_a_reconciler_checkout(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = srt.main(["--repo", self._tmp.name, "--github-output", "/dev/null", "--summary-file", ""])
        self.assertEqual(rc, 2)

    # ── 실제 CLI 호출(워크플로와 같은 방식) ──

    def test_cli_subprocess_writes_github_output(self):
        self.f.task("tbm_a", "rct_1", "planned")
        self.f.write()
        out = Path(self._tmp.name) / "gh_out"
        out.write_text("existing=1\n")
        proc = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.f.repo), "--target", ""],
                              env={"GITHUB_OUTPUT": str(out), "PATH": "/usr/bin:/bin"},
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = out.read_text()
        self.assertTrue(text.startswith("existing=1\n"))  # append, 덮어쓰지 않음
        self.assertIn("target_id=rct_1\n", text)
        self.assertIn("found=true\n", text)


if __name__ == "__main__":
    unittest.main()
