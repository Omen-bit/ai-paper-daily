// scout-spike: measures what LangGraph costs inside an edge function, so Scout's
// graph can be checked against the free plan's CPU limit (about 2s per request)
// without touching the real Scout. Only callers with SYNC_SECRET get in.
// It loads LangGraph, then runs Scout's graph three times with fake search and
// LLM steps, and reports the time each part took. The first call after a deploy
// is the cold one.
//   curl -X POST -H "x-sync-secret: $SYNC_SECRET" https://<project>.supabase.co/functions/v1/scout-spike
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { json, safely, sameSecret } from "../_shared/http.ts";
import { initialState, type ScoutDeps } from "../_shared/scout_agent.ts";
import { runScoutGraph } from "../_shared/scout_graph.ts";

const SYNC_SECRET = Deno.env.get("SYNC_SECRET") ?? "";
const bootedAt = performance.now();
let calls = 0;

const fake: ScoutDeps = {
  groq: async () => null, // no LLM: the ranker falls back, which still runs every step but expand_search
  search: async (text) => [{ id: `2611.${String(text.length).padStart(5, "0")}`, title: "Fake", similarity: 0.8 }],
  abstracts: async (ids) => new Map(ids.map((id) => [id, "A fake abstract."])),
};

Deno.serve(safely("scout-spike", async (req) => {
  if (!sameSecret(req.headers.get("x-sync-secret") ?? "", SYNC_SECRET)) {
    return json(req, { error: "Only the project owner can run the spike." }, 401);
  }
  calls += 1;
  const t0 = performance.now();
  const lg = await import("../_shared/langgraph.ts");
  const t1 = performance.now();
  const runs: number[] = [];
  for (let i = 0; i < 3; i++) {
    const s = performance.now();
    await runScoutGraph(lg, initialState("An offline voice notes app for Android that tags notes by topic."), fake);
    runs.push(Math.round(performance.now() - s));
  }
  return json(req, {
    cold: calls === 1,
    since_boot_ms: Math.round(t0 - bootedAt),
    load_langgraph_ms: Math.round(t1 - t0),
    graph_runs_ms: runs,
    note: "Times are wall-clock; with no network calls inside, they are close to CPU time.",
  });
}));
