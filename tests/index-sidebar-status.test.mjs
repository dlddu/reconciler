import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const functionMatch = html.match(
  /  function latestDisplayTask\(modelId\) \{[\s\S]*?\n  \}\n\n  \/\/ ---------- rendering ----------/
);

assert.ok(functionMatch, "latestDisplayTask must exist in index.html");

const functionSource = functionMatch[0].replace(
  /\n\n  \/\/ ---------- rendering ----------$/,
  ""
);
const renderMatch = html.match(
  /  function renderSidebar\(\) \{[\s\S]*?\n  \}\n\n  function renderDetail\(\)/
);

assert.ok(renderMatch, "renderSidebar must exist in index.html");

const renderSource = renderMatch[0].replace(
  /\n\n  function renderDetail\(\)$/,
  ""
);

function selectDisplayTask(tasks) {
  const context = {
    result: undefined,
    state: { tasksByModel: { model: tasks } }
  };

  vm.runInNewContext(
    functionSource + '\nresult = latestDisplayTask("model");',
    context
  );

  return context.result;
}

function renderSidebar(tasks) {
  const list = {
    innerHTML: "",
    querySelectorAll() { return []; }
  };
  const modelCount = { textContent: "" };
  const context = {
    $: (selector) => selector === "#modellist" ? list : modelCount,
    escapeHtml: (value) => String(value),
    isModelEnabled: () => true,
    lastAction: () => null,
    relTime: () => "방금",
    list,
    modeMeta: () => ({ head: "ToBeModels", empty: "없습니다." }),
    progressTaskCount: () => 0,
    manualApprovalTaskCount: () => 0,
    decisionTaskCount: () => 0,
    DONE_STATUSES: ["succeeded", "cancelled", "no_action_needed"],
    result: undefined,
    select() {},
    state: {
      filter: "",
      mode: "active",
      models: [{ id: "model", metadata: { name: "Model", tags: [] } }],
      selected: null,
      tasksByModel: { model: tasks }
    },
    visibleModels: () => context.state.models,
    STATUS_META: {
      no_action_needed: { color: "#no-action" },
      planned: { color: "#planned" }
    }
  };

  vm.runInNewContext(
    functionSource + "\n" + renderSource + "\nrenderSidebar(); result = list.innerHTML;",
    context
  );

  return context.result;
}

test("uses the latest non-no-action task for the sidebar status", () => {
  const result = selectDisplayTask([
    { id: "older", status: "succeeded", createdAt: "2026-07-30T00:00:00Z" },
    { id: "latest", status: "no_action_needed", createdAt: "2026-08-02T00:00:00Z" },
    { id: "visible", status: "planned", createdAt: "2026-08-01T00:00:00Z" }
  ]);

  assert.equal(result.id, "visible");
  assert.equal(result.status, "planned");
});

test("returns no display task when every task needs no action", () => {
  const result = selectDisplayTask([
    { id: "first", status: "no_action_needed", createdAt: "2026-08-01T00:00:00Z" },
    { id: "second", status: "no_action_needed", createdAt: "2026-08-02T00:00:00Z" }
  ]);

  assert.equal(result, null);
});

test("renders the prior meaningful status instead of no action", () => {
  const sidebar = renderSidebar([
    { id: "visible", status: "planned", createdAt: "2026-08-01T00:00:00Z" },
    { id: "latest", status: "no_action_needed", createdAt: "2026-08-02T00:00:00Z" }
  ]);

  assert.match(sidebar, /title="planned"/);
  assert.doesNotMatch(sidebar, /title="no_action_needed"/);
});

test("renders a neutral status when every task needs no action", () => {
  const sidebar = renderSidebar([
    { id: "latest", status: "no_action_needed", createdAt: "2026-08-02T00:00:00Z" }
  ]);

  assert.match(sidebar, /title="표시할 상태 없음"/);
  assert.doesNotMatch(sidebar, /title="no_action_needed"/);
});

// ---------- workflow badges ----------
// Rendered with the real status sets and counters, so the wording on each badge is pinned
// to the statuses it actually counts.
const constsMatch = html.match(
  /  var DONE_STATUSES = [\s\S]*?\n  var DEFAULT_MODE = "[a-z]+";\n/
);
assert.ok(constsMatch, "the status sets / MODES / DEFAULT_MODE must exist in index.html");
const modesMatch = html.match(
  /  \/\/ ---------- view modes ----------\n[\s\S]*?\n  function modeContaining\(modelId\) \{[\s\S]*?\n  \}\n/
);
assert.ok(modesMatch, "the view modes block must exist in index.html");

function renderBadges(tasks) {
  const list = { innerHTML: "", querySelectorAll() { return []; } };
  const context = {
    $: (selector) => selector === "#modellist" ? list : { textContent: "" },
    escapeHtml: (value) => String(value),
    isModelEnabled: () => true,
    lastAction: () => null,
    relTime: () => "방금",
    select() {},
    STATUS_META: {},
    state: {
      filter: "",
      mode: "active",
      repo: "",
      models: [{ id: "model", metadata: { name: "Model", tags: [] } }],
      selected: null,
      tasksByModel: { model: tasks }
    }
  };
  vm.runInNewContext(
    constsMatch[0] + modesMatch[0] + functionSource + "\n" + renderSource + "\nrenderSidebar();",
    context
  );
  const meta = list.innerHTML.match(/<div class="mi-meta">([\s\S]*?)<span class="taskcount">/);
  assert.ok(meta, "the sidebar item must render its badge row");
  return meta[1];
}

test("a task waiting for manual approval is badged as such", () => {
  const badges = renderBadges([
    { id: "a", status: "approved", attempts: [{ review: { status: "approved", manualApproval: { sha: "a".repeat(40), context: "review/manual-approval" } } }] },
    { id: "b", status: "succeeded" }
  ]);
  assert.match(badges, />진행 중 1</);
  assert.match(badges, /class="manualpill"[^>]*>수동 승인 대기 1</);
});

test("a model with no review work shows neither review badge", () => {
  const badges = renderBadges([{ id: "a", status: "planning" }]);
  assert.match(badges, />진행 중 1</);
  assert.doesNotMatch(badges, /리뷰 대기|승인 진행 중|수동 승인 대기|결정 대기/);
});

test("a task waiting for a human decision is badged as such", () => {
  const badges = renderBadges([
    { id: "a", status: "approved", attempts: [{ review: { status: "approved" }, decision: { sha: "b".repeat(40) } }] },
    { id: "b", status: "approved", attempts: [{ review: { status: "approved" }, decision: { sha: "b".repeat(40), verdict: "approved" } }] }
  ]);
  assert.match(badges, /class="decisionpill"[^>]*>결정 대기 1</);
  assert.doesNotMatch(badges, /수동 승인 대기/);
});
