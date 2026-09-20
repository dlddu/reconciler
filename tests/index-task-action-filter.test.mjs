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

const needsMatch = html.match(/  function taskNeedsAction\(t\) \{[\s\S]*?\n  \}\n/);
assert.ok(needsMatch, "taskNeedsAction must exist in index.html");

const pillMatch = html.match(/  function actionPillHtml\(t\) \{[\s\S]*?\n  \}\n/);
assert.ok(pillMatch, "actionPillHtml must exist in index.html");

const titleMatch = html.match(/  function taskSectionTitleHtml\(tasks, needAction\) \{[\s\S]*?\n  \}\n/);
assert.ok(titleMatch, "taskSectionTitleHtml must exist in index.html");

const listMatch = html.match(/  function taskListHtml\(tasks, needAction\) \{[\s\S]*?\n  \}\n/);
assert.ok(listMatch, "taskListHtml must exist in index.html");

const ctx = vm.createContext({
  state: { tasksActionOnly: false },
  // the list only needs to say which tasks it drew, not how they look
  fmtTask: (t) => `<task id="${t.id}">`
});
vm.runInContext(doneMatch[0] + needsMatch[0] + pillMatch[0] + titleMatch[0] + listMatch[0], ctx);

const DONE = vm.runInContext("DONE_STATUSES", ctx);
const taskNeedsAction = vm.runInContext("taskNeedsAction", ctx);
const actionPillHtml = vm.runInContext("actionPillHtml", ctx);
const taskSectionTitleHtml = vm.runInContext("taskSectionTitleHtml", ctx);
const taskListHtml = vm.runInContext("taskListHtml", ctx);
const state = vm.runInContext("state", ctx);

function task(id, status, actionRequired) {
  const t = { id, status };
  if (actionRequired !== undefined) t.assessment = { actionRequired, reason: "r" };
  return t;
}

function render(tasks, actionOnly) {
  state.tasksActionOnly = actionOnly;
  const needAction = tasks.filter(taskNeedsAction);
  return taskSectionTitleHtml(tasks, needAction) + taskListHtml(tasks, needAction);
}

function drawnIds(htmlOut) {
  return [...htmlOut.matchAll(/<task id="([^"]+)">/g)].map((m) => m[1]);
}

test("조치 필요 means exactly what the pill means", () => {
  // If the two ever drift, the toggle labelled 조치 필요만 would hide or show tasks
  // that carry the opposite pill.
  for (const status of SCHEMA_STATUSES) {
    for (const actionRequired of [true, false, undefined]) {
      const t = task("x", status, actionRequired);
      assert.equal(
        taskNeedsAction(t),
        /조치 필요</.test(actionPillHtml(t)),
        `${status} (actionRequired=${actionRequired}) must agree with its pill`
      );
    }
  }
});

test("terminal tasks never count as 조치 필요, whatever they were judged", () => {
  for (const status of DONE) {
    for (const actionRequired of [true, false, undefined]) {
      assert.equal(taskNeedsAction(task("x", status, actionRequired)), false);
    }
  }
  assert.equal(taskNeedsAction(null), false);
});

test("an open task with no judgement yet counts as 조치 필요", () => {
  // nobody has decided about it, so it stays in the filtered view rather than
  // dropping out as if it were settled
  for (const status of SCHEMA_STATUSES.filter((s) => !DONE.includes(s))) {
    assert.equal(taskNeedsAction(task("x", status, undefined)), true, `${status} is unresolved`);
    assert.equal(taskNeedsAction({ id: "x", status, assessment: { reason: "r" } }), true);
  }
  assert.equal(taskNeedsAction(task("x", "planning", false)), false);
});

const TASKS = [
  task("open", "action_required", true),     // 조치 필요
  task("rework", "failed", true),            // 재작업 진입점 — 종료가 아니므로 조치 필요
  task("done", "succeeded", true),           // 끝난 건
  task("clear", "planning", false),          // 조치 불필요 판정
  task("fresh", "assessing", undefined)      // 아직 판단 전 — 판정이 날 때까지 조치 필요
];

test("off shows every task, on shows only the ones needing action", () => {
  assert.deepEqual(drawnIds(render(TASKS, false)), ["open", "rework", "done", "clear", "fresh"]);
  assert.deepEqual(drawnIds(render(TASKS, true)), ["open", "rework", "fresh"]);
});

test("the toggle reports the count and its pressed state", () => {
  const off = render(TASKS, false);
  assert.match(off, /id="taskfilter"/);
  assert.match(off, /aria-pressed="false"/);
  assert.match(off, /조치 필요만 <span class="n">3<\/span>/);
  assert.match(render(TASKS, true), /aria-pressed="true"/);
});

test("the title keeps the full count so the filter never hides the total", () => {
  for (const on of [false, true]) {
    assert.match(render(TASKS, on), /정합성 작업 · 5건/);
  }
});

test("filtering down to nothing says it was filtered, not that there are no tasks", () => {
  const none = [task("done", "succeeded", true), task("clear", "planning", false)];
  const out = render(none, true);
  assert.deepEqual(drawnIds(out), []);
  assert.match(out, /조치가 필요한 작업이 없습니다/);
  assert.match(out, /전체 2건/);
  assert.doesNotMatch(out, /아직 생성된 작업이 없습니다/);
});

test("a model with no tasks shows no toggle at all", () => {
  for (const on of [false, true]) {
    const out = render([], on);
    assert.doesNotMatch(out, /id="taskfilter"/);
    assert.match(out, /아직 생성된 작업이 없습니다/);
  }
});
