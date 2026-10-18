// URL safety helpers shared by request building and the panel view-model.

export const MAX_URL_LENGTH = 2048;

/** Returns a normalized http(s) href, or null for anything else (javascript:, data:, credentials, etc.). */
export function safeHttpUrl(value) {
  if (typeof value !== "string" || !value || value.length > MAX_URL_LENGTH) return null;
  let url;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  if (url.username || url.password || !url.hostname) return null;
  return url.href;
}

/** Hostname for display, or empty string. */
export function displayHost(href) {
  try {
    return new URL(href).hostname;
  } catch {
    return "";
  }
}
