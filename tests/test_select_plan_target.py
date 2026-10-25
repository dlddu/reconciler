"""`.github/scripts/select_plan_target.py` 테스트 (python3 -m unittest discover -s tests).

임시 reconciler checkout(data/ 만)을 만들어 main()을 그대로 돌린다. 네트워크·토큰 없이 돈다.
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
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import select_plan_target as spt  # noqa: E402


class Fixture:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.repo = tmp / "reconciler"
        (self.repo / "data" / "reconciliation-tasks").mkdir(parents=True)
        self.models = []
        self.tasks = {}

    def model(self, mid, *, enabled=None, check_policy=None):
        m = {"id": mid, "metadata": {"name": mid}, "definition": "# def"}
        if enabled is not None:
            m["checkPolicy"] = {"enabled": enabled}
        if check_policy is not None:
            m["checkPolicy"] = check_policy
        self.models.append(m)
        return m

    def task(self, mid, tid, status, *, updated="2026-10-20T00:00:00Z", created="2026-10-01T00:00:00Z",
             attempts=0):
        t = {"id": tid, "toBeModelId": mid, "status": status, "trigger": {"source": "version_change"},
             "createdAt": created}
        if updated is not None:
            t["updatedAt"] = updated
        if attempts:
            # 중첩 status(이력)는 최상위 status 판단에 섞이면 안 된다.
            t["attempts"] = [{"plan": {"summary": "s"}, "execution": {"status": "action_required"}}
                             for _ in range(attempts)]
        self.tasks.setdefault(mid, []).append(t)
        return t

    def write(self):
        (self.repo / "data" / "to-be-models.json").write_text(json.dumps(self.models))
        for mid, tasks in self.tasks.items():
            (self.repo / "data" / "reconciliation-tasks" / f"{mid}.json").write_text(json.dumps(tasks))

    def run(self, *extra):
        """main()을 돌려 (exit code, outputs dict, stdout) 반환."""
        self.write()
        out_file = self.tmp / "gh_output"
        out_file.write_text("")
        argv = ["--repo", str(self.repo), "--github-output", str(out_file),
                "--summary-file", str(self.tmp / "summary.md"), *extra]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = spt.main(argv)
        outputs = dict(line.split("=", 1) for line in out_file.read_text().splitlines())
        return code, outputs, buf.getvalue()


class SelectPlanTargetTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = Fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def assertPicked(self, out, model_id, task_id, status, reason="oldest_ready"):
        self.assertEqual(out["found"], "true")
        self.assertEqual(out["target_kind"], "task")
        self.assertEqual((out["model_id"], out["target_id"], out["from_status"], out["reason"]),
                         (model_id, task_id, status, reason))

    # ── 대상 없음 ──

    def test_no_target_when_nothing_at_handoff_point(self):
        self.fx.model("tbm_a")
        for i, st in enumerate(["assessing", "no_action_needed", "planned", "reviewing", "approved",
                                "executing", "verifying", "succeeded", "cancelled"]):
            self.fx.task("tbm_a", f"rct_20261001-{i:04d}", st)
        code, out, stdout = self.fx.run()
        self.assertEqual(code, 0)
        self.assertEqual(out["found"], "false")
        self.assertEqual(out["target_id"], "")
        self.assertEqual(out["ready_count"], "0")
        self.assertIn("이번에 계획할 대상 없음", stdout)
        self.assertIn("planned 1건: 계획 완료, 검토 판단 대기 — work-review 몫", stdout)

    def test_empty_repo_has_no_target(self):
        code, out, _ = self.fx.run()
        self.assertEqual((code, out["found"]), (0, "false"))

    def test_planning_is_never_picked(self):
        """새 러너는 resume할 lock이 없다 — 남이 잡은 planning을 가로채지 않는다."""
        self.fx.model("tbm_a")
        self.fx.task("tbm_a", "rct_20261001-0001", "planning", updated="2026-01-01T00:00:00Z")
        code, out, stdout = self.fx.run()
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertIn("다른 planner 워커가 점유 중", stdout)

    # ── 계획 대상 ──

    def test_each_handoff_status_is_ready(self):
        for st in spt.READY_STATUSES:
            with self.subTest(status=st):
                self.fx.models, self.fx.tasks = [], {}
                self.fx.model("tbm_a")
                self.fx.task("tbm_a", "rct_20261001-0001", st)
                code, out, _ = self.fx.run()
                self.assertEqual(code, 0)
                self.assertPicked(out, "tbm_a", "rct_20261001-0001", st)

    def test_oldest_waiting_task_wins_across_models_and_rest_stay_unclaimed(self):
        self.fx.model("tbm_a")
        self.fx.model("tbm_b")
        self.fx.task("tbm_a", "rct_20261010-0001", "action_required", updated="2026-10-10T00:00:00Z")
        self.fx.task("tbm_b", "rct_20261005-0001", "review_rejected", updated="2026-10-05T00:00:00Z")
        self.fx.task("tbm_b", "rct_20261007-0001", "failed", updated="2026-10-07T09:00:00+09:00")
        code, out, stdout = self.fx.run()
        self.assertEqual(code, 0)
        self.assertPicked(out, "tbm_b", "rct_20261005-0001", "review_rejected")
        self.assertEqual(out["ready_count"], "3")
        self.assertIn("이번엔 점유하지 않고 미점유로 남김: tbm_b/rct_20261007-0001, tbm_a/rct_20261010-0001",
                      stdout)

    def test_timezone_offsets_compare_as_instants(self):
        self.fx.model("tbm_a")
        self.fx.task("tbm_a", "rct_20261001-0001", "action_required", updated="2026-10-10T08:00:00+09:00")
        self.fx.task("tbm_a", "rct_20261001-0002", "action_required", updated="2026-10-10T00:00:00Z")
        _, out, _ = self.fx.run()
        self.assertEqual(out["target_id"], "rct_20261001-0001")  # 2026-10-09T23:00Z

    def test_falls_back_to_created_at_then_id(self):
        self.fx.model("tbm_a")
        self.fx.task("tbm_a", "rct_20261001-0003", "action_required", updated=None, created="2026-10-02T00:00:00Z")
        self.fx.task("tbm_a", "rct_20261001-0002", "action_required", updated="2026-10-03T00:00:00Z")
        self.fx.task("tbm_a", "rct_20261001-0001", "action_required", updated=None, created="2026-10-02T00:00:00Z")
        _, out, _ = self.fx.run()
        self.assertEqual(out["target_id"], "rct_20261001-0001")

    def test_unparseable_timestamp_counts_as_oldest(self):
        self.fx.model("tbm_a")
        self.fx.task("tbm_a", "rct_20261001-0001", "action_required", updated="2026-10-01T00:00:00Z")
        self.fx.task("tbm_a", "rct_20261001-0002", "action_required", updated="not-a-date", created="??")
        code, out, _ = self.fx.run()
        self.assertEqual((code, out["target_id"]), (0, "rct_20261001-0002"))

    def test_attempt_count_reports_rework_history(self):
        self.fx.model("tbm_a")
        self.fx.task("tbm_a", "rct_20261001-0001", "review_rejected", attempts=2)
        _, out, stdout = self.fx.run()
        self.assertEqual(out["attempt_count"], "2")
        self.assertIn("이전 시도 2건", stdout)

    def test_nested_status_is_ignored(self):
        """attempts[] 안의 status는 이력이다 — 최상위 status만 본다."""
        self.fx.model("tbm_a")
        self.fx.task("tbm_a", "rct_20261001-0001", "succeeded", attempts=1)
        _, out, _ = self.fx.run()
        self.assertEqual(out["found"], "false")

    def test_does_not_write_to_repo(self):
        self.fx.model("tbm_a")
        self.fx.task("tbm_a", "rct_20261001-0001", "action_required")
        self.fx.write()
        before = {p: p.read_bytes() for p in self.fx.repo.rglob("*") if p.is_file()}
        self.fx.run()
        after = {p: p.read_bytes() for p in self.fx.repo.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    # ── 꺼진 모델 ──

    def test_disabled_model_tasks_are_parked(self):
        self.fx.model("tbm_off", enabled=False)
        self.fx.model("tbm_on")
        self.fx.task("tbm_off", "rct_20261001-0001", "action_required", updated="2026-01-01T00:00:00Z")
        self.fx.task("tbm_on", "rct_20261001-0002", "failed", updated="2026-10-20T00:00:00Z")
        _, out, stdout = self.fx.run()
        self.assertPicked(out, "tbm_on", "rct_20261001-0002", "failed")
        self.assertEqual(out["ready_count"], "1")
        self.assertIn("tbm_off/rct_20261001-0001", stdout)
        self.assertIn("주차됨", stdout)

    def test_only_parked_tasks_means_no_target(self):
        self.fx.model("tbm_off", enabled=False)
        self.fx.task("tbm_off", "rct_20261001-0001", "review_rejected")
        code, out, stdout = self.fx.run()
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertIn("checkPolicy.enabled를 켜면 다시 계획 대상", stdout)

    def test_enabled_predicate_matches_precheck(self):
        """JSON false만 끈다 — 필드 없음·null·문자열은 켜진 것(precheck-plan.py와 같은 fail-open)."""
        for policy in [None, {}, {"enabled": True}, {"enabled": None}, {"enabled": "false"}, {"enabled": 0}]:
            with self.subTest(policy=policy):
                self.assertTrue(spt.is_enabled({"id": "m", **({"checkPolicy": policy} if policy is not None else {})}))
        self.assertFalse(spt.is_enabled({"checkPolicy": {"enabled": False}}))

    def test_orphan_task_file_is_treated_as_enabled_with_warning(self):
        self.fx.task("tbm_ghost", "rct_20261001-0001", "action_required")
        code, out, stdout = self.fx.run()
        self.assertEqual(code, 0)
        self.assertPicked(out, "tbm_ghost", "rct_20261001-0001", "action_required")
        self.assertIn("::warning::tbm_ghost", stdout)

    # ── 지목 ──

    def test_explicit_task_is_picked_over_older_ones(self):
        self.fx.model("tbm_a")
        self.fx.task("tbm_a", "rct_20261001-0001", "action_required", updated="2026-01-01T00:00:00Z")
        self.fx.task("tbm_a", "rct_20261001-0002", "failed", updated="2026-10-20T00:00:00Z")
        _, out, _ = self.fx.run("--target", "rct_20261001-0002")
        self.assertPicked(out, "tbm_a", "rct_20261001-0002", "failed", reason="explicit")

    def test_explicit_task_not_at_handoff_point(self):
        self.fx.model("tbm_a")
        self.fx.task("tbm_a", "rct_20261001-0001", "planned")
        code, out, stdout = self.fx.run("--target", "rct_20261001-0001")
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertIn("status=planned — 계획 완료, 검토 판단 대기 — work-review 몫", stdout)

    def test_explicit_task_on_disabled_model(self):
        self.fx.model("tbm_off", enabled=False)
        self.fx.task("tbm_off", "rct_20261001-0001", "action_required")
        code, out, stdout = self.fx.run("--target", "rct_20261001-0001")
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertIn("감지 비활성", stdout)

    def test_explicit_model_picks_its_oldest_ready_task(self):
        self.fx.model("tbm_a")
        self.fx.model("tbm_b")
        self.fx.task("tbm_a", "rct_20261001-0001", "action_required", updated="2026-01-01T00:00:00Z")
        self.fx.task("tbm_b", "rct_20261001-0002", "failed", updated="2026-10-20T00:00:00Z")
        self.fx.task("tbm_b", "rct_20261001-0003", "action_required", updated="2026-10-10T00:00:00Z")
        self.fx.task("tbm_b", "rct_20261001-0004", "planning", updated="2026-01-01T00:00:00Z")
        _, out, stdout = self.fx.run("--target", "tbm_b")
        self.assertPicked(out, "tbm_b", "rct_20261001-0003", "action_required", reason="explicit")
        self.assertEqual(out["ready_count"], "2")
        self.assertIn("rct_20261001-0002", stdout)

    def test_explicit_model_without_ready_task(self):
        self.fx.model("tbm_a")
        self.fx.task("tbm_a", "rct_20261001-0001", "no_action_needed")
        code, out, stdout = self.fx.run("--target", "tbm_a")
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertIn("rct_20261001-0001=no_action_needed", stdout)

    def test_explicit_disabled_model(self):
        self.fx.model("tbm_off", enabled=False)
        self.fx.task("tbm_off", "rct_20261001-0001", "action_required")
        code, out, _ = self.fx.run("--target", "tbm_off")
        self.assertEqual((code, out["found"]), (0, "false"))

    def test_explicit_target_is_trimmed(self):
        self.fx.model("tbm_a")
        self.fx.task("tbm_a", "rct_20261001-0001", "action_required")
        _, out, _ = self.fx.run("--target", "  rct_20261001-0001\n")
        self.assertEqual(out["target_id"], "rct_20261001-0001")

    def test_explicit_unknown_or_malformed_target_errors(self):
        self.fx.model("tbm_a")
        self.assertEqual(self.fx.run("--target", "tbm_nope")[0], 2)
        self.assertEqual(self.fx.run("--target", "rct_20990101-0001")[0], 2)
        self.assertEqual(self.fx.run("--target", "garbage")[0], 2)

    def test_explicit_ambiguous_task_id_errors_with_candidates(self):
        """task id는 모델 파일 안에서만 유일하다 — 겹치면 추측하지 않고 후보를 보여 준다."""
        self.fx.model("tbm_a")
        self.fx.model("tbm_b")
        self.fx.task("tbm_a", "rct_20261001-0001", "no_action_needed")
        self.fx.task("tbm_b", "rct_20261001-0001", "action_required")
        code, _, stdout = self.fx.run("--target", "rct_20261001-0001")
        self.assertEqual(code, 2)
        self.assertIn("tbm_a/rct_20261001-0001(no_action_needed)", stdout)
        self.assertIn("tbm_b/rct_20261001-0001(action_required)", stdout)

    def test_explicit_model_slash_task_disambiguates(self):
        self.fx.model("tbm_a")
        self.fx.model("tbm_b")
        self.fx.task("tbm_a", "rct_20261001-0001", "action_required", updated="2026-01-01T00:00:00Z")
        self.fx.task("tbm_b", "rct_20261001-0001", "failed")
        _, out, _ = self.fx.run("--target", "tbm_b/rct_20261001-0001")
        self.assertPicked(out, "tbm_b", "rct_20261001-0001", "failed", reason="explicit")

    def test_explicit_model_slash_task_not_ready_or_unknown(self):
        self.fx.model("tbm_a")
        self.fx.model("tbm_b")
        self.fx.task("tbm_a", "rct_20261001-0001", "action_required")
        self.fx.task("tbm_b", "rct_20261001-0001", "approved")
        code, out, stdout = self.fx.run("--target", "tbm_b/rct_20261001-0001")
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertIn("tbm_b/rct_20261001-0001: status=approved", stdout)
        self.assertEqual(self.fx.run("--target", "tbm_b/rct_20261001-0009")[0], 2)

    def test_malformed_target_forms(self):
        for bad in ["rct_1/rct_2", "tbm_a/tbm_b", "tbm_a/", "/rct_1", "x/rct_1"]:
            with self.subTest(target=bad), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(spt.main(["--repo", str(self.fx.repo), "--target", bad,
                                           "--github-output", str(self.fx.tmp / "o")]), 2)

    def test_parse_target(self):
        self.assertEqual(spt.parse_target("rct_1"), (None, "rct_1"))
        self.assertEqual(spt.parse_target("tbm_a"), ("tbm_a", None))
        self.assertEqual(spt.parse_target("tbm_a/rct_1"), ("tbm_a", "rct_1"))

    # ── 깨진 데이터: "계획할 것 없음"으로 단정하지 않는다 ──

    def test_broken_task_file_fails(self):
        self.fx.model("tbm_a")
        self.fx.write()
        (self.fx.repo / "data" / "reconciliation-tasks" / "tbm_a.json").write_text("{not json")
        out_file = self.fx.tmp / "o"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = spt.main(["--repo", str(self.fx.repo), "--github-output", str(out_file)])
        self.assertEqual(code, 2)
        self.assertIn("::error::", buf.getvalue())
        self.assertFalse(out_file.exists() and "found=false" in out_file.read_text())

    def test_non_array_task_file_fails(self):
        self.fx.model("tbm_a")
        self.fx.write()
        (self.fx.repo / "data" / "reconciliation-tasks" / "tbm_a.json").write_text('{"id": "x"}')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(spt.main(["--repo", str(self.fx.repo)]), 2)

    def test_missing_models_file_fails(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(spt.main(["--repo", str(self.fx.repo)]), 2)

    def test_summary_file_and_outputs_written(self):
        self.fx.model("tbm_a")
        self.fx.task("tbm_a", "rct_20261001-0001", "action_required")
        self.fx.run()
        summary = (self.fx.tmp / "summary.md").read_text()
        self.assertTrue(summary.startswith("#### Select target\n"))
        self.assertIn("`tbm_a/rct_20261001-0001`", summary)


class RealDataTest(unittest.TestCase):
    def test_runs_against_real_repo_data(self):
        """레포의 실제 data/로 선정이 끝까지 돌아야 하고, 고른 task는 실제로 계획 대상이어야 한다."""
        sel = spt.select_target(ROOT)
        state = spt.load_state(ROOT)
        if sel.found:
            ref = next(r for r in state.tasks if r.id == sel.target_id and r.model_id == sel.model_id)
            self.assertIsNone(spt.why_not(ref, state))
        ready = [r for r in state.tasks if spt.why_not(r, state) is None]
        self.assertEqual(sel.ready_count, len(ready))
        self.assertEqual(sel.found, bool(ready))

    def test_cli_runs_as_workflow_step(self):
        """워크플로가 부르는 그대로(python3 스크립트 경로) 돌아 output 형식을 지키는지."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            proc = subprocess.run(
                [sys.executable, str(ROOT / ".github" / "scripts" / "select_plan_target.py"),
                 "--repo", str(ROOT), "--target", "", "--summary-file", str(Path(tmp) / "s.md")],
                env={"GITHUB_OUTPUT": str(out), "PATH": "/usr/bin:/bin"},
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            keys = [line.split("=", 1)[0] for line in out.read_text().splitlines()]
            self.assertEqual(keys, ["found", "target_id", "target_kind", "model_id", "from_status",
                                    "reason", "attempt_count", "ready_count"])


if __name__ == "__main__":
    unittest.main()
