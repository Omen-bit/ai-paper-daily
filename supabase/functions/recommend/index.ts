// recommend: the "For you" list on the home page.
// Takes the IDs this browser has opened (sent by the page, never stored) and
// returns recent papers closest in meaning to them.
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { db, guard, json, underLimit } from "../_shared/http.ts";

const CALLS_PER_HOUR = 60;
const ID = /^[0-9]{4}\.[0-9]{4,5}$/;

Deno.serve(async (req) => {
  const blocked = guard(req);
  if (blocked) return blocked;

  const body = await req.json().catch(() => ({}));
  const raw: unknown[] = Array.isArray(body.ids) ? body.ids : [];
  const ids = [...new Set(raw.map(String).filter((id) => ID.test(id)))].slice(0, 50);
  if (ids.length === 0) return json(req, { results: [] });
  const limit = Math.min(Math.max(Number(body.limit) || 6, 1), 20);
  const days = Math.min(Math.max(Number(body.days) || 30, 1), 365);

  if (!(await underLimit(req, "recommend", CALLS_PER_HOUR))) {
    return json(req, { error: "Too many requests. Try again in a few minutes." }, 429);
  }

  const since = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
  const { data, error } = await db.rpc("recommend_papers", { read_ids: ids, match_count: limit, since });
  if (error) {
    console.error("recommend_papers failed", error.message);
    return json(req, { error: "Recommendations are unavailable right now." }, 500);
  }
  return json(req, { results: data ?? [] });
});
