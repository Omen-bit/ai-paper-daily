// Run with: node --experimental-strip-types --test supabase/tests/scout.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  type Candidate, cleanDescription, descriptionProblem, fallbackReport, looksLikeCode, mergeMatches, type Need,
  parseNeeds, parseReport, planInput, singleNeed,
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

const m = (id: string, similarity: number, code_url: string | null = null) => ({ id, title: id, similarity, code_url });

test("matches merge by need, reward repeats and drop weak ones", () => {
  const merged = mergeMatches([[m("a", 0.80), m("b", 0.79)], [m("b", 0.78), m("c", 0.70)]], 10, ["n1", "n2"], 0.74);
  assert.deepEqual(merged.map((c) => c.id), ["b", "a"]); // c is below the floor
  assert.deepEqual(merged[0].needs, ["n1", "n2"]);
  assert.equal(merged[0].hits, 2);
});

const NEEDS: Need[] = [
  { id: "n1", label: "Speech to text", query: "on-device speech recognition" },
  { id: "n2", label: "Runs on Android", query: "mobile deployment of neural networks" },
];
const CANDS = (ids: string[]): Candidate[] => ids.map((id) => ({ ...m(id, 0.8), hits: 1, needs: ["n1"] }));

test("only papers that fit are kept, and the verdict is worked out from them", () => {
  const raw = JSON.stringify({
    papers: [
      { id: "c", fit: "partial", needs: ["n2"], stage: "core", reason: "Shows how to shrink a model for phones.", approach: "Quantises weights to 4 bits" },
      { id: "zzz", fit: "direct", needs: ["n1"], stage: "start", reason: "Invented paper that is not a candidate." },
      { id: "a", fit: "direct", needs: ["n1", "n9"], stage: "start", reason: "A small speech model that runs offline.", requires: "One GPU to train", result: "word ".repeat(40) },
      { id: "b", fit: "none", needs: ["n1"], stage: "further", reason: "Rated not relevant by the planner." },
      { id: "d", fit: "direct", needs: [], stage: "core", reason: "Serves no need, so it is dropped." },
    ],
    coverage: [{ need: "n1", note: "Paper a covers offline speech." }, { need: "n2", note: "Only general phone tricks." }],
    steps: [
      { title: "Pick a small model", detail: "Start from the distilled model in paper a.", papers: ["a", "zzz"] },
      { title: "Ship to Android", detail: "Package with an on-device runtime; no paper covers this.", papers: [] },
    ],
    you_need: ["A GPU for training", "LibriSpeech"], watch_out: ["Accents hurt accuracy."], try: ["android speech recognition"],
  });
  const r = parseReport(raw, CANDS(["a", "b", "c", "d"]), NEEDS)!;
  assert.deepEqual(r.papers.map((p) => [p.id, p.fit, p.stage]), [["a", "direct", "start"], ["c", "partial", "core"]]);
  assert.deepEqual(r.papers[0].needs, ["n1"]);
  assert.equal(r.papers[0].result, ""); // too long to be a real result
  assert.deepEqual(r.coverage.map((c) => c.status), ["covered", "partly"]);
  assert.equal(r.verdict, "partial");
  assert.deepEqual(r.steps[0].papers, ["a"]);
  assert.deepEqual(r.steps[1].papers, []);
  assert.deepEqual(r.try, ["android speech recognition"]);
});

test("no fitting papers gives an honest empty answer", () => {
  const r = parseReport(JSON.stringify({ papers: [], coverage: [], steps: [{ title: "x", detail: "y", papers: [] }], try: ["speech apps"] }),
    CANDS(["a"]), NEEDS)!;
  assert.equal(r.verdict, "none");
  assert.deepEqual(r.papers, []);
  assert.deepEqual(r.steps, []);
  assert.deepEqual(r.coverage.map((c) => c.status), ["missing", "missing"]);
  assert.deepEqual(r.try, ["speech apps"]);
  assert.equal(parseReport("not json", [], NEEDS), null);
});

test("all needs covered by direct fits is a good match", () => {
  const raw = JSON.stringify({ papers: [
    { id: "a", fit: "direct", needs: ["n1"], stage: "start", reason: "Covers offline speech recognition well." },
    { id: "b", fit: "direct", needs: ["n2"], stage: "core", reason: "Covers running models on Android phones." },
  ] });
  assert.equal(parseReport(raw, CANDS(["a", "b"]), NEEDS)!.verdict, "good");
});

test("without the planner the closest papers are partial fits", () => {
  const fb = fallbackReport(mergeMatches([[m("a", .9), m("b", .8)], [m("c", .78)]], 10, ["n1", "n2"]), NEEDS);
  assert.deepEqual(fb.papers.map((p) => p.stage), ["start", "start", "core"]);
  assert.ok(fb.papers.every((p) => p.fit === "partial"));
  assert.deepEqual(fb.coverage.map((c) => c.status), ["partly", "partly"]);
  assert.equal(fallbackReport([], NEEDS).verdict, "none");
  assert.match(planInput("Project", NEEDS, CANDS(["a"])), /n2: Runs on Android[\s\S]*code released: no/);
});
