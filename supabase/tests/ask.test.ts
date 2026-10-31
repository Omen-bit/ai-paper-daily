// Run with: node --experimental-strip-types --test supabase/tests/ask.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { askInput, cleanQuestion, findQuote, NOT_IN_ABSTRACT, paperDetails, parseAnswer, sentences } from "../functions/_shared/ask.ts";

const ABSTRACT = "We present a distilled speech model for phones. Existing methods need large compute budgets. " +
  "Our approach reduces memory use by 48% while matching the accuracy of strong baselines on four benchmarks. We release code.";

test("abstract splits into sentences", () => {
  assert.equal(sentences(ABSTRACT).length, 4);
  assert.equal(cleanQuestion("  what   is new? ".repeat(1)), "what is new?");
});

test("quotes must come from the abstract", () => {
  assert.equal(findQuote("reduces memory use by 48% while matching the accuracy", ABSTRACT), sentences(ABSTRACT)[2]);
  assert.equal(findQuote("Our approach cuts memory use by 48% while matching the accuracy of strong baselines on four benchmarks.", ABSTRACT), sentences(ABSTRACT)[2]);
  assert.equal(findQuote("It runs on the moon with no power at all.", ABSTRACT), null);
  assert.equal(findQuote("", ABSTRACT), null);
});

test("answers are parsed safely", () => {
  const ok = parseAnswer(JSON.stringify({ answerable: true, answer: "It uses about half the memory.", quote: "reduces memory use by 48%" }), ABSTRACT);
  assert.equal(ok!.answer, "It uses about half the memory.");
  assert.equal(ok!.quote, sentences(ABSTRACT)[2]);
  const made_up = parseAnswer(JSON.stringify({ answerable: true, answer: "It was trained on 10,000 GPUs.", quote: "We trained on ten thousand GPUs for a year." }), ABSTRACT);
  assert.equal(made_up!.quote, null);
  assert.deepEqual(parseAnswer('{"answerable": false, "answer": "", "quote": ""}', ABSTRACT),
    { answer: NOT_IN_ABSTRACT, quote: null, answerable: false });
  assert.equal(parseAnswer("nope", ABSTRACT), null);
  assert.equal(parseAnswer(JSON.stringify({ answer: "word ".repeat(120) }), ABSTRACT), null);
});


test("Ask knows who wrote the paper and when it came out", () => {
  const d = paperDetails({ authors: ["Ana Smith", "Bo Li", "Chen Wu"], submitted: "2026-10-12" });
  assert.equal(d, "The paper was written by 3 authors: Ana Smith, Bo Li and Chen Wu. It came out on arXiv on 12 October 2026.");
  assert.equal(paperDetails({ authors: ["Solo Author"] }), "The paper was written by Solo Author.");
  const many = paperDetails({ authors: Array.from({ length: 35 }, (_, i) => `Person ${i}`) });
  assert.match(many, /35 authors: Person 0, .*Person 29 and 5 others\./);
  assert.equal(paperDetails({}), "");
  assert.match(askInput("T", "A.", "Who wrote it?", undefined, d), /About this paper: The paper was written by 3 authors/);
  const raw = JSON.stringify({ answerable: true, answer: "Ana Smith, Bo Li and Chen Wu.", quote: "The paper was written by 3 authors: Ana Smith, Bo Li and Chen Wu." });
  assert.ok(parseAnswer(raw, `${d}\n${ABSTRACT}`)!.quote);
});
