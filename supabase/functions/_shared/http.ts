// Helpers shared by the public functions (search, and later For you and Project Scout).
import { createClient } from "npm:@supabase/supabase-js@2";

// Only pages on these sites may call the public functions from a browser
const ALLOWED_ORIGINS = [
  "https://omen-bit.github.io",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
];

export const db = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  { auth: { persistSession: false } },
);

export function corsHeaders(req: Request): Record<string, string> {
  const origin = req.headers.get("origin") ?? "";
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

export function json(req: Request, body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(req), "Content-Type": "application/json" },
  });
}

/** Handles the CORS preflight and blocks other sites. Returns a response to send, or null to go on. */
export function guard(req: Request): Response | null {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(req) });
  if (req.method !== "POST") return json(req, { error: "Use POST." }, 405);
  const origin = req.headers.get("origin");
  if (origin && !ALLOWED_ORIGINS.includes(origin)) return json(req, { error: "This service only answers AI Papers Daily." }, 403);
  return null;
}

/** True while this visitor is under maxPerHour calls of this kind. */
export async function underLimit(req: Request, kind: string, maxPerHour: number): Promise<boolean> {
  const ip = (req.headers.get("x-forwarded-for") ?? "unknown").split(",")[0].trim();
  const { data, error } = await db.rpc("hit_rate_limit", { bucket_key: `${kind}:${ip}`, max_hits: maxPerHour });
  if (error) {
    console.error("rate limit check failed", error.message);
    return true; // fail open: a broken counter should not take search down
  }
  return data === true;
}

/** Compares two secrets in constant time, so the check can't be timed. */
export function sameSecret(a: string, b: string): boolean {
  if (!a || !b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
