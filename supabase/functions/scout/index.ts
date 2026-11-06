// scout: Project Scout. The visitor describes a project in plain words and gets
// the papers in our database that are most relevant to it, best first, each with
// one line on why it fits, and an honest note for any need nothing covers.
//   1. Groq splits the description into 2-4 needs, each with a search phrase
//      (fallback: the whole description is one need). The page shows this split
//      first ({step: "split"}), the visitor can edit it, and the search call then
//      sends the edited needs back.
//   2. Hybrid search (meaning + keywords, hybrid_papers in schema.sql) for each
//      need, plus a meaning-only search for the whole description
//   3. The lists are merged with reciprocal rank fusion into up to 40 candidates
//   4. Groq scores each candidate's relevance (0-100) and writes why it fits
//      (fallback: the fused order, marked as not checked)
//   5. If a need has no strong paper, search once more with the ranker's
//      suggested phrases and score only the new papers (round 2)
// Steps 1-5 are an agent loop (_shared/scout_agent.ts) run as a LangGraph graph
// (_shared/scout_graph.ts). SCOUT_ENGINE=loop runs the same steps without
// LangGraph, and Scout falls back to that by itself if LangGraph fails to load.
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { db, guard, json, safely, underLimit } from "../_shared/http.ts";
import { groq } from "../_shared/groq.ts";
import {
  cleanDescription, descriptionProblem, type Match, type Library, MIN_SIMILARITY, type Need, NEEDS_PROMPT, parseNeeds,
  SOURCES, userNeeds,
} from "../_shared/scout.ts";
import { initialState, runScoutLoop, type ScoutDeps, type ScoutState } from "../_shared/scout_agent.ts";
import { runScoutGraph } from "../_shared/scout_graph.ts";

const model = new Supabase.ai.Session("gte-small");
const SCOUTS_PER_HOUR = 10;
const SPLITS_PER_HOUR = 20; // the split is one small LLM call, and people may redo it
const PER_QUERY = 30;
// "Watch this project" still compares new papers by meaning against this floor
const FLOOR = Number(Deno.env.get("SCOUT_MIN_SIMILARITY")) || MIN_SIMILARITY;
const ENGINE = (Deno.env.get("SCOUT_ENGINE") ?? "graph").trim().toLowerCase() === "loop" ? "loop" : "graph";
// Loaded while the worker boots, not inside a request; null when it fails or is switched off
const langgraph = ENGINE === "graph"
  ? import("../_shared/langgraph.ts").catch((e) => {
    console.error("LangGraph failed to load, Scout runs the plain loop", String(e));
    return null;
  })
  : Promise.resolve(null);

const deps: ScoutDeps = {
  groq: (system, user, maxTokens) => groq(system, user, maxTokens),
  search,
  async abstracts(ids) {
    const { data: rows } = await db.from("papers").select("id, abstract").in("id", ids);
    return new Map<string, string>((rows ?? []).map((r: { id: string; abstract: string }) => [r.id, r.abstract] as [string, string]));
  },
};

/** One Scout run on LangGraph, or on the plain loop. Same steps either way. */
async function runScout(state: ScoutState): Promise<{ result: ScoutState; engine: string }> {
  const lg = await langgraph;
  return lg ? { result: await runScoutGraph(lg, state, deps), engine: "langgraph" }
    : { result: await runScoutLoop(state, deps), engine: "loop" };
}

/** Hybrid search for one query. Keywords are skipped for the long description, where they add noise. */
async function search(text: string, withKeywords: boolean): Promise<Match[]> {
  const vector = await model.run(text, { mean_pool: true, normalize: true });
  const { data, error } = await db.rpc("hybrid_papers", {
    query_embedding: JSON.stringify(vector), query_text: withKeywords ? text : "", match_count: PER_QUERY,
  });
  if (error) throw new Error(error.message);
  return (data ?? []) as Match[];
}

