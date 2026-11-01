// scout: Project Scout. The visitor describes a project in plain words and gets
// the papers in our database that are most relevant to it, best first, each with
// one line on why it fits, and an honest note for any need nothing covers.
//   1. Groq splits the description into 2-4 needs, each with a search phrase
//      (fallback: the whole description is one need)
//   2. Hybrid search (meaning + keywords, hybrid_papers in schema.sql) for each
//      need, plus a meaning-only search for the whole description
//   3. The lists are merged with reciprocal rank fusion into up to 40 candidates
//   4. Groq scores each candidate's relevance (0-100) and writes why it fits
//      (fallback: the fused order, marked as not checked)
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { db, guard, json, underLimit } from "../_shared/http.ts";
import { groq } from "../_shared/groq.ts";
import {
  type Candidate, cleanDescription, coverageOf, descriptionProblem, fallbackRanking, fuseLists, type Match,
  MIN_SIMILARITY, NEEDS_PROMPT, parseNeeds, parseRanking, RANK_PROMPT, rankInput, singleNeed,
} from "../_shared/scout.ts";

const model = new Supabase.ai.Session("gte-small");
const SCOUTS_PER_HOUR = 10;
const PER_QUERY = 30;
// "Watch this project" still compares new papers by meaning against this floor
const FLOOR = Number(Deno.env.get("SCOUT_MIN_SIMILARITY")) || MIN_SIMILARITY;

/** Hybrid search for one query. Keywords are skipped for the long description, where they add noise. */
async function search(text: string, withKeywords: boolean): Promise<Match[]> {
  const vector = await model.run(text, { mean_pool: true, normalize: true });
  const { data, error } = await db.rpc("hybrid_papers", {
    query_embedding: JSON.stringify(vector), query_text: withKeywords ? text : "", match_count: PER_QUERY,
  });
  if (error) throw new Error(error.message);
  return (data ?? []) as Match[];
}

Deno.serve(async (req) => {
  const blocked = guard(req);
  if (blocked) return blocked;

  const body = await req.json().catch(() => ({}));
  const description = cleanDescription(body.description);
  const problem = descriptionProblem(description);
  if (problem) return json(req, { error: problem }, 400);

  if (!(await underLimit(req, "scout", SCOUTS_PER_HOUR))) {
    return json(req, { error: "You've run Scout a lot in the last hour. Try again in a little while." }, 429);
  }

  try {
    // 1. Split the project into needs
    const planned = parseNeeds(await groq(NEEDS_PROMPT, description, 400));
    const needs = planned?.needs ?? singleNeed(description);

    // 2. Search for each need, then the whole description (one at a time: the free plan limits CPU per request)
    const lists: Match[][] = [];
    const queryNeeds: (string | null)[] = [];
    for (const n of needs) {
      lists.push(await search(n.query, true));
      queryNeeds.push(n.id);
    }
    if (planned) {
      lists.push(await search(description.slice(0, 600), false));
      queryNeeds.push(null);
    }

    // 3. Merge into one candidate list
    const candidates: Candidate[] = fuseLists(lists, queryNeeds);

    // 4. Score relevance and explain each fit
    let ranking = null;
    if (candidates.length) {
      const { data: rows } = await db.from("papers").select("id, abstract").in("id", candidates.map((c) => c.id));
      const abstracts = new Map<string, string>((rows ?? []).map((r: { id: string; abstract: string }) => [r.id, r.abstract] as [string, string]));
      candidates.forEach((c) => { c.abstract = abstracts.get(c.id) ?? ""; });
      ranking = parseRanking(await groq(RANK_PROMPT, rankInput(description, needs, candidates), 2400), candidates, needs);
    }
    const mode = ranking ? "ai" : "basic";
    ranking = ranking ?? fallbackRanking(candidates);

    const byId = new Map(candidates.map((c) => [c.id, c]));
    const plan = ranking.papers.map((p) => {
      const c = byId.get(p.id)!;
      return {
        ...p, title: c.title, authors: (c.authors ?? []).slice(0, 3), n_authors: (c.authors ?? []).length,
        categories: c.categories ?? [], submitted: c.submitted ?? null, first_seen: c.first_seen,
        code_url: c.code_url ?? null, hf_upvotes: c.hf_upvotes ?? 0, similarity: Math.round((c.similarity ?? 0) * 1000) / 1000,
      };
    });
    const { count } = await db.from("papers").select("id", { count: "exact", head: true });
    return json(req, {
      version: 3,
      summary: planned?.summary ?? "",
      needs: needs.map((n) => ({ id: n.id, label: n.label, query: n.query })),
      coverage: coverageOf(needs, ranking.papers),
      plan,
      gaps: ranking.gaps,
      searched: count ?? null,
      floor: FLOOR,
      mode,
    });
  } catch (e) {
    console.error("scout failed", String(e));
    return json(req, { error: "Scout is unavailable right now. Try search by meaning on All papers." }, 500);
  }
});
