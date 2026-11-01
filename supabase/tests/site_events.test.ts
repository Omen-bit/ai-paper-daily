// Run with: node --experimental-strip-types --test supabase/tests/site_events.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SITE_EVENTS, isSiteEvent } from "../functions/_shared/site_events.ts";

test("accepts the events the page sends and nothing else", () => {
  for (const e of ["visit_new", "visit_return_7d", "click_pick", "click_most_read", "seen_trending_no", "scout_dismiss"]) {
    assert.ok(isSiteEvent(e), e);
  }
  for (const e of ["view", "click_", "seen_pick", "click_pick; drop table", ""]) {
    assert.ok(!isSiteEvent(e), e);
  }
});

test("every event passes the database check in schema.sql", () => {
  const sql = readFileSync(new URL("../schema.sql", import.meta.url), "utf8");
  const pattern = sql.match(/what !~ '([^']+)'/)![1];
  const re = new RegExp(pattern);
  for (const e of SITE_EVENTS) assert.ok(re.test(e), e);
  assert.equal(SITE_EVENTS.length, 19);
});
