// QA OUT-03 cross-channel check. tests/qa_fixtures/cross_channel_response.json is a SYNTHETIC
// response produced by the Python backend pipeline with mocked providers (kept in sync by
// tests/test_qa_cross_channel.py). The phone text in it comes from the Python formatter; here the
// same assessment goes through the extension validator, view-model and renderer.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { buildMessageText } from "../src/lib/request.js";
import { safeHttpUrl } from "../src/lib/safe-url.js";
import { validateEvaluateResponse } from "../src/lib/response.js";
import { buildPanelViewModel } from "../src/lib/view-model.js";
import { EXT_ROOT, fakeDocument, loadClassicScripts } from "./helpers.js";

const QA = join(EXT_ROOT, "..", "tests", "qa_fixtures");
const R = loadClassicScripts(["src/content/styles.js", "src/content/render.js"]).VIZS_RENDER;
const URL_RE = /https?:\/\/[^\s"'<>]+/g;

function load(name) {
  const data = JSON.parse(readFileSync(join(QA, name), "utf8"));
  assert.match(data.label, /^SYNTHETIC/);
  return data;
}

test("QA OUT-03: real backend output passes the extension validator and keeps decision, risk and promise rows", () => {
  const { response } = load("cross_channel_response.json");
  const result = validateEvaluateResponse(response, response.assessment.request_id);
  assert.equal(result.ok, true, result.error);
  const a = response.assessment;
  const vm = structuredClone(buildPanelViewModel(result.assessment));
  assert.equal(vm.risk.value, a.seller_risk);
  assert.equal(vm.decision.value, a.decision);
  assert.equal(vm.summary, a.summary);
  assert.deepEqual(vm.missingInformation, a.missing_information);
  assert.deepEqual(vm.promises.map((p) => p.status), a.promise_sheet.records.map((r) => r.status));
  assert.deepEqual(vm.promises.map((p) => p.explanation), a.promise_sheet.records.map((r) => r.explanation));
  assert.deepEqual(vm.promises.flatMap((p) => p.quotes.map((q) => q.text)), a.promise_sheet.records.flatMap((r) => r.quotes.map((q) => q.quote)));
  assert.equal(vm.dataMode.value, a.data_mode);
});

test("QA OUT-03: every quote and link in the phone reply also appears in the extension panel", () => {
  const { response } = load("cross_channel_response.json");
  const phone = response.message_text;
  const vm = buildPanelViewModel(validateEvaluateResponse(response, response.assessment.request_id).assessment);
  const panel = R.renderPanel(fakeDocument(), structuredClone(vm));
  const hrefs = new Set(panel.querySelectorAll("a").map((a) => a.getAttribute("href")));
  for (const url of phone.match(URL_RE) || []) assert.ok(hrefs.has(url), `phone link missing from panel: ${url}`);
  for (const [, quote] of phone.matchAll(/"([^"]+)"/g)) assert.ok(panel.textContent.includes(quote), quote);
  assert.ok(phone.includes(response.assessment.seller_risk));
  assert.ok(panel.textContent.includes("Not enough evidence"));
  // Both channels say authenticity is not established / certified.
  assert.match(phone, /authenticity is not established/);
  assert.match(panel.textContent, /does not certify authenticity/);
});

test("QA INPUT-01: extension message_text format matches the strings the backend URL/price parser is tested with", () => {
  const { cases } = load("extension_message_texts.json");
  for (const c of cases) {
    assert.equal(safeHttpUrl(c.href), c.href, c.id);
    assert.equal(buildMessageText(c.href, c.price), c.message_text, c.id);
  }
});
