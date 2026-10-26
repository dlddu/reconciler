"""`.github/scripts/check_detector_result.py` 테스트 (python3 -m unittest discover -s tests).

실제 schemas/를 복사한 임시 git 레포에 "러너 점유 커밋"을 만들고(기준), 스킬이 했을 법한 변경을
커밋한 뒤 점검기가 계약 위반을 잡는지 본다. jsonschema가 필요하다.
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

MID, TID = "tbm_demo", "rct_20261025-0001"
SCRIPT = {"runtime": "bash", "code": "git rev-parse HEAD\n"}


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def model(mid=MID, as_is="v2"):
    side = lambda v: {"dataSource": {"type": "github", "repository": "dlddu/demo", "ref": "main"},  # noqa: E731
                      "versionScript": SCRIPT, "lastObservedVersion": v, "lastObservedAt": "2026-10-25T00:00:00Z"}
    return {"id": mid, "metadata": {"name": mid, "createdAt": "2026-10-01T00:00:00Z"},
            "definition": "# def", "asIs": side(as_is), "toBe": side("t1")}


def claimed_task(tid=TID):
    return {"id": tid, "toBeModelId": MID, "status": "assessing", "createdAt": "2026-10-25T00:00:00Z",
            "trigger": {"source": "version_change", "detectedAt": "2026-10-25T00:00:00Z",
                        "asIs": {"previousVersion": "v1", "currentVersion": "v2"}}}


def judged(status="action_required", **extra):
    t = claimed_task()
    t.update(status=status, updatedAt="2026-10-25T00:05:00Z",
             stateSummary={"asIs": "실제 상태", "toBe": "목표 상태", "gap": "차이", "summarizedAt": "2026-10-25T00:03:00Z"},
             assessment={"reason": "근거", "assessedAt": "2026-10-25T00:05:00Z"})
    t.update(extra)
    return t


class Repo:
    """기준 = 러너의 점유 커밋(모델 기준선 갱신 + assessing task)."""

    def __init__(self, tmp: Path, tasks=None):
        self.path = tmp / "reconciler"
        (self.path / "data" / "reconciliation-tasks").mkdir(parents=True)
        shutil.copytree(ROOT / "schemas", self.path / "schemas")
        git(self.path, "init", "-q", "-b", "main")
        git(self.path, "config", "user.email", "t@example.com")
        git(self.path, "config", "user.name", "t")
        self.models = [model(), model("tbm_other")]
        self.write(tasks or {MID: [claimed_task()]})
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", f"detect({MID}/{TID}): claim")
        self.base = git(self.path, "rev-parse", "HEAD")

    def write(self, tasks, models=None):
        (self.path / "data" / "to-be-models.json").write_text(json.dumps(models or self.models, ensure_ascii=False, indent=2))
        for mid, items in tasks.items():
            (self.path / "data" / "reconciliation-tasks" / f"{mid}.json").write_text(
                json.dumps(items, ensure_ascii=False, indent=2))

    def commit(self, tasks, msg, models=None):
        self.write(tasks, models)
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", msg)

    def check(self, subject=None):
        return cdr.check(self.path, self.base, MID, TID, subject)


class CheckDetectorResultTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_summarize_then_assess_passes(self):
        repo = Repo(self.tmp)
        half = claimed_task()
        half["stateSummary"] = judged()["stateSummary"]
        repo.commit({MID: [half]}, f"detect({MID}/{TID}): summarize state")
        repo.commit({MID: [judged()]}, f"detect({MID}/{TID}): assess action")
        res = repo.check()
        self.assertEqual(res.errors, [])
        self.assertEqual(res.facts["status"], "action_required")
        self.assertEqual(len(res.facts["commits"]), 2)

    def test_parked_requires_recheck_after(self):
        repo = Repo(self.tmp)
        repo.commit({MID: [judged("assessing")]}, f"detect({MID}/{TID}): park")
        self.assertTrue(any("recheckAfter" in e for e in repo.check().errors))
        repo2 = Repo(self.tmp / "b")
        t = judged("assessing")
        t["assessment"]["recheckAfter"] = "2026-10-25T03:00:00Z"
        repo2.commit({MID: [t]}, f"detect({MID}/{TID}): park")
        self.assertEqual(repo2.check().errors, [])

    def test_touching_models_or_schema_after_claim_is_error(self):
        repo = Repo(self.tmp)
        models = copy.deepcopy(repo.models)
        models[0]["asIs"]["lastObservedVersion"] = "v3"
        (repo.path / "schemas" / "reconciliation-task.schema.json").write_text(
            (ROOT / "schemas" / "reconciliation-task.schema.json").read_text() + "\n")
        repo.commit({MID: [judged()]}, f"detect({MID}/{TID}): assess", models=models)
        joined = "\n".join(repo.check().errors)
        self.assertIn("data/to-be-models.json", joined)
        self.assertIn("schemas/reconciliation-task.schema.json", joined)

    def test_rewriting_claim_record_is_error(self):
        repo = Repo(self.tmp)
        t = judged()
        t["trigger"] = {"source": "manual", "detectedAt": "2026-10-25T00:00:00Z", "reason": "바꿈"}
        repo.commit({MID: [t]}, f"detect({MID}/{TID}): assess")
        self.assertTrue(any("점유 기록을 고침: trigger" in e for e in repo.check().errors))

    def test_new_task_or_other_task_is_error(self):
        repo = Repo(self.tmp)
        repo.commit({MID: [judged(), judged(id="rct_20261025-0002")]}, f"detect({MID}/{TID}): assess")
        self.assertTrue(any("한 건만" in e for e in repo.check().errors))

    def test_bad_commit_message_and_schema_violation(self):
        repo = Repo(self.tmp)
        repo.commit({MID: [judged(unknownField=1)]}, "update data")
        joined = "\n".join(repo.check().errors)
        self.assertIn("커밋 규약 위반", joined)
        self.assertIn("task 스키마 위반", joined)

    def test_commit_for_other_task_is_error(self):
        repo = Repo(self.tmp)
        repo.commit({MID: [judged()]}, f"detect({MID}/rct_20261025-0009): assess")
        self.assertTrue(any("다른 대상" in e for e in repo.check().errors))

    def test_no_commits_is_error(self):
        repo = Repo(self.tmp)
        self.assertTrue(any("새 커밋이 없음" in e for e in repo.check().errors))

    def test_still_claimed_without_judgement_is_error(self):
        repo = Repo(self.tmp)
        t = claimed_task()
        t["updatedAt"] = "2026-10-25T00:01:00Z"
        repo.commit({MID: [t]}, f"detect({MID}/{TID}): touch")
        joined = "\n".join(repo.check().errors)
        self.assertIn("recheckAfter", joined)
        self.assertIn("assessment.reason", joined)

    def test_rebased_claim_commit_is_found_by_subject(self):
        repo = Repo(self.tmp)
        # 스킬의 pull --rebase로 점유 커밋이 새 해시로 다시 쓰인 상황: 원격의 다른 모델 커밋 위로 재적용.
        # base(원래 점유 커밋)는 새 HEAD 이력에 없다.
        other = repo.path / "data" / "reconciliation-tasks" / "tbm_other.json"
        # 새 이력: base 부모 없이 '다른 모델 커밋' → '같은 제목의 점유 커밋'
        git(repo.path, "checkout", "-q", "--orphan", "rebased")
        git(repo.path, "rm", "-rq", "--cached", ".")
        other.write_text("[]\n")
        git(repo.path, "add", "data/reconciliation-tasks/tbm_other.json", "schemas", "data/to-be-models.json")
        git(repo.path, "commit", "-q", "-m", "plan(tbm_other/x): upstream")
        repo.commit({MID: [claimed_task()]}, f"detect({MID}/{TID}): claim")
        repo.commit({MID: [judged()]}, f"detect({MID}/{TID}): assess")
        with self.assertRaises(RuntimeError):
            repo.check()
        res = repo.check(subject=f"detect({MID}/{TID}): claim")
        self.assertEqual(res.errors, [])
        self.assertTrue(any("rebase" in w for w in res.warnings))

    # ── 실제 모드: 점유가 push된 뒤 다른 작업자가 기본 브랜치에 커밋하고, 스킬이 pull --rebase로 그 위에 쌓는다 ──

    def upstream(self, repo, files, msg="docs(drift-detector): 다른 세션의 수정"):
        """repo의 점유 커밋을 bare 원격에 push하고, 다른 클론에서 files를 바꾼 커밋을 원격에 올린다."""
        remote = self.tmp / "remote.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(remote))
        git(repo.path, "remote", "add", "origin", str(remote))
        git(repo.path, "push", "-q", "origin", "main")
        other = self.tmp / "other"
        git(self.tmp, "clone", "-q", str(remote), str(other))
        for rel, text in files.items():
            (other / rel).parent.mkdir(parents=True, exist_ok=True)
            (other / rel).write_text(text)
        git(other, "add", "-A")
        git(other, "-c", "user.name=o", "-c", "user.email=o@example.com", "commit", "-q", "-m", msg)
        git(other, "push", "-q", "origin", "main")

    def test_upstream_commit_pulled_in_by_rebase_is_excluded(self):
        repo = Repo(self.tmp)
        self.upstream(repo, {".github/workflows/x.yml": "on: push\n"})
        repo.commit({MID: [judged()]}, f"detect({MID}/{TID}): assess")
        git(repo.path, "pull", "-q", "--rebase", "origin", "main")
        res = repo.check(subject=f"detect({MID}/{TID}): claim")
        self.assertEqual(res.errors, [])
        self.assertEqual(res.facts["commits"], [f"detect({MID}/{TID}): assess"])
        self.assertEqual(res.facts["foreign_commits"], ["docs(drift-detector): 다른 세션의 수정"])
        self.assertTrue(any("다른 작업자의 커밋 1개" in w for w in res.warnings))
        self.assertEqual(res.facts["changed_files"], [f"data/reconciliation-tasks/{MID}.json"])

    def test_upstream_change_to_other_task_in_same_file_is_not_counted(self):
        repo = Repo(self.tmp, tasks={MID: [claimed_task(), judged(id="rct_20261020-0001")]})
        other_task = judged(id="rct_20261020-0001", status="planning")
        self.upstream(repo, {f"data/reconciliation-tasks/{MID}.json":
                             json.dumps([claimed_task(), other_task], ensure_ascii=False, indent=2)},
                      msg=f"plan({MID}/rct_20261020-0001): claim")
        repo.commit({MID: [judged(), judged(id="rct_20261020-0001")]}, f"detect({MID}/{TID}): assess")
        git(repo.path, "pull", "-q", "--rebase", "origin", "main")
        res = repo.check(subject=f"detect({MID}/{TID}): claim")
        self.assertEqual(res.errors, [])
        self.assertEqual(res.facts["touched_tasks"], [TID])

    def test_own_bad_commit_still_caught_when_upstream_commit_present(self):
        repo = Repo(self.tmp)
        self.upstream(repo, {"README.md": "x\n"})
        models = copy.deepcopy(repo.models)
        models[0]["asIs"]["lastObservedVersion"] = "v3"
        repo.commit({MID: [judged()]}, "update data", models=models)
        git(repo.path, "pull", "-q", "--rebase", "origin", "main")
        joined = "\n".join(repo.check(subject=f"detect({MID}/{TID}): claim").errors)
        self.assertIn("커밋 규약 위반", joined)
        self.assertIn("data/to-be-models.json", joined)
        self.assertNotIn("README.md", joined)

    def test_without_reflog_all_commits_count_as_skill_commits(self):
        repo = Repo(self.tmp)
        self.upstream(repo, {"README.md": "x\n"})
        repo.commit({MID: [judged()]}, f"detect({MID}/{TID}): assess")
        git(repo.path, "pull", "-q", "--rebase", "origin", "main")
        git(repo.path, "reflog", "expire", "--expire=all", "--all")
        res = repo.check(subject=f"detect({MID}/{TID}): claim")
        self.assertTrue(any("reflog" in w for w in res.warnings))
        self.assertTrue(any("README.md" in e for e in res.errors))

    def test_patch_includes_uncommitted(self):
        repo = Repo(self.tmp)
        repo.write({MID: [judged()]})
        patch = self.tmp / "r.patch"
        rc = cdr.main(["--repo", str(repo.path), "--base", repo.base, "--model-id", MID, "--task-id", TID,
                       "--patch", str(patch)])
        self.assertEqual(rc, 1)  # 커밋이 없으니 실패
        self.assertIn(f"{MID}.json", patch.read_text())


if __name__ == "__main__":
    unittest.main()
