// QA verification tests (EXT-01..07, API-01/02 client side). SYNTHETIC data only; no network.
// Encodes docs/EXTENSION_SCOPE.md, docs/ACCEPTANCE_TESTS.md and the tech-lead-confirmed rules:
// USD-only "$<amount>" price, Unverified/Merchant's own page/Verified fact labels, dismiss aborts.
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { test } from "node:test";
import { PetController } from "../src/lib/controller.js";
import { STATES, reduce, INITIAL_STATE } from "../src/lib/pet-state.js";
import { buildEvaluateRequest, normalizePrice } from "../src/lib/request.js";
import { errorForStatus, validateEvaluateResponse } from "../src/lib/response.js";
import { buildPanelViewModel } from "../src/lib/view-model.js";
import { EXT_ROOT, LISTING, RUNTIME_ID, contentSender, fakeDocument, fixture, jsonResponse, loadClassicScripts } from "./helpers.js";

const TOKEN = "qa-synthetic-pairing-token-0123456789";
const R = loadClassicScripts(["src/content/styles.js", "src/content/render.js"]).VIZS_RENDER;
const BANNED = [/\d+(?:\.\d+)?\s*%/, /\bpercent/i, /probabilit/i, /\bscam/i, /\bfake\b/i, /\bguarantee/i,
  /authentic(?:ity)? (?:is )?(?:verified|confirmed|guaranteed)/i, /\bis (?:a )?fraud/i];
const DISCLAIMER = "VIZS does not certify authenticity. An unknown seller is not automatically fraudulent, and a low price does not prove counterfeit goods.";

function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function setup({ respond, tabUrl = LISTING, settings } = {}) {
  const calls = [];
  const delivered = [];
  const responses = [];
  let n = 0;
  let currentTab = tabUrl;
  const controller = new PetController({
    runtimeId: RUNTIME_ID,
    newRequestId: () => `req-${++n}`,
    loadSettings: async () => settings ?? { backendUrl: "http://127.0.0.1:8000", token: TOKEN },
    fetchImpl: (url, init) => {
      calls.push({ url, init });
      if (respond) return respond(calls.length, init);
      const d = deferred();
      init.signal.addEventListener("abort", () => d.reject(new DOMException("aborted", "AbortError")));
      responses.push(d);
      return d.promise;
    },
    deliver: async (tabId, message) => delivered.push(structuredClone({ tabId, message })),
    getTabUrl: async () => currentTab,
    setTimer: (fn, ms) => setTimeout(fn, ms).unref(),
  });
  const handle = async (msg, sender = contentSender()) => {
    const res = await controller.handle(msg, sender);
    return structuredClone(res);
  };
  return { controller, calls, delivered, responses, handle, setTab: (u) => { currentTab = u; } };
}

function assessment(overrides = {}) {
  return {
    request_id: "req-1", seller_risk: "INSUFFICIENT_EVIDENCE", decision: "VERIFY_FIRST",
    summary: "SYNTHETIC summary.", evidence: [], promise_sheet: null, research: [], missing_information: [],
    data_mode: "partial", ...overrides,
  };
}

function renderText(a) {
  const result = validateEvaluateResponse({ assessment: a, message_text: "x" }, a.request_id);
  assert.equal(result.ok, true, result.error);
  const vm = structuredClone(buildPanelViewModel(result.assessment));
  return { vm, panel: R.renderPanel(fakeDocument(), vm) };
}

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

// ---------------------------------------------------------------- EXT-07 / API-01: token isolation

test("QA EXT-07: pairing token never reaches the content script in any response or pushed state", async () => {
  for (const status of [200, 401, 403, 429, 500]) {
    const t = setup({
      respond: async () => (status === 200 ? jsonResponse(fixture("synthetic-promise-conflict.json", "req-1")) : jsonResponse({ detail: TOKEN }, status)),
    });
    const replies = [await t.handle({ type: "check", price: "12" }), await t.handle({ type: "getState" })];
    await t.controller.pending(7);
    replies.push(await t.handle({ type: "getState" }), await t.handle({ type: "getPosition" }), await t.handle({ type: "dismiss" }));
    const visible = JSON.stringify([replies, t.delivered]);
    assert.ok(!visible.includes(TOKEN), `token leaked to content side (HTTP ${status})`);
    assert.ok(!/Bearer/.test(visible));
    assert.equal(t.calls[0].init.headers.Authorization, `Bearer ${TOKEN}`);
  }
});

