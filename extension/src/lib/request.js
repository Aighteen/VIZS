// Builds the backend request. Pure: callers inject the tab URL (from sender.tab.url) and ids.
import { EVALUATE_PATH } from "./config.js";
import { safeHttpUrl } from "./safe-url.js";

export const CHANNEL = "debug"; // The backend has no extension channel; debug is required.
const MAX_MESSAGE_LENGTH = 4000;

/**
 * The backend only accepts an explicitly currency-marked price ("$89.99" or "USD 89.99"),
 * so a bare number typed by the user is normalized to "$<amount>".
 * Returns { ok:true, value: "$89.99" | null } or { ok:false, error }.
 */
export function normalizePrice(input) {
  if (input === undefined || input === null) return { ok: true, value: null };
  if (typeof input !== "string") return { ok: false, error: "Price must be text." };
  const trimmed = input.trim();
  if (!trimmed) return { ok: true, value: null };
  const match = /^(?:\$|USD\s*)?\s*(\d{1,3}(?:,\d{3})+|\d{1,9})(?:\.(\d{1,2}))?$/i.exec(trimmed);
  if (!match) return { ok: false, error: "Enter a price like 89.99 (US dollars)." };
  const whole = match[1].replace(/,/g, "");
  if (whole.length > 9) return { ok: false, error: "That price is too large." };
  const cents = match[2] ? `.${match[2].padEnd(2, "0")}` : "";
  return { ok: true, value: `$${String(Number(whole))}${cents}` };
}

/**
 * Listing URL must come from the browser's view of the sender tab, never from page-supplied data.
 * Returns { ok:true, value } or { ok:false, error }.
 */
export function listingUrlFromSender(sender) {
  const raw = sender?.tab?.url;
  if (typeof raw !== "string" || !raw) {
    return { ok: false, error: "Could not read this page's address. Click the VIZS toolbar button again on the listing." };
  }
  const href = safeHttpUrl(raw);
  if (!href) return { ok: false, error: "VIZS can only check regular http or https web pages." };
  return { ok: true, value: href };
}

/**
 * The tab href is wrapped in angle brackets so the backend takes it verbatim, including a
 * trailing ".", "?", "!", ";", ":" or unmatched ")" (QA-07). safeHttpUrl output never
 * contains a raw "<", ">" or whitespace, so the brackets are an unambiguous boundary.
 */
export function buildMessageText(listingUrl, price) {
  return `Check this listing <${listingUrl}>` + (price ? ` price ${price}` : "");
}

/**
 * Returns { ok:true, url, init, requestId } where init is a fetch() RequestInit, or { ok:false, error }.
 */
export function buildEvaluateRequest({ backendUrl, token, listingUrl, price, requestId }) {
  if (!backendUrl) return { ok: false, error: "Backend URL is not configured." };
  if (!token) return { ok: false, error: "Pairing token is not configured." };
  if (typeof requestId !== "string" || !requestId || requestId.length > 128) return { ok: false, error: "Invalid request id." };
  const href = safeHttpUrl(listingUrl);
  if (!href) return { ok: false, error: "Invalid listing URL." };
  const priceResult = normalizePrice(price ?? null);
  if (!priceResult.ok) return { ok: false, error: priceResult.error };
  const message_text = buildMessageText(href, priceResult.value);
  if (message_text.length > MAX_MESSAGE_LENGTH) return { ok: false, error: "This page address is too long to check." };
  const body = { request_id: requestId, message_text, channel: CHANNEL };
  return {
    ok: true,
    requestId,
    url: backendUrl.replace(/\/+$/, "") + EVALUATE_PATH,
    init: {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
    },
  };
}
