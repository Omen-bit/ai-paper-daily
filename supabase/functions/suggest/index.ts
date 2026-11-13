// suggest: a reader suggests an engineering write-up for the Case studies page. Stores it as
// "new" in case_suggestions; the daily pipeline (src/case_suggestions.py) checks it and the
// owner approves it on the private review page. Only a salted hash of the visitor's address is kept.
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { db, safely } from "../_shared/http.ts";
import { handleSuggest } from "../_shared/suggest_handlers.ts";

const SALT = Deno.env.get("SUGGEST_SALT") ?? Deno.env.get("SYNC_SECRET") ?? "";

Deno.serve(safely("suggest", (req) => handleSuggest(req, {
  salt: SALT,
  rateLimit: async (bucket, max) => await db.rpc("hit_rate_limit", { bucket_key: bucket, max_hits: max }),
  insert: async (row) => await db.from("case_suggestions").insert(row),
})));
