import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

const lastActionMatch = html.match(
  /  function lastAction\(modelId\) \{[\s\S]*?\n  \}\n\n  function latestDisplayTask/
);
assert.ok(lastActionMatch, "lastAction must exist in index.html");
const lastActionSource = lastActionMatch[0].replace(
  /\n\n  function latestDisplayTask$/,
  ""
);

const relTimeMatch = html.match(/  function relTime\(iso, now\) \{[\s\S]*?\n  \}\n/);
assert.ok(relTimeMatch, "relTime must exist in index.html");

function lastAction(tasks) {
  const context = {
    result: undefined,
    state: { tasksByModel: { model: tasks } }
  };
  vm.runInNewContext(
    lastActionSource + '\nresult = lastAction("model");',
    context
  );
  return context.result;
}

function relTime(iso, now) {
  const context = { result: undefined };
  vm.runInNewContext(
    relTimeMatch[0] + "\nresult = relTime(" + JSON.stringify(iso) + ", " + now + ");",
    context
  );
  return context.result;
}

test("a task with no updatedAt still reports the time it was created", () => {
  const result = lastAction([
    { id: "rct_a", createdAt: "2026-08-05T11:08:13Z" }
  ]);

  assert.equal(result.at, "2026-08-05T11:08:13Z");
  assert.equal(result.label, "작업 생성");
  assert.equal(result.taskId, "rct_a");
});

test("a step recorded after updatedAt wins over the stale updatedAt", () => {
  const result = lastAction([
    {
      id: "rct_a",
      createdAt: "2026-08-01T00:00:00Z",
      updatedAt: "2026-08-01T00:00:00Z",
      attempts: [
        {
          plan: { plannedAt: "2026-08-02T00:00:00Z" },
          execution: {
            startedAt: "2026-08-03T00:00:00Z",
            finishedAt: "2026-08-03T04:00:00Z",
            entries: []
          },
          verification: { verifiedAt: "2026-08-03T05:00:00Z" }
        }
      ]
    }
  ]);

  assert.equal(result.at, "2026-08-03T05:00:00Z");
  assert.equal(result.label, "검증");
});

test("the newest moment across every task of the model is used", () => {
  const result = lastAction([
    { id: "old", createdAt: "2026-07-01T00:00:00Z", updatedAt: "2026-07-02T00:00:00Z" },
    { id: "new", createdAt: "2026-08-30T10:12:12Z" },
    { id: "middle", createdAt: "2026-08-01T00:00:00Z" }
  ]);

  assert.equal(result.at, "2026-08-30T10:12:12Z");
  assert.equal(result.taskId, "new");
});

test("a no-op detection is not an action", () => {
  const result = lastAction([
    { id: "real", status: "succeeded", createdAt: "2026-08-01T00:00:00Z" },
    { id: "noop", status: "no_action_needed", createdAt: "2026-08-30T10:12:12Z", trigger: { detectedAt: "2026-08-30T10:12:12Z" } }
  ]);

  assert.equal(result.at, "2026-08-01T00:00:00Z");
  assert.equal(result.taskId, "real");
});

test("a model whose every task needed no action reports nothing", () => {
  const result = lastAction([
    { id: "noop1", status: "no_action_needed", createdAt: "2026-08-01T00:00:00Z" },
    { id: "noop2", status: "no_action_needed", createdAt: "2026-08-30T10:12:12Z" }
  ]);

  assert.equal(result, null);
});

test("a model with no task at all reports nothing", () => {
  assert.equal(lastAction([]), null);
});

test("unparseable timestamps are ignored rather than displayed", () => {
  const result = lastAction([
    { id: "rct_a", createdAt: "2026-08-01T00:00:00Z", updatedAt: "not-a-date" }
  ]);

  assert.equal(result.at, "2026-08-01T00:00:00Z");
});

test("elapsed time is phrased in the largest fitting unit", () => {
  const now = Date.parse("2026-09-04T00:00:00Z");
  assert.equal(relTime("2026-09-03T23:59:30Z", now), "방금");
  assert.equal(relTime("2026-09-03T23:20:00Z", now), "40분 전");
  assert.equal(relTime("2026-09-03T18:00:00Z", now), "6시간 전");
  assert.equal(relTime("2026-08-30T00:00:00Z", now), "5일 전");
  assert.equal(relTime("2026-06-04T00:00:00Z", now), "3개월 전");
  assert.equal(relTime("2024-09-04T00:00:00Z", now), "2년 전");
});

test("a timestamp ahead of the clock reads as just now, not a negative age", () => {
  const now = Date.parse("2026-09-04T00:00:00Z");
  assert.equal(relTime("2026-09-04T00:05:00Z", now), "방금");
});

