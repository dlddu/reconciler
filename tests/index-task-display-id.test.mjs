import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

const helperMatch = html.match(/  function taskDisplayId\(t\) \{[\s\S]*?\n  \}\n/);
assert.ok(helperMatch, "taskDisplayId must exist in index.html");

function run(expression) {
  const context = { result: undefined };
  vm.runInNewContext(helperMatch[0] + "\nresult = " + expression + ";", context);
  return context.result;
}

test("a task is labelled <toBeModelId>-<task id>", () => {
  assert.equal(
    run('taskDisplayId({ id: "rct_20260808-0001", toBeModelId: "tbm_session-platform-docs-impl" })'),
    "tbm_session-platform-docs-impl-rct_20260808-0001"
  );
});

test("the same task number under two models gets two distinct labels", () => {
  const a = run('taskDisplayId({ id: "rct_20260808-0001", toBeModelId: "tbm_a" })');
  const b = run('taskDisplayId({ id: "rct_20260808-0001", toBeModelId: "tbm_b" })');
  assert.notEqual(a, b);
});

test("a record without toBeModelId falls back to the bare task id", () => {
  assert.equal(run('taskDisplayId({ id: "rct_20260808-0001" })'), "rct_20260808-0001");
});

test("the task header renders the prefixed id, not the bare one", () => {
  const head = html.match(/'<div class="task-head">'[\s\S]*?\+ actionPill/);
  assert.ok(head, "the task header must exist in index.html");
  assert.match(head[0], /escapeHtml\(taskDisplayId\(t\)\)/);
  assert.doesNotMatch(head[0], /escapeHtml\(t\.id\)/);
});
