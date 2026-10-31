// Run with: node --experimental-strip-types --test supabase/tests/scout.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  cleanDescription, descriptionProblem, fallbackPlan, looksLikeCode, mergeMatches, parsePlan, parseQueries,
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

test("queries need at least two usable phrases", () => {
  const ok = parseQueries('{"summary":"An offline voice app.","queries":["on-device speech recognition","small ASR models","on-device speech recognition"]}');
  assert.deepEqual(ok, { summary: "An offline voice app.", queries: ["on-device speech recognition", "small ASR models"] });
  assert.equal(parseQueries('{"queries":["only one"]}'), null);
  assert.equal(parseQueries("not json"), null);
});

const m = (id: string, similarity: number, code_url: string | null = null) => ({ id, title: id, similarity, code_url });

test("matches merge by best similarity and reward repeats", () => {
  const merged = mergeMatches([[m("a", 0.80), m("b", 0.79)], [m("b", 0.78), m("c", 0.70)]]);
  assert.deepEqual(merged.map((c) => c.id), ["b", "a", "c"]);
  assert.equal(merged[0].hits, 2);
});

test("plan keeps only known ids, valid stages and orders by stage", () => {
  const raw = JSON.stringify({ plan: [
    { id: "c", stage: "core", reason: "Shows how to shrink the model for phones." },
    { id: "zzz", stage: "start", reason: "Invented paper that is not a candidate." },
    { id: "a", stage: "start", reason: "Explains the basic speech pipeline simply." },
    { id: "b", stage: "further", reason: "Adds speaker labels once the basics work." },
    { id: "a", stage: "core", reason: "Duplicate entry that should be dropped." },
  ] });
  const plan = parsePlan(raw, ["a", "b", "c"]);
  assert.deepEqual(plan!.map((s) => [s.id, s.stage]), [["a", "start"], ["c", "core"], ["b", "further"]]);
  assert.equal(parsePlan('{"plan":[]}', ["a"]), null);
  const fb = fallbackPlan(mergeMatches([[m("a", .9), m("b", .8), m("c", .7)]]));
  assert.deepEqual(fb.map((s) => s.stage), ["start", "start", "core"]);
});