test("the sidebar item renders the last action time", () => {
  const item = html.match(/var acted = la\n?[\s\S]*?: '<div class="mi-acted"[\s\S]*?;/);
  assert.ok(item, "the sidebar must build a mi-acted line");
  assert.match(item[0], /마지막 조치/);
  assert.match(item[0], /relTime\(la\.at\)/);

  const render = html.match(/  function renderSidebar\(\) \{[\s\S]*?\n  \}\n\n  function renderDetail\(\)/);
  assert.match(render[0], /\+\s*acted\s*\+/);
});

test("the model detail shows the exact last action timestamp", () => {
  const detail = html.match(/  function renderDetail\(\) \{[\s\S]*?\n  \}\n\n  function renderTemplateSidebar\(\)/);
  assert.ok(detail, "renderDetail must exist in index.html");
  assert.match(detail[0], /var lastAct = lastAction\(m\.id\);/);
  assert.match(detail[0], /마지막 조치/);
  assert.match(detail[0], /fmtDate\(lastAct\.at\)/);
});

// ---------- ordering ----------
// The sidebar list is built from visibleModels(), so the ordering is exercised
// through that function rather than through byLastActionDesc alone.
const modesMatch = html.match(
  /  \/\/ ---------- view modes ----------\n[\s\S]*?\n  function modeContaining\(modelId\) \{[\s\S]*?\n  \}\n/
);
assert.ok(modesMatch, "the view modes block must exist in index.html");
const enabledMatch = html.match(/  function isModelEnabled\(m\) \{[\s\S]*?\n  \}\n/);
assert.ok(enabledMatch, "isModelEnabled must exist in index.html");
const constsMatch = html.match(
  /  var DONE_STATUSES = [\s\S]*?\n  var DEFAULT_MODE = "[a-z]+";\n/
);
assert.ok(constsMatch, "the status sets / MODES / DEFAULT_MODE must exist in index.html");

const orderSource =
  constsMatch[0] + enabledMatch[0] + modesMatch[0] + lastActionSource + "\n";

function orderedIds(models, tasksByModel) {
  const context = {
    result: undefined,
    state: {
      filter: "",
      mode: "active",
      repo: "",
      models,
      selected: null,
      tasksByModel
    }
  };
  vm.runInNewContext(orderSource + "\nresult = visibleModels();", context);
  return Array.from(context.result).map((m) => m.id);
}

const plainModels = (...ids) =>
  ids.map((id) => ({ id, metadata: { name: id, tags: [] } }));

test("the model acted on most recently is listed first", () => {
  assert.deepEqual(
    orderedIds(plainModels("stale", "fresh", "middle"), {
      stale: [{ id: "a", createdAt: "2026-07-01T00:00:00Z" }],
      fresh: [{ id: "b", createdAt: "2026-09-01T00:00:00Z" }],
      middle: [{ id: "c", createdAt: "2026-08-01T00:00:00Z" }]
    }),
    ["fresh", "middle", "stale"]
  );
});

test("a step buried in an attempt still lifts its model to the top", () => {
  assert.deepEqual(
    orderedIds(plainModels("recent-createdAt", "recent-step"), {
      "recent-createdAt": [{ id: "a", createdAt: "2026-08-20T00:00:00Z" }],
      "recent-step": [
        {
          id: "b",
          createdAt: "2026-01-01T00:00:00Z",
          attempts: [{ verification: { verifiedAt: "2026-08-25T00:00:00Z" } }]
        }
      ]
    }),
    ["recent-step", "recent-createdAt"]
  );
});

test("models with no recorded action sink below the ones that have acted", () => {
  assert.deepEqual(
    orderedIds(plainModels("never", "noop-only", "acted"), {
      never: [],
      "noop-only": [
        {
          id: "a",
          status: "no_action_needed",
          createdAt: "2026-09-08T00:00:00Z"
        }
      ],
      acted: [{ id: "b", createdAt: "2026-01-01T00:00:00Z" }]
    }),
    ["acted", "never", "noop-only"]
  );
});

test("models that tie keep the order they have in the data file", () => {
  const same = { id: "x", createdAt: "2026-08-01T00:00:00Z" };
  assert.deepEqual(
    orderedIds(plainModels("first", "second", "third"), {
      first: [{ ...same }],
      second: [{ ...same }],
      third: [{ ...same }]
    }),
    ["first", "second", "third"]
  );
});

test("the search filter narrows the list without disturbing the order", () => {
  const models = [
    { id: "docs-old", metadata: { name: "docs old", tags: [] } },
    { id: "e2e-new", metadata: { name: "e2e new", tags: [] } },
    { id: "docs-new", metadata: { name: "docs new", tags: [] } }
  ];
  const tasks = {
    "docs-old": [{ id: "a", createdAt: "2026-07-01T00:00:00Z" }],
    "e2e-new": [{ id: "b", createdAt: "2026-09-01T00:00:00Z" }],
    "docs-new": [{ id: "c", createdAt: "2026-08-01T00:00:00Z" }]
  };

  assert.deepEqual(orderedIds(models, tasks), ["e2e-new", "docs-new", "docs-old"]);

  const context = {
    result: undefined,
    state: {
      filter: "docs",
      mode: "active",
      repo: "",
      models,
      selected: null,
      tasksByModel: tasks
    }
  };
  vm.runInNewContext(orderSource + "\nresult = visibleModels();", context);
  assert.deepEqual(
    Array.from(context.result).map((m) => m.id),
    ["docs-new", "docs-old"]
  );
});

test("lastAction is computed once per model, not once per comparison", () => {
  const order = html.match(/  function byLastActionDesc\(models\) \{[\s\S]*?\n  \}\n/);
  assert.ok(order, "byLastActionDesc must exist in index.html");
  assert.doesNotMatch(
    order[0].split(".sort(")[1] || "",
    /lastAction\(/,
    "the comparator must not call lastAction"
  );
});
