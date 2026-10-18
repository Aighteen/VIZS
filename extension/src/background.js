// MV3 service worker: thin Chrome glue around PetController. Only this context reads the token.
import { STORAGE_KEYS, normalizeSettings } from "./lib/config.js";
import { PetController } from "./lib/controller.js";

const CONTENT_FILES = ["src/content/styles.js", "src/content/render.js", "src/content/pet.js"];
const KEEPALIVE_MS = 20_000;

// Best effort: keep stored settings away from content scripts. Not all Chrome versions support
// changing local storage access; the content script never reads storage either way.
try {
  chrome.storage.local.setAccessLevel?.({ accessLevel: "TRUSTED_CONTEXTS" })?.catch?.(() => {});
} catch {
  /* unsupported */
}

let keepAliveTimer = null;
function onActiveCountChange(count) {
  // A long fetch alone may not keep an MV3 worker alive; a periodic extension API call does.
  if (count > 0 && !keepAliveTimer) {
    keepAliveTimer = setInterval(() => chrome.runtime.getPlatformInfo(() => void chrome.runtime.lastError), KEEPALIVE_MS);
  } else if (count === 0 && keepAliveTimer) {
    clearInterval(keepAliveTimer);
    keepAliveTimer = null;
  }
}

const controller = new PetController({
  runtimeId: chrome.runtime.id,
  fetchImpl: (url, init) => fetch(url, init),
  loadSettings: async () => normalizeSettings(await chrome.storage.local.get([STORAGE_KEYS.backendUrl, STORAGE_KEYS.token])),
  newRequestId: () => crypto.randomUUID(),
  deliver: (tabId, message) => chrome.tabs.sendMessage(tabId, message, { frameId: 0 }),
  getTabUrl: async (tabId) => (await chrome.tabs.get(tabId))?.url,
  onActiveCountChange,
  savePosition: (pos) => chrome.storage.local.set({ [STORAGE_KEYS.position]: pos }),
  getPosition: async () => {
    const pos = (await chrome.storage.local.get(STORAGE_KEYS.position))[STORAGE_KEYS.position];
    return pos && Number.isFinite(pos.x) && Number.isFinite(pos.y) ? { x: pos.x, y: pos.y } : null;
  },
  openOptions: () => chrome.runtime.openOptionsPage(),
});

// User-triggered activation only: inject the pet into the active tab when the toolbar button is clicked.
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab?.id || tab.id < 0) return;
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id, frameIds: [0] }, files: CONTENT_FILES });
  } catch {
    // Restricted page (chrome://, Web Store, PDF viewer...). Signal briefly on the badge.
    chrome.action.setBadgeText({ tabId: tab.id, text: "!" });
    chrome.action.setTitle({ tabId: tab.id, title: "VIZS cannot run on this page. Open a regular shopping page." });
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  controller
    .handle(message, sender)
    .then(sendResponse, () => sendResponse({ ok: false, error: "internal_error" }));
  return true; // async response
});

// A full navigation or reload invalidates any pending request for that tab.
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading" || changeInfo.url) controller.discard(tabId);
});
chrome.tabs.onRemoved.addListener((tabId) => controller.discard(tabId));
