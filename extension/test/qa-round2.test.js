// QA round 2: extension side of the Q1 (JSON-only) and QA-03/QA-07 (listing URL fidelity) checks.
// SYNTHETIC data; no network.
import assert from "node:assert/strict";
import { test } from "node:test";
import { buildEvaluateRequest, buildMessageText, listingUrlFromSender } from "../src/lib/request.js";

// Must match tests/test_qa_round2.py::EXTENSION_END_PUNCTUATION and extension_message().
const END_PUNCTUATION = [
  ["https://synthetic-shop.com/product.", null],
  ["https://synthetic-shop.com/p?", null],
  ["https://synthetic-shop.com/p?", "$20"],
  ["https://synthetic-shop.com/sale!", null],
  ["https://synthetic-shop.com/a;b;", null],
  ["https://synthetic-shop.com/p:", null],
  ["https://synthetic-shop.com/p?q=1)", "$5"],
];

test("QA Q1: extension requests always declare application/json and carry no extra Origin", () => {
  const req = buildEvaluateRequest({ backendUrl: "http://127.0.0.1:8000", token: "qa-synthetic-token", listingUrl: "https://synthetic-shop.com/p", price: "5", requestId: "r" });
  assert.equal(req.init.headers["Content-Type"], "application/json");
  assert.equal(req.init.headers.Origin, undefined);
  assert.equal(req.init.method, "POST");
  assert.doesNotThrow(() => JSON.parse(req.init.body));
});

test("QA-07: Chrome-style hrefs keep trailing punctuation and are sent verbatim inside angle brackets", () => {
  for (const [href, price] of END_PUNCTUATION) {
    const tab = listingUrlFromSender({ tab: { url: href } });
    assert.deepEqual(tab, { ok: true, value: href }, href);
    const expected = `Check this listing <${href}>` + (price ? ` price ${price}` : "");
    assert.equal(buildMessageText(href, price), expected);
  }
});
