// Run with: node --experimental-strip-types --test supabase/tests/respond.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { safely } from "../functions/_shared/respond.ts";

const req = () => new Request("https://x.supabase.co/functions/v1/search", {
  method: "POST", headers: { origin: "https://omen-bit.github.io" },
});

test("an unexpected error becomes a JSON answer the page can show", async () => {
  const errors = console.error; console.error = () => {};
  try {
    const handler = safely("search", async () => { throw new Error("database unreachable"); }, "Search is down.");
    const res = await handler(req());
    assert.equal(res.status, 503);
    assert.equal(res.headers.get("access-control-allow-origin"), "https://omen-bit.github.io");  // the browser can read it
    assert.deepEqual(await res.json(), { error: "Search is down.", retry: true });
  } finally { console.error = errors; }
});

test("normal answers pass through untouched", async () => {
  const handler = safely("search", async () => new Response("ok", { status: 200 }));
  const res = await handler(req());
  assert.equal(res.status, 200);
  assert.equal(await res.text(), "ok");
});
