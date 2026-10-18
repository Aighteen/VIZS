import assert from "node:assert/strict";
import { test } from "node:test";
import { validateBackendUrl, validateToken, normalizeSettings, CLIENT_TIMEOUT_MS } from "../src/lib/config.js";
import { buildEvaluateRequest, listingUrlFromSender, normalizePrice } from "../src/lib/request.js";
import { LISTING, contentSender } from "./helpers.js";

const base = { backendUrl: "http://127.0.0.1:8000", token: "synthetic-token_123", requestId: "11111111-2222-4333-8444-555555555555" };

test("request body and headers: channel debug, bearer token, listing URL, no price", () => {
  const req = buildEvaluateRequest({ ...base, listingUrl: LISTING, price: null });
  assert.equal(req.ok, true);
  assert.equal(req.url, "http://127.0.0.1:8000/api/v1/extension/evaluate");
  assert.equal(req.init.method, "POST");
  assert.deepEqual(req.init.headers, { "Content-Type": "application/json", Authorization: "Bearer synthetic-token_123" });
  assert.equal(req.init.credentials, "omit");
  assert.deepEqual(JSON.parse(req.init.body), {
    request_id: base.requestId,
    message_text: `Check this listing ${LISTING}`,
    channel: "debug",
  });
});

test("optional price is appended as an explicit dollar amount (backend requires currency marker)", () => {
  const req = buildEvaluateRequest({ ...base, listingUrl: LISTING, price: "89.9" });
  assert.equal(JSON.parse(req.init.body).message_text, `Check this listing ${LISTING} price $89.90`);
  assert.deepEqual(normalizePrice("$1,234.5"), { ok: true, value: "$1234.50" });
  assert.deepEqual(normalizePrice("USD 45"), { ok: true, value: "$45" });
  assert.deepEqual(normalizePrice("  "), { ok: true, value: null });
  assert.equal(normalizePrice("abc").ok, false);
  assert.equal(normalizePrice("-5").ok, false);
  assert.equal(normalizePrice("12.345").ok, false);
  assert.equal(buildEvaluateRequest({ ...base, listingUrl: LISTING, price: "free" }).ok, false);
});

test("listing URL comes from sender.tab.url only, and must be http(s)", () => {
  assert.deepEqual(listingUrlFromSender(contentSender()), { ok: true, value: LISTING });
  assert.equal(listingUrlFromSender(contentSender({ tab: { id: 7 } })).ok, false);
  assert.equal(listingUrlFromSender(contentSender({ tab: { id: 7, url: "chrome://settings" } })).ok, false);
  assert.equal(listingUrlFromSender(contentSender({ tab: { id: 7, url: "file:///etc/passwd" } })).ok, false);
  assert.equal(listingUrlFromSender(contentSender({ tab: { id: 7, url: "https://u:p@shop.example/" } })).ok, false);
});

test("request refuses missing config, bad ids and over-long messages", () => {
  assert.equal(buildEvaluateRequest({ ...base, token: null, listingUrl: LISTING }).ok, false);
  assert.equal(buildEvaluateRequest({ ...base, backendUrl: null, listingUrl: LISTING }).ok, false);
  assert.equal(buildEvaluateRequest({ ...base, requestId: "", listingUrl: LISTING }).ok, false);
  assert.equal(buildEvaluateRequest({ ...base, listingUrl: "javascript:alert(1)" }).ok, false);
  assert.equal(buildEvaluateRequest({ ...base, listingUrl: "https://shop.example/?q=" + "a".repeat(2000) }).ok, true);
  assert.equal(buildEvaluateRequest({ ...base, listingUrl: "https://shop.example/?q=" + "a".repeat(3000) }).ok, false);
});

test("backend URL validation: loopback http with port, or https only", () => {
  assert.deepEqual(validateBackendUrl("http://127.0.0.1:8000"), { ok: true, value: "http://127.0.0.1:8000" });
  assert.deepEqual(validateBackendUrl("http://localhost:8765/"), { ok: true, value: "http://localhost:8765" });
  assert.deepEqual(validateBackendUrl("https://vizs.synthetic.example"), { ok: true, value: "https://vizs.synthetic.example" });
  for (const bad of ["http://127.0.0.1", "http://example.com:8000", "http://192.168.1.5:8000", "ftp://127.0.0.1:21",
    "javascript:alert(1)", "https://u:p@x.example", "http://127.0.0.1:8000/api", "https://x.example/?a=1", "", "not a url"]) {
    assert.equal(validateBackendUrl(bad).ok, false, bad);
  }
});

test("token validation and settings normalization", () => {
  assert.equal(validateToken("abc_DEF-123").ok, true);
  assert.equal(validateToken("has space").ok, false);
  assert.equal(validateToken("a".repeat(501)).ok, false);
  assert.equal(validateToken("").ok, false);
  assert.deepEqual(normalizeSettings({}), { backendUrl: "http://127.0.0.1:8000", token: null });
  assert.deepEqual(normalizeSettings({ backendUrl: "http://evil.example:1", pairingToken: "t" }), { backendUrl: null, token: "t" });
  assert.ok(CLIENT_TIMEOUT_MS >= 100_000 && CLIENT_TIMEOUT_MS <= 120_000);
});
