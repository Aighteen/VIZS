// Pure configuration helpers. No Chrome APIs here so Node can test them.

export const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";
export const EVALUATE_PATH = "/api/v1/extension/evaluate";
export const HEALTH_PATH = "/healthz";
// Backend workflow timeout is 100 s; give the network a little headroom.
export const CLIENT_TIMEOUT_MS = 110_000;
export const MAX_TOKEN_LENGTH = 500; // backend rejects Authorization values over 512 chars
export const STORAGE_KEYS = Object.freeze({ backendUrl: "backendUrl", token: "pairingToken", position: "petPosition" });

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost"]);

/**
 * Accepts http://127.0.0.1:<port>, http://localhost:<port>, or https://<host>[:port].
 * Rejects paths, queries, fragments and credentials. Returns { ok, value } or { ok:false, error }.
 */
export function validateBackendUrl(input) {
  if (typeof input !== "string" || !input.trim()) return { ok: false, error: "Enter a backend URL." };
  const raw = input.trim();
  let url;
  try {
    url = new URL(raw);
  } catch {
    return { ok: false, error: "That is not a valid URL." };
  }
  if (url.username || url.password) return { ok: false, error: "URLs with credentials are not allowed." };
  if ((url.pathname && url.pathname !== "/") || url.search || url.hash || raw.includes("?") || raw.includes("#")) {
    return { ok: false, error: "Use only the scheme, host and port (no path)." };
  }
  if (url.protocol === "http:") {
    if (!LOOPBACK_HOSTS.has(url.hostname)) {
      return { ok: false, error: "Plain http is only allowed for 127.0.0.1 or localhost." };
    }
    if (!url.port) return { ok: false, error: "Include the port, e.g. http://127.0.0.1:8000." };
  } else if (url.protocol !== "https:") {
    return { ok: false, error: "Only http (loopback) or https URLs are allowed." };
  }
  return { ok: true, value: `${url.protocol}//${url.host}` };
}

/** Pairing tokens are opaque URL-safe strings (secrets.token_urlsafe on the backend). */
export function validateToken(input) {
  if (typeof input !== "string") return { ok: false, error: "Enter the pairing token." };
  const value = input.trim();
  if (!value) return { ok: false, error: "Enter the pairing token." };
  if (value.length > MAX_TOKEN_LENGTH) return { ok: false, error: "Token is too long." };
  if (!/^[A-Za-z0-9._~+/=-]+$/.test(value)) return { ok: false, error: "Token contains unexpected characters." };
  return { ok: true, value };
}

/** Reads stored settings defensively; never throws. Token is only used by the service worker. */
export function normalizeSettings(stored) {
  const backend = validateBackendUrl(stored?.[STORAGE_KEYS.backendUrl] ?? DEFAULT_BACKEND_URL);
  const token = validateToken(stored?.[STORAGE_KEYS.token] ?? "");
  return {
    backendUrl: backend.ok ? backend.value : null,
    token: token.ok ? token.value : null,
  };
}
