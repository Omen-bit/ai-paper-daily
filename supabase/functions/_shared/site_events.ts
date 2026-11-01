// Site-wide events the page may send with id "site". Keep in step with
// bump_site() in schema.sql.
const SLOTS = ["pick", "trending", "runner_up", "most_read"];

export const SITE_EVENTS: string[] = [
  "visit_new", "visit_return_7d", "visit_return_old",
  ...SLOTS.map((s) => `click_${s}`),
  ...SLOTS.flatMap((s) => [`seen_${s}_yes`, `seen_${s}_no`]),
  // Project Scout results: opened, saved, marked not relevant, "more like this"
  "scout_click", "scout_save", "scout_dismiss", "scout_more",
];

export function isSiteEvent(event: string): boolean {
  return SITE_EVENTS.includes(event);
}
