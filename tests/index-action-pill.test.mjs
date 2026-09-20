import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const schema = JSON.parse(
  readFileSync(new URL("../schemas/reconciliation-task.schema.json", import.meta.url), "utf8")
);
const SCHEMA_STATUSES = schema.properties.status.enum;

const doneMatch = html.match(/  var DONE_STATUSES = \[[^\]]*\];\n/);
assert.ok(doneMatch, "DONE_STATUSES must exist in index.html");

// actionPillHtml delegates the "조치 필요" judgement to taskNeedsAction — the task list
// filter reads the same function, so both must agree by construction.
const needsMatch = html.match(/  function taskNeedsAction\(t\) \{[\s\S]*?\n  \}\n/);
assert.ok(needsMatch, "taskNeedsAction must exist in index.html");

const pillMatch = html.match(/  function actionPillHtml\(t\) \{[\s\S]*?\n  \}\n/);
assert.ok(pillMatch, "actionPillHtml must exist in index.html");

const ctx = vm.createContext({});
vm.runInContext(doneMatch[0] + needsMatch[0] + pillMatch[0], ctx);

const DONE = vm.runInContext("DONE_STATUSES", ctx);
const actionPillHtml = vm.runInContext("actionPillHtml", ctx);

function pill(status, assessment) {
  const t = { id: "x", status };
  if (assessment !== undefined) t.assessment = assessment;
  return actionPillHtml(t);
}

test("terminal tasks carry no pill", () => {
  for (const status of DONE) {
    assert.equal(pill(status), "", `${status} must not show a pill`);
    assert.equal(pill(status, { reason: "r" }), "", `${status} must not show a pill`);
  }
});

test("succeeded is the case that motivated hiding it", () => {
  assert.equal(pill("succeeded"), "");
  assert.match(pill("executing"), /조치 필요/);
});

test("rework entry points keep the pill", () => {
  // failed / review_rejected are picked back up by the planner, so they are not done
  for (const status of ["failed", "review_rejected"]) {
    assert.equal(DONE.includes(status), false, `${status} must not be a terminal status`);
    assert.match(pill(status), /조치 필요/);
  }
});

test("an assessing task reads 조치 필요 with a 판단 전 tooltip", () => {
  // no judgement yet is not a verdict of 조치 불필요 — it is a task nobody has resolved
  const open = pill("assessing");
  assert.match(open, /조치 필요</);
  assert.match(open, /title="아직 판단 전/);
  // terminal wins over it: a task cancelled before assessment carries no pill at all
  assert.equal(pill("cancelled"), "");
});

test("a parked assessing task says when it will be re-checked", () => {
  const parked = pill("assessing", { reason: "r", recheckAfter: "2026-09-21T09:00:00Z" });
  assert.match(parked, /조치 필요</);
  assert.match(parked, /title="재확인 대기 — 2026-09-21T09:00:00Z/);
});

test("a judged 조치 필요 carries no tooltip", () => {
  assert.doesNotMatch(pill("action_required", { reason: "r" }), /title=/);
});

test("every schema status shows a pill exactly when it is not terminal", () => {
  for (const status of SCHEMA_STATUSES) {
    const shown = pill(status) !== "";
    assert.equal(
      shown,
      !DONE.includes(status),
      `${status} should ${DONE.includes(status) ? "not " : ""}show the pill`
    );
  }
});

test("the pill never reads 조치 불필요 — that verdict is the no_action_needed status", () => {
  for (const status of SCHEMA_STATUSES) {
    assert.doesNotMatch(pill(status, { reason: "r" }), /조치 불필요/);
  }
});
