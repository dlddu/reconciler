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
    list,
    modeMeta: () => ({ head: "ToBeModels", empty: "없습니다." }),
    pendingTaskCount: () => 0,
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
