import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

const constsMatch = html.match(
  /  var PLANNING_STATUSES = [\s\S]*?\n  var DEFAULT_MODE = "[a-z]+";\n/
);
assert.ok(constsMatch, "the status sets / MODES / DEFAULT_MODE must exist in index.html");

const enabledMatch = html.match(/  function isModelEnabled\(m\) \{[\s\S]*?\n  \}\n/);
assert.ok(enabledMatch, "isModelEnabled must exist in index.html");

const modesMatch = html.match(
  /  \/\/ ---------- view modes ----------\n[\s\S]*?\n  function modeContaining\(modelId\) \{[\s\S]*?\n  \}\n/
);
assert.ok(modesMatch, "the view modes block must exist in index.html");

const source = constsMatch[0] + enabledMatch[0] + modesMatch[0];

// One active model per workflow stage, one idle, one hidden.
const MODELS = [
  { id: "thinking", metadata: { name: "Thinking", tags: [] } },
  { id: "waiting", metadata: { name: "Waiting", tags: ["k8s"] } },
  { id: "busy", metadata: { name: "Busy", tags: [] } },
  { id: "idle", metadata: { name: "Idle", tags: [] } },
  { id: "off", metadata: { name: "Off", tags: [] }, checkPolicy: { enabled: false } }
];

const TASKS = {
  thinking: [
    { id: "h", status: "succeeded" },
    { id: "i", status: "planning" }
  ],
  waiting: [
    { id: "a", status: "succeeded" },
    { id: "b", status: "planned" }
  ],
  busy: [
    { id: "e", status: "succeeded" },
    { id: "f", status: "executing" }
  ],
  idle: [{ id: "c", status: "succeeded" }],
  off: [
    { id: "d", status: "planned" },
    { id: "g", status: "verifying" },
    { id: "j", status: "assessing" }
  ]
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
  assert.ok(
    run("MODES.some(function (m) { return m.id === DEFAULT_MODE; })"),
    "DEFAULT_MODE must name a real mode"
  );
});

test("the modes are listed in workflow order", () => {
  assert.deepEqual(Array.from(run("MODES.map(function (m) { return m.id; })")), [
    "planning",
    "pending",
    "running",
    "active",
    "hidden"
  ]);
});

test("planning mode keeps only active models a detector or planner is holding", () => {
  assert.deepEqual(ids(run('modelsInMode("planning")')), ["thinking"]);
});

test("pending mode keeps only active models waiting on the next worker", () => {
  assert.deepEqual(ids(run('modelsInMode("pending")')), ["waiting"]);
});

test("running mode keeps only active models an executor is holding", () => {
  assert.deepEqual(ids(run('modelsInMode("running")')), ["busy"]);
});

test("no workflow mode surfaces a hidden model, whatever its tasks are doing", () => {
  for (const mode of ["planning", "pending", "running"]) {
    assert.equal(
      run(`modelsInMode("${mode}")`).some((m) => m.id === "off"),
      false,
      `${mode} must not surface a hidden model`
    );
  }
});

test("the three workflow status sets are disjoint", () => {
  assert.equal(
    run("PENDING_STATUSES.filter(function (s) { return PLANNING_STATUSES.indexOf(s) !== -1; }).length"),
    0
  );
  assert.equal(
    run("PENDING_STATUSES.filter(function (s) { return RUNNING_STATUSES.indexOf(s) !== -1; }).length"),
    0
  );
  assert.equal(
    run("PLANNING_STATUSES.filter(function (s) { return RUNNING_STATUSES.indexOf(s) !== -1; }).length"),
    0
  );
});

test("planning is the detector/planner lock, pending is the handoff, running covers review/approval/execution", () => {
  assert.deepEqual(Array.from(run("PLANNING_STATUSES")), ["assessing", "planning"]);
  assert.deepEqual(Array.from(run("PENDING_STATUSES")), ["planned", "approved"]);
  assert.deepEqual(Array.from(run("RUNNING_STATUSES")), [
    "reviewing",
    "awaiting_review",
    "approving",
    "executing",
    "verifying"
  ]);
});

test("active mode is every model whose detection is enabled", () => {
  assert.deepEqual(ids(run('modelsInMode("active")')), [
    "thinking",
    "waiting",
    "busy",
    "idle"
  ]);
});

test("hidden mode is only the models whose detection is disabled", () => {
  assert.deepEqual(ids(run('modelsInMode("hidden")')), ["off"]);
});

test("each counter counts only the statuses in its own set", () => {
  assert.equal(run('planningTaskCount("thinking")'), 1);
  assert.equal(run('planningTaskCount("waiting")'), 0);
  assert.equal(run('pendingTaskCount("waiting")'), 1);
  assert.equal(run('pendingTaskCount("busy")'), 0);
  assert.equal(run('runningTaskCount("busy")'), 1);
  assert.equal(run('runningTaskCount("thinking")'), 0);
});

test("counters return zero for a model with no tasks at all", () => {
  for (const fn of ["planningTaskCount", "pendingTaskCount", "runningTaskCount"]) {
    assert.equal(run(`${fn}("nope")`), 0, `${fn} should tolerate an unknown model`);
  }
});

test("every status in a set is recognised by its counter", () => {
  const cases = [
    ["planningTaskCount", run("PLANNING_STATUSES")],
    ["pendingTaskCount", run("PENDING_STATUSES")],
    ["runningTaskCount", run("RUNNING_STATUSES")]
  ];

  for (const [fn, statuses] of cases) {
    for (const status of statuses) {
      assert.equal(
        run(`${fn}("solo")`, { tasksByModel: { solo: [{ id: "x", status }] } }),
        1,
        `${status} should be counted by ${fn}`
      );
    }
  }
});

test("visibleModels applies the search filter on top of the mode", () => {
  assert.deepEqual(ids(run("visibleModels()", { mode: "active" })), [
    "thinking",
    "waiting",
    "busy",
    "idle"
  ]);
  assert.deepEqual(
    ids(run("visibleModels()", { mode: "active", filter: "idle" })),
    ["idle"]
  );
  assert.deepEqual(ids(run("visibleModels()", { mode: "active", filter: "k8s" })), [
    "waiting"
  ]);
  assert.deepEqual(ids(run("visibleModels()", { mode: "pending", filter: "idle" })), []);
  assert.deepEqual(ids(run("visibleModels()", { mode: "planning", filter: "think" })), [
    "thinking"
  ]);
  assert.deepEqual(ids(run("visibleModels()", { mode: "running", filter: "busy" })), [
    "busy"
  ]);
});

test("modeContaining resolves a deep link to a mode that shows the model", () => {
  assert.equal(run('modeContaining("thinking")'), "planning");
  assert.equal(run('modeContaining("waiting")'), "pending");
  assert.equal(run('modeContaining("busy")'), "running");
  assert.equal(run('modeContaining("idle")'), "active");
  assert.equal(run('modeContaining("off")'), "hidden");
  assert.equal(run('modeContaining("unknown")'), "pending");
});

test("a model in several stages resolves to the earliest stage that holds it", () => {
  const both = {
    tasksByModel: { thinking: [{ id: "i", status: "planning" }, { id: "k", status: "planned" }] }
  };
  assert.equal(run('modeContaining("thinking")', both), "planning");
});

test("every mode carries a label, a list heading and an empty-state message", () => {
  for (const id of ["planning", "pending", "running", "active", "hidden"]) {
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
