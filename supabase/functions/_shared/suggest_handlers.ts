// The request handlers behind functions/suggest and functions/suggest-admin. The database calls
// come in as `deps`, so the tests (supabase/tests/suggest.test.ts) can run them with stand-ins.
import { ALLOWED_ORIGINS, corsHeaders, json } from "./respond.ts";
import { clientIp, hashIp, parseReview, parseSuggestion, SUGGESTIONS_PER_HOUR } from "./suggest.ts";

type Result<T = unknown> = { data?: T; error?: { message: string; code?: string } | null };

export type SuggestDeps = {
  /** hit_rate_limit(bucket_key, max_hits): true while the bucket is under its limit */
  rateLimit: (bucket: string, max: number) => Promise<Result<boolean>>;
  insert: (row: Record<string, unknown>) => Promise<Result>;
  salt: string;
};

export type AdminDeps = {
  token: string;
  list: () => Promise<Result<unknown[]>>;
  update: (id: number, patch: Record<string, unknown>) => Promise<Result>;
  sameSecret: (a: string, b: string) => boolean;
};

/** The CORS preflight, POST only, and only from the site's own pages. Null to go on. */
function gate(req: Request): Response | null {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(req) });
  if (req.method !== "POST") return json(req, { error: "Use POST." }, 405);
  const origin = req.headers.get("origin");
  if (origin && !ALLOWED_ORIGINS.includes(origin)) return json(req, { error: "This service only answers AI Papers Daily." }, 403);
  return null;
}

/** Store one suggestion. Honeypot hits get the same "thanks" as real ones, and nothing is stored. */
export async function handleSuggest(req: Request, deps: SuggestDeps): Promise<Response> {
  const blocked = gate(req);
  if (blocked) return blocked;
  const body = await req.json().catch(() => ({}));
  const parsed = parseSuggestion(body);
  if (parsed.kind === "honeypot") return json(req, { ok: true });
  if (parsed.kind === "invalid") return json(req, { ok: false, error: parsed.error }, 400);

  const ipHash = await hashIp(clientIp(req), deps.salt);
  const limit = await deps.rateLimit(`suggest:${ipHash}`, SUGGESTIONS_PER_HOUR);
  if (limit.error) console.error("suggest rate limit check failed", limit.error.message); // fail open, like search
  else if (limit.data !== true) {
    return json(req, { ok: false, error: "You have sent a few suggestions already. Please try again in an hour." }, 429);
  }

  const { error } = await deps.insert({ ...parsed.row, ip_hash: ipHash, status: "new" });
  if (error && error.code !== "23505") { // 23505: someone already suggested this post, which is fine
    console.error("suggest insert failed", error.message);
    return json(req, { ok: false, error: "We couldn't save it just now. Please try again in a minute.", retry: true }, 500);
  }
  return json(req, { ok: true });
}

/** The owner's review page: list the suggestions, or approve or reject one. Needs ADMIN_TOKEN. */
export async function handleAdmin(req: Request, deps: AdminDeps): Promise<Response> {
  const blocked = gate(req);
  if (blocked) return blocked;
  const body = await req.json().catch(() => ({})) as Record<string, unknown>;
  if (!deps.token || deps.token.length < 32 || !deps.sameSecret(String(body.token ?? ""), deps.token)) {
    return json(req, { ok: false, error: "That token didn't work." }, 401);
  }
  const action = parseReview(body);
  if (action.kind === "invalid") return json(req, { ok: false, error: action.error }, 400);
  if (action.kind === "list") {
    const { data, error } = await deps.list();
    if (error) return json(req, { ok: false, error: "Couldn't load the suggestions." }, 500);
    return json(req, { ok: true, rows: data ?? [] });
  }
  const patch: Record<string, unknown> = { status: action.status, reviewed_at: new Date().toISOString() };
  const { error } = await deps.update(action.id, patch);
  if (error) return json(req, { ok: false, error: "Couldn't save that decision." }, 500);
  return json(req, { ok: true, id: action.id, status: action.status });
}
