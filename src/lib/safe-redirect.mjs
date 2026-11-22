// Post-login redirect targets come from the URL (`/login?next=...`), so they are attacker-controlled.
// Only same-site paths are allowed; anything else falls back. (.mjs so that `node --test` can import it directly.)
const PLACEHOLDER_ORIGIN = "http://flowforge.invalid";

export function safeNext(next, fallback = "/dashboard") {
  // Must be a single-slash path. "//host" is protocol-relative, and browsers treat "\" like "/".
  if (typeof next !== "string" || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return fallback;
  try {
    // The URL parser strips tabs/newlines, so "/\t/host" becomes "//host": resolve it and make sure we stay on our origin.
    const url = new URL(next, PLACEHOLDER_ORIGIN);
    if (url.origin !== PLACEHOLDER_ORIGIN) return fallback;
    return url.pathname + url.search + url.hash;
  } catch {
    return fallback;
  }
}
