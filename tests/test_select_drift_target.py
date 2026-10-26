"""`.github/scripts/select_drift_target.py` 테스트 (python3 -m unittest discover -s tests).

대상 레포는 file:// 로컬 git 레포로 대신해, 실제 versionScript(bash/python)를 실제 클론 위에서 돌린다.
네트워크·토큰 없이 돈다.
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

import select_drift_target as sdt  # noqa: E402

NOW = "2026-10-25T10:00:00Z"
TREE_SCRIPT = {"runtime": "bash", "code": "set -euo pipefail\ngit rev-parse HEAD:docs\n"}
SRC_SCRIPT = {"runtime": "bash", "code": "set -euo pipefail\nprintf 'src:%s\\n' \"$(git rev-parse HEAD:src)\"\n"}


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class Fixture:
    """reconciler checkout + 대상 레포(file://)를 임시 디렉터리에 만든다."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.sources = tmp / "sources"
        self.repo = tmp / "reconciler"
        (self.repo / "data" / "reconciliation-tasks").mkdir(parents=True)
        self.models = []
        self.tasks = {}

    def source(self, name, files):
        """dlddu/<name> 대상 레포를 main 브랜치로 만든다. 반환: owner/repo"""
        path = self.sources / "dlddu" / name
        path.mkdir(parents=True, exist_ok=True)
        if not (path / ".git").exists():
            git(path, "init", "-q", "-b", "main")
            git(path, "config", "user.email", "t@example.com")
            git(path, "config", "user.name", "t")
        for rel, content in files.items():
            f = path / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content)
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", "update")
        return f"dlddu/{name}"

    def tree(self, repository, sub):
        return git(self.sources / repository, "rev-parse", f"HEAD:{sub}")

    def model(self, mid, repository, *, as_is=None, to_be=None, observed_at="2026-10-20T00:00:00Z",
              check_policy=None, as_is_script=SRC_SCRIPT, to_be_script=TREE_SCRIPT):
        def side(script, version):
            return {"dataSource": {"type": "github", "repository": repository, "ref": "main"},
                    "versionScript": script, "lastObservedVersion": version, "lastObservedAt": observed_at}
        m = {"id": mid, "metadata": {"name": mid, "createdAt": "2026-10-01T00:00:00Z"},
             "definition": "# def", "asIs": side(as_is_script, as_is), "toBe": side(to_be_script, to_be)}
        if check_policy is not None:
            m["checkPolicy"] = check_policy
        self.models.append(m)
        return m

    def current(self, repository):
        """SRC/TREE 스크립트 기준 현재 버전(=변화 없음 상태)."""
        return f"src:{self.tree(repository, 'src')}", self.tree(repository, "docs")

    def task(self, mid, tid, status, recheck_after=None):
        t = {"id": tid, "toBeModelId": mid, "status": status, "createdAt": "2026-10-20T00:00:00Z"}
        if recheck_after is not None or status == "assessing":
            t["assessment"] = {"reason": "r", "recheckAfter": recheck_after}
        self.tasks.setdefault(mid, []).append(t)

    def write(self):
        (self.repo / "data" / "to-be-models.json").write_text(json.dumps(self.models))
        for mid, tasks in self.tasks.items():
            (self.repo / "data" / "reconciliation-tasks" / f"{mid}.json").write_text(json.dumps(tasks))

    def run(self, *extra):
        """main()을 돌려 (exit code, outputs dict, stdout) 반환."""
        self.write()
        out_file = self.tmp / "gh_output"
        out_file.write_text("")
        argv = ["--repo", str(self.repo), "--now", NOW, "--work-dir", str(self.tmp / "work"),
                "--repo-url-template", f"file://{self.sources}/{{repository}}",
                "--github-output", str(out_file), "--summary-file", str(self.tmp / "summary.md"), *extra]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = sdt.main(argv)
        outputs = dict(line.split("=", 1) for line in out_file.read_text().splitlines())
        return code, outputs, buf.getvalue()


class SelectDriftTargetTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = Fixture(Path(self._tmp.name))
        self.repo_a = self.fx.source("alpha", {"src/a.py": "a=1\n", "docs/a.md": "# a\n"})
        self.repo_b = self.fx.source("beta", {"src/b.py": "b=1\n", "docs/b.md": "# b\n"})

    def tearDown(self):
        self._tmp.cleanup()

    def unchanged(self, mid, repository, **kw):
        as_is, to_be = self.fx.current(repository)
        return self.fx.model(mid, repository, as_is=as_is, to_be=to_be, **kw)

    # ── 대상 없음 ──

    def test_no_target_when_versions_unchanged(self):
        self.unchanged("tbm_a", self.repo_a)
        self.unchanged("tbm_b", self.repo_b)
        code, out, stdout = self.fx.run()
        self.assertEqual(code, 0)
        self.assertEqual(out["found"], "false")
        self.assertEqual(out["target_id"], "")
        self.assertIn("2개 버전 변화 없음", stdout)

    def test_multiline_stored_version_is_unchanged(self):
        # 기존 레코드는 여러 줄 stdout을 통째로 저장한 경우가 있다(e2e-mock-policy 등).
        script = {"runtime": "bash", "code": "echo 'sites=1 files=1'\ngit rev-parse HEAD:docs\n"}
        _, to_be = self.fx.current(self.repo_a)
        self.fx.model("tbm_a", self.repo_a, as_is=f"sites=1 files=1\n{to_be}", to_be=to_be,
                      as_is_script=script)
        code, out, _ = self.fx.run()
        self.assertEqual((code, out["found"]), (0, "false"))

    def test_last_line_stored_version_is_unchanged(self):
        script = {"runtime": "bash", "code": "echo 'diagnostic'\ngit rev-parse HEAD:docs\n"}
        _, to_be = self.fx.current(self.repo_a)
        self.fx.model("tbm_a", self.repo_a, as_is=to_be, to_be=to_be, as_is_script=script)
        code, out, _ = self.fx.run()
        self.assertEqual((code, out["found"]), (0, "false"))

    # ── 버전 변화 ──

    def test_version_change_selects_model(self):
        self.unchanged("tbm_a", self.repo_a)
        as_is, _ = self.fx.current(self.repo_b)
        self.fx.model("tbm_b", self.repo_b, as_is=as_is, to_be="stale-tree")
        code, out, stdout = self.fx.run()
        self.assertEqual(code, 0)
        self.assertEqual(out, {"found": "true", "target_id": "tbm_b", "target_kind": "model",
                               "model_id": "tbm_b", "reason": "version_changed", "error_count": "0"})
        self.assertIn("바뀐 side: toBe", stdout)

    def test_never_observed_counts_as_changed(self):
        self.fx.model("tbm_a", self.repo_a, as_is=None, to_be=None, observed_at=None)
        code, out, _ = self.fx.run()
        self.assertEqual((code, out["target_id"]), (0, "tbm_a"))

    def test_oldest_observed_model_wins_and_sweep_stops(self):
        self.fx.model("tbm_new", self.repo_a, as_is="x", to_be="y", observed_at="2026-10-24T00:00:00Z")
        self.fx.model("tbm_old", self.repo_b, as_is="x", to_be="y", observed_at="2026-10-01T00:00:00Z")
        code, out, stdout = self.fx.run()
        self.assertEqual(out["target_id"], "tbm_old")
        self.assertIn("첫 변화에서 스윕을 멈춤", stdout)
        # 첫 변화에서 멈췄으므로 tbm_new 레포는 클론조차 하지 않는다.
        self.assertFalse((self.fx.tmp / "work" / "dlddu__alpha@main").exists())

    def test_full_sweep_reports_remaining_changes(self):
        self.fx.model("tbm_new", self.repo_a, as_is="x", to_be="y", observed_at="2026-10-24T00:00:00Z")
        self.fx.model("tbm_old", self.repo_b, as_is="x", to_be="y", observed_at="2026-10-01T00:00:00Z")
        code, out, stdout = self.fx.run("--full-sweep")
        self.assertEqual(out["target_id"], "tbm_old")
        self.assertIn("버전 변화 1건", stdout)
        self.assertIn("tbm_new", stdout)

    def test_does_not_write_to_repo(self):
        self.fx.model("tbm_a", self.repo_a, as_is="x", to_be="y")
        self.fx.write()
        before = (self.fx.repo / "data" / "to-be-models.json").read_text()
        self.fx.run()
        self.assertEqual((self.fx.repo / "data" / "to-be-models.json").read_text(), before)

    def test_python_runtime_reads_worktree(self):
        script = {"runtime": "python", "code": "import pathlib\nprint(pathlib.Path('src/a.py').read_text().strip())\n"}
        _, to_be = self.fx.current(self.repo_a)
        self.fx.model("tbm_a", self.repo_a, as_is="a=1", to_be=to_be, as_is_script=script)
        code, out, _ = self.fx.run()
        self.assertEqual((code, out["found"]), (0, "false"))

    # ── 제외 ──

    def test_disabled_model_is_skipped_without_running_scripts(self):
        boom = {"runtime": "bash", "code": "exit 7\n"}
        self.fx.model("tbm_off", self.repo_a, as_is="x", to_be="y", check_policy={"enabled": False},
                      as_is_script=boom, to_be_script=boom)
        code, out, stdout = self.fx.run()
        self.assertEqual((code, out["found"], out["error_count"]), (0, "false", "0"))
        self.assertIn("1개 모델: 감지 비활성", stdout)

    def test_model_with_claimed_or_parked_assessing_is_excluded(self):
        self.fx.model("tbm_a", self.repo_a, as_is="x", to_be="y")
        self.fx.task("tbm_a", "rct_20261025-0001", "assessing")  # 점유 중
        self.fx.model("tbm_b", self.repo_b, as_is="x", to_be="y")
        self.fx.task("tbm_b", "rct_20261025-0002", "assessing", recheck_after="2026-10-25T11:00:00Z")
        code, out, stdout = self.fx.run()
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertIn("다른 워커가 점유 중", stdout)
        self.assertIn("재확인 유예 중(2026-10-25T11:00:00Z 이후)", stdout)

    def test_later_stage_task_does_not_exclude_model(self):
        self.fx.model("tbm_a", self.repo_a, as_is="x", to_be="y")
        self.fx.task("tbm_a", "rct_20261020-0001", "action_required")
        self.fx.task("tbm_a", "rct_20261020-0002", "planned")
        code, out, _ = self.fx.run()
        self.assertEqual((out["target_id"], out["reason"]), ("tbm_a", "version_changed"))

    # ── 우선순위 ──

    def test_expired_recheck_beats_manual_and_version(self):
        self.fx.model("tbm_a", self.repo_a, as_is="x", to_be="y",
                      check_policy={"manualTriggerRequestedAt": "2026-10-25T09:00:00Z", "manualTriggerReason": "다시 봐줘"})
        self.fx.model("tbm_b", self.repo_b, as_is="x", to_be="y")
        self.fx.task("tbm_b", "rct_20261024-0003", "assessing", recheck_after="2026-10-25T09:59:00Z")
        code, out, _ = self.fx.run()
        self.assertEqual(out, {"found": "true", "target_id": "rct_20261024-0003", "target_kind": "task",
                               "model_id": "tbm_b", "reason": "recheck_expired", "error_count": "0"})

    def test_earliest_expired_recheck_first(self):
        self.fx.model("tbm_a", self.repo_a)
        self.fx.task("tbm_a", "rct_20261024-0001", "assessing", recheck_after="2026-10-25T09:30:00Z")
        self.fx.model("tbm_b", self.repo_b)
        self.fx.task("tbm_b", "rct_20261024-0002", "assessing", recheck_after="2026-10-25T08:00:00Z")
        code, out, stdout = self.fx.run()
        self.assertEqual(out["target_id"], "rct_20261024-0002")
        self.assertIn("재확인 만료 1건", stdout)

    def test_manual_trigger_beats_version_and_oldest_request_first(self):
        self.unchanged("tbm_a", self.repo_a,
                       check_policy={"manualTriggerRequestedAt": "2026-10-25T09:00:00Z", "manualTriggerReason": "늦은 요청"})
        self.unchanged("tbm_b", self.repo_b,
                       check_policy={"manualTriggerRequestedAt": "2026-10-25T08:00:00Z", "manualTriggerReason": "이른 요청"})
        self.fx.model("tbm_c", self.repo_a, as_is="x", to_be="y")
        code, out, stdout = self.fx.run()
        self.assertEqual((out["target_id"], out["reason"]), ("tbm_b", "manual_trigger"))
        self.assertIn("이른 요청", stdout)

    def test_manual_trigger_ignored_on_disabled_model(self):
        self.unchanged("tbm_a", self.repo_a, check_policy={
            "enabled": False, "manualTriggerRequestedAt": "2026-10-25T09:00:00Z", "manualTriggerReason": "r"})
        code, out, _ = self.fx.run()
        self.assertEqual(out["found"], "false")

    def test_manual_trigger_without_reason_is_reported_and_skipped(self):
        self.unchanged("tbm_a", self.repo_a, check_policy={"manualTriggerRequestedAt": "2026-10-25T09:00:00Z",
                                                           "manualTriggerReason": ""})
        code, out, stdout = self.fx.run()
        # 깨진 요청이라 대상 없음으로 단정하지 않는다.
        self.assertEqual((code, out["found"], out["error_count"]), (1, "false", "1"))
        self.assertIn("manualTriggerReason이 비어 있음", stdout)

    # ── 오류 처리 ──

    def test_script_failure_fails_run_when_nothing_selected(self):
        self.fx.model("tbm_a", self.repo_a, as_is="x", to_be="y",
                      as_is_script={"runtime": "bash", "code": "echo nope >&2; exit 3\n"})
        code, out, stdout = self.fx.run()
        self.assertEqual((code, out["found"], out["error_count"]), (1, "false", "1"))
        self.assertIn("::warning::tbm_a: versionScript 종료 코드 3: nope", stdout)

    def test_script_failure_on_one_model_does_not_block_another(self):
        self.fx.model("tbm_bad", self.repo_a, as_is="x", to_be="y", observed_at="2026-10-01T00:00:00Z",
                      as_is_script={"runtime": "bash", "code": "exit 1\n"})
        self.fx.model("tbm_ok", self.repo_b, as_is="x", to_be="y")
        code, out, _ = self.fx.run()
        self.assertEqual((code, out["target_id"], out["error_count"]), (0, "tbm_ok", "1"))

    def test_clone_failure_is_reported_per_model(self):
        self.fx.model("tbm_gone", "dlddu/missing", as_is="x", to_be="y")
        code, out, stdout = self.fx.run()
        self.assertEqual(code, 1)
        self.assertIn("clone dlddu/missing@main 실패", stdout)

    def test_script_timeout(self):
        slow = {"runtime": "bash", "code": "sleep 5\n", "timeoutSeconds": 1}
        self.fx.model("tbm_a", self.repo_a, as_is="x", to_be="y", as_is_script=slow)
        code, _, stdout = self.fx.run()
        self.assertEqual(code, 1)
        self.assertIn("1s 안에 끝나지 않음", stdout)

    def test_scripts_do_not_see_tokens(self):
        leak = {"runtime": "bash", "code": "echo \"tok=${SOURCE_GITHUB_TOKEN:-none}\"\n"}
        _, to_be = self.fx.current(self.repo_a)
        self.fx.model("tbm_a", self.repo_a, as_is="tok=none", to_be=to_be, as_is_script=leak)
        import os
        os.environ["SOURCE_GITHUB_TOKEN"] = "secret-value"
        try:
            code, out, stdout = self.fx.run()
        finally:
            del os.environ["SOURCE_GITHUB_TOKEN"]
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertNotIn("secret-value", stdout)

    def test_scripts_do_not_inherit_runner_env(self):
        # 러너가 GITHUB_ENV로 내보낸 OUT을 스크립트가 같은 이름의 셸 변수로 이어 써도 지문이 오염되지 않는다.
        script = {"runtime": "bash", "code": 'OUT+="hit"; printf "%s|%s\\n" "$OUT" "${SKILL_DIR:-none}"\n'}
        _, to_be = self.fx.current(self.repo_a)
        self.fx.model("tbm_a", self.repo_a, as_is="hit|none", to_be=to_be, as_is_script=script)
        import os
        os.environ.update(OUT="/home/runner/work/_temp/out", SKILL_DIR="/runner/skill")
        try:
            code, out, stdout = self.fx.run()
        finally:
            del os.environ["OUT"], os.environ["SKILL_DIR"]
        self.assertEqual((code, out["found"]), (0, "false"), stdout)

    def test_script_env_allowlist(self):
        env = sdt.script_env({"PATH": "/bin", "HOME": "/h", "LC_ALL": "C", "OUT": "/o", "GITHUB_TOKEN": "t",
                              "MCP_LOCAL_URL": "http://x", "TZ": "UTC"})
        self.assertEqual(env, {"PATH": "/bin", "HOME": "/h", "LC_ALL": "C", "TZ": "UTC"})

    # ── 지목 ──

    def test_explicit_model_skips_sweep(self):
        boom = {"runtime": "bash", "code": "exit 9\n"}
        self.fx.model("tbm_a", self.repo_a, as_is="x", to_be="y", as_is_script=boom, to_be_script=boom)
        self.fx.model("tbm_b", self.repo_b, as_is="x", to_be="y")
        code, out, _ = self.fx.run("--target", "tbm_a")
        self.assertEqual(out, {"found": "true", "target_id": "tbm_a", "target_kind": "model",
                               "model_id": "tbm_a", "reason": "explicit", "error_count": "0"})

    def test_explicit_disabled_model_not_selected(self):
        self.fx.model("tbm_a", self.repo_a, check_policy={"enabled": False})
        code, out, stdout = self.fx.run("--target", "tbm_a")
        self.assertEqual((code, out["found"]), (0, "false"))
        self.assertIn("감지 비활성", stdout)

    def test_explicit_model_with_open_assessing(self):
        self.fx.model("tbm_a", self.repo_a)
        self.fx.task("tbm_a", "rct_20261025-0001", "assessing")
        _, out, _ = self.fx.run("--target", "tbm_a")
        self.assertEqual(out["found"], "false")

    def test_explicit_model_with_expired_recheck_resumes_task(self):
        self.fx.model("tbm_a", self.repo_a)
        self.fx.task("tbm_a", "rct_20261024-0001", "assessing", recheck_after="2026-10-25T09:00:00Z")
        _, out, _ = self.fx.run("--target", "tbm_a")
        self.assertEqual((out["target_id"], out["reason"]), ("rct_20261024-0001", "recheck_expired"))

    def test_explicit_task(self):
        self.fx.model("tbm_a", self.repo_a)
        self.fx.task("tbm_a", "rct_20261025-0001", "assessing")
        self.fx.task("tbm_a", "rct_20261020-0001", "planned")
        _, out, _ = self.fx.run("--target", "rct_20261025-0001")
        self.assertEqual((out["target_id"], out["target_kind"], out["model_id"]),
                         ("rct_20261025-0001", "task", "tbm_a"))
        _, out, stdout = self.fx.run("--target", "rct_20261020-0001")
        self.assertEqual(out["found"], "false")
        self.assertIn("status=planned", stdout)

    def test_explicit_unknown_target_errors(self):
        self.fx.model("tbm_a", self.repo_a)
        self.assertEqual(self.fx.run("--target", "tbm_nope")[0], 2)
        self.assertEqual(self.fx.run("--target", "rct_20990101-0001")[0], 2)
        self.assertEqual(self.fx.run("--target", "garbage")[0], 2)


class HelpersTest(unittest.TestCase):
    def test_parse_time_variants(self):
        a = sdt.parse_time("2026-09-15T10:14:23.752249Z")
        b = sdt.parse_time("2026-09-15T19:14:23.752249+09:00")
        self.assertEqual(a, b)
        self.assertIsNone(sdt.parse_time(None))

    def test_version_matches(self):
        self.assertTrue(sdt.version_matches("abc", "abc"))
        self.assertTrue(sdt.version_matches("x=1\nabc", "x=1\nabc"))
        self.assertTrue(sdt.version_matches("abc", "x=1\nabc"))
        self.assertFalse(sdt.version_matches("abd", "abc"))
        self.assertFalse(sdt.version_matches(None, "abc"))

    def test_runs_against_real_repo_data(self):
        """레포의 실제 data/는 파싱·분류 단계에서 깨지지 않아야 한다(버전 계산 전까지)."""
        models, tasks = sdt.load_state(ROOT)
        now = sdt.parse_time(NOW)
        for m in models:
            sdt.oldest_observed(m)
            sdt.open_assessing(tasks[m["id"]], now)


if __name__ == "__main__":
    unittest.main()
