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

// visibleModels orders the list by last action, so lastAction must be in scope too.
const lastActionMatch = html.match(/  function lastAction\(modelId\) \{[\s\S]*?\n  \}\n/);
assert.ok(lastActionMatch, "lastAction must exist in index.html");

const source =
  constsMatch[0] + enabledMatch[0] + modesMatch[0] + lastActionMatch[0];

// Two repos, plus a model whose sources are not github at all.
const MODELS = [
  {
    id: "alpha-docs",
    metadata: { name: "Alpha docs", tags: [] },
    toBe: { dataSource: { type: "github", repository: "dlddu/alpha", subPath: "docs" } },
    asIs: { dataSource: { type: "github", repository: "dlddu/alpha" } }
  },
  {
    id: "alpha-e2e",
    metadata: { name: "Alpha e2e", tags: [] },
    toBe: { dataSource: { type: "github", repository: "dlddu/alpha" } },
    asIs: { dataSource: { type: "github", repository: "dlddu/alpha" } }
  },
  {
    id: "beta-docs",
    metadata: { name: "Beta docs", tags: [] },
    toBe: { dataSource: { type: "github", repository: "dlddu/beta" } },
    asIs: { dataSource: { type: "github", repository: "dlddu/beta" } }
  },
  {
    // to-be and as-is live in different repos — the model belongs to both.
    id: "cross-repo",
    metadata: { name: "Cross repo", tags: [] },
    toBe: { dataSource: { type: "github", repository: "dlddu/alpha" } },
    asIs: { dataSource: { type: "github", repository: "dlddu/beta" } }
  },
  {
    id: "cluster-only",
    metadata: { name: "Cluster only", tags: [] },
    toBe: { dataSource: { type: "k8s", namespace: "prod" } },
    asIs: { dataSource: { type: "k8s", namespace: "prod" } }
  },
  {
    id: "alpha-off",
    metadata: { name: "Alpha off", tags: [] },
    checkPolicy: { enabled: false },
    toBe: { dataSource: { type: "github", repository: "dlddu/alpha" } },
    asIs: { dataSource: { type: "github", repository: "dlddu/alpha" } }
  }
];

const TASKS = {
  "alpha-docs": [{ id: "a", status: "planned" }],
  "alpha-e2e": [{ id: "b", status: "planning" }],
  "beta-docs": [{ id: "c", status: "planned" }],
  "cross-repo": [{ id: "d", status: "executing" }],
  "cluster-only": [{ id: "e", status: "planned" }],
  "alpha-off": [{ id: "f", status: "planned" }]
};

