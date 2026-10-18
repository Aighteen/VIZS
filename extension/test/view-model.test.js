import assert from "node:assert/strict";
import { test } from "node:test";
import { DATA_MODE_LABELS, DECISION_LABELS, PROMISE_STATUS_LABELS, RISK_LABELS } from "../src/lib/labels.js";
import { validateEvaluateResponse } from "../src/lib/response.js";
import { safeHttpUrl } from "../src/lib/safe-url.js";
import { buildPanelViewModel } from "../src/lib/view-model.js";
import { fixture } from "./helpers.js";

function vmFor(name) {
  const result = validateEvaluateResponse(fixture(name, "r1"), "r1");
  assert.equal(result.ok, true, result.error);
  return buildPanelViewModel(result.assessment);
}

test("promise conflict shows both quotes with their source links and labels", () => {
  const vm = vmFor("synthetic-promise-conflict.json");
  const conflict = vm.promises.find((p) => p.status === "conflicting");
  assert.equal(conflict.topic, "Return cost");
  assert.equal(conflict.statusLabel, "Conflicting terms");
  assert.equal(conflict.merchantStatement, "Free returns.");
  assert.match(conflict.conditions, /Region: US/);
  assert.deepEqual(conflict.quotes.map((q) => q.text), ["Free returns.", "US customers pay return shipping."]);
  assert.equal(conflict.quotes[0].source.href, "https://shop.synthetic.example/product");
  assert.equal(conflict.quotes[0].source.unverified, false); // merchant's own page: shown as merchant wording
  assert.equal(conflict.quotes[1].source.href, "https://shop.synthetic.example/returns");
  assert.equal(conflict.quotes[1].source.unverified, true); // search snippet
  assert.equal(conflict.quotes[1].source.badge, "Unverified source");
  const missing = vm.promises.find((p) => p.status === "not_disclosed");
  assert.equal(missing.statusLabel, "Not disclosed in the sources checked");
});

test("mock data mode is clearly labeled as a simulation", () => {
  const vm = vmFor("synthetic-promise-conflict.json");
  assert.equal(vm.dataMode.isSimulation, true);
  assert.match(vm.dataMode.note, /SIMULATION/);
  assert.match(vm.dataMode.note, /not a real seller check/);
  assert.equal(vmFor("synthetic-insufficient.json").dataMode.label, "Partial data");
});

test("at most two source links; unverified sources are labeled", () => {
  const vm = vmFor("synthetic-promise-conflict.json");
  assert.equal(vm.sources.length, 2);
  assert.equal(vm.sources[0].badge, "Verified fact");
  assert.equal(vm.sources[0].unverified, false);
  assert.equal(vm.sources[1].badge, "Unverified source");
  assert.equal(vm.sources[1].unverified, true);
  assert.ok(!vm.sources.some((s) => s.href.includes("third.synthetic.example")));
  const ins = vmFor("synthetic-insufficient.json");
  assert.equal(ins.sources[0].badge, "Unverified source");
});

test("research status line and domain/image context explanations", () => {
  const vm = vmFor("synthetic-insufficient.json");
  assert.deepEqual(vm.research, ["Research (Tavily): partial results — 2 of 5 results kept, 3 filtered."]);
  const conflict = vmFor("synthetic-promise-conflict.json");
  assert.match(conflict.research[0], /all results were filtered out/);
  assert.deepEqual(conflict.contexts.map((c) => [c.title, c.statusLabel]), [["Domain registration", "Not available"], ["Photo checks", "Not available"]]);
  assert.match(conflict.contexts[1].explanation, /no conclusion/);
});

test("hostile payload: javascript:/data: links rejected, markup kept as plain strings", () => {
  const vm = vmFor("synthetic-hostile.json");
  assert.equal(vm.summary, "<img src=x onerror=alert(1)> Synthetic hostile summary");
  assert.equal(vm.sources.length, 1);
  assert.equal(vm.sources[0].href, "https://complaints.synthetic.example/case/9");
  const quoteSource = vm.promises[0].quotes[0].source;
  assert.equal(quoteSource.href, null);
  assert.equal(quoteSource.badge, "Unverified source");
  assert.equal(vm.decision.label, "Avoid for now");
});

test("safeHttpUrl only allows http(s) without credentials", () => {
  assert.equal(safeHttpUrl("https://a.example/x"), "https://a.example/x");
  for (const bad of ["javascript:alert(1)", "JAVASCRIPT:alert(1)", " javascript:alert(1)", "data:text/html,x", "vbscript:x",
    "file:///etc/passwd", "chrome://settings", "https://u:p@a.example/", "//a.example", "", null, 5]) {
    assert.equal(safeHttpUrl(bad), null, String(bad));
  }
});

test("labels never claim certainty or percentages", () => {
  const all = [
    ...Object.values(RISK_LABELS), ...Object.values(DECISION_LABELS), ...Object.values(PROMISE_STATUS_LABELS),
    ...Object.values(DATA_MODE_LABELS).flatMap((m) => [m.label, m.note]),
    vmFor("synthetic-insufficient.json").disclaimer,
  ];
  for (const text of all) {
    assert.doesNotMatch(text, /%|percent|guarantee(d)?\b|certain(ly)?\b|authentic\b|scam|fraudulent seller/i, text);
  }
});
