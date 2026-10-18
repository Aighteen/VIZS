// QA verification for the Photon launcher (PH-03) and bounded bridge handler (PH-01/02).
// SYNTHETIC values only; all child processes, fetches and timers are fakes. No network, no messages.
import test from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { PassThrough } from "node:stream";
import { run, acquireLock, EXIT, FORWARD } from "./launch.mjs";
import { createBridgeHandler } from "./bridge-handler.mjs";

const SECRETS = { PROJECT_ID: "qa-synthetic-project-0001", PROJECT_SECRET: "qa-synthetic-secret-0002", VIZS_REGISTERED_RECIPIENT: "+15550009999" };
const PROVIDER = { XAI_API_KEY: "qa-synthetic-xai-0003", TAVILY_API_KEY: "qa-synthetic-tavily-0004" };

class FakeChild extends EventEmitter {
  static nextPid = 9000;
  constructor() { super(); this.pid = FakeChild.nextPid++; this.stdout = new PassThrough(); this.stderr = new PassThrough(); this.kills = []; this.done = false; }
  kill(signal) { this.kills.push(signal); if (!this.stubborn) this.exit(null, signal); return true; }
  exit(code, signal = null) {
    if (this.done) return; this.done = true;
    this.stdout.end(); this.stderr.end(); this.emit("exit", code, signal);
  }
}

function harness({ env = { ...SECRETS }, onBridge, onApi, lockPath, healthMode, stubbornApi = false, timers } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vizs-qa-launch-"));
  const out = [];
  const calls = [];
  let api = null, bridge = null, signalHandler = null;
  const deps = {
    env, platform: "darwin", pid: 777_001, nodePath: "/fake/node", root: "/fake/repo", spectrumDir: "/fake/spectrum",
    lockPath: lockPath ?? path.join(dir, "launch.lock"),
    exists: (p) => p.endsWith("test-bridge.mjs") || p.endsWith(path.join("node_modules", "spectrum-ts")),
    readFile: () => "", out: (line) => out.push(line), alive: () => false,
    now: (() => { let t = 0; return () => (t += 100); })(),
    sleep: () => new Promise((resolve) => setImmediate(resolve)),
    setTimer: timers ?? (() => () => {}),
    onSignal: (h) => { signalHandler = h; return () => { signalHandler = null; }; },
    healthTimeoutMs: 2_000, pollMs: 1, graceMs: 1,
    spawn: (command, args, options) => {
      const child = new FakeChild();
      calls.push({ command, args, options });
      if (args.includes("app.workflow.dev_server")) { api = child; child.stubborn = stubbornApi; setImmediate(() => onApi?.(child, h)); }
      else { bridge = child; setImmediate(() => onBridge?.(child, h)); }
      return child;
    },
    fetch: async () => {
      if (!api || api.done) throw new Error("ECONNREFUSED");
      const live = calls.find((c) => c.args.includes("app.workflow.dev_server")).args.includes("--live");
      return { ok: true, json: async () => ({ status: "ok", evaluation_ready: true, provider_mode: healthMode ?? (live ? "live" : "offline") }) };
    },
  };
  const h = { deps, out, calls, get api() { return api; }, get bridge() { return bridge; }, signal: (n) => signalHandler?.(n), text: () => out.join("\n") };
  return h;
}

const apiCalls = (h) => h.calls.filter((c) => c.args.includes("app.workflow.dev_server"));

test("QA PH-03: --live is never added from environment, --check, or look-alike flags", async () => {
  const envs = [{ VIZS_PROVIDER_MODE: "live" }, { VIZS_LIVE: "1", LIVE: "true" }, { npm_config_live: "true" }];
  for (const extra of envs) {
    const h = harness({ env: { ...SECRETS, ...extra }, onBridge: (b) => b.exit(0) });
    await run([], h.deps);
    for (const c of h.calls) assert.ok(!c.args.includes("--live"), JSON.stringify(extra));
  }
  const check = harness();
  assert.equal(await run(["--check"], check.deps), EXIT.ok);
  assert.ok(!apiCalls(check)[0].args.includes("--live"));
  for (const argv of [["--Live"], ["-l"], ["--live=true"], ["live"], ["--check", "--live"]]) {
    const h = harness();
    assert.equal(await run(argv, h.deps), EXIT.config, argv.join(" "));
    assert.equal(h.calls.length, 0, argv.join(" "));
  }
});

test("QA PH-03: offline run with a live-reporting API refuses before the bridge starts", async () => {
  const h = harness({ healthMode: "live" });
  assert.equal(await run([], h.deps), EXIT.failed);
  assert.equal(h.calls.length, 1);
  assert.ok(h.api.kills.length >= 1, "API stopped");
  assert.ok(!fs.existsSync(h.deps.lockPath), "lock released");
});