test("QA EXT-07: content scripts and options HTML never read storage or embed provider keys", () => {
  for (const file of walk(join(EXT_ROOT, "src"))) {
    const src = readFileSync(file, "utf8");
    const rel = relative(EXT_ROOT, file);
    assert.doesNotMatch(src, /XAI_API_KEY|TAVILY_API_KEY|api\.x\.ai|api\.tavily\.com|xai-[A-Za-z0-9]{10}|tvly-/, rel);
    if (rel.startsWith(join("src", "content"))) assert.doesNotMatch(src, /chrome\.storage|localStorage|sessionStorage|indexedDB|document\.cookie/, rel);
  }
});

// ---------------------------------------------------------------- INPUT-01 / EXT-02: request shape

test("QA INPUT-01: listing URL comes only from sender.tab.url, never sender.url or message fields", async () => {
  const t = setup();
  const sender = contentSender({ url: "https://frame.attacker.example/inner" });
  for (const forged of [{ type: "check", url: "https://evil.example/" }, { type: "check", listing: "x" },
    { type: "check", price: "12 https://evil.example/" }, { type: "check", price: { toString: () => "1" } }]) {
    await t.handle(forged, sender);
  }
  assert.equal(t.calls.length, 0, "forged or malformed checks never fetch");
  await t.handle({ type: "check" }, sender);
  const body = JSON.parse(t.calls[0].init.body);
  assert.deepEqual(Object.keys(body).sort(), ["channel", "message_text", "request_id"]);
  assert.equal(body.channel, "debug");
  assert.equal(body.message_text, `Check this listing <${LISTING}>`);
  assert.ok(!body.message_text.includes("attacker"));
});

test("QA INPUT-01: price is normalized to USD \"$<amount>\" or rejected; channel is always debug", () => {
  const ok = { "89.99": "$89.99", "$89.99": "$89.99", "USD 89.99": "$89.99", "usd89.9": "$89.90", "1,250": "$1250", " 7 ": "$7", "": null };
  for (const [input, expected] of Object.entries(ok)) assert.deepEqual(normalizePrice(input), { ok: true, value: expected }, input);
  for (const bad of ["€50", "50 EUR", "GBP 5", "1e3", "-5", "12.345", "abc", "$", "1 000", "0x10", "$5 https://x.example"]) {
    assert.equal(normalizePrice(bad).ok, false, bad);
  }
  for (const price of [null, "5", "$1,000.5"]) {
    const req = buildEvaluateRequest({ backendUrl: "http://127.0.0.1:8000", token: TOKEN, listingUrl: LISTING, price, requestId: "r" });
    assert.equal(JSON.parse(req.init.body).channel, "debug");
    assert.equal(req.init.redirect, "error");
    assert.equal(req.init.credentials, "omit");
  }
});

// ---------------------------------------------------------------- EXT-02 / EXT-04: single request, explicit retry

test("QA EXT-02: many rapid clicks produce one fetch; a new fetch only after an explicit check", async () => {
  const t = setup();
  await Promise.all(Array.from({ length: 6 }, () => t.handle({ type: "check" })));
  assert.equal(t.calls.length, 1);
  t.responses[0].resolve(jsonResponse(fixture("synthetic-insufficient.json", "req-1")));
  assert.equal(await t.controller.pending(7), STATES.FINISHED);
  await new Promise((r) => setTimeout(r, 20));
  assert.equal(t.calls.length, 1, "no background re-check");
  await t.handle({ type: "check" });
  assert.equal(t.calls.length, 2);
});

test("QA EXT-04: every non-2xx HTTP status becomes a retryable error, never an automatic retry", async () => {
  for (const status of [400, 401, 403, 404, 405, 409, 413, 422, 429, 500, 501, 502, 503, 504, 520]) {
    const t = setup({ respond: async () => jsonResponse({ detail: "QA-PRIVATE detail" }, status) });
    await t.handle({ type: "check" });
    assert.equal(await t.controller.pending(7), STATES.ERROR, String(status));
    const state = t.delivered.at(-1).message.state;
    assert.equal(state.name, "error");
    assert.equal(state.error.retryable, true, String(status));
    assert.ok(!state.error.message.includes("QA-PRIVATE"));
    assert.equal(errorForStatus(status).retryable, true);
    await new Promise((r) => setTimeout(r, 10));
    assert.equal(t.calls.length, 1, `no automatic retry after HTTP ${status}`);
    await t.handle({ type: "check" }); // explicit retry
    assert.equal(t.calls.length, 2);
  }
});

