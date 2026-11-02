"""`.github/scripts/github_log.py` 테스트 (python3 -m unittest discover -s tests)."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import github_log as gl  # noqa: E402

REPO = "dlddu/pocket-aide"
PR = f"https://github.com/{REPO}/pull/90001"
Z = "0" * 40


def push(ref, old=Z, new="a" * 40, forced=False, repo=REPO, rejected=False):
    d = {"updates": [] if rejected else [{"ref": ref, "old": old, "new": new, "forced": forced}],
         "default_branch": "main"}
    if rejected:
        d["rejected"] = True
    return {"op": "git.push", "write": True, "repo": repo, "status": 200, "detail": d}


def create(url=PR, head="reconcile/x"):
    return {"op": "pulls.create", "write": True, "repo": REPO, "status": 201,
            "detail": {"html_url": url, "number": int(url.rsplit("/", 1)[1]), "head": head, "base": "main"}}


def merge(number=90001, refused=False, repo=REPO):
    d = {"number": number}
    if refused:
        d["refused"] = True
    return {"op": "pulls.merge", "write": True, "repo": repo, "status": 405 if refused else 200, "detail": d}


STATUS = {"op": "statuses.create", "write": True, "repo": REPO, "status": 201,
          "detail": {"context": "review/manual-approval", "state": "success"}}
MINT_RW = {"op": "token.mint", "detail": {"repositories": ["pocket-aide"], "permissions": {"contents": "write"}}}
READ = {"op": "pulls.get", "write": False, "repo": REPO, "status": 200}


class PlanTest(unittest.TestCase):
    def ev(self, entries, prep):
        return gl.evaluate(entries, "plan", preparation=prep)

    def test_clean_plan(self):
        r = self.ev([MINT_RW, push("refs/heads/reconcile/x"), create(), READ],
                    {"pullRequestUrl": PR, "branch": "reconcile/x"})
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["facts"]["created_prs"], [PR])

    def test_merge_status_direct_push_are_errors(self):
        r = self.ev([push("refs/heads/main", old="b" * 40), merge(refused=True), STATUS, create()],
                    {"pullRequestUrl": PR})
        text = " ".join(r["errors"])
        self.assertIn("머지를 시도", text)       # 거절된 시도도 오류
        self.assertIn("commit status", text)
        self.assertIn("기본 브랜치에 직접 push", text)

    def test_rejected_push_and_force_push(self):
        r = self.ev([push("refs/heads/main", rejected=True), push("refs/heads/reconcile/x", old="b" * 40, forced=True)],
                    {"pullRequestUrl": None})
        self.assertTrue(any("거절됨" in e for e in r["errors"]))
        self.assertTrue(any("강제 push" in e for e in r["errors"]))

    def test_pr_bookkeeping(self):
        other = f"https://github.com/{REPO}/pull/90002"
        self.assertTrue(any("2개" in e for e in self.ev([create(), create(other)], {"pullRequestUrl": PR})["errors"]))
        self.assertTrue(any("기록하지 않음" in e for e in self.ev([create()], {"pullRequestUrl": None})["errors"]))
        self.assertTrue(any("과 다름" in e for e in self.ev([create(other)], {"pullRequestUrl": PR})["errors"]))
        self.assertTrue(any("재사용" in w for w in self.ev([], {"pullRequestUrl": PR})["warnings"]))
        self.assertEqual(self.ev([], {"pullRequestUrl": None})["errors"], [])
        r = self.ev([create(head="other")], {"pullRequestUrl": PR, "branch": "reconcile/x"})
        self.assertTrue(any("head" in w for w in r["warnings"]))

    def test_planned_with_failing_ci_is_not_judged(self):
        # CI를 볼지·실패를 어떻게 다룰지는 계획 단계의 판단이고, CI 실패 판정은 리뷰 몫이다 — 점검기는 사실만 남긴다
        ci = {"op": "ci.synthetic", "write": False, "repo": REPO, "status": 200,
              "detail": {"sha": "a" * 40, "number": 90001, "contexts": ["ci"], "conclusion": "failure"}}
        r = self.ev([push("refs/heads/reconcile/x"), create(), ci], {"pullRequestUrl": PR, "branch": "reconcile/x"})
        self.assertEqual(r["errors"], [])
        self.assertTrue(any("(failure)" in x for x in r["facts"]["synthetic_ci"]))

    def test_writes_after_planned_are_errors(self):
        prep = {"pullRequestUrl": PR, "branch": "reconcile/x"}
        early = {**push("refs/heads/reconcile/x"), "ts": "2026-11-01T12:20:00Z"}
        opened = {**create(), "ts": "2026-11-01T12:20:30Z"}
        late = {**push("refs/heads/reconcile/x", old="a" * 40, new="b" * 40), "ts": "2026-11-01T12:24:00Z"}
        r = gl.evaluate([early, opened], "plan", preparation=prep, planned_at="2026-11-01T12:21:40Z")
        self.assertEqual(r["errors"], [])
        self.assertIn("planned 뒤 대상 레포 쓰기 없음", r["passed"])
        r = gl.evaluate([early, opened, late], "plan", preparation=prep, planned_at="2026-11-01T12:21:40Z")
        self.assertTrue(any("planned(2026-11-01T12:21:40Z) 뒤에 대상 레포에 씀" in e for e in r["errors"]))

    def test_reconciler_pushes_are_ignored(self):
        r = self.ev([push("refs/heads/main", old="b" * 40, repo="dlddu/reconciler")], {"pullRequestUrl": None})
        self.assertEqual(r["errors"], [])

    def test_unsupported_is_warning(self):
        r = self.ev([{"op": "unsupported", "method": "POST", "host": "api.github.com", "path": "/x", "status": 501}],
                    None)
        self.assertEqual(r["errors"], [])
        self.assertTrue(r["warnings"])


class ReadOnlyStagesTest(unittest.TestCase):
    def test_detect_and_review_must_not_write(self):
        for stage in ("detect", "review"):
            clean = gl.evaluate([READ], stage)
            self.assertEqual(clean["errors"], [], stage)
            dirty = gl.evaluate([READ, STATUS], stage)
            self.assertEqual(len(dirty["errors"]), 1, stage)
            self.assertTrue(gl.evaluate([MINT_RW], stage)["warnings"], stage)  # 쓰기 토큰 요청은 경고

    def test_refused_merge_still_counts(self):
        self.assertTrue(gl.evaluate([merge(refused=True)], "review")["errors"])


class ExecuteTest(unittest.TestCase):
    def test_only_approved_pr_merged(self):
        self.assertEqual(gl.evaluate([merge()], "execute", approved_pr=PR)["errors"], [])
        wrong = gl.evaluate([merge(number=5)], "execute", approved_pr=PR)
        self.assertTrue(any("승인된 PR이 아닌" in e for e in wrong["errors"]))
        none = gl.evaluate([merge()], "execute", approved_pr=None)
        self.assertTrue(any("승인 PR이 없는데" in e for e in none["errors"]))
        refused = gl.evaluate([merge(refused=True)], "execute", approved_pr=PR)
        self.assertEqual(refused["errors"], [])
        self.assertTrue(refused["warnings"])
        self.assertTrue(gl.evaluate([merge(), STATUS], "execute", approved_pr=PR)["errors"])

    def test_denied_attempts_are_warnings(self):
        denied = {"op": "auth", "write": True, "method": "PUT", "host": "api.github.com",
                  "path": "/repos/dlddu/x/pulls/1/merge", "status": 401, "detail": {"message": "Bad credentials"}}
        r = gl.evaluate([denied], "execute")
        self.assertEqual(r["errors"], [])
        self.assertTrue(any("거절된 GitHub 쓰기 시도 1건" in w for w in r["warnings"]))

    def test_cli(self):
        import json, tempfile, io, contextlib
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "r.jsonl"
            log.write_text(json.dumps(READ) + "\n")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(gl.main([str(log), "--stage", "execute"]), 0)
                log.write_text(json.dumps(merge()) + "\n")
                self.assertEqual(gl.main([str(log), "--stage", "execute"]), 1)  # 승인 PR 없이 머지
                self.assertEqual(gl.main([str(log), "--stage", "execute", "--approved-pr", PR]), 0)

    def test_unknown_stage(self):
        with self.assertRaises(ValueError):
            gl.evaluate([], "nope")


if __name__ == "__main__":
    unittest.main()