test("QA PH-03/SEC-01: Spectrum secrets never reach the Python API; provider keys and phone never printed", async () => {
  const h = harness({ env: { ...SECRETS, ...PROVIDER }, onBridge: (b) => {
    b.stdout.write(`EVALUATION_STATUS:{"decision":"VERIFY_FIRST"}\nREPLY_REQUEST_COMPLETED to ${SECRETS.VIZS_REGISTERED_RECIPIENT}\nDELIVERY_STATUS ${SECRETS.PROJECT_SECRET}\n`);
    setImmediate(() => b.exit(0));
  } });
  assert.equal(await run([], h.deps), EXIT.ok);
  const apiEnv = apiCalls(h)[0].options.env;
  for (const key of Object.keys(SECRETS)) assert.equal(apiEnv[key], undefined, key);
  assert.equal(apiCalls(h)[0].options.stdio, "ignore", "API output suppressed");
  const bridgeCall = h.calls.find((c) => !c.args.includes("app.workflow.dev_server"));
  assert.match(bridgeCall.options.env.VIZS_LOCAL_API, /^http:\/\/127\.0\.0\.1:\d+\/api\/v1\/evaluate-message$/);
  const text = h.text();
  for (const [name, value] of Object.entries({ ...SECRETS, ...PROVIDER })) assert.ok(!text.includes(value), `${name} leaked to output`);
  assert.ok(!text.includes("5550009999"));
  assert.match(text, /BRIDGE: EVALUATION_STATUS/);
});

test("QA SEC-01: provider keys are not handed to the bridge and never forwarded from bridge status lines",
  { todo: "QA-04: launch.mjs passes the full env (XAI/TAVILY keys) to the bridge and redacts only Spectrum values" }, async () => {
    const h = harness({ env: { ...SECRETS, ...PROVIDER }, onBridge: (b) => {
      b.stdout.write(`DELIVERY_STATUS ${PROVIDER.XAI_API_KEY}\n`);
      setImmediate(() => b.exit(0));
    } });
    assert.equal(await run([], h.deps), EXIT.ok);
    const bridgeCall = h.calls.find((c) => !c.args.includes("app.workflow.dev_server"));
    for (const key of Object.keys(PROVIDER)) assert.equal(bridgeCall.options.env[key], undefined, `${key} given to bridge`);
    for (const value of Object.values(PROVIDER)) assert.ok(!h.text().includes(value), "provider key printed");
  });

test("QA SEC-01: secrets passed as arguments or a malformed port are never echoed", async () => {
  for (const argv of [[SECRETS.PROJECT_SECRET], ["--port", SECRETS.PROJECT_SECRET], [`--port=${SECRETS.VIZS_REGISTERED_RECIPIENT}`]]) {
    const h = harness();
    assert.equal(await run(argv, h.deps), EXIT.config);
    for (const value of Object.values(SECRETS)) assert.ok(!h.text().includes(value), argv.join(" "));
    assert.equal(h.calls.length, 0);
  }
});

test("QA PH-03: a second launcher refuses while the first holds the lock, then can start after release", async () => {
  const lockPath = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "vizs-qa-lock-")), "l.lock");
  let releaseFirst;
  const gate = new Promise((r) => { releaseFirst = r; });
  const first = harness({ lockPath, onBridge: (b) => gate.then(() => b.exit(0)) });
  const firstRun = run([], first.deps);
  while (!first.bridge) await new Promise((r) => setImmediate(r));
  const second = harness({ lockPath });
  second.deps.pid = 777_002;
  second.deps.alive = (pid) => pid === first.deps.pid;
  assert.equal(await run([], second.deps), EXIT.busy);
  assert.equal(second.calls.length, 0, "no duplicate listener");
  assert.ok(fs.existsSync(lockPath), "refusing launcher must not delete the owner's lock");
  releaseFirst();
  assert.equal(await firstRun, EXIT.ok);
  assert.ok(!fs.existsSync(lockPath));
  const third = harness({ lockPath, onBridge: (b) => b.exit(0) });
  assert.equal(await run([], third.deps), EXIT.ok);
});

test("QA PH-03: lock release only deletes a lock owned by this pid; corrupt lock is reclaimed", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vizs-qa-lock-"));
  const lockPath = path.join(dir, "l.lock");
  const mine = acquireLock(lockPath, { pid: 11, alive: () => true });
  assert.equal(mine.acquired, true);
  fs.writeFileSync(lockPath, JSON.stringify({ pid: 22 }));
  mine.release();
  assert.ok(fs.existsSync(lockPath), "foreign lock survives release");
  fs.writeFileSync(lockPath, "not json");
  const reclaimed = acquireLock(lockPath, { pid: 33, alive: () => true });
  assert.equal(reclaimed.acquired, true);
  assert.equal(reclaimed.reclaimed, true);
  reclaimed.release();
  assert.ok(!fs.existsSync(lockPath));
});