/** What the library holds: paper count and the range of publication dates. Cached for an hour. Never fails. */
let libraryCache: { at: number; value: Library } | null = null;
async function library(): Promise<Library> {
  if (libraryCache && Date.now() - libraryCache.at < 3600_000) return libraryCache.value;
  const value: Library = { papers: null, from: null, to: null, sources: SOURCES };
  try {
    const [{ count }, first, last] = await Promise.all([
      db.from("papers").select("id", { count: "exact", head: true }),
      db.from("papers").select("submitted").not("submitted", "is", null).order("submitted", { ascending: true }).limit(1),
      db.from("papers").select("submitted").not("submitted", "is", null).order("submitted", { ascending: false }).limit(1),
    ]);
    value.papers = count ?? null;
    value.from = first.data?.[0]?.submitted ?? null;
    value.to = last.data?.[0]?.submitted ?? null;
    libraryCache = { at: Date.now(), value };
  } catch (e) {
    console.error("library scope", String(e));
  }
  return value;
}

Deno.serve(safely("scout", async (req) => {
  const blocked = guard(req);
  if (blocked) return blocked;

  const body = await req.json().catch(() => ({}));
  const description = cleanDescription(body.description);
  const problem = descriptionProblem(description);
  if (problem) return json(req, { error: problem }, 400);

  // Step 1 on its own: how Scout would split the project, for the visitor to check and edit
  if (body.step === "split") {
    if (!(await underLimit(req, "scout-split", SPLITS_PER_HOUR))) {
      return json(req, { error: "You've run Scout a lot in the last hour. Try again in a little while." }, 429);
    }
    try {
      const planned = parseNeeds(await groq(NEEDS_PROMPT, description, 400));
      return json(req, {
        version: 3, step: "split", planned: !!planned,
        summary: planned?.summary ?? "", needs: planned?.needs ?? [],
      });
    } catch (e) {
      console.error("scout split failed", String(e));
      // Still let the visitor write the parts themselves
      return json(req, { version: 3, step: "split", planned: false, summary: "", needs: [] });
    }
  }

  // Parts the visitor checked or edited, when the page sends them
  let edited: Need[] | null = null;
  if (body.needs !== undefined) {
    const checked = userNeeds(body.needs);
    if ("error" in checked) return json(req, { error: checked.error }, 400);
    edited = checked.needs;
  }

  if (!(await underLimit(req, "scout", SCOUTS_PER_HOUR))) {
    return json(req, { error: "You've run Scout a lot in the last hour. Try again in a little while." }, 429);
  }

  try {
    const started = Date.now();
    const summary = typeof body.summary === "string" ? cleanDescription(body.summary).slice(0, 300) : "";
    const { result: s, engine } = await runScout(initialState(description, edited ? { summary, needs: edited } : null));
    const ranking = s.ranking!;
    console.log(JSON.stringify({ scout: engine, ms: Date.now() - started, round: s.round, expanded: s.expanded.length }));

    const byId = new Map(s.candidates.map((c) => [c.id, c]));
    const plan = ranking.papers.map((p) => {
      const c = byId.get(p.id)!;
      return {
        ...p, title: c.title, authors: (c.authors ?? []).slice(0, 3), n_authors: (c.authors ?? []).length,
        categories: c.categories ?? [], submitted: c.submitted ?? null, first_seen: c.first_seen,
        code_url: c.code_url ?? null, hf_upvotes: c.hf_upvotes ?? 0, similarity: Math.round((c.similarity ?? 0) * 1000) / 1000,
      };
    });
    const scope = await library();
    return json(req, {
      version: 3,
      summary: s.summary,
      needs: s.needs.map((n) => ({ id: n.id, label: n.label, query: n.query })),
      edited: s.edited,
      coverage: s.coverage,
      plan,
      gaps: ranking.gaps,
      // Round 2: the phrases Scout searched again for, so the page can say so
      expanded: s.expanded.map((e) => e.query),
      rounds: s.round,
      engine,
      searched: scope.papers,
      library: scope,
      floor: FLOOR,
      mode: s.mode,
    });
  } catch (e) {
    console.error("scout failed", String(e));
    return json(req, { error: "Scout is unavailable right now. Try search by meaning on All papers." }, 500);
  }
}, "Scout is unavailable for a moment. Try again shortly, or use search by meaning on All papers."));
