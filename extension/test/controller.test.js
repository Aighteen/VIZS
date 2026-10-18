import assert from "node:assert/strict";
import { test } from "node:test";
import { PetController } from "../src/lib/controller.js";
import { LISTING, RUNTIME_ID, contentSender, fixture, jsonResponse } from "./helpers.js";

function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function setup(opts = {}) {
  const calls = [];
  const delivered = [];
  let n = 0;
  let tabUrl = LISTING;
  const pendingFetches = [];
  const controller = new PetController({
    runtimeId: RUNTIME_ID,
    newRequestId: () => `req-${++n}`,
    loadSettings: async () => opts.settings ?? { backendUrl: "http://127.0.0.1:8000", token: "synthetic-token" },
    fetchImpl: (url, init) => {
      calls.push({ url, init });
      if (opts.fetchImpl) return opts.fetchImpl(url, init, calls.length);
      const d = deferred();
      init.signal.addEventListener("abort", () => d.reject(new DOMException("aborted", "AbortError")));
      pendingFetches.push(d);
      return d.promise;
    },
    deliver: async (tabId, message) => delivered.push({ tabId, message }),
    getTabUrl: async () => tabUrl,
    timeoutMs: opts.timeoutMs ?? 110_000,
    // Unref only long timers so never-settled synthetic fetches do not keep the test
    // process alive for 110 s; short ones must stay ref'd or the loop empties first (Node 22).
    setTimer: (fn, ms) => (ms > 1000 ? setTimeout(fn, ms).unref() : setTimeout(fn, ms)),
  });
  return {
    controller, calls, delivered, pendingFetches,
    setTabUrl: (u) => { tabUrl = u; },
    lastBody: () => JSON.parse(calls.at(-1).init.body),
  };
}

test("check sends one request with URL from sender.tab.url and channel debug", async () => {
  const t = setup();
  // A hostile page cannot pick the URL: extra fields such as `url` are rejected outright.
  const forged = await t.controller.handle({ type: "check", url: "https://evil.example/" }, contentSender());
  assert.deepEqual(forged, { ok: false, error: "invalid_message" });
  const res = await t.controller.handle({ type: "check", price: "50" }, contentSender());
  assert.equal(res.state.name, "searching");
  assert.equal(t.calls.length, 1);
  assert.equal(t.calls[0].init.headers.Authorization, "Bearer synthetic-token");
  assert.deepEqual(t.lastBody(), { request_id: "req-1", message_text: `Check this listing <${LISTING}> price $50`, channel: "debug" });
});

test("duplicate clicks while searching send exactly one request", async () => {
  const t = setup();
  const [a, b] = await Promise.all([
    t.controller.handle({ type: "check" }, contentSender()),
    t.controller.handle({ type: "check" }, contentSender()),
  ]);
  const c = await t.controller.handle({ type: "check" }, contentSender());
  assert.equal(t.calls.length, 1);
  assert.equal(a.state.name, "searching");
  assert.equal(b.ignored, true);
  assert.equal(c.ignored, true);
  t.pendingFetches[0].resolve(jsonResponse(fixture("synthetic-insufficient.json", "req-1")));
  assert.equal(await t.controller.pending(7), "finished");
});

test("insufficient evidence is a finished state with a panel view-model, not an error", async () => {
  const t = setup();
  await t.controller.handle({ type: "check" }, contentSender());
  t.pendingFetches[0].resolve(jsonResponse(fixture("synthetic-insufficient.json", "req-1")));
  assert.equal(await t.controller.pending(7), "finished");
  const msg = t.delivered.at(-1).message;
  assert.equal(msg.type, "state");
  assert.equal(msg.state.name, "finished");
  assert.equal(msg.state.viewModel.risk.label, "Not enough evidence");
  assert.equal(msg.state.viewModel.decision.label, "Verify before buying");
  assert.equal(msg.state.viewModel.insufficient, true);
  assert.equal(msg.state.error, null);
});

test("navigation (tab URL changed) while pending discards the result", async () => {
  const t = setup();
  await t.controller.handle({ type: "check" }, contentSender());
  t.setTabUrl("https://other.synthetic.example/listing");
  t.pendingFetches[0].resolve(jsonResponse(fixture("synthetic-insufficient.json", "req-1")));
  assert.equal(await t.controller.pending(7), "discarded");
  assert.ok(t.delivered.every((d) => d.message.state.name !== "finished"));
  assert.equal(t.controller.stateFor(7).name, "idle");
});

test("navigation event (tabs.onUpdated) and dismissal abort and discard the pending request", async () => {
  for (const action of ["navigated-event", "dismiss", "navigated-message"]) {
    const t = setup();
    await t.controller.handle({ type: "check" }, contentSender());
    const pending = t.controller.pending(7);
    let res = null;
    if (action === "navigated-event") t.controller.discard(7);
    else res = await t.controller.handle({ type: action === "dismiss" ? "dismiss" : "navigated" }, contentSender());
    if (res) {
      assert.equal(res.discarded, true);
      assert.match(res.note, /not reversed/); // no claim that provider costs are undone
    }
    assert.equal(await pending, "discarded", action);
    assert.equal(t.delivered.length, 0, action);
    // A new check after dismissal is a fresh request; the late old result cannot leak into it.
    await t.controller.handle({ type: "check" }, contentSender());
    assert.equal(t.calls.length, 2);
    assert.equal(t.lastBody().request_id, "req-2");
  }
});

