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

function pill(status, actionRequired) {
  const t = { id: "x", status };
  if (actionRequired !== undefined) t.assessment = { actionRequired, reason: "r" };
  return actionPillHtml(t);
}

test("terminal tasks carry no pill, whatever the assessment said", () => {
  for (const status of DONE) {
    for (const actionRequired of [true, false]) {
      assert.equal(
        pill(status, actionRequired),
        "",
        `${status} (actionRequired=${actionRequired}) must not show a pill`
      );
    }
  }
});

test("succeeded is the case that motivated hiding it", () => {
  // every succeeded task is actionRequired:true — it can only get there via action_required
  assert.equal(pill("succeeded", true), "");
  assert.match(pill("executing", true), /조치 필요/);
});

test("rework entry points keep the pill", () => {
  // failed / review_rejected are picked back up by the planner, so they are not done
  for (const status of ["failed", "review_rejected"]) {
    assert.equal(DONE.includes(status), false, `${status} must not be a terminal status`);
    assert.match(pill(status, true), /조치 필요/);
  }
});

test("an unassessed task reads 조치 필요 while it is still open", () => {
  // no judgement yet is not a verdict of 조치 불필요 — it is a task nobody has resolved,
  // so it keeps the pill (with a tooltip saying why) until the assessment lands
  const open = pill("assessing", undefined);
  assert.match(open, /조치 필요</);
  assert.match(open, /title="아직 판단 전/);
  assert.doesNotMatch(open, /조치 불필요/);
  // terminal wins over it: a task cancelled before assessment carries no pill at all
  assert.equal(pill("cancelled", undefined), "");
});

test("a judged 조치 필요 carries no 판단 전 tooltip", () => {
  assert.doesNotMatch(pill("action_required", true), /title=/);
});

test("every schema status shows a pill exactly when it is not terminal", () => {
  for (const status of SCHEMA_STATUSES) {
    const shown = pill(status, true) !== "";
    assert.equal(
      shown,
      !DONE.includes(status),
      `${status} should ${DONE.includes(status) ? "not " : ""}show the pill`
    );
  }
});

test("a non-terminal false assessment still reads 조치 불필요", () => {
  assert.match(pill("assessing", false), /조치 불필요/);
});
