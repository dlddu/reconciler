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

test("a no-op detection still counts as the last action", () => {
  const result = lastAction([
    { id: "noop", status: "no_action_needed", createdAt: "2026-08-30T10:12:12Z", trigger: { detectedAt: "2026-08-30T10:12:12Z" } }
  ]);

  assert.equal(result.label, "감지");
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
