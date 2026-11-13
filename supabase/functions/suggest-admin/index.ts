// suggest-admin: the owner's private review page (case-studies/review.html) lists the suggested
// write-ups and approves or rejects them. Every call must carry ADMIN_TOKEN (a long random secret
// set with `supabase secrets set`), which the page keeps in the owner's browser only.
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { db, safely, sameSecret } from "../_shared/http.ts";
import { handleAdmin } from "../_shared/suggest_handlers.ts";

const COLUMNS = "id,url,canonical_url,note,credit,status,checks,topic,techniques,industry,build_details,build_score," +
  "title,company,problem,solution,created_at,reviewed_at";

Deno.serve(safely("suggest-admin", (req) => handleAdmin(req, {
  token: Deno.env.get("ADMIN_TOKEN") ?? "",
  sameSecret,
  list: async () => await db.from("case_suggestions").select(COLUMNS).order("created_at", { ascending: false }).limit(300),
  update: async (id, patch) => await db.from("case_suggestions").update(patch).eq("id", id),
})));
