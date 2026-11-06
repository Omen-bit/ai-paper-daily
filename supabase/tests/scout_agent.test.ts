// Run with: node --experimental-strip-types --test supabase/tests/scout_agent.test.ts
// The graph tests need LangGraph from npm (npm install --no-save @langchain/langgraph@1.5.1
// @langchain/core zod) and are skipped without it.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  expansionQueries, initialState, MAX_EXPANSIONS, mergeRankings, runScoutLoop, type ScoutDeps,
} from "../functions/_shared/scout_agent.ts";
import { buildScoutGraph, NODES, runScoutGraph } from "../functions/_shared/scout_graph.ts";
import { type Match, NEEDS_PROMPT } from "../functions/_shared/scout.ts";

const DESCRIPTION = "An offline voice notes app for Android that transcribes speech and tags each note by topic.";
const NEEDS = { summary: "Offline voice notes.", needs: [
  { label: "Speech to text", query: "on-device speech recognition" },
  { label: "Topic tags", query: "short text topic classification" },
] };

const m = (id: string): Match => ({ id, title: `Paper ${id}`, similarity: 0.8 });

/** A fake world: search results by query, and a ranker that scores the papers it is shown. */
function fakeDeps(opts: { scores: Record<string, [number, string[]]>; gaps?: unknown; failRank?: number[] }) {
  const calls = { searches: [] as string[], ranks: [] as string[][], groq: 0 };
  const results: Record<string, Match[]> = {
    "on-device speech recognition": [m("2611.00001"), m("2611.00002")],
    "short text topic classification": [m("2611.00003")],
    "zero-shot note tagging": [m("2611.00009"), m("2611.00001")],
    "keyword extraction small models": [m("2611.00010")],
  };
  const deps: ScoutDeps = {
    async groq(system, user) {
      calls.groq++;
      if (system === NEEDS_PROMPT) return JSON.stringify(NEEDS);
      const ids = [...user.matchAll(/^id: (\S+)$/gm)].map((x) => x[1]);
      calls.ranks.push(ids);
      if (opts.failRank?.includes(calls.ranks.length)) return null;
      const papers = ids.filter((id) => opts.scores[id]).map((id) => ({
        id, score: opts.scores[id][0], needs: opts.scores[id][1], why: `Gives this project a working ${id} method.`,
      }));
      return JSON.stringify({ papers, gaps: calls.ranks.length === 1 ? opts.gaps ?? [] : [] });
    },
    async search(text) {
      calls.searches.push(text);
      return results[text] ?? [m("2611.00004")];
    },
    async abstracts(ids) {
      return new Map(ids.map((id) => [id, `Abstract of ${id}.`]));
    },
  };
  return { deps, calls };
}

const GAP = [{ need: "n2", try: ["zero-shot note tagging", "keyword extraction small models"] }];

test("one round when every need has a strong paper", async () => {
  const { deps, calls } = fakeDeps({ scores: { "2611.00001": [90, ["n1"]], "2611.00003": [85, ["n2"]] } });
  const s = await runScoutLoop(initialState(DESCRIPTION), deps);
  assert.equal(s.round, 1);
  assert.deepEqual(s.expanded, []);
  assert.equal(calls.searches.length, 3); // two needs and the whole description
  assert.equal(calls.ranks.length, 1);
  assert.deepEqual(s.coverage.map((c) => c.status), ["covered", "covered"]);
  assert.equal(s.mode, "ai");
});

test("a gap triggers a second search, and the new paper fills it", async () => {
  const { deps, calls } = fakeDeps({
    scores: { "2611.00001": [90, ["n1"]], "2611.00003": [60, ["n2"]], "2611.00009": [88, ["n2"]] },
    gaps: GAP,
  });
  const s = await runScoutLoop(initialState(DESCRIPTION), deps);
  assert.equal(s.round, 2);
  assert.deepEqual(s.expanded.map((e) => e.query), GAP[0].try);
  // The second ranking reads only papers round 1 hadn't seen
  assert.deepEqual(calls.ranks[1].sort(), ["2611.00009", "2611.00010"]);
  assert.deepEqual(s.ranking!.papers.map((p) => p.id), ["2611.00001", "2611.00009", "2611.00003"]);
  assert.deepEqual(s.coverage.map((c) => c.status), ["covered", "covered"]);
  assert.deepEqual(s.ranking!.gaps, []);
  // A round 1 paper that round 2 found again is now credited to that need too
  assert.ok(s.candidates.find((c) => c.id === "2611.00001")!.needs.includes("n2"));
});

