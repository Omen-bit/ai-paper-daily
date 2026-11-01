// Replies for the public functions, kept free of database imports so they can be
// tested on their own. http.ts re-exports these.

// Only pages on these sites may call the public functions from a browser
export const ALLOWED_ORIGINS = [
  "https://omen-bit.github.io",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
];

export function corsHeaders(req: Request): Record<string, string> {
  const origin = req.headers.get("origin") ?? "";
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

export function json(req: Request, body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(req), "Content-Type": "application/json" },
  });
}

/**
 * Wraps a function's handler so nothing can escape it. Without this, an error the
 * code didn't expect (the database or the AI model unreachable, a timeout) makes
 * the platform send a bare 500 with no CORS headers, which the browser reports as
 * a network failure. With it, the page always gets a JSON answer it can show, and
 * "retry: true" tells it the problem is temporary.
 */
export function safely(name: string, handler: (req: Request) => Promise<Response>,
                       message = "This is unavailable for a moment. Please try again shortly.") {
  return async (req: Request): Promise<Response> => {
    try {
      return await handler(req);
    } catch (e) {
      console.error(`${name} failed unexpectedly`, e instanceof Error ? e.stack ?? e.message : String(e));
      return json(req, { error: message, retry: true }, 503);
    }
  };
}