test("QA EXT-04: network failure and malformed payloads are errors with retry, not finished", async () => {
  const bad = [
    async () => { throw new TypeError("fetch failed"); },
    async () => jsonResponse("<html>gateway</html>"),
    async () => jsonResponse({ assessment: assessment({ seller_risk: "LOWER_RISK", decision: "AVOID" }) }),
    async () => jsonResponse({ assessment: assessment({ request_id: "someone-else" }) }),
    async () => jsonResponse({ assessment: assessment({ summary: "" }) }),
    async () => jsonResponse({ assessment: assessment({ research: [{ status: "partial", records_received: 3, records_retained: 1, records_filtered: 1 }] }) }),
  ];
  for (const respond of bad) {
    const t = setup({ respond });
    await t.handle({ type: "check" });
    assert.equal(await t.controller.pending(7), STATES.ERROR);
    assert.equal(t.delivered.at(-1).message.state.error.retryable, true);
  }
});

test("QA EXT-03: insufficient evidence and clarification results are finished, not errors", async () => {
  for (const a of [assessment(), assessment({ decision: "NEED_MORE_INFORMATION", summary: "Shopping extraction is unavailable; please try again later." })]) {
    const t = setup({ respond: async () => jsonResponse({ assessment: a, message_text: "x" }) });
    await t.handle({ type: "check" });
    assert.equal(await t.controller.pending(7), STATES.FINISHED);
    const vm = t.delivered.at(-1).message.state.viewModel;
    assert.equal(vm.insufficient, true);
    const { panel } = renderText(a);
    assert.match(panel.textContent, /completed result, not an error/);
  }
});

// ---------------------------------------------------------------- EXT-05: stale results

test("QA EXT-05: dismissal aborts the fetch and a late result is never delivered", async () => {
  let aborted = false;
  const late = deferred();
  const t = setup({ respond: (n, init) => { init.signal.addEventListener("abort", () => { aborted = true; }); return late.promise; } });
  await t.handle({ type: "check" });
  const pending = t.controller.pending(7);
  const res = await t.handle({ type: "dismiss" });
  assert.equal(aborted, true);
  assert.match(res.note, /not reversed/);
  assert.doesNotMatch(res.note, /refund|costs? (?:were|was|are) (?:cancel|revers)/i);
  late.resolve(jsonResponse(fixture("synthetic-insufficient.json", "req-1")));
  assert.equal(await pending, "discarded");
  assert.equal(t.delivered.filter((d) => d.message.state.name === "finished").length, 0);
});

test("QA EXT-05: navigation during the request (including hash/SPA URL change) drops the result", async () => {
  for (const next of [LISTING + "#reviews", "https://shop.synthetic.example/product?id=2", undefined]) {
    const t = setup();
    await t.handle({ type: "check" });
    t.setTab(next);
    t.responses[0].resolve(jsonResponse(fixture("synthetic-insufficient.json", "req-1")));
    assert.equal(await t.controller.pending(7), "discarded", String(next));
    assert.ok(t.delivered.every((d) => d.message.state.name !== "finished"));
  }
});

test("QA EXT-05: state machine ignores results whose token does not match the pending request", () => {
  let s = reduce(INITIAL_STATE, { type: "CHECK", token: "a" });
  s = reduce(s, { type: "RESULT", token: "b", viewModel: {} });
  assert.equal(s.name, STATES.SEARCHING);
  s = reduce(s, { type: "FAIL", token: "b", error: { message: "x" } });
  assert.equal(s.name, STATES.SEARCHING);
});

// ---------------------------------------------------------------- EXT-02: no fabricated phases

