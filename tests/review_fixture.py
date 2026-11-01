"""리뷰 단계 러너 스크립트 테스트용 공용 픽스처(claim_review_target · replay_review_task · check_review_result).

실제 schemas/를 복사한 임시 git 레포(reconciler checkout)에 로컬 bare origin을 붙인다 — 네트워크 없음.
"""

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MID = "tbm_demo"
TID = "rct_20261025-0001"
PR = "https://github.com/dlddu/demo/pull/7"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def model(mid=MID, enabled=True):
    side = {"dataSource": {"type": "github", "repository": "dlddu/demo", "ref": "main"},
            "versionScript": {"runtime": "bash", "code": "git rev-parse HEAD\n"}}
    m = {"id": mid, "metadata": {"name": mid, "createdAt": "2026-10-01T00:00:00Z"},
         "definition": "# def", "asIs": dict(side), "toBe": dict(side)}
    if not enabled:
        m["checkPolicy"] = {"enabled": False}
    return m


def planned_task(tid=TID, mid=MID, status="planned", pr=PR, updated="2026-10-25T01:00:00Z", review=None):
    attempt = {
        "plan": {"summary": "주석 제거", "riskLevel": "low", "plannedAt": "2026-10-25T00:30:00Z",
                 "steps": [{"seq": 1, "action": "주석 3줄 제거", "expectedOutcome": "판정기 통과"}],
                 "executionGuide": "1. PR 머지\n2. 검증: 판정기\n3. 롤백: revert"},
        "preparation": {"repository": "dlddu/demo", "branch": "reconcile/x", "pullRequestUrl": pr,
                        "preparedAt": "2026-10-25T01:00:00Z", "notes": "로컬 테스트 통과"},
    }
    if review:
        attempt["review"] = review
    return {"id": tid, "toBeModelId": mid, "status": status, "createdAt": "2026-10-25T00:00:00Z",
            "updatedAt": updated,
            "trigger": {"source": "version_change", "detectedAt": "2026-10-25T00:00:00Z",
                        "asIs": {"previousVersion": "v1", "currentVersion": "v2"}},
            "stateSummary": {"asIs": "주석 3줄", "toBe": "주석 없음", "gap": "주석 3줄 남음"},
            "assessment": {"reason": "작업 필요", "assessedAt": "2026-10-25T00:10:00Z"},
            "attempts": [attempt]}


class ReviewRepo:
    """reconciler checkout(git) + bare origin. tasks: {model_id: [task, ...]}."""

    def __init__(self, tmp: Path, tasks=None, models=None, message="base"):
        self.tmp = tmp
        self.path = tmp / "reconciler"
        (self.path / "data" / "reconciliation-tasks").mkdir(parents=True)
        shutil.copytree(ROOT / "schemas", self.path / "schemas")
        git(self.path, "init", "-q", "-b", "main")
        git(self.path, "config", "user.email", "t@example.com")
        git(self.path, "config", "user.name", "t")
        self.models = models or [model(), model("tbm_other")]
        self.write(tasks if tasks is not None else {MID: [planned_task()]})
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", message)
        self.origin = tmp / "origin.git"
        git(tmp, "clone", "-q", "--bare", str(self.path), str(self.origin))
        git(self.path, "remote", "add", "origin", str(self.origin))
        git(self.path, "fetch", "-q", "origin")
        git(self.path, "branch", "-q", "-u", "origin/main")

    def write(self, tasks, models=None):
        (self.path / "data" / "to-be-models.json").write_text(
            json.dumps(models or self.models, ensure_ascii=False, indent=2) + "\n")
        for mid, items in tasks.items():
            (self.path / "data" / "reconciliation-tasks" / f"{mid}.json").write_text(
                json.dumps(items, ensure_ascii=False, indent=2) + "\n")

    def commit(self, tasks, msg, models=None):
        self.write(tasks, models)
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", msg)
        return git(self.path, "rev-parse", "HEAD")

    def tasks(self, mid=MID, rev=None):
        if rev:
            return json.loads(git(self.path, "show", f"{rev}:data/reconciliation-tasks/{mid}.json"))
        return json.loads((self.path / "data" / "reconciliation-tasks" / f"{mid}.json").read_text())

    def other_worker(self, name="other"):
        path = self.tmp / name
        if not path.exists():
            git(self.tmp, "clone", "-q", str(self.origin), str(path))
            git(path, "config", "user.email", "w@example.com")
            git(path, "config", "user.name", "w")
        git(path, "pull", "-q", "--rebase")
        return path
