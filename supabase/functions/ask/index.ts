// ask: "Ask this paper" on each paper page.
// The first question about a paper reads its full text from arXiv's HTML version,
// splits it into passages and saves them. Every question then searches the saved
// passages and answers only from the best ones, naming the section it used.
// Papers with no readable full text are answered from the abstract, and say so.
// The daily pipeline can also prepare a paper in advance: {"id", "prepare": true}
// with the x-sync-secret header.
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { db, guard, json, sameSecret, underLimit } from "../_shared/http.ts";
import { groq, hasGroq } from "../_shared/groq.ts";
import { ASK_PROMPT, askInput, cleanQuestion, DETAILS_HEADING, paperDetails, parseAnswer } from "../_shared/ask.ts";
import {
  FULL_PROMPT, fullInput, htmlUrl, type Passage, parseArxivHtml, parseFullAnswer, searchText, toPassages, usable,
} from "../_shared/fulltext.ts";

const QUESTIONS_PER_HOUR = 30;
const PASSAGES_PER_ANSWER = 5;
const SYNC_SECRET = Deno.env.get("SYNC_SECRET") ?? "";
const ID = /^[0-9]{4}\.[0-9]{4,5}$/;

/**
 * Makes sure the paper's full text is saved, reading it from arXiv the first time.
 * Returns "ready" or "none". A failure that may be temporary (arXiv slow or down)
 * is not saved, so the next question tries again.
 */
async function ensureFullText(id: string): Promise<"ready" | "none"> {
  const { data: row } = await db.from("paper_fulltext").select("status").eq("paper_id", id).maybeSingle();
  if (row) return row.status === "ready" ? "ready" : "none";

  let res: Response;
  try {
    res = await fetch(htmlUrl(id), {
      headers: { "User-Agent": "AIPapersDaily/1.0 (+https://omen-bit.github.io/ai-paper-daily/)" },
      signal: AbortSignal.timeout(12000),
    });
  } catch (e) {
    console.error("arxiv html", id, String(e));
    return "none";
  }
  if (res.status >= 500 || res.status === 429) return "none"; // try again next time
  const passages = res.ok ? toPassages(parseArxivHtml(await res.text())) : [];
  if (!usable(passages)) {
    await db.from("paper_fulltext").upsert({ paper_id: id, status: "none", source: htmlUrl(id) });
    return "none";
  }
  const { error } = await db.from("paper_fulltext").upsert({
    paper_id: id, status: "ready", source: res.url || htmlUrl(id), n_sections: passages.length,
  });
  if (error) { console.error("save fulltext", error.message); return "none"; }
  for (let i = 0; i < passages.length; i += 200) {
    const rows = passages.slice(i, i + 200).map((p, j) => ({ paper_id: id, idx: i + j, heading: p.heading, body: p.body }));
    const { error: e } = await db.from("paper_sections").upsert(rows, { onConflict: "paper_id,idx" });
    if (e) {
      console.error("save sections", e.message);
      await db.from("paper_fulltext").delete().eq("paper_id", id); // don't keep half a paper
      return "none";
    }
  }
  return "ready";
}

Deno.serve(async (req) => {
  const blocked = guard(req);
  if (blocked) return blocked;
  const body = await req.json().catch(() => ({}));
  const id = String(body.id ?? "");
  if (!ID.test(id)) return json(req, { error: "Unknown paper." }, 400);

  // The daily pipeline preparing today's picks in advance
  if (body.prepare === true) {
    if (!sameSecret(req.headers.get("x-sync-secret") ?? "", SYNC_SECRET)) {
      return json(req, { error: "Only the pipeline can prepare papers." }, 401);
    }
    return json(req, { id, status: await ensureFullText(id) });
  }

  if (!hasGroq()) return json(req, { error: "Asking questions isn't switched on yet." }, 503);
  const question = cleanQuestion(body.question);
  if (question.length < 4) return json(req, { error: "Type a question first." }, 400);
  if (!(await underLimit(req, "ask", QUESTIONS_PER_HOUR))) {
    return json(req, { error: "You've asked a lot in the last hour. Try again in a little while." }, 429);
  }

  const { data: paper, error } = await db.from("papers").select("title, abstract, authors, submitted").eq("id", id).maybeSingle();
  if (error || !paper || !paper.abstract) {
    return json(req, { error: "This paper isn't in our database yet. Try again tomorrow." }, 404);
  }
  const previous = body.previous && typeof body.previous === "object" ? body.previous : undefined;
  const details = paperDetails(paper);

  // 1. From the full paper, when we can read it
  if ((await ensureFullText(id)) === "ready") {
    const { data: hits, error: e } = await db.rpc("match_sections", {
      pid: id, q: searchText(question, previous), n: PASSAGES_PER_ANSWER,
    });
    if (e) console.error("match_sections", e.message);
    if (hits && hits.length) {
      const passages: Passage[] = [
        { heading: "Abstract", body: paper.abstract },
        { heading: DETAILS_HEADING, body: details || "No author or date details." },
        ...(hits as Passage[]).map((h) => ({ heading: h.heading, body: h.body })),
      ];
      const answer = parseFullAnswer(await groq(FULL_PROMPT, fullInput(paper.title, passages, question, previous), 500, 0.1, 30000), passages);
      if (answer) return json(req, { ...answer, mode: "full" });
    }
  }

  // 2. From the abstract only
  const raw = await groq(ASK_PROMPT, askInput(paper.title, paper.abstract, question, previous, details), 400, 0.1, 30000);
  const answer = parseAnswer(raw, `${details}\n${paper.abstract}`);
  if (!answer) return json(req, { error: "Couldn't answer that right now. Try asking it another way." }, 502);
  const section = !answer.quote ? null : details.includes(answer.quote) ? DETAILS_HEADING : "Abstract";
  return json(req, { ...answer, section, mode: "abstract" });
});
