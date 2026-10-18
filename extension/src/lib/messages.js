// Validation for messages between the injected content script and the service worker.

const MAX_PRICE_INPUT = 40;
const MAX_COORD = 100_000;

/**
 * The service worker only accepts messages from this extension's own content script running in a
 * top-level tab frame. Extension pages (no tab), other extensions (different id), web pages via
 * externally_connectable (not declared) and sub-frames are rejected.
 */
export function isTrustedContentSender(sender, runtimeId) {
  if (!sender || typeof runtimeId !== "string" || !runtimeId) return false;
  if (sender.id !== runtimeId) return false;
  const tab = sender.tab;
  if (!tab || !Number.isInteger(tab.id) || tab.id < 0) return false;
  if (sender.frameId !== 0) return false;
  return true;
}

function exactKeys(msg, keys) {
  return Object.keys(msg).every((k) => keys.includes(k));
}

/** Returns a normalized command or null. Unknown types or extra fields are rejected. */
export function parseCommand(msg) {
  if (!msg || typeof msg !== "object" || Array.isArray(msg) || typeof msg.type !== "string") return null;
  switch (msg.type) {
    case "check":
      if (!exactKeys(msg, ["type", "price"])) return null;
      if (msg.price !== undefined && msg.price !== null && (typeof msg.price !== "string" || msg.price.length > MAX_PRICE_INPUT)) return null;
      return { type: "check", price: msg.price ?? null };
    case "dismiss":
    case "navigated":
    case "getState":
    case "getPosition":
    case "openOptions":
      return exactKeys(msg, ["type"]) ? { type: msg.type } : null;
    case "savePosition": {
      if (!exactKeys(msg, ["type", "x", "y"])) return null;
      const ok = (v) => Number.isFinite(v) && v >= 0 && v <= MAX_COORD;
      return ok(msg.x) && ok(msg.y) ? { type: "savePosition", x: Math.round(msg.x), y: Math.round(msg.y) } : null;
    }
    default:
      return null;
  }
}