test("QA PH-03: signal while waiting for /healthz stops the API, releases the lock, starts no bridge", async () => {
  const h = harness();
  h.deps.fetch = async () => { throw new Error("ECONNREFUSED"); };
  h.deps.sleep = () => new Promise((resolve) => setTimeout(resolve, 5));
  const running = run([], h.deps);
  while (!h.api) await new Promise((r) => setImmediate(r));
  h.signal("SIGINT");
  assert.equal(await running, 130);
  assert.equal(h.calls.length, 1);
  assert.ok(h.api.kills.includes("SIGTERM"));
  assert.ok(!fs.existsSync(h.deps.lockPath));
});

test("QA PH-03: hard run cap stops bridge then API and releases the lock", async () => {
  const timers = (fn, ms) => { if (ms >= 60_000) setImmediate(fn); return () => {}; };
  const h = harness({ timers, onBridge: () => {} });
  h.deps.maxRunMs = 12 * 60_000;
  assert.equal(await run([], h.deps), EXIT.failed);
  assert.match(h.text(), /LAUNCHER_TIMEOUT/);
  assert.ok(h.bridge.kills.includes("SIGTERM"));
  assert.ok(h.api.kills.includes("SIGTERM"));
  assert.ok(!fs.existsSync(h.deps.lockPath));
  assert.match(h.text(), /LAUNCHER_LOCK: released/);
});

test("QA PH-03: forwarded bridge lines are limited to status prefixes", () => {
  for (const line of ["READY: x", "EVALUATION_STATUS:{}", "DELIVERY_STATUS:{}", "REPLY_FAILED: no automatic retry.", "BRIDGE_STOPPED"]) assert.match(line, FORWARD);
  for (const line of ["incoming: buy", "Error: secret", " READY", "message from +15550009999", "{\"text\":\"hi\"}"]) assert.doesNotMatch(line, FORWARD);
});

// ---------------------------------------------------------------- PH-01 / PH-02 bridge handler

function space(type = "dm") {
  const sent = [];
  return { type, sent, send: async (body) => { sent.push(body); return { id: "m" }; } };
}
const inbound = (overrides = {}) => ({ id: `id-${Math.random()}`, direction: "inbound", sender: { id: SECRETS.VIZS_REGISTERED_RECIPIENT }, content: { type: "text", text: "Check https://synthetic-shop.com/p" }, ...overrides });

test("QA PH-01: only registered direct inbound text is admitted", async () => {
  const calls = [];
  const handler = createBridgeHandler({ recipient: SECRETS.VIZS_REGISTERED_RECIPIENT, evaluate: async (p) => { calls.push(p); return { message_text: "ok" }; } });
  const rejected = [
    [space("group"), inbound()], [space(), inbound({ direction: "outbound" })], [space(), inbound({ sender: { id: "+15550000000" } })],
    [space(), inbound({ content: { type: "image" } })], [space(), inbound({ content: { type: "text", text: "   " } })],
    [space(), inbound({ content: { type: "text", text: "x".repeat(4001) } })], [space(), inbound({ id: "" })], [null, inbound()],
  ];
  for (const [s, m] of rejected) assert.equal(await handler.handle(s, m), "ignored");
  assert.equal(calls.length, 0);
  const s = space();
  assert.equal(await handler.handle(s, inbound()), "send_request_completed");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].channel, "debug");
  assert.match(calls[0].request_id, /^[0-9a-f-]{36}$/);
  assert.equal(s.sent.length, 1);
});

test("QA PH-02: a thrown send is not retried and no second reply is issued", async () => {
  let sends = 0;
  const handler = createBridgeHandler({ recipient: SECRETS.VIZS_REGISTERED_RECIPIENT, evaluate: async () => ({ message_text: "ok" }) });
  const s = { type: "dm", send: async () => { sends++; throw new Error("ambiguous"); } };
  const message = inbound();
  await assert.rejects(handler.handle(s, message));
  assert.equal(await handler.handle(s, message), "ignored");
  assert.equal(sends, 1);
});

test("QA PH-02: oversized or malformed evaluation output is replaced by a neutral unavailable reply", async () => {
  for (const result of [{ message_text: "x".repeat(2001) }, { message_text: 5 }, null]) {
    const s = space();
    const handler = createBridgeHandler({ recipient: SECRETS.VIZS_REGISTERED_RECIPIENT, evaluate: async () => result });
    await handler.handle(s, inbound());
    assert.equal(s.sent.length, 1);
    assert.match(s.sent[0], /unavailable or timed out\. No seller conclusion/);
    assert.doesNotMatch(s.sent[0], /scam|fraud|counterfeit/i);
  }
});
