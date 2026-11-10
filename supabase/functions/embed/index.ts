// embed: fills papers.embedding for rows that have none, using Supabase's
// built-in gte-small model (384 numbers per paper). Called by the daily
// pipeline after it uploads new papers. Only callers with SYNC_SECRET get in.
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { createClient } from "npm:@supabase/supabase-js@2";

const model = new Supabase.ai.Session("gte-small");
const db = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  { auth: { persistSession: false } },
);
const SYNC_SECRET = Deno.env.get("SYNC_SECRET") ?? "";
// The free plan allows about 2 s of CPU per call. Stop taking new papers after
// this much time so the call always returns cleanly; the caller simply calls again.
const TIME_BUDGET_MS = 1000;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

// Compare secrets without leaking their length or content through timing
function sameSecret(a: string, b: string) {
  if (!a || !b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ error: "Use POST." }, 405);
  if (!sameSecret(req.headers.get("x-sync-secret") ?? "", SYNC_SECRET)) {
    return json({ error: "This function is only for the pipeline." }, 401);
  }
  const body = await req.json().catch(() => ({}));
  const limit = Math.min(Math.max(Number(body.limit) || 8, 1), 20);
  const started = Date.now();

  const { data, error } = await db.from("papers").select("id,title,abstract").is("embedding", null).limit(limit);
  if (error) return json({ error: error.message }, 500);

  let embedded = 0;
  for (const paper of data ?? []) {
    if (embedded > 0 && Date.now() - started > TIME_BUDGET_MS) break;
    // Title plus abstract, cut to stay inside gte-small's 512-token window
    const text = `${paper.title}\n\n${paper.abstract ?? ""}`.slice(0, 2000);
    const vector = await model.run(text, { mean_pool: true, normalize: true });
    const { error: updateError } = await db.from("papers")
      .update({ embedding: JSON.stringify(vector) }).eq("id", paper.id);
    if (updateError) return json({ error: updateError.message, embedded }, 500);
    embedded++;
  }

  // Company case studies, once every paper has its vector (Scout suggests them by meaning)
  if (embedded < limit && Date.now() - started < TIME_BUDGET_MS) {
    const { data: cases } = await db.from("cases").select("url,title,problem,issue,summary,tags")
      .is("embedding", null).limit(limit - embedded);
    for (const c of cases ?? []) {
      if (embedded > 0 && Date.now() - started > TIME_BUDGET_MS) break;
      const vector = await model.run(caseText(c), { mean_pool: true, normalize: true });
      const { error: updateError } = await db.from("cases")
        .update({ embedding: JSON.stringify(vector) }).eq("url", c.url);
      if (updateError) return json({ error: updateError.message, embedded }, 500);
      embedded++;
    }
  }

  const [{ count }, { count: casesLeft }] = await Promise.all([
    db.from("papers").select("id", { count: "exact", head: true }).is("embedding", null),
    db.from("cases").select("url", { count: "exact", head: true }).is("embedding", null),
  ]);
  return json({ embedded, remaining: (count ?? 0) + (casesLeft ?? 0) });
});

type CaseRow = { title: string; problem: string; issue: string; summary: string; tags: string[] };
/** What a case study is about, in the words a project description would use. */
function caseText(c: CaseRow): string {
  return [c.title, c.issue, c.summary, (c.tags ?? []).join(", ")].filter(Boolean).join("\n\n").slice(0, 2000);
}
