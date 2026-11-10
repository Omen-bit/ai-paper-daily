// Site-wide events the page may send with id "site". Keep in step with
// bump_site() in schema.sql.
const SLOTS = ["pick", "trending", "runner_up", "most_read"];
const SOURCES = [
  "direct", "google", "bing", "duckduckgo", "hn", "reddit", "x", "linkedin", "github",
  "producthunt", "discord", "telegram", "newsletter", "rss", "other",
];

export const SITE_EVENTS: string[] = [
  "visit_new", "visit_return_7d", "visit_return_old",
  ...SLOTS.map((s) => `click_${s}`),
  ...SLOTS.flatMap((s) => [`seen_${s}_yes`, `seen_${s}_no`]),
  // Project Scout results: opened, saved, marked not relevant, "more like this",
  // a case study opened, the brief copied for an AI assistant
  "scout_click", "scout_save", "scout_dismiss", "scout_more", "scout_case", "scout_brief",
  // Paper pages: the full breakdown opened, and clicks out to the paper elsewhere
  "breakdown_load", "out_pdf", "out_arxiv", "out_hf", "out_code",
  // Where each day's first visit came from (the ?ref= tag or the referring site)
  ...SOURCES.map((s) => `src_${s}`),
  // Sign-ups: the RSS link clicked, the email form sent
  "subscribe_rss", "subscribe_email", "subscribe_confirmed",
];

export function isSiteEvent(event: string): boolean {
  return SITE_EVENTS.includes(event);
}
