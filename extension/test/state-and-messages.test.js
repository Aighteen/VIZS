import assert from "node:assert/strict";
import { test } from "node:test";
import { isTrustedContentSender, parseCommand } from "../src/lib/messages.js";
import { INITIAL_STATE, STATES, reduce } from "../src/lib/pet-state.js";
import { RUNTIME_ID, contentSender } from "./helpers.js";

test("state machine: idle -> searching -> finished; duplicates and stale tokens ignored", () => {
  let s = reduce(INITIAL_STATE, { type: "CHECK", token: "a" });
  assert.equal(s.name, STATES.SEARCHING);
  assert.equal(reduce(s, { type: "CHECK", token: "b" }), s);
  assert.equal(reduce(s, { type: "RESULT", token: "old", viewModel: {} }), s);
  assert.equal(reduce(s, { type: "FAIL", token: "old", error: {} }), s);
  assert.equal(reduce(s, { type: "FAIL", token: null, error: {} }), s);
  s = reduce(s, { type: "RESULT", token: "a", viewModel: { ok: 1 } });
  assert.equal(s.name, STATES.FINISHED);
  assert.equal(reduce(s, { type: "CHECK", token: "c" }).name, STATES.SEARCHING);
  assert.equal(reduce(s, { type: "RESET" }), INITIAL_STATE);
  assert.deepEqual(Object.values(STATES).sort(), ["error", "finished", "idle", "searching"]); // no reviewing phase
});

test("state machine: error and explicit retry", () => {
  let s = reduce(INITIAL_STATE, { type: "CHECK", token: "a" });
  s = reduce(s, { type: "FAIL", token: "a", error: { code: "network" } });
  assert.equal(s.name, STATES.ERROR);
  s = reduce(s, { type: "CHECK", token: "b" });
  assert.equal(s.name, STATES.SEARCHING);
  assert.equal(s.token, "b");
});

test("service worker message-sender validation", () => {
  assert.equal(isTrustedContentSender(contentSender(), RUNTIME_ID), true);
  assert.equal(isTrustedContentSender(contentSender({ id: "x" }), RUNTIME_ID), false);
  assert.equal(isTrustedContentSender({ id: RUNTIME_ID, frameId: 0 }, RUNTIME_ID), false); // no tab: extension page
  assert.equal(isTrustedContentSender(contentSender({ frameId: 1 }), RUNTIME_ID), false);
  assert.equal(isTrustedContentSender(contentSender({ tab: { url: "https://a.example" } }), RUNTIME_ID), false);
  assert.equal(isTrustedContentSender(contentSender(), ""), false);
  assert.equal(isTrustedContentSender(null, RUNTIME_ID), false);
});

test("command parsing rejects unknown types, extra fields and bad values", () => {
  assert.deepEqual(parseCommand({ type: "check" }), { type: "check", price: null });
  assert.deepEqual(parseCommand({ type: "check", price: "12" }), { type: "check", price: "12" });
  assert.equal(parseCommand({ type: "check", price: 12 }), null);
  assert.equal(parseCommand({ type: "check", price: "1".repeat(41) }), null);
  assert.equal(parseCommand({ type: "check", url: "https://evil.example" }), null);
  assert.equal(parseCommand({ type: "getToken" }), null);
  assert.equal(parseCommand({ type: "dismiss", extra: 1 }), null);
  assert.deepEqual(parseCommand({ type: "savePosition", x: 10.4, y: 20 }), { type: "savePosition", x: 10, y: 20 });
  assert.equal(parseCommand({ type: "savePosition", x: -1, y: 20 }), null);
  assert.equal(parseCommand({ type: "savePosition", x: Infinity, y: 20 }), null);
  assert.equal(parseCommand("check"), null);
  assert.equal(parseCommand(null), null);
});
