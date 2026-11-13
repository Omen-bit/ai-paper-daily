// Run with: node --experimental-strip-types --test supabase/tests/suggest.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  canonicalUrl, checkUrl, cleanCredit, cleanNote, CREDIT_MAX, NOTE_MAX, parseReview, parseSuggestion, privateHost,
} from "../functions/_shared/suggest.ts";
import { handleAdmin, handleSuggest } from "../functions/_shared/suggest_handlers.ts";

const SITE = "https://omen-bit.github.io";

function post(body: unknown, ip = "203.0.113.7", origin = SITE): Request {
  return new Request("https://x.supabase.co/functions/v1/suggest", {
    method: "POST", body: JSON.stringify(body),
    headers: { "content-type": "application/json", origin, "x-forwarded-for": `${ip}, 10.0.0.1` },
  });
}

/** A stand-in database: hit_rate_limit counts per bucket, inserts are kept, a canonical url is unique. */
function fakeDb(max = 5) {
  const hits = new Map<string, number>();
  const rows: Record<string, unknown>[] = [];
  return {
    rows, hits,
    deps: {
      salt: "pepper",
      rateLimit: async (bucket: string, limit: number) => {
        const n = (hits.get(bucket) ?? 0) + 1;
        hits.set(bucket, n);
        return { data: n <= Math.min(limit, max), error: null };
      },
      insert: async (row: Record<string, unknown>) => {
        if (rows.some((r) => r.canonical_url === row.canonical_url)) return { error: { message: "dup", code: "23505" } };
        rows.push(row);
        return { error: null };
      },
    },
  };
}

test("canonical addresses match the pipeline's normalise_url", () => {
  assert.equal(canonicalUrl("http://Eng.Example.COM/Post-A/?utm_source=x#top"), "https://eng.example.com/Post-A");
  assert.equal(canonicalUrl("https://eng.example.com/a"), canonicalUrl("https://ENG.example.com/a/"));
});

test("only public https links are taken", () => {
  assert.ok(checkUrl("https://netflixtechblog.com/a-post-123").ok);
  for (const bad of ["", "netflixtechblog.com/post", "http://netflixtechblog.com/post", "ftp://example.com/a",
                     "javascript:alert(1)", "data:text/html,hi", "https://localhost/a", "https://127.0.0.1/a",
                     "https://10.1.2.3/a", "https://192.168.0.5/x", "https://172.20.1.1/x", "https://169.254.169.254/latest",
                     "https://[::1]/a", "https://intranet/a", "https://user:pw@example.com/a", "https://2130706433/a",
                     "https://example.com/" + "a".repeat(2001)]) {
    assert.equal(checkUrl(bad).ok, false, bad);
  }
  assert.ok(privateHost("printer.local") && privateHost("100.64.0.1") && !privateHost("eng.uber.com"));
});

test("error messages never blame the reader", () => {
  for (const bad of ["", "not a link", "http://x.com/a", "https://localhost/a"]) {
    const r = checkUrl(bad);
    assert.ok(!r.ok && !/invalid|wrong|you entered|bad/i.test(r.error), r.ok ? "" : r.error);
  }
});

test("notes and credits are trimmed, length-limited and plain text", () => {
  assert.equal(cleanNote("  Great\n\tpost   about RAG  "), "Great post about RAG");
  assert.equal(cleanNote("x".repeat(400)).length, NOTE_MAX);
  assert.equal(cleanCredit("<b>Priya</b> <script>alert(1)</script>"), "bPriyab scriptalert1script");
  assert.equal(cleanCredit("  @priya_k  "), "@priya_k");
  assert.equal(cleanCredit("José Núñez-Ruiz"), "José Núñez-Ruiz");
  assert.equal(cleanCredit("https://evil.example/?a=1"), "httpsevil.examplea1");
  assert.ok(cleanCredit("y".repeat(80)).length <= CREDIT_MAX);
});

test("a suggestion is stored as new with a hashed address, never the raw one", async () => {
  const db = fakeDb();
  const res = await handleSuggest(post({ url: "https://eng.example.com/rag?utm=1", note: " Good ", credit: "Ana" }), db.deps);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { ok: true });
  assert.equal(db.rows.length, 1);
  const row = db.rows[0];
  assert.equal(row.canonical_url, "https://eng.example.com/rag");
  assert.equal(row.note, "Good");
  assert.equal(row.credit, "Ana");
  assert.equal(row.status, "new");
  assert.match(String(row.ip_hash), /^[0-9a-f]{32}$/);
  assert.ok(!JSON.stringify(row).includes("203.0.113.7"));
});

test("honeypot hits get a thank-you and nothing is stored", async () => {
  const db = fakeDb();
  const res = await handleSuggest(post({ url: "https://eng.example.com/a", website: "http://spam.example" }), db.deps);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { ok: true });
  assert.equal(db.rows.length, 0);
  assert.equal(db.hits.size, 0); // not even counted
});

test("bad links are refused with a helpful message", async () => {
  const db = fakeDb();
  const res = await handleSuggest(post({ url: "https://192.168.1.1/admin" }), db.deps);
  assert.equal(res.status, 400);
  assert.match((await res.json()).error, /public websites/);
  assert.equal(db.rows.length, 0);
});