test("QA EXT-02: only idle/searching/finished/error states; no reviewing-sources or progress percentage", () => {
  assert.deepEqual(Object.values(STATES).sort(), ["error", "finished", "idle", "searching"]);
  const pet = readFileSync(join(EXT_ROOT, "src", "content", "pet.js"), "utf8");
  const literals = [...pet.matchAll(/(["'`])((?:\\.|(?!\1).)*)\1/g)].map((m) => m[2]);
  for (const text of literals) {
    assert.doesNotMatch(text, /review(?:ing)? sources|reading sources|analy[sz]ing|progress|\d+\s*%/i, text);
  }
});

// ---------------------------------------------------------------- EXT-07: safe rendering and links

test("QA EXT-07: only http(s) anchors, hardened, and at most two links in the Sources section", () => {
  const evidence = ["javascript:alert(1)", "data:text/html,x", "https://a.synthetic.example/1", "http://b.synthetic.example/2",
    "https://c.synthetic.example/3", "https://user:pw@d.synthetic.example/"].map((u, i) => ({
    claim: `SYNTHETIC claim ${i}`, source_url: u, evidence_type: "search_snippet", claim_status: "unknown", retrieved_at: "2026-10-17T12:00:00Z",
  }));
  const { vm, panel } = renderText(assessment({ evidence }));
  assert.equal(vm.sources.length, 2);
  assert.deepEqual(vm.sources.map((s) => s.href), ["https://a.synthetic.example/1", "http://b.synthetic.example/2"]);
  for (const a of panel.querySelectorAll("a")) {
    assert.match(a.getAttribute("href"), /^https?:\/\//);
    assert.equal(a.getAttribute("rel"), "noopener noreferrer");
    assert.ok(!a.getAttribute("href").includes("@"));
  }
  const sourcesSection = panel.querySelectorAll("div").find((d) => d.children[0]?.textContent === "Sources");
  assert.ok(sourcesSection.querySelectorAll("a").length <= 2);
});

test("QA EXT-07: markup in every backend string field is rendered as text", () => {
  const evil = "<img src=x onerror=alert(1)><a href=javascript:alert(2)>x</a>";
  const a = assessment({
    summary: evil, missing_information: [evil],
    evidence: [{ claim: evil, source_url: "https://a.synthetic.example/", source_title: evil, evidence_type: "community", claim_status: "allegation", retrieved_at: "2026-10-17T12:00:00Z" }],
    promise_sheet: {
      seller_domain: "shop.synthetic.example",
      sources: [{ source_id: "s1", url: "https://shop.synthetic.example/r", title: evil, content: "x", content_kind: "merchant_page", retrieved_at: "2026-10-17T12:00:00Z", seller_domain: "shop.synthetic.example" }],
      records: [{ topic: "returns", status: "supported_as_statement", merchant_statement: evil, explanation: evil, quotes: [{ source_id: "s1", quote: evil }], conditions: { region: evil } }],
      domain_context: { status: "unavailable", explanation: evil }, image_context: { status: "unavailable", explanation: evil },
    },
  });
  const { panel } = renderText(a);
  assert.equal(panel.querySelectorAll("img").length, 0);
  for (const anchor of panel.querySelectorAll("a")) assert.match(anchor.getAttribute("href"), /^https:\/\//);
  assert.ok(panel.textContent.split(evil).length > 5);
});

// ---------------------------------------------------------------- labels (tech-lead confirmed)

test("QA labels: evidence is 'Unverified source' unless claim_status is verified_fact", () => {
  const statuses = ["verified_fact", "allegation", "inference", "unknown"];
  const evidence = statuses.map((claim_status, i) => ({
    claim: "SYNTHETIC", source_url: `https://e${i}.synthetic.example/`, evidence_type: "official", claim_status, retrieved_at: "2026-10-17T12:00:00Z",
  }));
  for (let i = 0; i < statuses.length; i++) {
    const { vm, panel } = renderText(assessment({ evidence: [evidence[i]] }));
    const expected = statuses[i] === "verified_fact" ? "Verified fact" : "Unverified source";
    assert.equal(vm.sources[0].badge, expected, statuses[i]);
    assert.equal(vm.sources[0].unverified, statuses[i] !== "verified_fact");
    assert.ok(panel.textContent.includes(expected));
  }
});

test("QA labels: promise quotes from merchant_page say \"Merchant's own page\"; other kinds say 'Unverified source'", () => {
  const kinds = ["merchant_page", "search_snippet", "independent_page"];
  for (const kind of kinds) {
    const a = assessment({
      promise_sheet: {
        seller_domain: "shop.synthetic.example",
        sources: [{ source_id: "s1", url: "https://shop.synthetic.example/r", content: "Free returns.", content_kind: kind, retrieved_at: "2026-10-17T12:00:00Z", seller_domain: "shop.synthetic.example" }],
        records: [{ topic: "returns", status: "supported_as_statement", merchant_statement: "Free returns.", explanation: "Merchant statement in retrieved content; fulfillment unverified.", quotes: [{ source_id: "s1", quote: "Free returns." }] }],
      },
    });
    const { vm, panel } = renderText(a);
    const badge = vm.promises[0].quotes[0].source.badge;
    const cite = panel.querySelectorAll("blockquote")[0].parentNode;
    if (kind === "merchant_page") {
      assert.equal(badge, "Merchant's own page");
      assert.ok(cite.textContent.includes("Merchant's own page"));
      assert.ok(!cite.textContent.includes("Unverified source"));
    } else {
      assert.equal(badge, "Unverified source", kind);
      assert.ok(cite.textContent.includes("Unverified source"), kind);
    }
  }
});

test("QA OUT-02: mock data shows SIMULATION; partial/live never do", () => {
  for (const mode of ["mock", "partial", "live"]) {
    const { vm, panel } = renderText(assessment({ data_mode: mode }));
    assert.equal(vm.dataMode.isSimulation, mode === "mock");
    assert.equal(/SIMULATION/.test(panel.textContent), mode === "mock", mode);
  }
});

test("QA RISK-01/02: panel wording never shows probabilities, accusations or authenticity certainty", () => {
  const combos = [["LOWER_RISK", "CONSIDER_BUYING"], ["HIGHER_RISK", "AVOID"], ["INSUFFICIENT_EVIDENCE", "VERIFY_FIRST"], ["INSUFFICIENT_EVIDENCE", "NEED_MORE_INFORMATION"]];
  for (const [risk, decision] of combos) {
    for (const name of ["synthetic-promise-conflict.json", null]) {
      const base = name ? fixture(name, "req-1").assessment : assessment();
      const research = [{ provider: "tavily", status: "partial", provider_called: true, records_received: 5, records_retained: 2, records_filtered: 3 }];
      const { panel } = renderText({ ...base, seller_risk: risk, decision, research });
      const text = panel.textContent.replace(DISCLAIMER, "");
      for (const pattern of BANNED) assert.doesNotMatch(text, pattern, `${risk}/${decision}`);
      assert.ok(panel.textContent.includes(DISCLAIMER));
    }
  }
});

// ---------------------------------------------------------------- EXT-01 / manifest

test("QA EXT-01: manifest has no passive injection, broad hosts, web-accessible resources or external messaging", () => {
  const m = JSON.parse(readFileSync(join(EXT_ROOT, "manifest.json"), "utf8"));
  for (const key of ["content_scripts", "web_accessible_resources", "externally_connectable", "optional_host_permissions", "declarative_net_request"]) {
    assert.equal(m[key], undefined, key);
  }
  const text = JSON.stringify(m);
  assert.doesNotMatch(text, /<all_urls>|\*:\/\/\*|https?:\/\/\*/);
  for (const host of m.host_permissions) assert.match(host, /^http:\/\/(127\.0\.0\.1|localhost):\d+\/\*$/);
  for (const p of m.permissions) assert.ok(["activeTab", "scripting", "storage"].includes(p), p);
  assert.ok(!m.permissions.includes("tabs") && !m.permissions.includes("history") && !m.permissions.includes("webRequest"));
  const bg = readFileSync(join(EXT_ROOT, "src", "background.js"), "utf8");
  assert.doesNotMatch(bg, /onUpdated[\s\S]{0,200}executeScript|onActivated|webNavigation/);
  assert.match(bg, /action\.onClicked\.addListener/);
});

test("QA EXT-07: untrusted senders (web page, other extension, sub-frame, extension page) get nothing", async () => {
  const t = setup();
  const senders = [
    { id: "otherextensionidotherextensionid", frameId: 0, tab: { id: 7, url: LISTING } },
    { id: RUNTIME_ID, frameId: 3, tab: { id: 7, url: LISTING } },
    { id: RUNTIME_ID, frameId: 0 },
    { url: LISTING, frameId: 0, tab: { id: 7, url: LISTING } },
    { id: RUNTIME_ID, frameId: 0, tab: { id: -1, url: LISTING } },
  ];
  for (const sender of senders) {
    for (const msg of [{ type: "check" }, { type: "getState" }, { type: "openOptions" }]) {
      const res = await t.handle(msg, sender);
      assert.deepEqual(res, { ok: false, error: "untrusted_sender" });
    }
  }
  assert.equal(t.calls.length, 0);
  assert.ok(R.isTrustedWorkerSender({ id: RUNTIME_ID }, RUNTIME_ID));
  assert.ok(!R.isTrustedWorkerSender({ id: RUNTIME_ID, tab: { id: 1 } }, RUNTIME_ID));
});
