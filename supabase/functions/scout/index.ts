// scout: Project Scout. The visitor describes a project in plain words and gets
// a short reading plan of papers from our database, in order, with a reason each.
//   1. Groq turns the description into 3-4 search phrases (fallback: the description itself)
//   2. Each phrase is embedded with gte-small and matched against the papers
//   3. Groq orders the best matches into start / core / further (fallback: by similarity)
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { db, guard, json, underLimit } from "../_shared/http.ts";
import {
  type Candidate, type Match, cleanDescription, descriptionProblem, fallbackPlan, mergeMatches,
  parsePlan, parseQueries, PLAN_PROMPT, planInput, QUERY_PROMPT,
} from "../_shared/scout.ts";

const model = new Supabase.ai.Session("gte-small");
const SCOUTS_PER_HOUR = 10;
const GROQ_KEY = Deno.env.get("GROQ_API_KEY") ?? "";
const GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"];

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
        signal: AbortSignal.timeout(20000),
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
    // 1. Plan the searches
    const planned = parseQueries(await groq(QUERY_PROMPT, description, 300));
    const queries = planned?.queries ?? [description];

    // 2. Search for each phrase (one at a time: the free plan limits CPU per request)
    const lists: Match[][] = [];
    for (const q of queries) lists.push(await match(q));
    const candidates: Candidate[] = mergeMatches(lists, 10);
    if (candidates.length === 0) {
      return json(req, { summary: planned?.summary ?? "", queries, plan: [], mode: "basic" });
    }

    // 3. Order them into a reading plan
    const { data: rows } = await db.from("papers").select("id, abstract").in("id", candidates.map((c) => c.id));
    const abstracts = new Map((rows ?? []).map((r: { id: string; abstract: string }) => [r.id, r.abstract]));
    candidates.forEach((c) => (c.abstract = abstracts.get(c.id) ?? ""));
    const ordered = parsePlan(await groq(PLAN_PROMPT, planInput(description, candidates), 900),
                              candidates.map((c) => c.id));
    const steps = ordered ?? fallbackPlan(candidates);

    const byId = new Map(candidates.map((c) => [c.id, c]));
    const plan = steps.map((s) => {
      const c = byId.get(s.id)!;
      return {
        id: c.id, title: c.title, authors: (c.authors ?? []).slice(0, 3), categories: c.categories ?? [],
        first_seen: c.first_seen, code_url: c.code_url ?? null, similarity: c.similarity,
        stage: s.stage, reason: s.reason,
      };
    });
    return json(req, {
      summary: planned?.summary ?? "",
      queries: planned ? queries : [],
      plan,
      mode: ordered ? "ai" : "basic",
    });
  } catch (e) {
    console.error("scout failed", String(e));
    return json(req, { error: "Scout is unavailable right now. Try search by meaning on All papers." }, 500);
  }
});
