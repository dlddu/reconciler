import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

const baseMatch = html.match(/  function dataBase\(loc\) \{[\s\S]*?\n  \}\n/);
assert.ok(baseMatch, "dataBase must exist in index.html");

function dataBase(loc) {
  const context = { loc, result: undefined };
  vm.runInNewContext(baseMatch[0] + "result = dataBase(loc);", context);
  return context.result;
}

test("GitHub Pages reads data from raw main of the same repo", () => {
  assert.equal(
    dataBase({ hostname: "dlddu.github.io", pathname: "/reconciler/" }),
    "https://raw.githubusercontent.com/dlddu/reconciler/main/",
  );
  assert.equal(
    dataBase({ hostname: "dlddu.github.io", pathname: "/reconciler/index.html" }),
    "https://raw.githubusercontent.com/dlddu/reconciler/main/",
  );
});

test("local server and other hosts read from the page's own path", () => {
  assert.equal(dataBase({ hostname: "localhost", pathname: "/" }), "");
  assert.equal(dataBase({ hostname: "127.0.0.1", pathname: "/index.html" }), "");
  assert.equal(dataBase({ hostname: "", pathname: "/tmp/index.html" }), "");
});

test("a user site root (no repo segment) falls back to relative paths", () => {
  assert.equal(dataBase({ hostname: "dlddu.github.io", pathname: "/" }), "");
});

test("every fetch helper prefixes DATA_BASE", () => {
  const helpers = html.match(/  function fetch(JSON|Text)\(url\) \{[\s\S]*?\n  \}\n/g) || [];
  assert.equal(helpers.length, 2);
  for (const h of helpers) assert.match(h, /fetch\(DATA_BASE \+ url,/);
});