test("a failed second ranking keeps the first", async () => {
  const { deps } = fakeDeps({ scores: { "2611.00001": [90, ["n1"]] }, gaps: GAP, failRank: [2] });
  const s = await runScoutLoop(initialState(DESCRIPTION), deps);
  assert.equal(s.round, 2);
  assert.deepEqual(s.ranking!.papers.map((p) => p.id), ["2611.00001"]);
  assert.deepEqual(s.coverage.map((c) => c.status), ["covered", "missing"]);
});

test("no second round without the ranker, and the fused order is returned unchecked", async () => {
  const { deps, calls } = fakeDeps({ scores: {}, gaps: GAP, failRank: [1] });
  const s = await runScoutLoop(initialState(DESCRIPTION), deps);
  assert.equal(s.mode, "basic");
  assert.equal(calls.ranks.length, 1);
  assert.ok(s.ranking!.papers.every((p) => p.fit === "unchecked"));
});

test("edited needs skip the planner", async () => {
  const { deps, calls } = fakeDeps({ scores: { "2611.00001": [90, ["n1"]] } });
  const edited = { summary: "Mine.", needs: [{ id: "n1", label: "Speech", query: "on-device speech recognition" }] };
  const s = await runScoutLoop(initialState(DESCRIPTION, edited), deps);
  assert.equal(s.summary, "Mine.");
  assert.equal(calls.searches[0], "on-device speech recognition");
  assert.equal(calls.groq, 1); // the ranker only
});

test("expansion phrases are spread across gaps, capped and never repeat a search", () => {
  const s = initialState(DESCRIPTION, { summary: "", needs: [
    { id: "n1", label: "A", query: "alpha" }, { id: "n2", label: "B", query: "beta" },
  ] });
  s.ranking = { papers: [], gaps: [{ need: "n1", try: ["alpha", "a2", "a3"] }, { need: "n2", try: ["b1", "b2"] }] };
  const qs = expansionQueries(s);
  assert.equal(qs.length, MAX_EXPANSIONS);
  assert.deepEqual(qs.map((q) => q.query), ["b1", "a2", "b2"]);
});

test("merging keeps the best papers and drops gaps that were filled", () => {
  const r = (id: string, score: number, needs: string[]) =>
    ({ id, score, fit: score >= 80 ? "strong" as const : "related" as const, needs, why: "x" });
  const merged = mergeRankings(
    { papers: [r("a", 70, ["n1"]), r("b", 90, ["n2"])], gaps: [{ need: "n1", try: ["x"] }, { need: "n3", try: ["y"] }] },
    { papers: [r("c", 85, ["n1"])], gaps: [{ need: "n3", try: ["z"] }] },
  );
  assert.deepEqual(merged.papers.map((p) => p.id), ["b", "c", "a"]);
  assert.deepEqual(merged.gaps, [{ need: "n3", try: ["z"] }]);
});

// ---------- The LangGraph engine ----------

// deno-lint-ignore no-explicit-any
let lg: any = null;
try {
  lg = await import("@langchain/langgraph/web");
} catch { /* not installed: the graph tests are skipped */ }

test("the graph has the documented steps", { skip: !lg && "LangGraph not installed" }, () => {
  const { deps } = fakeDeps({ scores: {} });
  const nodes = Object.keys(buildScoutGraph(lg, deps, initialState(DESCRIPTION)).getGraph().nodes);
  for (const n of NODES) assert.ok(nodes.includes(n), n);
});

test("the graph and the hand-run loop give the same answer", { skip: !lg && "LangGraph not installed" }, async () => {
  const cases = [
    { scores: { "2611.00001": [90, ["n1"]], "2611.00003": [85, ["n2"]] } },
    { scores: { "2611.00001": [90, ["n1"]], "2611.00003": [60, ["n2"]], "2611.00009": [88, ["n2"]] }, gaps: GAP },
    { scores: {}, gaps: GAP, failRank: [1] },
  ] as Parameters<typeof fakeDeps>[0][];
  for (const opts of cases) {
    const a = await runScoutLoop(initialState(DESCRIPTION), fakeDeps(opts).deps);
    const b = await runScoutGraph(lg, initialState(DESCRIPTION), fakeDeps(opts).deps);
    assert.deepEqual(
      { ranking: b.ranking, coverage: b.coverage, expanded: b.expanded, round: b.round, mode: b.mode },
      { ranking: a.ranking, coverage: a.coverage, expanded: a.expanded, round: a.round, mode: a.mode },
    );
  }
});
