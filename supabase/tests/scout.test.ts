// Run with: node --experimental-strip-types --test supabase/tests/scout.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  type Candidate, cleanDescription, coverageOf, descriptionProblem, fallbackRanking, fuseLists, looksLikeCode,
  type CaseMatch, MAX_NEEDS, type Match, type Need, parseNeeds, parseRanking, pickCases, rankInput, singleNeed, userNeeds,
} from "../functions/_shared/scout.ts";

const PLAIN = [
  "I want to build a voice notes app that transcribes speech offline on an Android phone, with no server.",
  "A tool that reads support tickets and suggests replies; it should run on a laptop without a GPU (<8GB RAM).",
  "Chatbot for my college library that answers questions from our PDF catalogue and cites the page.",
];
const CODE = [
  "import torch\nmodel = torch.load('x.pt')\nprint(model)",
  "def train(x):\n    return x + 1\n",
  "```python\nfoo()\n```",
  "function go(a) { return a.map(x => x * 2); }",
  "const app = express();\napp.get('/', (req, res) => { res.send('hi'); });",
  "<div class=\"card\"><span>{{ title }}</span></div>",
];

test("plain descriptions pass, code is rejected", () => {
  for (const t of PLAIN) assert.equal(looksLikeCode(t), false, t);
  for (const t of CODE) assert.equal(looksLikeCode(t), true, t);
  assert.match(descriptionProblem(CODE[0].padEnd(40, " "))!, /looks like code/);
  assert.match(descriptionProblem("too short")!, /at least/);
  assert.equal(descriptionProblem(PLAIN[0]), null);
  assert.equal(cleanDescription("  a \n\n b ".repeat(1)), "a b");
  assert.equal(cleanDescription("x".repeat(5000)).length, 1000);
});

test("needs need at least two usable items", () => {
  const ok = parseNeeds(JSON.stringify({ summary: "An offline voice app.", needs: [
    { label: "Speech to text", query: "on-device speech recognition" },
    { label: "Small model", query: "compact ASR model distillation" },
    { label: "Duplicate", query: "On-device speech recognition" },
    { label: "x", query: "too short label" },
  ] }));
  assert.deepEqual(ok!.needs.map((n) => [n.id, n.label]), [["n1", "Speech to text"], ["n2", "Small model"]]);
  assert.equal(ok!.summary, "An offline voice app.");
  assert.equal(parseNeeds('{"needs":[{"label":"Only one","query":"single search phrase"}]}'), null);
  assert.equal(parseNeeds("not json"), null);
  assert.equal(singleNeed(PLAIN[0])[0].id, "n1");
});

const m = (id: string, similarity = 0.8): Match => ({ id, title: `Paper ${id}`, similarity });
const NEEDS: Need[] = [
  { id: "n1", label: "Read the PDFs", query: "pdf document parsing" },
  { id: "n2", label: "Find the passage", query: "dense passage retrieval" },
  { id: "n3", label: "Cite the page", query: "attributed question answering" },
];

test("rank fusion rewards papers found by several searches and remembers their needs", () => {
  const fused = fuseLists([[m("a"), m("b"), m("c")], [m("b"), m("d")], [m("c"), m("b")]], ["n1", "n2", null]);
  assert.equal(fused[0].id, "b");                       // in all three lists
  assert.deepEqual(fused[0].needs, ["n1", "n2"]);       // the description search adds no need
  assert.deepEqual(fused.find((c) => c.id === "c")!.needs, ["n1"]);
  assert.equal(fuseLists([[m("a"), m("b")]], ["n1"], 1).length, 1);
});

test("the ranking keeps only known papers that clear the bar, best first", () => {
  const cands = fuseLists([[m("a"), m("b"), m("c"), m("d")]], ["n2"]);
  const raw = JSON.stringify({
    papers: [
      { id: "b", score: 72, needs: ["n2"], why: "A retriever that handles long scanned documents well." },
      { id: "a", score: 91, needs: ["n1", "n9"], why: "Turns PDFs into structured text with page numbers." },
      { id: "c", score: 40, needs: ["n2"], why: "Too weak to show, so it is dropped here." },
      { id: "zzz", score: 99, needs: ["n1"], why: "Not a candidate, so it must be ignored." },
      { id: "d", score: 88, needs: [], why: "short" },
      { id: "a", score: 95, needs: ["n1"], why: "A duplicate of a paper already kept above." },
    ],
    gaps: [{ need: "n3", try: ["citation grounding", "attributed QA"] }, { need: "n7", try: ["x y"] }],
  });
  const r = parseRanking(raw, cands, NEEDS)!;
  assert.deepEqual(r.papers.map((p) => [p.id, p.score, p.fit]), [["a", 91, "strong"], ["b", 72, "related"]]);
  assert.deepEqual(r.papers[0].needs, ["n1"]);
  assert.deepEqual(r.gaps, [{ need: "n3", try: ["citation grounding", "attributed QA"] }]);
  assert.equal(parseRanking("not json", cands, NEEDS), null);
});

