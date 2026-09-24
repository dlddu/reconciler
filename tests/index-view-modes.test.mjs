import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const schema = JSON.parse(
  readFileSync(new URL("../schemas/reconciliation-task.schema.json", import.meta.url), "utf8")
);
const SCHEMA_STATUSES = schema.properties.status.enum;

const constsMatch = html.match(
  /  var DONE_STATUSES = [\s\S]*?\n  var DEFAULT_MODE = "[a-z]+";\n/
);
assert.ok(constsMatch, "the status sets / MODES / DEFAULT_MODE must exist in index.html");

const enabledMatch = html.match(/  function isModelEnabled\(m\) \{[\s\S]*?\n  \}\n/);
assert.ok(enabledMatch, "isModelEnabled must exist in index.html");

const modesMatch = html.match(
  /  \/\/ ---------- view modes ----------\n[\s\S]*?\n  function modeContaining\(modelId\) \{[\s\S]*?\n  \}\n/
);
assert.ok(modesMatch, "the view modes block must exist in index.html");

// visibleModels orders the list by last action, so lastAction must be in scope too.
const lastActionMatch = html.match(/  function lastAction\(modelId\) \{[\s\S]*?\n  \}\n/);
assert.ok(lastActionMatch, "lastAction must exist in index.html");

const source =
  constsMatch[0] + enabledMatch[0] + modesMatch[0] + lastActionMatch[0];

const MODELS = [
  { id: "working", metadata: { name: "Working", tags: [] } },
  { id: "asking", metadata: { name: "Asking", tags: ["k8s"] } },
  { id: "claimed", metadata: { name: "Claimed", tags: [] } },
  { id: "retry", metadata: { name: "Retry", tags: [] } },
  { id: "idle", metadata: { name: "Idle", tags: [] } },
  { id: "empty", metadata: { name: "Empty", tags: [] } },
  { id: "off", metadata: { name: "Off", tags: [] }, checkPolicy: { enabled: false } }
];

const TASKS = {
  working: [
    { id: "a", status: "succeeded" },
    { id: "b", status: "planning" }
  ],
  asking: [
    { id: "c", status: "succeeded" },
    { id: "d", status: "awaiting_review" }
  ],
  // a human session picked it up but the human has not answered yet
  claimed: [{ id: "e", status: "approving" }],
  // failed is the planner's rework entry point, not a finished task
  retry: [{ id: "f", status: "failed" }],
  idle: [
    { id: "g", status: "succeeded" },
    { id: "h", status: "no_action_needed" },
    { id: "i", status: "cancelled" }
  ],
  off: [
    { id: "j", status: "awaiting_review" },
    { id: "k", status: "planning" }
  ]
};

