import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

const parseMatch = html.match(/  function parseTemplateIndex\(src\) \{[\s\S]*?\n  \}\n/);
assert.ok(parseMatch, "parseTemplateIndex must exist in index.html");

const escapeMatch = html.match(/  function escapeHtml\(s\) \{[\s\S]*?\n  \}\n/);
assert.ok(escapeMatch, "escapeHtml must exist in index.html");

const inlineMatch = html.match(/  function renderInline\(s\) \{[\s\S]*?\n  \}\n/);
assert.ok(inlineMatch, "renderInline must exist in index.html");

const mdMatch = html.match(/  function md\(src\) \{[\s\S]*?\n  \}\n/);
assert.ok(mdMatch, "md must exist in index.html");

const prefixMatch = html.match(/  var TEMPLATE_HASH_PREFIX = "[^"]+";\n/);
const toHashMatch = html.match(/  function templateHash\(file\) \{[\s\S]*?\n  \}\n/);
const fromHashMatch = html.match(/  function templateFileFromHash\(hash\) \{[\s\S]*?\n  \}\n/);
assert.ok(prefixMatch, "TEMPLATE_HASH_PREFIX must exist in index.html");
assert.ok(toHashMatch, "templateHash must exist in index.html");
assert.ok(fromHashMatch, "templateFileFromHash must exist in index.html");

const hashSource = prefixMatch[0] + toHashMatch[0] + fromHashMatch[0];

function run(source, expression) {
  const context = { result: undefined };
  vm.runInNewContext(source + "\nresult = " + expression + ";", context);
  return context.result;
}

// The parsed rows come back from another realm, so compare them as plain data.
const parse = (src) =>
  JSON.parse(
    JSON.stringify(run(parseMatch[0], "parseTemplateIndex(" + JSON.stringify(src) + ")"))
  );

const render = (src) =>
  run(
    escapeMatch[0] + inlineMatch[0] + mdMatch[0],
    "md(" + JSON.stringify(src) + ")"
  );

const hashRun = (expression) => run(hashSource, expression);

// ---------- template index ----------

test("reads the file, type and target of every template row", () => {
  const index = parse(
    [
      "| 파일 | 유형 | 대상 |",
      "|---|---|---|",
      "| `docs-impl.tbm.md` | 제품 문서 ↔ 구현 정합성 | 문서와 구현의 일치 |",
      "| `ac-e2e.tbm.md` | AC ↔ E2E 1:1 정합성 | AC와 e2e 파일의 전단사 |"
    ].join("\n")
  );

  assert.deepEqual(index, [
    {
      file: "docs-impl.tbm.md",
      name: "제품 문서 ↔ 구현 정합성",
      type: "제품 문서 ↔ 구현 정합성",
      target: "문서와 구현의 일치"
    },
    {
      file: "ac-e2e.tbm.md",
      name: "AC ↔ E2E 1:1 정합성",
      type: "AC ↔ E2E 1:1 정합성",
      target: "AC와 e2e 파일의 전단사"
    }
  ]);
});

test("ignores table rows that do not name a template file", () => {
  const index = parse(
    [
      "| 항목 | 규약 |",
      "|---|---|",
      "| id | `tbm_<slug>-docs-impl` |",
      "| checkPolicy | `{\"intervalSeconds\": 3600}` |",
      "",
      "| 파일 | 유형 | 대상 |",
      "|---|---|---|",
      "| `README.md` | 개요 | 슬롯 규약 |",
      "| `docs-impl.tbm.md` | 문서 ↔ 구현 | 일치 |"
    ].join("\n")
  );

  assert.deepEqual(
    index.map((t) => t.file),
    ["docs-impl.tbm.md"]
  );
});

test("a template listed twice is kept once", () => {
  const index = parse(
    [
      "| `docs-impl.tbm.md` | 첫 번째 | a |",
      "| `docs-impl.tbm.md` | 두 번째 | b |"
    ].join("\n")
  );

  assert.deepEqual(index.map((t) => t.type), ["첫 번째"]);
});

test("a template with no listed target still parses", () => {
  const index = parse("| `solo.tbm.md` | 유형만 |");
  assert.deepEqual(index, [
    { file: "solo.tbm.md", name: "유형만", type: "유형만", target: "" }
  ]);
});

