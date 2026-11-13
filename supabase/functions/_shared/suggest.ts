// Checks for "Suggest a write-up" (functions/suggest and functions/suggest-admin), kept free of
// database imports so they can be tested on their own. The canonical address follows
// normalise_url() in src/case_studies.py, so the site, the pipeline and the database agree on
// which suggestions are the same post.

export const NOTE_MAX = 280;
export const CREDIT_MAX = 40;
export const URL_MAX = 2000;
export const SUGGESTIONS_PER_HOUR = 5;
export const DECISIONS = { approve: "approved", reject: "rejected", duplicate: "rejected" } as const;

/** One address per post: no query or fragment, https, a lowercase host, no trailing slash. */
export function canonicalUrl(url: string): string {
  let u = String(url ?? "").trim().replace(/[?#].*$/, "").replace(/^http:\/\//i, "https://");
  u = u.replace(/^https:\/\/[^/]+/i, (m) => m.toLowerCase());
  return u.replace(/\/+$/, "");
}

/** True for hosts a public blog post can never live on: localhost, private and reserved IPs. */
export function privateHost(host: string): boolean {
  const h = host.toLowerCase().replace(/^\[|\]$/g, "").replace(/\.$/, "");
  if (!h || h === "localhost" || h.endsWith(".localhost") || h.endsWith(".local") || h.endsWith(".internal")) return true;
  if (!h.includes(".") && !h.includes(":")) return true; // a bare intranet name
  const v4 = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (v4) {
    const [a, b] = [Number(v4[1]), Number(v4[2])];
    return a === 0 || a === 10 || a === 127 || a >= 224 || (a === 169 && b === 254) ||
      (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127);
  }
  if (h.includes(":")) return true; // IPv6 literals: no public blog is addressed this way
  return /^\d+$/.test(h); // a number standing in for an IP
}

export type UrlCheck = { ok: true; url: string; canonical: string } | { ok: false; error: string };

/** The suggested link, if it is a public https address. */
export function checkUrl(raw: unknown): UrlCheck {
  const text = String(raw ?? "").trim();
  if (!text) return { ok: false, error: "Add the link to the post so we can check it." };
  if (text.length > URL_MAX) return { ok: false, error: "That link is longer than we can take." };
  let u: URL;
  try {
    u = new URL(text);
  } catch {
    return { ok: false, error: "We need the full link to the post, starting with https://" };
  }
  if (u.protocol !== "https:") return { ok: false, error: "We can only take https:// links." };
  if (u.username || u.password) return { ok: false, error: "We can only take plain links to public posts." };
  if (privateHost(u.hostname)) return { ok: false, error: "We can only take links to public websites." };
  const url = u.toString();
  return { ok: true, url, canonical: canonicalUrl(url) };
}

/** A note as plain text: no control characters, single spaces, at most NOTE_MAX characters. */
export function cleanNote(raw: unknown): string {
  return String(raw ?? "").replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, NOTE_MAX);
}

/** The credit as plain text: letters, digits, spaces and @ . _ - only, at most CREDIT_MAX characters. */
export function cleanCredit(raw: unknown): string {
  return String(raw ?? "").normalize("NFKC").replace(/[^\p{L}\p{N} @._-]/gu, "").replace(/\s+/g, " ").trim()
    .slice(0, CREDIT_MAX).trim();
}

export type Suggestion =
  | { kind: "ok"; row: { url: string; canonical_url: string; note: string; credit: string } }
  | { kind: "honeypot" }
  | { kind: "invalid"; error: string };

/** A request body as a row to store, a honeypot hit to drop quietly, or the reason it can't be used. */
export function parseSuggestion(body: unknown): Suggestion {
  const b = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  if (String(b.website ?? "").trim()) return { kind: "honeypot" }; // a field people never see
  const url = checkUrl(b.url);
  if (!url.ok) return { kind: "invalid", error: url.error };
  return { kind: "ok", row: { url: url.url, canonical_url: url.canonical, note: cleanNote(b.note), credit: cleanCredit(b.credit) } };
}

/** The visitor's address hashed with a salt, so rows never hold a raw IP. */
export async function hashIp(ip: string, salt: string): Promise<string> {
  const data = new TextEncoder().encode(`${salt}:${ip}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest)).map((x) => x.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

/** The first address in x-forwarded-for, the way the platform reports the visitor. */
export function clientIp(req: Request): string {
  return (req.headers.get("x-forwarded-for") ?? "unknown").split(",")[0].trim() || "unknown";
}

export type Review =
  | { kind: "list" }
  | { kind: "review"; id: number; status: (typeof DECISIONS)[keyof typeof DECISIONS]; duplicate: boolean }
  | { kind: "invalid"; error: string };

/** What the owner asked the admin function to do. */
export function parseReview(body: unknown): Review {
  const b = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  if (b.action === "list") return { kind: "list" };
  if (b.action !== "review") return { kind: "invalid", error: "Unknown action." };
  const id = Number(b.id);
  const decision = String(b.decision ?? "") as keyof typeof DECISIONS;
  if (!Number.isInteger(id) || id <= 0) return { kind: "invalid", error: "Unknown suggestion." };
  if (!(decision in DECISIONS)) return { kind: "invalid", error: "Unknown decision." };
  return { kind: "review", id, status: DECISIONS[decision], duplicate: decision === "duplicate" };
}
