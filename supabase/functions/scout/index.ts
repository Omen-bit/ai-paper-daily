// scout: Project Scout. The visitor describes a project in plain words and gets an
// honest answer: which of its needs our papers cover, the papers that really fit
// (none, if nothing does), build steps, and a comparison of the papers.
//   1. Groq splits the description into 2-4 needs, each with a search phrase
//      (fallback: the whole description is one need)
//   2. Each need is embedded with gte-small and matched against the papers;
//      very weak matches are dropped
//   3. Groq rates each candidate (direct fit, partial fit, or left out) and writes
//      the brief (fallback: the closest papers, marked as not checked)
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { db, guard, json, underLimit } from "../_shared/http.ts";
import {
  type Candidate, cleanDescription, descriptionProblem, fallbackReport, type Match, MIN_SIMILARITY, mergeMatches,
  NEEDS_PROMPT, parseNeeds, parseReport, PLAN_PROMPT, planInput, singleNeed,
} from "../_shared/scout.ts";

const model = new Supabase.ai.Session("gte-small");
const SCOUTS_PER_HOUR = 10;
const GROQ_KEY = Deno.env.get("GROQ_API_KEY") ?? "";
const GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"];
// Can be tuned without a code change: set SCOUT_MIN_SIMILARITY as a Supabase secret
const FLOOR = Number(Deno.env.get("SCOUT_MIN_SIMILARITY")) || MIN_SIMILARITY;

/** One JSON-mode Groq call, trying each model in turn. Returns the raw text or null. */
async function groq(system: string, user: string, maxTokens: number): Promise<string | null> {
  if (!GROQ_KEY) return null;
  for (const m of GROQ_MODELS) {
    try {
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { "Authorization": `Bearer ${GROQ_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          model: m, temperature: 0.2, max_tokens: maxTokens,
          response_format: { type: "json_object" },
          messages: [{ role: "system", content: system }, { role: "user", content: user }],
        }),
        signal: AbortSignal.timeout(25000),
      });
      if (!res.ok) {
        console.error("groq", m, res.status);
        continue;
      }
      const data = await res.json();
      const text = data?.choices?.[0]?.message?.content;
      if (typeof text === "string" && text.trim()) return text;
    } catch (e) {
      console.error("groq", m, String(e));
    }
  }
  return null;
}

async function match(text: string): Promise<Match[]> {
  const vector = await model.run(text, { mean_pool: true, normalize: true });
  const { data, error } = await db.rpc("match_papers", { query_embedding: JSON.stringify(vector), match_count: 8 });
  if (error) throw new Error(error.message);
  return (data ?? []) as Match[];
}

/** Setup and limitation passages for papers whose full text Ask has already saved. Never fails. */
async function fullTextNotes(ids: string[]): Promise<Map<string, string>> {
  const notes = new Map<string, string>();
  try {
    const { data } = await db.from("paper_sections").select("paper_id, heading, body").in("paper_id", ids)
      .or("heading.ilike.*limit*,heading.ilike.*setup*,heading.ilike.*implementation*,heading.ilike.*training detail*")
      .order("idx").limit(60);
    for (const row of (data ?? []) as { paper_id: string; heading: string; body: string }[]) {
      const have = notes.get(row.paper_id) ?? "";
      if (have.length < 450) notes.set(row.paper_id, `${have} ${row.heading}: ${row.body}`.trim().slice(0, 500));
    }
  } catch (e) {
    console.error("fulltext notes", String(e));
  }
  return notes;
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

    // 2. Search for each need (one at a time: the free plan limits CPU per request)
    const lists: Match[][] = [];
    for (const n of needs) lists.push(await match(n.query));
    const candidates: Candidate[] = mergeMatches(lists, 10, needs.map((n) => n.id), FLOOR);

    // 3. Rate the candidates and write the brief
    let report = null;
    if (candidates.length) {
      const ids = candidates.map((c) => c.id);
      const { data: rows } = await db.from("papers").select("id, abstract").in("id", ids);
      const abstracts = new Map((rows ?? []).map((r: { id: string; abstract: string }) => [r.id, r.abstract]));
      const notes = await fullTextNotes(ids);
      candidates.forEach((c) => {
        c.abstract = abstracts.get(c.id) ?? "";
        c.notes = notes.get(c.id);
      });
      report = parseReport(await groq(PLAN_PROMPT, planInput(description, needs, candidates), 1800), candidates, needs);
    } else if (planned) {
      // Nothing close enough: still ask for other phrasings to try
      report = parseReport(await groq(PLAN_PROMPT, planInput(description, needs, []), 300), [], needs);
    }
    const mode = report ? "ai" : "basic";
    report = report ?? fallbackReport(candidates, needs);

    const byId = new Map(candidates.map((c) => [c.id, c]));
    const plan = report.papers.map((p) => {
      const c = byId.get(p.id)!;
      return {
        ...p, title: c.title, authors: (c.authors ?? []).slice(0, 3), categories: c.categories ?? [],
        first_seen: c.first_seen, code_url: c.code_url ?? null, similarity: Math.round(c.similarity * 1000) / 1000,
      };
    });
    return json(req, {
      version: 2,
      summary: planned?.summary ?? "",
      needs: needs.map((n) => ({ id: n.id, label: n.label, query: n.query })),
      verdict: report.verdict,
      coverage: report.coverage,
      plan,
      steps: report.steps,
      you_need: report.you_need,
      watch_out: report.watch_out,
      try: report.try,
      floor: FLOOR,
      mode,
    });
  } catch (e) {
    console.error("scout failed", String(e));
    return json(req, { error: "Scout is unavailable right now. Try search by meaning on All papers." }, 500);
  }
});
