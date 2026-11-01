// track: anonymous counts for "Most read", the feedback buttons, and the
// site-wide numbers that say whether readers value our pick (id "site").
// Stores totals per day only, never who sent them. The page sends a view once
// per paper per browser, feedback once per paper, and a visit once per day.
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { db, guard, json, underLimit } from "../_shared/http.ts";
import { isSiteEvent } from "../_shared/site_events.ts";

const EVENTS_PER_HOUR = 200;
const ID = /^([0-9]{4}\.[0-9]{4,5}|scout)$/;
const EVENTS = ["view", "useful", "not_useful"];

Deno.serve(async (req) => {
  const blocked = guard(req);
  if (blocked) return blocked;

  const body = await req.json().catch(() => ({}));
  const id = String(body.id ?? "");
  const event = String(body.event ?? "");
  const site = id === "site";
  if (site ? !isSiteEvent(event) : !ID.test(id) || !EVENTS.includes(event)) {
    return json(req, { error: "Unknown event." }, 400);
  }
  if (id === "scout" && event === "view") return json(req, { error: "Unknown event." }, 400);

  if (!(await underLimit(req, "track", EVENTS_PER_HOUR))) return json(req, { ok: false }, 429);
  const { error } = site
    ? await db.rpc("bump_site", { what: event })
    : await db.rpc("bump_stat", { pid: id, what: event });
  if (error) {
    console.error(site ? "bump_site failed" : "bump_stat failed", error.message);
    return json(req, { ok: false }, 500);
  }
  return json(req, { ok: true });
});
