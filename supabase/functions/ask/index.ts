// ask: "Ask this paper" on each paper page. Answers come only from the paper's
// title and abstract, with the sentence they are based on.
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { db, guard, json, underLimit } from "../_shared/http.ts";
import { ASK_PROMPT, askInput, cleanQuestion, parseAnswer } from "../_shared/ask.ts";

const QUESTIONS_PER_HOUR = 30;
const GROQ_KEY = Deno.env.get("GROQ_API_KEY") ?? "";
const GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"];
const ID = /^[0-9]{4}\.[0-9]{4,5}$/;

async function groq(user: string): Promise<string | null> {
  for (const model of GROQ_MODELS) {
    try {
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { "Authorization": `Bearer ${GROQ_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          model, temperature: 0.1, max_tokens: 400, response_format: { type: "json_object" },
          messages: [{ role: "system", content: ASK_PROMPT }, { role: "user", content: user }],
        }),
        signal: AbortSignal.timeout(20000),
      });
      if (!res.ok) { console.error("groq", model, res.status); continue; }
      const text = (await res.json())?.choices?.[0]?.message?.content;
      if (typeof text === "string" && text.trim()) return text;
    } catch (e) {
      console.error("groq", model, String(e));
    }
  }
  return null;
}

Deno.serve(async (req) => {
  const blocked = guard(req);
  if (blocked) return blocked;
  if (!GROQ_KEY) return json(req, { error: "Asking questions isn't switched on yet." }, 503);

  const body = await req.json().catch(() => ({}));
  const id = String(body.id ?? "");
  const question = cleanQuestion(body.question);
  if (!ID.test(id)) return json(req, { error: "Unknown paper." }, 400);
  if (question.length < 4) return json(req, { error: "Type a question first." }, 400);

  if (!(await underLimit(req, "ask", QUESTIONS_PER_HOUR))) {
    return json(req, { error: "You've asked a lot in the last hour. Try again in a little while." }, 429);
  }

  const { data: paper, error } = await db.from("papers").select("title, abstract").eq("id", id).maybeSingle();
  if (error || !paper || !paper.abstract) {
    return json(req, { error: "This paper isn't in our database yet. Try again tomorrow." }, 404);
  }
  const previous = body.previous && typeof body.previous === "object" ? body.previous : undefined;
  const answer = parseAnswer(await groq(askInput(paper.title, paper.abstract, question, previous)), paper.abstract);
  if (!answer) return json(req, { error: "Couldn't answer that right now. Try asking it another way." }, 502);
  return json(req, answer);
});