test("an empty or missing index yields no templates", () => {
  assert.deepEqual(parse(""), []);
  assert.deepEqual(parse("템플릿이 아직 없습니다."), []);
});

// The page lists templates by parsing templates/README.md, so that table is the
// single source of truth for the list. This guards it against drifting from the
// files actually sitting in templates/.
test("the shipped index lists exactly the template files on disk", () => {
  const readme = readFileSync(
    new URL("../templates/README.md", import.meta.url),
    "utf8"
  );
  const listed = parse(readme).map((t) => t.file).sort();
  const onDisk = readdirSync(new URL("../templates/", import.meta.url))
    .filter((f) => f.endsWith(".tbm.md"))
    .sort();

  assert.ok(onDisk.length > 0, "templates/ must contain at least one template");
  assert.deepEqual(listed, onDisk);
});

test("every shipped template row carries a type and a target", () => {
  const readme = readFileSync(
    new URL("../templates/README.md", import.meta.url),
    "utf8"
  );

  for (const t of parse(readme)) {
    assert.ok(t.type, `${t.file} must have a type`);
    assert.ok(t.target, `${t.file} must have a target`);
  }
});

// ---------- template deep links ----------

test("a template deep link round-trips through the hash", () => {
  assert.equal(
    hashRun('templateFileFromHash(templateHash("docs-impl.tbm.md"))'),
    "docs-impl.tbm.md"
  );
});

test("a model id is not mistaken for a template link", () => {
  assert.equal(hashRun('templateFileFromHash("tbm_dear-baby-docs-impl")'), null);
  assert.equal(hashRun('templateFileFromHash("")'), null);
});

// ---------- markdown tables ----------
// The substance of a template lives in its slot table, so the renderer has to
// turn pipe tables into real tables rather than leaving raw pipes on screen.

test("a pipe table renders as a table with a header row", () => {
  const out = render(
    [
      "| 슬롯 | 의미 |",
      "|---|---|",
      "| `{{REPO}}` | owner/repo |",
      "| `{{SLUG}}` | 소문자 레포명 |"
    ].join("\n")
  );

  assert.match(out, /<table>/);
  assert.match(out, /<th>슬롯<\/th><th>의미<\/th>/);
  assert.match(out, /<td><code>\{\{REPO\}\}<\/code><\/td><td>owner\/repo<\/td>/);
  assert.equal(out.match(/<tr>/g).length, 3);
});

test("alignment markers in the delimiter row are accepted", () => {
  const out = render(["| a | b |", "| :--- | ---: |", "| 1 | 2 |"].join("\n"));
  assert.match(out, /<th>a<\/th><th>b<\/th>/);
  assert.match(out, /<td>1<\/td><td>2<\/td>/);
});

test("an escaped pipe stays inside its cell", () => {
  const out = render(["| 패턴 | 뜻 |", "|---|---|", "| a\\|b | 둘 중 하나 |"].join("\n"));
  assert.match(out, /<td>a\|b<\/td><td>둘 중 하나<\/td>/);
  assert.equal(out.match(/<td>/g).length, 2);
});

test("cell contents are escaped, not injected", () => {
  const out = render(["| x |", "|---|", "| <img src=x> |"].join("\n"));
  assert.match(out, /&lt;img src=x&gt;/);
  assert.doesNotMatch(out, /<img/);
});

test("a lone pipe line without a delimiter row stays a paragraph", () => {
  const out = render("| 이건 표가 아니다 |");
  assert.doesNotMatch(out, /<table>/);
  assert.match(out, /<p>/);
});

test("a table inside a fenced block is left as code", () => {
  const out = render(["```markdown", "| a | b |", "|---|---|", "```"].join("\n"));
  assert.doesNotMatch(out, /<table>/);
  assert.match(out, /<pre class="code">/);
});

test("prose around a table still renders", () => {
  const out = render(
    ["## 슬롯 표", "", "| a | b |", "|---|---|", "| 1 | 2 |", "", "끝."].join("\n")
  );

  assert.match(out, /<h2>슬롯 표<\/h2>/);
  assert.match(out, /<table>[\s\S]*<\/table>/);
  assert.match(out, /<p>끝\.<\/p>/);
});
