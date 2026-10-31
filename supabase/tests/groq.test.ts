// Run with: node --experimental-strip-types --test supabase/tests/groq.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";

// The module reads its settings from Deno.env when it loads
(globalThis as unknown as { Deno: unknown }).Deno = { env: { get: () => undefined } };
const { DEFAULT_MODELS, modelList, requestBody } = await import("../functions/_shared/groq.ts");

test("no retired models by default, and the list can be changed by a secret", () => {
  assert.ok(DEFAULT_MODELS.every((m) => !m.startsWith("llama-3")));
  assert.deepEqual(modelList(undefined), DEFAULT_MODELS);
  assert.deepEqual(modelList(" "), DEFAULT_MODELS);
  assert.deepEqual(modelList("a/b, c ,"), ["a/b", "c"]);
});

test("reasoning models think briefly, out of sight, with room to do it", () => {
  const r = requestBody("openai/gpt-oss-120b", "sys", "user", 400, 0.1) as Record<string, unknown>;
  assert.equal(r.reasoning_effort, "low");
  assert.equal(r.include_reasoning, false);
  assert.equal(r.max_tokens, 1424);
  assert.deepEqual(r.response_format, { type: "json_object" });
  const plain = requestBody("some/other-model", "sys", "user", 400, 0.1) as Record<string, unknown>;
  assert.equal(plain.max_tokens, 400);
  assert.equal("reasoning_effort" in plain, false);
});