function run(expression, overrides = {}) {
  const context = {
    result: undefined,
    state: {
      filter: "",
      mode: "active",
      repo: "",
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

test("a model's repos come from both of its github data sources", () => {
  assert.deepEqual(Array.from(run('modelRepos(state.models[0])')), ["dlddu/alpha"]);
  assert.deepEqual(Array.from(run('modelRepos(state.models[3])')), [
    "dlddu/alpha",
    "dlddu/beta"
  ]);
});

test("a model with no github source belongs to no repo", () => {
  assert.deepEqual(Array.from(run('modelRepos(state.models[4])')), []);
  assert.equal(run('matchesRepo(state.models[4], "dlddu/alpha")'), false);
});

test("the repo list is every repo present in the data, sorted, without duplicates", () => {
  assert.deepEqual(Array.from(run("allRepos()")), ["dlddu/alpha", "dlddu/beta"]);
});

test("an empty repo means no filter at all", () => {
  assert.equal(run('matchesRepo(state.models[2], "")'), true);
  assert.deepEqual(ids(run("modelsInRepo(state.repo)")), ids(MODELS));
});

test("picking a repo narrows the list to that repo, hidden models included", () => {
  assert.deepEqual(ids(run('modelsInRepo("dlddu/alpha")')), [
    "alpha-docs",
    "alpha-e2e",
    "cross-repo",
    "alpha-off"
  ]);
  assert.deepEqual(ids(run('modelsInRepo("dlddu/beta")')), ["beta-docs", "cross-repo"]);
});

test("a model straddling two repos shows up under each of them", () => {
  for (const repo of ["dlddu/alpha", "dlddu/beta"]) {
    assert.ok(
      run(`modelsInRepo("${repo}")`).some((m) => m.id === "cross-repo"),
      `cross-repo should appear under ${repo}`
    );
  }
});

test("the repo filter applies inside every view mode", () => {
  assert.deepEqual(ids(run("modelsInMode('active')", { repo: "dlddu/beta" })), [
    "beta-docs",
    "cross-repo"
  ]);
  assert.deepEqual(ids(run("modelsInMode('pending')", { repo: "dlddu/beta" })), [
    "beta-docs"
  ]);
  assert.deepEqual(ids(run("modelsInMode('running')", { repo: "dlddu/beta" })), [
    "cross-repo"
  ]);
  assert.deepEqual(ids(run("modelsInMode('planning')", { repo: "dlddu/beta" })), []);
});

test("the hidden mode is scoped to the chosen repo too", () => {
  assert.deepEqual(ids(run("modelsInMode('hidden')", { repo: "dlddu/alpha" })), [
    "alpha-off"
  ]);
  assert.deepEqual(ids(run("modelsInMode('hidden')", { repo: "dlddu/beta" })), []);
});

test("the repo filter never resurrects a model whose detection is disabled", () => {
  for (const mode of ["planning", "pending", "running", "active"]) {
    assert.equal(
      run(`modelsInMode("${mode}")`, { repo: "dlddu/alpha" }).some((m) => m.id === "alpha-off"),
      false,
      `${mode} must not surface a hidden model`
    );
  }
});

test("choosing a repo drops models that track something other than a repo", () => {
  assert.equal(
    run("modelsInMode('active')", { repo: "dlddu/alpha" }).some((m) => m.id === "cluster-only"),
    false
  );
  assert.ok(
    run("modelsInMode('active')").some((m) => m.id === "cluster-only"),
    "the all-repos view must still show it"
  );
});

test("the search filter stacks on top of the repo filter", () => {
  assert.deepEqual(
    ids(run("visibleModels()", { repo: "dlddu/alpha", filter: "docs" })),
    ["alpha-docs"]
  );
  assert.deepEqual(ids(run("visibleModels()", { repo: "dlddu/beta", filter: "alpha" })), []);
});

test("state carries no repo filter by default", () => {
  assert.match(html, /repo: "",\s*\/\/ 대상 레포 필터/);
});

test("the toolbar has a repo select bound to setRepo", () => {
  assert.match(html, /<select id="repo"/);
  assert.match(html, /\$\("#repo"\)\.addEventListener\("change", function \(e\) \{ setRepo\(e\.target\.value\); \}\)/);
  assert.match(html, /function renderRepoFilter\(\) \{[\s\S]*?allRepos\(\)/);
});

test("the repo select offers an all-repos option plus one option per repo", () => {
  const render = html.match(/  function renderRepoFilter\(\) \{[\s\S]*?\n  \}\n/);

  assert.ok(render, "renderRepoFilter must exist in index.html");
  assert.match(render[0], /<option value="">전체 레포/);
  assert.match(render[0], /repos\.map\(function \(r\) \{/);
  assert.match(render[0], /modelsInRepo\(r\)\.length/);
});

test("both the mode and the repo are written to localStorage when chosen", () => {
  assert.match(html, /var STORE_MODE = "reconciler-mode";/);
  assert.match(html, /var STORE_REPO = "reconciler-repo";/);
  assert.match(html, /function setMode\(mode\) \{[\s\S]*?setStoredMode\(mode\);/);
  assert.match(html, /function setRepo\(repo\) \{[\s\S]*?setStoredRepo\(repo\);/);
});

test("init restores the saved mode and repo before the first render", () => {
  const init = html.match(/  function init\(\) \{[\s\S]*?\n  \}\n/);

  assert.ok(init, "init must exist in index.html");
  assert.match(init[0], /var savedMode = storedMode\(\);/);
  assert.match(init[0], /state\.repo = storedRepo\(\);/);
  assert.ok(
    init[0].indexOf("state.repo = storedRepo();") < init[0].indexOf("renderRepoFilter();"),
    "the saved selections must be restored before rendering"
  );
});

test("a saved mode is only honoured when it names a real mode", () => {
  const stored = html.match(/  function storedMode\(\) \{[\s\S]*?\n  \}\n/);

  assert.ok(stored, "storedMode must exist in index.html");
  assert.match(stored[0], /MODES\.some\(function \(mo\) \{ return mo\.id === v; \}\)/);
});

test("a saved repo that no longer exists in the data falls back to all repos", () => {
  const render = html.match(/  function renderRepoFilter\(\) \{[\s\S]*?\n  \}\n/);

  // The guard on state.models.length matters: the first render happens before the fetch
  // resolves, when the repo list is always empty, and must not wipe the restored choice.
  assert.match(
    render[0],
    /if \(state\.repo && state\.models\.length && repos\.indexOf\(state\.repo\) === -1\) \{\s*setStoredRepo\(\(state\.repo = ""\)\);/
  );
});

test("storage failures never break the page", () => {
  assert.match(html, /function storeGet\(key\) \{ try \{ return localStorage\.getItem\(key\); \} catch \(e\) \{ return null; \} \}/);
  assert.match(html, /function storeSet\(key, value\) \{ try \{ localStorage\.setItem\(key, value\); \} catch \(e\) \{\} \}/);
});

test("a deep link releases a repo filter that would hide its model", () => {
  const release = html.match(/  function releaseRepoFilterFor\(modelId\) \{[\s\S]*?\n  \}\n/);

  assert.ok(release, "releaseRepoFilterFor must exist in index.html");
  assert.match(release[0], /if \(!state\.repo\) return;/);
  assert.match(release[0], /if \(m && matchesRepo\(m, state\.repo\)\) return;/);
  assert.match(release[0], /state\.repo = "";/);
  assert.match(release[0], /setStoredRepo\(""\);/);
});

test("a deep link also outranks a saved mode that would hide its model", () => {
  assert.match(
    html,
    /if \(target\) \{\s*releaseRepoFilterFor\(target\);[\s\S]*?state\.mode = modeContaining\(target\);/
  );
  assert.match(html, /\} else if \(!state\.modePinned\) \{\s*state\.mode = DEFAULT_MODE;/);
});

test("the repo filter is hidden in the templates view", () => {
  assert.match(html, /\$\("#repofilter"\)\.style\.display = tpl \? "none" : "";/);
});
