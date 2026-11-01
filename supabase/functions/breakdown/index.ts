// breakdown: the full breakdown on each paper page.
// {"id", "peek": true} returns a saved breakdown, or {"status": "missing"} without doing any work.
// {"id"} makes it: reads the paper's arXiv HTML once, copies its contributions, results
// tables, limitations and conclusion (plain code, no LLM), and saves them for good.
// {"summary": true} also asks for the short AI summary, for papers without curator
// notes. Summaries are capped per day; past the cap the page shows the rest without one.
// The daily pipeline prepares today's picks in advance: {"id", "prepare": true} with
// the x-sync-secret header.
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { db, guard, json, safely, sameSecret, underLimit } from "../_shared/http.ts";
import { groq, hasGroq, MODELS } from "../_shared/groq.ts";
import { htmlUrl } from "../_shared/fulltext.ts";
import {
  type Breakdown, parseBreakdown, parseSummary, SUMMARY_PROMPT, summaryInput, worthShowing,
} from "../_shared/breakdown.ts";

const MAKES_PER_HOUR = 20;
const SUMMARIES_PER_DAY = Number(Deno.env.get("SUMMARIES_PER_DAY") ?? "50");
// The smaller model first: a short summary doesn't need the big one
const SUMMARY_MODELS = ["openai/gpt-oss-20b", ...MODELS.filter((m) => m !== "openai/gpt-oss-20b")];
const SYNC_SECRET = Deno.env.get("SYNC_SECRET") ?? "";
const ID = /^[0-9]{4}\.[0-9]{4,5}$/;

type Row = { status: "ready" | "none"; data: Breakdown | null; summary: string | null };

function reply(req: Request, row: Row, summaryLater = false) {
  return json(req, { status: row.status, breakdown: row.data, summary: row.summary, summaryLater });
}

async function summariesToday(): Promise<number> {
  const since = new Date(Date.now() - 86400000).toISOString();
  const { count, error } = await db.from("paper_breakdown").select("paper_id", { count: "exact", head: true }).gt("summary_at", since);
  if (error) { console.error("count summaries", error.message); return SUMMARIES_PER_DAY; } // fail closed: protect the limit
  return count ?? 0;
}

/** Adds the short summary when the daily cap allows. Returns false when it had to wait. */
async function addSummary(id: string, row: Row): Promise<boolean> {
  if (!hasGroq() || !row.data) return true;
  if ((await summariesToday()) >= SUMMARIES_PER_DAY) return false;
  const { data: paper } = await db.from("papers").select("title, abstract").eq("id", id).maybeSingle();
  if (!paper?.abstract) return true;
  const b = row.data;
  const source = [paper.abstract, ...b.contributions, b.conclusion?.text ?? ""].join("\n");
  const summary = parseSummary(await groq(SUMMARY_PROMPT, summaryInput(paper.title, paper.abstract, b), 300, 0.2, 25000, SUMMARY_MODELS), source);
  // Saved even when the check failed (as an empty summary), so one paper can't use the budget twice
  const { error } = await db.from("paper_breakdown").update({ summary: summary ?? "", summary_at: new Date().toISOString() }).eq("paper_id", id);
  if (error) console.error("save summary", error.message);
  row.summary = summary ?? "";
  return true;
}

Deno.serve(safely("breakdown", async (req) => {
  const blocked = guard(req);
  if (blocked) return blocked;
  const body = await req.json().catch(() => ({}));
  const id = String(body.id ?? "");
  if (!ID.test(id)) return json(req, { error: "Unknown paper." }, 400);
  const wantSummary = body.summary === true;

  const prepare = body.prepare === true;
  if (prepare && !sameSecret(req.headers.get("x-sync-secret") ?? "", SYNC_SECRET)) {
    return json(req, { error: "Only the pipeline can prepare papers." }, 401);
  }

  const { data: saved } = await db.from("paper_breakdown").select("status, data, summary").eq("paper_id", id).maybeSingle();
  if (saved) {
    const row = saved as Row;
    if (row.status === "ready" && wantSummary && row.summary === null && !body.peek) {
      const done = await addSummary(id, row);
      return reply(req, row, !done);
    }
    return reply(req, row, row.status === "ready" && wantSummary && row.summary === null);
  }
  if (body.peek === true) return json(req, { status: "missing" });

  if (!prepare && !(await underLimit(req, "breakdown", MAKES_PER_HOUR))) {
    return json(req, { error: "You've opened a lot of breakdowns in the last hour. Try again in a little while." }, 429);
  }
  const { data: known, error: readError } = await db.from("papers").select("id").eq("id", id).maybeSingle();
  if (readError) {
    console.error("read paper", readError.message);
    return json(req, { error: "The breakdown is unavailable for a moment. Please try again shortly.", retry: true }, 503);
  }
  if (!known) return json(req, { error: "This paper isn't in our database yet. Try again tomorrow." }, 404);

  let res: Response;
  try {
    res = await fetch(htmlUrl(id), {
      headers: { "User-Agent": "AIPapersDaily/1.0 (+https://omen-bit.github.io/ai-paper-daily/)" },
      signal: AbortSignal.timeout(15000),
    });
  } catch (e) {
    console.error("arxiv html", id, String(e));
    return json(req, { error: "arXiv didn't answer in time. Try again in a minute." }, 503);
  }
  if (res.status >= 500 || res.status === 429) return json(req, { error: "arXiv is busy right now. Try again in a minute." }, 503);
  const b = res.ok ? parseBreakdown(await res.text()) : null;
  const row: Row = b && worthShowing(b) ? { status: "ready", data: b, summary: null } : { status: "none", data: null, summary: null };
  const { error } = await db.from("paper_breakdown").upsert({ paper_id: id, status: row.status, data: row.data });
  if (error) console.error("save breakdown", error.message);
  if (row.status === "ready" && wantSummary) {
    const done = await addSummary(id, row);
    return reply(req, row, !done);
  }
  return reply(req, row);
}, "The breakdown is unavailable for a moment. Please try again shortly."));
