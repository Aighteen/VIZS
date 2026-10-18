# VIZS Chrome extension (pet)

Manifest V3, plain JS/HTML/CSS. No bundler, no framework, no runtime dependencies. You can load it unpacked from this folder.

## Load and pair (local development)

1. Backend: from the repo root run `python -m app.workflow.dev_server --pair` (offline by default, port 8000). `--pair` writes `VIZS_EXTENSION_TOKEN` to the ignored root `.env` if it is missing.
2. Chrome: open `chrome://extensions`, turn on Developer mode, click **Load unpacked** and pick this `extension/` folder.
3. Open the extension's **Details → Extension options**. Paste the `VIZS_EXTENSION_TOKEN` value and keep the backend URL `http://127.0.0.1:8000`. Save.
4. The options page shows this extension's origin, `chrome-extension://<id>`. Add it to `VIZS_EXTENSION_ORIGINS` in the root `.env` (comma-separated) and restart the backend. Without it, the backend answers 403 for requests that carry that Origin.
5. Open a fragrance listing and click the VIZS toolbar button. The pet appears; click **Check seller**.

## Design

- **User-triggered only.** The extension uses `activeTab` + `scripting`. Clicking the toolbar action injects `src/content/{styles,render,pet}.js` into the top frame of the active tab. It declares no `content_scripts`, no `<all_urls>` and no `tabs` permission. Host permissions cover only `http://127.0.0.1:8000/*` and `http://localhost:8000/*`. Other configured backends (another loopback port, or https) depend on the backend's CORS for `VIZS_EXTENSION_ORIGINS`.
- **The token stays in the service worker.** The options page writes `{backendUrl, pairingToken}` to `chrome.storage.local`. Only `src/background.js` reads them. The content script never touches storage and never sends a URL: the worker takes the listing URL from `sender.tab.url`. It accepts messages only when `sender.id === chrome.runtime.id`, a tab is present and `frameId === 0`. The content script accepts state pushes only from its own worker (`sender.id` matches and there is no `sender.tab`).
- **Request:** `POST {backendUrl}/api/v1/extension/evaluate` with `Authorization: Bearer <token>` and body `{"request_id": uuid, "message_text": "Check this listing <URL>[ price $<amount>]", "channel": "debug"}`, for example `Check this listing <https://shop.example/p?> price $89.99`. The angle brackets are literal: they mark the exact tab href, so the backend keeps a trailing `.`, `?`, `!`, `;`, `:` or unmatched `)` (QA-07). The backend only accepts a currency-marked price, so `89.99` becomes `$89.99`. The client timeout is 110 s and requests carry `redirect: "error"`.
- **States:** idle → searching ("Checking seller…" for the whole request; there is no fake phase or percentage) → finished (bubble opens the panel) or error (puzzled pet, message, explicit **Retry**, plus **Open settings** for pairing problems). INSUFFICIENT_EVIDENCE is a finished result, not an error.
- **One request per tab.** The worker reserves the slot before any await, so repeated clicks are ignored. Dismissal, navigation (`tabs.onUpdated`, SPA URL polling in the page, or a tab URL that no longer matches when the result arrives) and request-id mismatches all discard the result. Dismissing aborts the client fetch, but already-started backend/provider work is not reversed, and the UI says so.
- **Safe rendering.** Everything is built with `createElement`/`textContent`; there is no `innerHTML` anywhere in `src/` (enforced by tests). Links must be `http:`/`https:` and are checked twice (worker view-model and content renderer). They open with `target=_blank rel="noopener noreferrer"`. Sources that are not `verified_fact` evidence, and promise quotes that do not come from the merchant's own page, carry the label "Unverified source". Mock data shows a SIMULATION banner.
- **Pet:** a code-native SVG perfume-bottle mascot in a closed Shadow DOM, styled through a constructable stylesheet. You can drag it with the pointer or move it with the arrow keys (Shift for bigger steps) while it is focused. The × button dismisses it. Focus is visible. `prefers-reduced-motion` makes the pet static. Only the pet position is stored, through the worker; no browsing history is kept.

## Layout

```
manifest.json
src/background.js          service worker glue (Chrome APIs only)
src/lib/*.js               pure ES modules: config, request, response validation, labels,
                           view-model, safe-url, messages, pet-state, controller
src/content/*.js           classic scripts injected on click (isolated world)
src/options/*              options page
test/*.test.js             node --test unit tests; fixtures in test/fixtures are SYNTHETIC
scripts/backend-smoke.mjs  loopback smoke test against an OFFLINE backend
```

## Tests

```
cd extension
node --test test/*.test.js      # or: npm test
```

Optional smoke test against an offline backend on loopback (it makes no paid calls and refuses to run if `/healthz` reports anything but offline):

```
VIZS_EXTENSION_TOKEN=test-token VIZS_PROVIDER_MODE=offline python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
VIZS_SMOKE_URL=http://127.0.0.1:8765 VIZS_SMOKE_TOKEN=test-token node scripts/backend-smoke.mjs
```
