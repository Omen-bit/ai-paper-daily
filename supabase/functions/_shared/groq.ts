// One place for the Groq models every function uses, and for the call itself.
// Groq retires models every few months, so the list can be changed without a
// code change: set GROQ_MODELS (comma-separated) as a Supabase secret.
const GROQ_KEY = Deno.env.get("GROQ_API_KEY") ?? "";
export const DEFAULT_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"];
export const MODELS = modelList(Deno.env.get("GROQ_MODELS"));
export const hasGroq = () => GROQ_KEY !== "";

export function modelList(setting: string | undefined): string[] {
  const list = (setting ?? "").split(",").map((m) => m.trim()).filter(Boolean);
  return list.length ? list : DEFAULT_MODELS;
}

/** The request body for one JSON-mode call. Reasoning models think briefly and
 * keep their thinking out of the reply; their thinking also needs token room. */
export function requestBody(model: string, system: string, user: string, maxTokens: number, temperature: number) {
  const reasoning = /gpt-oss/.test(model);
  return {
    model, temperature,
    max_tokens: reasoning ? maxTokens + 1024 : maxTokens,
    response_format: { type: "json_object" },
    ...(reasoning ? { reasoning_effort: "low", include_reasoning: false } : {}),
    messages: [{ role: "system", content: system }, { role: "user", content: user }],
  };
}

/** One JSON-mode Groq call, trying each model in turn. Returns the raw text or null. */
export async function groq(system: string, user: string, maxTokens: number, temperature = 0.2, timeoutMs = 25000): Promise<string | null> {
  if (!GROQ_KEY) return null;
  for (const model of MODELS) {
    try {
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { "Authorization": `Bearer ${GROQ_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify(requestBody(model, system, user, maxTokens, temperature)),
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (!res.ok) {
        console.error("groq", model, res.status, (await res.text()).slice(0, 300));
        continue;
      }
      const text = (await res.json())?.choices?.[0]?.message?.content;
      if (typeof text === "string" && text.trim()) return text;
      console.error("groq", model, "empty reply");
    } catch (e) {
      console.error("groq", model, String(e));
    }
  }
  return null;
}