test("a late response for an old request id never finishes a newer request", async () => {
  const fetches = [];
  const t = setup({ fetchImpl: () => { const d = deferred(); fetches.push(d); return d.promise; } });
  await t.controller.handle({ type: "check" }, contentSender());
  const first = t.controller.pending(7);
  t.controller.discard(7); // abort is ignored by this fake fetch, simulating a late response
  await t.controller.handle({ type: "check" }, contentSender());
  fetches[0].resolve(jsonResponse(fixture("synthetic-insufficient.json", "req-1")));
  assert.equal(await first, "discarded");
  assert.equal(t.controller.stateFor(7).name, "searching");
  assert.equal(t.controller.stateFor(7).token, "req-2");
  // Response echoing a different request id is invalid, not finished.
  fetches[1].resolve(jsonResponse(fixture("synthetic-insufficient.json", "req-1")));
  assert.equal(await t.controller.pending(7), "error");
  assert.equal(t.controller.stateFor(7).error.code, "invalid_response");
});

const STATUS_CASES = [
  [401, "pairing", true],
  [403, "origin", true],
  [429, "busy", false],
  [503, "unavailable", false],
  [504, "server_timeout", false],
  [502, "dependency", false],
  [422, "rejected", false],
  [500, "server", false],
];

for (const [status, code, showSettings] of STATUS_CASES) {
  test(`HTTP ${status} maps to error "${code}" with explicit retry and no automatic retry`, async () => {
    const t = setup({ fetchImpl: async () => jsonResponse({ detail: "synthetic" }, status) });
    await t.controller.handle({ type: "check" }, contentSender());
    assert.equal(await t.controller.pending(7), "error");
    const state = t.controller.stateFor(7);
    assert.equal(state.error.code, code);
    assert.equal(state.error.showSettings, showSettings);
    assert.equal(state.error.retryable, true);
    assert.doesNotMatch(state.error.message, /%/);
    assert.equal(t.calls.length, 1, "no automatic retry");
    // Explicit retry is a user action and sends exactly one new request.
    await t.controller.handle({ type: "check" }, contentSender());
    await t.controller.pending(7);
    assert.equal(t.calls.length, 2);
  });
}

test("network failure maps to network error", async () => {
  const t = setup({ fetchImpl: async () => { throw new TypeError("Failed to fetch"); } });
  await t.controller.handle({ type: "check" }, contentSender());
  assert.equal(await t.controller.pending(7), "error");
  assert.equal(t.controller.stateFor(7).error.code, "network");
  assert.equal(t.calls.length, 1);
});

test("client timeout aborts the fetch and maps to client_timeout", async () => {
  const t = setup({ timeoutMs: 20 });
  await t.controller.handle({ type: "check" }, contentSender());
  assert.equal(await t.controller.pending(7), "error");
  assert.equal(t.controller.stateFor(7).error.code, "client_timeout");
});

test("invalid JSON and invalid payloads become error, never finished", async () => {
  const bad = [
    "not json{",
    "",
    JSON.stringify({ message_text: "no assessment" }),
    JSON.stringify({ assessment: { ...fixture("synthetic-insufficient.json", "req-1").assessment, decision: "CONSIDER_BUYING" } }),
    JSON.stringify({ assessment: { ...fixture("synthetic-insufficient.json", "req-1").assessment, seller_risk: "SAFE" } }),
    JSON.stringify({ assessment: { ...fixture("synthetic-insufficient.json", "req-1").assessment, summary: "" } }),
    JSON.stringify({ assessment: { ...fixture("synthetic-insufficient.json", "req-1").assessment, data_mode: "real" } }),
    JSON.stringify([1, 2, 3]),
  ];
  for (const body of bad) {
    const t = setup({ fetchImpl: async () => jsonResponse(body, 200) });
    await t.controller.handle({ type: "check" }, contentSender());
    assert.equal(await t.controller.pending(7), "error", body.slice(0, 60));
    assert.equal(t.controller.stateFor(7).error.code, "invalid_response");
  }
});

test("not paired: error state with settings action and no request sent", async () => {
  const t = setup({ settings: { backendUrl: "http://127.0.0.1:8000", token: null } });
  const res = await t.controller.handle({ type: "check" }, contentSender());
  assert.equal(res.state.name, "error");
  assert.equal(res.state.error.code, "not_paired");
  assert.equal(res.state.error.showSettings, true);
  assert.equal(t.calls.length, 0);
});

test("invalid price and unsupported pages fail before any request", async () => {
  const t = setup();
  const r1 = await t.controller.handle({ type: "check", price: "lots" }, contentSender());
  assert.equal(r1.state.error.code, "invalid_input");
  const r2 = await t.controller.handle({ type: "check" }, contentSender({ tab: { id: 7, url: "chrome://extensions" } }));
  assert.equal(r2.state.error.code, "unsupported_page");
  assert.equal(t.calls.length, 0);
});

test("untrusted senders cannot trigger requests or read state", async () => {
  const t = setup();
  const senders = [
    contentSender({ id: "otherextensionidotherextensionid" }), // another extension
    { id: RUNTIME_ID, url: "chrome-extension://x/options.html" }, // extension page (no tab)
    contentSender({ frameId: 3 }), // sub-frame
    contentSender({ tab: { id: -1, url: LISTING } }),
    undefined,
  ];
  for (const s of senders) {
    assert.deepEqual(await t.controller.handle({ type: "check" }, s), { ok: false, error: "untrusted_sender" });
    assert.deepEqual(await t.controller.handle({ type: "getState" }, s), { ok: false, error: "untrusted_sender" });
  }
  assert.equal(t.calls.length, 0);
});

test("tabs are independent: one in-flight request per tab", async () => {
  const t = setup();
  await t.controller.handle({ type: "check" }, contentSender());
  await t.controller.handle({ type: "check" }, contentSender({ tab: { id: 8, url: LISTING } }));
  await t.controller.handle({ type: "check" }, contentSender({ tab: { id: 8, url: LISTING } }));
  assert.equal(t.calls.length, 2);
});