test("five suggestions an hour per hashed address, then a polite 429", async () => {
  const db = fakeDb();
  for (let i = 0; i < 5; i++) {
    const res = await handleSuggest(post({ url: `https://eng.example.com/p${i}` }), db.deps);
    assert.equal(res.status, 200);
  }
  const sixth = await handleSuggest(post({ url: "https://eng.example.com/p6" }), db.deps);
  assert.equal(sixth.status, 429);
  assert.match((await sixth.json()).error, /try again in an hour/);
  const other = await handleSuggest(post({ url: "https://eng.example.com/p7" }, "198.51.100.9"), db.deps);
  assert.equal(other.status, 200); // another visitor is not affected
  assert.ok([...db.hits.keys()].every((k) => /^suggest:[0-9a-f]{32}$/.test(k)));
});

test("the same post suggested twice is fine for the reader and stored once", async () => {
  const db = fakeDb();
  await handleSuggest(post({ url: "https://eng.example.com/a" }), db.deps);
  const again = await handleSuggest(post({ url: "https://ENG.example.com/a/" }, "198.51.100.1"), db.deps);
  assert.equal(again.status, 200);
  assert.equal(db.rows.length, 1);
});

test("only the site's pages and POST are answered", async () => {
  const db = fakeDb();
  assert.equal((await handleSuggest(post({ url: "https://a.com/x" }, "1.2.3.4", "https://evil.example"), db.deps)).status, 403);
  const get = new Request("https://x.supabase.co/functions/v1/suggest", { method: "GET" });
  assert.equal((await handleSuggest(get, db.deps)).status, 405);
  const pre = new Request("https://x.supabase.co/functions/v1/suggest", { method: "OPTIONS", headers: { origin: SITE } });
  assert.equal((await handleSuggest(pre, db.deps)).status, 204);
});

// ---------- the owner's review page

const TOKEN = "t".repeat(48);
function adminDeps(token = TOKEN) {
  const updates: [number, Record<string, unknown>][] = [];
  return {
    updates,
    deps: {
      token,
      sameSecret: (a: string, b: string) => a === b,
      list: async () => ({ data: [{ id: 1, status: "checked" }], error: null }),
      update: async (id: number, patch: Record<string, unknown>) => { updates.push([id, patch]); return { error: null }; },
    },
  };
}

test("the review function needs the admin token", async () => {
  const a = adminDeps();
  assert.equal((await handleAdmin(post({ action: "list" }), a.deps)).status, 401);
  assert.equal((await handleAdmin(post({ action: "list", token: "wrong" }), a.deps)).status, 401);
  const short = adminDeps("short");
  assert.equal((await handleAdmin(post({ action: "list", token: "short" }), short.deps)).status, 401); // a weak token is never accepted
  const ok = await handleAdmin(post({ action: "list", token: TOKEN }), a.deps);
  assert.deepEqual(await ok.json(), { ok: true, rows: [{ id: 1, status: "checked" }] });
});

test("approve, reject and close as duplicate", async () => {
  const a = adminDeps();
  for (const [decision, status] of [["approve", "approved"], ["reject", "rejected"], ["duplicate", "rejected"]]) {
    const res = await handleAdmin(post({ action: "review", id: 7, decision, token: TOKEN }), a.deps);
    assert.equal((await res.json()).status, status);
  }
  assert.equal(a.updates.length, 3);
  assert.ok(a.updates.every(([id, p]) => id === 7 && typeof p.reviewed_at === "string"));
  assert.deepEqual(parseReview({ action: "review", id: "x", decision: "approve" }).kind, "invalid");
  assert.deepEqual(parseReview({ action: "review", id: 3, decision: "publish" }).kind, "invalid");
  assert.deepEqual(parseReview({ action: "drop" }).kind, "invalid");
});

test("schema.sql has the table, its checks and no public access", () => {
  const sql = readFileSync(new URL("../schema.sql", import.meta.url), "utf8");
  assert.match(sql, /create table if not exists public\.case_suggestions/);
  assert.match(sql, /check \(status in \('new', 'checked', 'approved', 'rejected', 'duplicate'\)\)/);
  assert.match(sql, /char_length\(note\) <= 280 and char_length\(credit\) <= 40/);
  assert.match(sql, /alter table public\.case_suggestions enable row level security/);
  assert.match(sql, /revoke all on public\.case_suggestions from anon, authenticated/);
  const config = readFileSync(new URL("../config.toml", import.meta.url), "utf8");
  assert.match(config, /\[functions\.suggest\]/);
  assert.match(config, /\[functions\.suggest-admin\]/);
});

test("parseSuggestion keeps only the known fields", () => {
  const p = parseSuggestion({ url: "https://a.example/b", note: "n", credit: "c", status: "approved", id: 9 });
  assert.equal(p.kind, "ok");
  if (p.kind === "ok") assert.deepEqual(Object.keys(p.row).sort(), ["canonical_url", "credit", "note", "url"]);
});
