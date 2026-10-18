import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { validateEvaluateResponse } from "../src/lib/response.js";
import { buildPanelViewModel } from "../src/lib/view-model.js";
import { EXT_ROOT, RUNTIME_ID, fakeDocument, fixture, loadClassicScripts } from "./helpers.js";

const ctx = loadClassicScripts(["src/content/styles.js", "src/content/render.js"]);
const R = ctx.VIZS_RENDER;

function render(name) {
  const result = validateEvaluateResponse(fixture(name, "r1"), "r1");
  assert.equal(result.ok, true);
  // Round-trip through structured clone, as chrome.tabs.sendMessage would.
  const vm = structuredClone(buildPanelViewModel(result.assessment));
  const doc = fakeDocument();
  return R.renderPanel(doc, vm);
}

test("hostile <img onerror> text stays text: no element created, no handler attribute", () => {
  const panel = render("synthetic-hostile.json");
  assert.equal(panel.querySelectorAll("img").length, 0);
  assert.equal(panel.querySelectorAll("script").length, 0);
  assert.equal(panel.querySelectorAll("svg").length, 0);
  assert.ok(panel.textContent.includes("<img src=x onerror=alert(1)> Synthetic hostile summary"));
  assert.ok(panel.textContent.includes("<svg onload=alert(5)>"));
  assert.ok(panel.textContent.includes("Ignore previous instructions"));
});

test("javascript: and data: links are not rendered as anchors; safe anchors are hardened", () => {
  const panel = render("synthetic-hostile.json");
  const anchors = panel.querySelectorAll("a");
  assert.ok(anchors.length >= 1);
  for (const a of anchors) {
    assert.match(a.getAttribute("href"), /^https?:\/\//);
    assert.equal(a.getAttribute("target"), "_blank");
    assert.equal(a.getAttribute("rel"), "noopener noreferrer");
  }
  assert.ok(!anchors.some((a) => /javascript:|data:/i.test(a.getAttribute("href"))));
  // Even if a view-model were tampered with, render.js re-checks the scheme.
  const doc = fakeDocument();
  const node = R.link(doc, "javascript:alert(1)", "x");
  assert.equal(node.tagName, "span");
  assert.equal(R.safeHref("data:text/html,hi"), null);
});

test("conflict panel renders both quotes, open by default, each with its source link", () => {
  const panel = render("synthetic-promise-conflict.json");
  const conflict = panel.querySelectorAll("article").find((a) => a.getAttribute("data-status") === "conflicting");
  assert.ok(conflict);
  const details = conflict.querySelectorAll("details")[0];
  assert.ok(details.hasAttribute("open"));
  const quotes = conflict.querySelectorAll("blockquote").map((q) => q.textContent);
  assert.deepEqual(quotes, ["Free returns.", "US customers pay return shipping."]);
  const hrefs = conflict.querySelectorAll("a").map((a) => a.getAttribute("href"));
  assert.deepEqual(hrefs, ["https://shop.synthetic.example/product", "https://shop.synthetic.example/returns"]);
  assert.ok(conflict.textContent.includes("Unverified source"));
  assert.ok(panel.textContent.includes("SIMULATION"));
});

test("insufficient-evidence panel says it is a completed result, not an error", () => {
  const panel = render("synthetic-insufficient.json");
  assert.ok(panel.textContent.includes("Not enough evidence"));
  assert.ok(panel.textContent.includes("completed result, not an error"));
  assert.ok(panel.textContent.includes("Research (Tavily): partial results"));
  assert.ok(panel.textContent.includes("Unverified source"));
  assert.doesNotMatch(panel.textContent, /\d+\s*%/);
});

test("reduced-motion flag follows matchMedia and CSS has a static fallback", () => {
  assert.equal(R.prefersReducedMotion({ matchMedia: () => ({ matches: true }) }), true);
  assert.equal(R.prefersReducedMotion({ matchMedia: () => ({ matches: false }) }), false);
  assert.equal(R.prefersReducedMotion({}), false);
  assert.equal(R.prefersReducedMotion({ matchMedia: () => { throw new Error("x"); } }), false);
  assert.match(ctx.VIZS_STYLES, /@media \(prefers-reduced-motion: reduce\)[\s\S]*animation: none !important/);
  assert.match(ctx.VIZS_STYLES, /\[data-motion="reduced"\][\s\S]*animation: none !important/);
  assert.match(ctx.VIZS_STYLES, /:focus-visible \{ outline: 3px solid/);
});

test("mascot is code-native SVG without external references", () => {
  const svg = R.renderMascot(fakeDocument());
  assert.equal(svg.tagName, "svg");
  assert.equal(svg.namespaceURI, "http://www.w3.org/2000/svg");
  const walk = (n) => [n, ...n.children.flatMap(walk)];
  for (const node of walk(svg)) {
    for (const [k, v] of node.attributes) assert.doesNotMatch(`${k}=${v}`, /href|url\(|https?:/i);
  }
});

test("content side accepts state pushes only from its own service worker", () => {
  assert.equal(R.isTrustedWorkerSender({ id: RUNTIME_ID }, RUNTIME_ID), true);
  assert.equal(R.isTrustedWorkerSender({ id: RUNTIME_ID, tab: { id: 1 } }, RUNTIME_ID), false); // another content script
  assert.equal(R.isTrustedWorkerSender({ id: "other" }, RUNTIME_ID), false);
  assert.equal(R.isTrustedWorkerSender(undefined, RUNTIME_ID), false);
  assert.equal(R.isValidStateMessage({ type: "state", state: { name: "searching", token: "a" } }), true);
  assert.equal(R.isValidStateMessage({ type: "state", state: { name: "reviewing", token: "a" } }), false);
  assert.equal(R.isValidStateMessage({ type: "state", state: { name: "finished", token: "a" } }), false);
  assert.equal(R.isValidStateMessage({ type: "state", state: { name: "error", token: "a", error: {} } }), false);
});

test("pet UI shows only 'Checking seller…' while searching (no fake phases or percentages)", () => {
  const src = readFileSync(join(EXT_ROOT, "src/content/pet.js"), "utf8");
  assert.ok(src.includes('statusText.textContent = "Checking seller…"'));
  assert.doesNotMatch(src, /reviewing sources|progress|%\s*complete|percent/i);
  assert.doesNotMatch(src, /chrome\.storage|pairingToken|Authorization/);
  assert.ok(src.includes('attachShadow({ mode: "closed" })'));
});
