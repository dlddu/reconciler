import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const functionMatch = html.match(
  /  function isModelEnabled\(m\) \{[\s\S]*?\n  \}\n/
);

assert.ok(functionMatch, "isModelEnabled must exist in index.html");

const functionSource = functionMatch[0];

function isModelEnabled(model) {
  const context = { model, result: undefined };

  vm.runInNewContext(
    functionSource + "\nresult = isModelEnabled(model);",
    context
  );

  return context.result;
}

function visibleModels(models) {
  return models.filter(isModelEnabled).map((m) => m.id);
}

test("hides models whose detection is explicitly disabled", () => {
  assert.equal(isModelEnabled({ id: "off", checkPolicy: { enabled: false } }), false);
});

test("shows models whose detection is explicitly enabled", () => {
  assert.equal(isModelEnabled({ id: "on", checkPolicy: { enabled: true } }), true);
});

test("treats a missing enabled flag as enabled", () => {
  assert.equal(isModelEnabled({ id: "no-flag", checkPolicy: { intervalSeconds: 300 } }), true);
  assert.equal(isModelEnabled({ id: "no-policy" }), true);
});

test("keeps only enabled models in the sidebar list", () => {
  const visible = visibleModels([
    { id: "a" },
    { id: "b", checkPolicy: { enabled: false } },
    { id: "c", checkPolicy: { enabled: true } },
    { id: "d", checkPolicy: { intervalSeconds: 600 } }
  ]);

  assert.deepEqual(visible, ["a", "c", "d"]);
});

test("loadData keeps hidden models in state so the hidden view can show them", () => {
  assert.match(html, /state\.models = Array\.isArray\(models\) \? models : \[\];/);
  assert.doesNotMatch(html, /state\.models = all\.filter\(isModelEnabled\);/);
});

test("the view mode filter is what applies isModelEnabled", () => {
  assert.match(html, /function modelsInMode\(mode\) \{[\s\S]*?state\.models\.filter\(function \(m\) \{ return !isModelEnabled\(m\); \}\)/);
  assert.match(html, /function modelsInMode\(mode\) \{[\s\S]*?var active = state\.models\.filter\(isModelEnabled\);/);
});
