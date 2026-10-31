// search: "search by meaning" for the All papers page.
// Turns the visitor's words into a vector with gte-small (the same model that
// embedded the papers) and returns the closest papers.
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { db, guard, json, underLimit } from "../_shared/http.ts";

const model = new Supabase.ai.Session("gte-small");
const SEARCHES_PER_HOUR = 120;

Deno.serve(async (req) => {
  const blocked = guard(req);
  if (blocked) return blocked;

  const body = await req.json().catch(() => ({}));
  const q = String(body.q ?? "").replace(/\s+/g, " ").trim().slice(0, 300);
  if (q.length < 3) return json(req, { error: "Type at least 3 characters." }, 400);
  const limit = Math.min(Math.max(Number(body.limit) || 30, 1), 50);
  // Optional: only papers first seen on or after this day (used by "Watch this project")
  const since = /^\d{4}-\d{2}-\d{2}$/.test(String(body.since ?? "")) ? String(body.since) : null;

  if (!(await underLimit(req, "search", SEARCHES_PER_HOUR))) {
    return json(req, { error: "You've searched a lot in the last hour. Try again in a few minutes." }, 429);
  }

  const vector = await model.run(q, { mean_pool: true, normalize: true });
  const { data, error } = await db.rpc("match_papers", {
    query_embedding: JSON.stringify(vector),
    match_count: limit,
    since,
  });
  if (error) {
    console.error("match_papers failed", error.message);
    return json(req, { error: "Search is unavailable right now. Keyword search still works." }, 500);
  }
  return json(req, { results: data ?? [] });
});