test("a paper with no needs from the ranker keeps the needs its searches found", () => {
  const cands = fuseLists([[m("a")]], ["n2"]);
  const r = parseRanking(JSON.stringify({ papers: [{ id: "a", score: 300, why: "Retrieval method built for long library catalogues." }] }), cands, NEEDS)!;
  assert.deepEqual([r.papers[0].score, r.papers[0].needs], [100, ["n2"]]);
});

test("coverage says which needs have strong papers, only related ones, or nothing", () => {
  const cov = coverageOf(NEEDS, [
    { id: "a", score: 90, fit: "strong", needs: ["n1"], why: "" },
    { id: "b", score: 60, fit: "related", needs: ["n1", "n2"], why: "" },
  ]);
  assert.deepEqual(cov.map((c) => [c.need, c.status, c.strong, c.related]),
    [["n1", "covered", 1, 1], ["n2", "partial", 0, 1], ["n3", "missing", 0, 0]]);
});

test("without the ranker the fused order is shown, marked as not checked", () => {
  const cands = fuseLists([[m("a"), m("b")]], ["n1"]);
  const r = fallbackRanking(cands);
  assert.deepEqual(r.papers.map((p) => [p.id, p.fit, p.score]), [["a", "unchecked", null], ["b", "unchecked", null]]);
});

test("the ranking request carries the needs and cut abstracts", () => {
  const cands: Candidate[] = fuseLists([[m("a")]], ["n1"]);
  cands[0].abstract = "word ".repeat(400);
  const text = rankInput("My project", NEEDS, cands);
  assert.match(text, /n3: Cite the page/);
  assert.ok(text.length < 1200);
  assert.deepEqual(singleNeed("x".repeat(400))[0].query.length, 300);
});

test("coverage says how many papers each need's search brought in", () => {
  const cands = fuseLists([[m("a"), m("b")], [m("b")], []], ["n1", "n2", "n3"]);
  const cov = coverageOf(NEEDS, [{ id: "a", score: 90, fit: "strong", needs: ["n1"], why: "" }], cands);
  assert.deepEqual(cov.map((c) => [c.need, c.status, c.considered]), [["n1", "covered", 2], ["n2", "missing", 1], ["n3", "missing", 0]]);
  assert.equal(coverageOf(NEEDS, [])[0].considered, 0); // older callers without candidates
});

test("parts edited by the visitor are cleaned, numbered and checked", () => {
  const ok = userNeeds([
    { label: "  Speech to text ", query: "on-device speech recognition" },
    { label: "", query: "small language models on phones" },          // label falls back to the query
    { label: "Dup", query: "On-device speech recognition" },           // same search twice
    { label: "Empty", query: "   " },                                  // empty rows are skipped
  ]);
  assert.ok("needs" in ok);
  if ("needs" in ok) {
    assert.deepEqual(ok.needs.map((n) => [n.id, n.label, n.query]), [
      ["n1", "Speech to text", "on-device speech recognition"],
      ["n2", "small language models on phones", "small language models on phones"],
    ]);
  }
  assert.match((userNeeds([]) as { error: string }).error, /at least one/);
  assert.match((userNeeds("x") as { error: string }).error, /list/);
  assert.match((userNeeds([{ label: "x", query: "import torch\nmodel = torch.load('x')" }]) as { error: string }).error, /plain words/);
  assert.match((userNeeds([{ label: "x", query: "word ".repeat(20) }]) as { error: string }).error, /under/);
  const many = Array.from({ length: MAX_NEEDS + 1 }, (_, i) => ({ label: `Part ${i}`, query: `search phrase number ${i}` }));
  assert.match((userNeeds(many) as { error: string }).error, /at most/);
});

const CASE = (url: string, similarity: number, extra: Partial<CaseMatch> = {}): CaseMatch => ({
  url, company: "Acme", title: `Write-up ${url}`, published: "2026-10-01", problem: "rag",
  summary: "", issue: "", result: "", tags: [], similarity, ...extra,
});

test("case studies: close to the project, best first, tagged with the parts they match", () => {
  const needs: Need[] = [
    { id: "n1", label: "Read the PDFs", query: "PDF document parsing with page layout" },
    { id: "n2", label: "Find the right passage", query: "retrieval reranking for question answering" },
  ];
  const picked = pickCases([
    CASE("b", 0.80, { title: "Reranking passages at scale", tags: ["Reranking"] }),
    CASE("a", 0.83, { title: "Parsing millions of PDF invoices", summary: "Layout-aware document parsing." }),
    CASE("far", 0.70),
    CASE("tail", 0.765),
  ], needs);
  assert.deepEqual(picked.map((c) => c.url), ["a", "b"]);
  assert.deepEqual(picked[0].needs, ["n1"]);
  assert.deepEqual(picked[1].needs, ["n2"]);
});

test("case studies: nothing close enough means none, and repeats are dropped", () => {
  assert.deepEqual(pickCases([CASE("a", 0.6)], []), []);
  assert.deepEqual(pickCases([], []), []);
  const twice = pickCases([CASE("a", 0.9, { title: "Same" }), CASE("b", 0.89, { title: "Same" })], []);
  assert.equal(twice.length, 1);
  const many = pickCases(Array.from({ length: 10 }, (_, i) => CASE(`u${i}`, 0.9 - i * 0.001)), []);
  assert.equal(many.length, 6);
});
