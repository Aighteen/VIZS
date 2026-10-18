// Options page (trusted extension context). Writes backend URL + token to chrome.storage.local.
import { DEFAULT_BACKEND_URL, HEALTH_PATH, STORAGE_KEYS, validateBackendUrl, validateToken } from "../lib/config.js";

const $ = (id) => document.getElementById(id);
const form = $("settings");
const urlInput = $("backendUrl");
const tokenInput = $("token");
const message = $("message");
const origin = `chrome-extension://${chrome.runtime.id}`;

function say(text, kind) {
  message.textContent = text;
  message.className = kind || "";
}

async function load() {
  const stored = await chrome.storage.local.get([STORAGE_KEYS.backendUrl, STORAGE_KEYS.token]);
  urlInput.value = stored[STORAGE_KEYS.backendUrl] || DEFAULT_BACKEND_URL;
  tokenInput.value = "";
  tokenInput.placeholder = stored[STORAGE_KEYS.token] ? "Saved (hidden). Paste a new token to replace it." : "Paste VIZS_EXTENSION_TOKEN";
  $("origin").textContent = origin;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = validateBackendUrl(urlInput.value);
  if (!url.ok) return say(url.error, "error");
  const update = { [STORAGE_KEYS.backendUrl]: url.value };
  if (tokenInput.value.trim()) {
    const token = validateToken(tokenInput.value);
    if (!token.ok) return say(token.error, "error");
    update[STORAGE_KEYS.token] = token.value;
  } else {
    const stored = await chrome.storage.local.get(STORAGE_KEYS.token);
    if (!stored[STORAGE_KEYS.token]) return say("Enter the pairing token.", "error");
  }
  await chrome.storage.local.set(update);
  urlInput.value = url.value;
  await load();
  say("Saved. Click the VIZS toolbar button on a listing to use the pet.", "ok");
});

$("clear").addEventListener("click", async () => {
  await chrome.storage.local.remove(STORAGE_KEYS.token);
  await load();
  say("Token removed.", "ok");
});

$("test").addEventListener("click", async () => {
  const url = validateBackendUrl(urlInput.value);
  if (!url.ok) return say(url.error, "error");
  say("Checking…");
  try {
    // /healthz makes no provider calls and needs no token. It does not verify pairing.
    const res = await fetch(url.value + HEALTH_PATH, { cache: "no-store", credentials: "omit" });
    const body = await res.json();
    if (res.ok && body && body.status === "ok") {
      say(`Backend is running (provider mode: ${String(body.provider_mode)}). This does not test the token.`, "ok");
    } else {
      say(`Backend answered with HTTP ${res.status}.`, "error");
    }
  } catch {
    say("Could not reach the backend. Is it running? For non-default addresses, add this extension's origin to VIZS_EXTENSION_ORIGINS.", "error");
  }
});

$("copyOrigin").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(origin);
    say("Origin copied.", "ok");
  } catch {
    say("Copy failed; select the origin text manually.", "error");
  }
});

load();