function run(expression, overrides = {}) {
  const context = {
    result: undefined,
    state: {
      filter: "",
      mode: "progress",
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

test("defaults to the in-progress view", () => {
  assert.equal(run("DEFAULT_MODE"), "progress");
  assert.ok(
    run("MODES.some(function (m) { return m.id === DEFAULT_MODE; })"),
    "DEFAULT_MODE must name a real mode"
  );
});

test("the toolbar offers exactly the four requested modes, in order", () => {
  assert.deepEqual(Array.from(run("MODES.map(function (m) { return m.id; })")), [
    "progress",
    "review",
    "active",
    "hidden"
  ]);
  assert.deepEqual(Array.from(run("MODES.map(function (m) { return m.label; })")), [
    "진행 중",
    "리뷰 대기 중",
    "활성 전체",
    "숨김"
  ]);
});

test("done is the terminal statuses only; review is awaiting human approval", () => {
  assert.deepEqual(Array.from(run("DONE_STATUSES")), ["succeeded", "cancelled", "no_action_needed"]);
  assert.deepEqual(Array.from(run("REVIEW_STATUSES")), ["awaiting_review", "approving"]);
});

test("the review tab is exactly the waiting and in-progress approval sets, which never overlap", () => {
  const awaiting = run("AWAITING_REVIEW_STATUSES");
  const approving = run("APPROVING_STATUSES");
  assert.deepEqual(Array.from(awaiting), ["awaiting_review"]);
  assert.deepEqual(Array.from(approving), ["approving"]);
  assert.deepEqual(Array.from(run("REVIEW_STATUSES")), [...awaiting, ...approving]);
  assert.equal(awaiting.filter((s) => approving.includes(s)).length, 0);
});

test("the review badges split the review tab's count between waiting, in progress and manual approval", () => {
  assert.equal(run('awaitingReviewTaskCount("asking")'), 1);
  assert.equal(run('approvingTaskCount("asking")'), 0);
  assert.equal(run('awaitingReviewTaskCount("claimed")'), 0);
  assert.equal(run('approvingTaskCount("claimed")'), 1);
  const withGated = { tasksByModel: { ...TASKS, ...MANUAL_TASKS } };
  for (const id of ["asking", "claimed", "working", "idle", "nope", "gated", "ready", "moved"]) {
    assert.equal(
      run(`awaitingReviewTaskCount("${id}") + approvingTaskCount("${id}") + manualApprovalTaskCount("${id}")`, withGated),
      run(`reviewTaskCount("${id}")`, withGated),
      `${id}: the three badges must add up to the review tab's count`
    );
  }
});

// approved + review.manualApproval on the latest attempt = waiting for the target repo's human approval status.
const MANUAL = { sha: "a".repeat(40), context: "review/manual-approval" };
const MANUAL_TASKS = {
  gated: [{ id: "m1", status: "approved", attempts: [{ review: { required: true, status: "approved", manualApproval: MANUAL } }] }],
  // approved without manualApproval (incl. legacy required:true) needs no human
  ready: [
    { id: "m2", status: "approved", attempts: [{ review: { required: false, status: "approved" } }] },
    { id: "m3", status: "approved", attempts: [{ review: { required: true, status: "approved", reviewer: "human" } }] }
  ],
  // only the latest attempt counts
  moved: [{ id: "m4", status: "approved", attempts: [
    { review: { required: true, status: "approved", manualApproval: MANUAL } },
    { review: { required: false, status: "approved" } }
  ] }],
  // once it runs, it leaves approved and the review tab
  ran: [{ id: "m5", status: "executing", attempts: [{ review: { required: true, status: "approved", manualApproval: MANUAL } }] }]
};
const MANUAL_MODELS = Object.keys(MANUAL_TASKS).map((id) => ({ id, metadata: { name: id, tags: [] } }));

test("an approved task waiting for manual approval shows in the review tab", () => {
  const o = { models: MANUAL_MODELS, tasksByModel: MANUAL_TASKS };
  assert.deepEqual(ids(run('modelsInMode("review")', o)), ["gated"]);
  assert.equal(run('manualApprovalTaskCount("gated")', o), 1);
  assert.equal(run('reviewTaskCount("gated")', o), 1);
  for (const id of ["ready", "moved", "ran"]) {
    assert.equal(run(`manualApprovalTaskCount("${id}")`, o), 0, `${id} is not waiting for manual approval`);
  }
  const progress = ids(run('modelsInMode("progress")', o));
  assert.ok(progress.includes("gated"), "manual approval is still in progress");
});

test("manual approval tolerates tasks without attempts or review", () => {
  const o = { tasksByModel: { x: [{ id: "1", status: "approved" }, { id: "2", status: "approved", attempts: [] }, { id: "3", status: "approved", attempts: [{}] }] } };
  assert.equal(run('manualApprovalTaskCount("x")', o), 0);
});

test("every status the page names is a real schema status", () => {
  for (const status of [...run("DONE_STATUSES"), ...run("REVIEW_STATUSES")]) {
    assert.ok(SCHEMA_STATUSES.includes(status), `${status} is not in the task schema`);
  }
});

test("every non-terminal schema status counts as in progress", () => {
  const done = run("DONE_STATUSES");
  for (const status of SCHEMA_STATUSES) {
    assert.equal(
      run('progressTaskCount("solo")', { tasksByModel: { solo: [{ id: "x", status }] } }),
      done.includes(status) ? 0 : 1,
      `${status} should ${done.includes(status) ? "not " : ""}count as in progress`
    );
  }
});

test("waiting for review is a subset of in progress", () => {
  const done = run("DONE_STATUSES");
  for (const status of run("REVIEW_STATUSES")) {
    assert.equal(done.includes(status), false, `${status} cannot be both done and awaiting review`);
  }
  const review = ids(run('modelsInMode("review")'));
  const progress = ids(run('modelsInMode("progress")'));
  for (const id of review) assert.ok(progress.includes(id), `${id} is awaiting review but not in progress`);
});

test("progress mode keeps active models with any unfinished task", () => {
  assert.deepEqual(ids(run('modelsInMode("progress")')), ["working", "asking", "claimed", "retry"]);
});

test("review mode keeps only active models with a task awaiting approval", () => {
  assert.deepEqual(ids(run('modelsInMode("review")')), ["asking", "claimed"]);
});

test("a task whose approval session is still open keeps waiting for review", () => {
  // approving is held until the human answers; if that session is abandoned the task
  // would otherwise vanish from the review tab while still needing a decision.
  assert.equal(run('progressTaskCount("claimed")'), 1);
  assert.equal(run('reviewTaskCount("claimed")'), 1);
  assert.equal(run('reviewTaskCount("working")'), 0, "a planner lock is not a review");
  assert.equal(run('reviewTaskCount("retry")'), 0, "a failed task is not a review");
});

test("no workflow mode surfaces a hidden model, whatever its tasks are doing", () => {
  for (const mode of ["progress", "review"]) {
    assert.equal(
      run(`modelsInMode("${mode}")`).some((m) => m.id === "off"),
      false,
      `${mode} must not surface a hidden model`
    );
  }
});

test("active mode is every model whose detection is enabled", () => {
  assert.deepEqual(ids(run('modelsInMode("active")')), [
    "working",
    "asking",
    "claimed",
    "retry",
    "idle",
    "empty"
  ]);
});

test("hidden mode is only the models whose detection is disabled", () => {
  assert.deepEqual(ids(run('modelsInMode("hidden")')), ["off"]);
});

test("each counter counts every matching task of the model", () => {
  const busy = { tasksByModel: { m: [
    { id: "1", status: "awaiting_review" },
    { id: "2", status: "awaiting_review" },
    { id: "3", status: "executing" },
    { id: "4", status: "succeeded" }
  ] } };
  assert.equal(run('progressTaskCount("m")', busy), 3);
  assert.equal(run('reviewTaskCount("m")', busy), 2);
  assert.equal(run('progressTaskCount("idle")'), 0);
  assert.equal(run('reviewTaskCount("working")'), 0);
});

test("counters return zero for a model with no tasks at all", () => {
  for (const fn of ["progressTaskCount", "reviewTaskCount"]) {
    assert.equal(run(`${fn}("nope")`), 0, `${fn} should tolerate an unknown model`);
    assert.equal(run(`${fn}("empty")`), 0, `${fn} should tolerate a model without a task file`);
  }
});

test("visibleModels applies the search filter on top of the mode", () => {
  assert.deepEqual(ids(run("visibleModels()", { mode: "active", filter: "idle" })), ["idle"]);
  assert.deepEqual(ids(run("visibleModels()", { mode: "active", filter: "k8s" })), ["asking"]);
  assert.deepEqual(ids(run("visibleModels()", { mode: "progress", filter: "idle" })), []);
  assert.deepEqual(ids(run("visibleModels()", { mode: "progress", filter: "retry" })), ["retry"]);
  assert.deepEqual(ids(run("visibleModels()", { mode: "review", filter: "ask" })), ["asking"]);
  assert.deepEqual(ids(run("visibleModels()", { mode: "review", filter: "claim" })), ["claimed"]);
  assert.deepEqual(ids(run("visibleModels()", { mode: "review", filter: "work" })), []);
});

test("modeContaining resolves a deep link to the first mode that shows the model", () => {
  assert.equal(run('modeContaining("working")'), "progress");
  assert.equal(run('modeContaining("asking")'), "progress");
  assert.equal(run('modeContaining("idle")'), "active");
  assert.equal(run('modeContaining("empty")'), "active");
  assert.equal(run('modeContaining("off")'), "hidden");
  assert.equal(run('modeContaining("unknown")'), "progress");
});

test("every mode carries a label, a list heading and an empty-state message", () => {
  for (const id of ["progress", "review", "active", "hidden"]) {
    const meta = run(`modeMeta("${id}")`);
    assert.equal(meta.id, id);
    assert.ok(meta.label, `${id} needs a label`);
    assert.ok(meta.head, `${id} needs a list heading`);
    assert.ok(meta.empty, `${id} needs an empty-state message`);
  }
});

test("the planned badge no longer reads as the review tab", () => {
  // planned waits for the automated review judgement, not for a human — it must not share
  // the review tab's wording, or its badge suggests it belongs in that tab.
  const planned = html.match(/    planned:\s*\{ label: "([^"]+)"/);
  assert.ok(planned, "STATUS_META.planned must exist in index.html");
  assert.doesNotMatch(planned[1], /리뷰 대기/);
});

test("the toolbar renders one button per mode with a live count", () => {
  assert.match(html, /<div class="modes" id="modes"/);
  assert.match(html, /MODES\.map\(function \(mo\) \{[\s\S]*?modelsInMode\(mo\.id\)\.length/);
  assert.match(html, /aria-pressed="' \+ \(state\.mode === mo\.id \? "true" : "false"\)/);
});

test("switching modes re-picks a selection that is still visible", () => {
  assert.match(html, /function setMode\(mode\) \{[\s\S]*?state\.selected = models\.length \? models\[0\]\.id : null;/);
});
