import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

const constsMatch = html.match(
  /  var PENDING_STATUS = [\s\S]*?\n  var DEFAULT_MODE = "[a-z]+";\n/
);
assert.ok(constsMatch, "PENDING_STATUS / MODES / DEFAULT_MODE must exist in index.html");

const enabledMatch = html.match(/  function isModelEnabled\(m\) \{[\s\S]*?\n  \}\n/);
assert.ok(enabledMatch, "isModelEnabled must exist in index.html");

const modesMatch = html.match(
  /  \/\/ ---------- view modes ----------\n[\s\S]*?\n  function modeContaining\(modelId\) \{[\s\S]*?\n  \}\n/
);
assert.ok(modesMatch, "the view modes block must exist in index.html");

const source = constsMatch[0] + enabledMatch[0] + modesMatch[0];

// Three models: one active with a planned task, one active without, one hidden.
const MODELS = [
  { id: "waiting", metadata: { name: "Waiting", tags: ["k8s"] } },
  { id: "idle", metadata: { name: "Idle", tags: [] } },
  { id: "off", metadata: { name: "Off", tags: [] }, checkPolicy: { enabled: false } }
];

const TASKS = {
  waiting: [
    { id: "a", status: "succeeded" },
    { id: "b", status: "planned" }
  ],
  idle: [{ id: "c", status: "succeeded" }],
  off: [{ id: "d", status: "planned" }]
};

function run(expression, overrides = {}) {
  const context = {
    result: undefined,
    state: {
      filter: "",
      mode: "pending",
      models: MODELS,
      selected: null,
      tasksByModel: TASKS,
      ...overrides
    }
  };

  vm.runInNewContext(source + "\nresult = " + expression + ";", context);

  return context.result;
}

const ids = (models) => models.map((m) => m.id);

test("defaults to the pending-execution view", () => {
  assert.equal(run("DEFAULT_MODE"), "pending");
  assert.equal(run("MODES[0].id"), "pending");
  assert.deepEqual(Array.from(run("MODES.map(function (m) { return m.id; })")), [
    "pending",
    "active",
    "hidden"
  ]);
});

test("pending mode keeps only active models that have a planned task", () => {
  assert.deepEqual(ids(run('modelsInMode("pending")')), ["waiting"]);
});

test("pending mode never surfaces a hidden model, even with a planned task", () => {
  assert.equal(run('modelsInMode("pending")').some((m) => m.id === "off"), false);
});

test("active mode is every model whose detection is enabled", () => {
  assert.deepEqual(ids(run('modelsInMode("active")')), ["waiting", "idle"]);
});

test("hidden mode is only the models whose detection is disabled", () => {
  assert.deepEqual(ids(run('modelsInMode("hidden")')), ["off"]);
});

test("pendingTaskCount counts planned tasks only", () => {
  assert.equal(run('pendingTaskCount("waiting")'), 1);
  assert.equal(run('pendingTaskCount("idle")'), 0);
  assert.equal(run('pendingTaskCount("nope")'), 0);
});

test("visibleModels applies the search filter on top of the mode", () => {
  assert.deepEqual(ids(run("visibleModels()", { mode: "active" })), ["waiting", "idle"]);
  assert.deepEqual(
    ids(run("visibleModels()", { mode: "active", filter: "idle" })),
    ["idle"]
  );
  assert.deepEqual(ids(run("visibleModels()", { mode: "active", filter: "k8s" })), [
    "waiting"
  ]);
  assert.deepEqual(ids(run("visibleModels()", { mode: "pending", filter: "idle" })), []);
});

test("modeContaining resolves a deep link to a mode that shows the model", () => {
  assert.equal(run('modeContaining("waiting")'), "pending");
  assert.equal(run('modeContaining("idle")'), "active");
  assert.equal(run('modeContaining("off")'), "hidden");
  assert.equal(run('modeContaining("unknown")'), "pending");
});

test("every mode carries a label, a list heading and an empty-state message", () => {
  for (const id of ["pending", "active", "hidden"]) {
    const meta = run(`modeMeta("${id}")`);
    assert.equal(meta.id, id);
    assert.ok(meta.label, `${id} needs a label`);
    assert.ok(meta.head, `${id} needs a list heading`);
    assert.ok(meta.empty, `${id} needs an empty-state message`);
  }
});

test("the toolbar renders one button per mode with a live count", () => {
  assert.match(html, /<div class="modes" id="modes"/);
  assert.match(html, /MODES\.map\(function \(mo\) \{[\s\S]*?modelsInMode\(mo\.id\)\.length/);
  assert.match(html, /aria-pressed="' \+ \(state\.mode === mo\.id \? "true" : "false"\)/);
});

test("switching modes re-picks a selection that is still visible", () => {
  assert.match(html, /function setMode\(mode\) \{[\s\S]*?state\.selected = models\.length \? models\[0\]\.id : null;/);
});
