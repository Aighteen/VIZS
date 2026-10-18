// QA round 3: the angle-bracket listing format (QA-07 fix) is an unambiguous boundary.
// SYNTHETIC data; no network.
import assert from "node:assert/strict";
import { test } from "node:test";
import { buildEvaluateRequest, buildMessageText, listingUrlFromSender } from "../src/lib/request.js";

test("QA-07: tab hrefs never contain raw <, > or whitespace, so the brackets cannot be broken out of", () => {
  const hostile = [
    "https://synthetic-shop.com/p<x>", "https://synthetic-shop.com/p?q=<b>&r=>", "https://synthetic-shop.com/p#<frag>",
    "https://synthetic-shop.com/a b", "https://synthetic-shop.com/p?x=> https://evil-shop.com/",
  ];
  for (const raw of hostile) {
    const res = listingUrlFromSender({ tab: { url: raw } });
    assert.equal(res.ok, true, raw);
    const message = buildMessageText(res.value, "$5");
    assert.equal(message.split("<").length - 1, 1, message);
    assert.equal(message.split(">").length - 1, 1, message);
    assert.match(message, /^Check this listing <https:\/\/synthetic-shop\.com\/\S*> price \$5$/);
  }
});

test("QA-07: a maximum-length listing URL fits the backend's 4000-character message limit", () => {
  const href = "https://synthetic-shop.com/p?" + "k=v&".repeat(600);
  const res = listingUrlFromSender({ tab: { url: href.slice(0, 2048) } });
  assert.equal(res.ok, true);
  const req = buildEvaluateRequest({ backendUrl: "http://127.0.0.1:8000", token: "qa-synthetic-token", listingUrl: res.value, price: "1,250.5", requestId: "r" });
  assert.equal(req.ok, true);
  const body = JSON.parse(req.init.body);
  assert.ok(body.message_text.length <= 4000);
  assert.ok(body.message_text.endsWith("> price $1250.50"));
});
