import test from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { PassThrough } from "node:stream";
import { run, acquireLock, resolvePython, parseArgs, EXIT } from "./launch.mjs";

// Synthetic values only; asserted never to appear in output.
const SECRETS = { PROJECT_ID: "synthetic-project-id-123", PROJECT_SECRET: "synthetic-secret-xyz-789", VIZS_REGISTERED_RECIPIENT: "+15550001111" };

class FakeChild extends EventEmitter {
  static nextPid = 5000;
  constructor() { super(); this.pid = FakeChild.nextPid++; this.stdout = new PassThrough(); this.stderr = new PassThrough(); this.kills = []; this.done = false; }
  kill(signal) { this.kills.push(signal); this.exit(null, signal); return true; }
  exit(code, signal = null) {
    if (this.done) return; this.done = true;
    this.stdout.end(); this.stderr.end(); this.emit("exit", code, signal);
  }
}

function harness({ env = SECRETS, healthy = true, mode, onBridge, onApi, lockPath } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vizs-launch-test-"));
  const out = [];
  const calls = [];
  let api = null, bridge = null, signalHandler = null;
  const deps = {
    env: { ...env }, platform: "darwin", pid: 4242_0, nodePath: "/fake/node",
    root: "/fake/repo", spectrumDir: "/fake/spectrum", lockPath: lockPath ?? path.join(dir, "launch.lock"),
    exists: (p) => p.endsWith("test-bridge.mjs") || p.endsWith(path.join("node_modules", "spectrum-ts")),
    readFile: () => "", out: (line) => out.push(line), alive: () => false,
    now: (() => { let t = 0; return () => (t += 100); })(),
    sleep: () => new Promise((resolve) => setImmediate(resolve)), setTimer: () => () => {}, onSignal: (h) => { signalHandler = h; return () => { signalHandler = null; }; },
    healthTimeoutMs: 2_000, pollMs: 1, graceMs: 1,
    spawn: (command, args, options) => {
      const child = new FakeChild();
      calls.push({ command, args, options });
      if (args.includes("app.workflow.dev_server")) { api = child; setImmediate(() => onApi?.(child, h)); }
      else { bridge = child; setImmediate(() => onBridge?.(child, h)); }
      return child;
    },
    fetch: async () => {
      if (!api || api.done || !healthy) throw new Error("ECONNREFUSED");
      const live = calls.find((c) => c.args.includes("app.workflow.dev_server")).args.includes("--live");
      return { ok: true, json: async () => ({ status: "ok", evaluation_ready: true, provider_mode: mode ?? (live ? "live" : "offline") }) };
    },
  };
  const h = { deps, out, calls, dir, get api() { return api; }, get bridge() { return bridge; }, signal: (n) => signalHandler?.(n),
    text: () => out.join("\n") };
  return h;
}

test("missing config refuses before spawning anything", async () => {
  const h = harness({ env: {} });
  assert.equal(await run([], h.deps), EXIT.config);
  assert.equal(h.calls.length, 0);
  assert.match(h.text(), /LAUNCHER_REFUSED.*PROJECT_ID, PROJECT_SECRET, VIZS_REGISTERED_RECIPIENT/);
  assert.ok(!fs.existsSync(h.deps.lockPath));
});

test("lock held by a live process prevents a second instance", async () => {
  const h = harness();
  fs.writeFileSync(h.deps.lockPath, JSON.stringify({ pid: 777 }));
  h.deps.alive = (pid) => pid === 777;
  assert.equal(await run([], h.deps), EXIT.busy);
  assert.equal(h.calls.length, 0);
  assert.match(h.text(), /another launcher holds the lock \(pid 777\)/);
  assert.ok(fs.existsSync(h.deps.lockPath), "foreign lock must be preserved");
});

test("stale lock is reclaimed and released after check", async () => {
  const h = harness();
  fs.writeFileSync(h.deps.lockPath, JSON.stringify({ pid: 778 }));
  assert.equal(await run(["--check"], h.deps), EXIT.ok);
  assert.match(h.text(), /stale lock reclaimed/);
  assert.match(h.text(), /LAUNCHER_CHECK_OK/);
  assert.equal(h.calls.length, 1, "check never starts the bridge");
  assert.deepEqual(h.api.kills, ["SIGTERM"]);
  assert.ok(!fs.existsSync(h.deps.lockPath));
});

test("acquireLock unit: second acquisition refused while owner alive", () => {
  const lockPath = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "vizs-lock-")), "l");
  const first = acquireLock(lockPath, { pid: 1, alive: () => true });
  assert.equal(first.acquired, true);
  assert.equal(acquireLock(lockPath, { pid: 2, alive: () => true }).acquired, false);
  first.release();
  assert.equal(acquireLock(lockPath, { pid: 2, alive: () => true }).acquired, true);
});

test("check mode works without credentials", async () => {
  const h = harness({ env: {} });
  assert.equal(await run(["--check"], h.deps), EXIT.ok);
  assert.match(h.text(), /a real run would refuse/);
  assert.ok(!h.calls[0].args.includes("--live"));
});

test("healthz timeout stops the API and releases the lock", async () => {
  const h = harness({ healthy: false });
  assert.equal(await run(["--check"], h.deps), EXIT.failed);
  assert.match(h.text(), /not ready within/);
  assert.deepEqual(h.api.kills, ["SIGTERM"]);
  assert.ok(!fs.existsSync(h.deps.lockPath));
});

test("API exiting before ready is reported and nothing else starts", async () => {
  const h = harness({ healthy: false, onApi: (api) => api.exit(1) });
  assert.equal(await run([], h.deps), EXIT.failed);
  assert.match(h.text(), /exited before ready \(code=1/);
  assert.equal(h.calls.length, 1);
});

test("bridge exit stops the API; status lines forwarded", async () => {
  const h = harness({ onBridge: (b) => { b.stdout.write("READY: test\nBOUNDED_TEST_FINISHED\nBRIDGE_STOPPED\n"); setImmediate(() => b.exit(0)); } });
  assert.equal(await run([], h.deps), EXIT.ok);
  assert.deepEqual(h.api.kills, ["SIGTERM"]);
  assert.match(h.text(), /BRIDGE: READY: test/);
  assert.match(h.text(), /BRIDGE: BOUNDED_TEST_FINISHED/);
  const bridgeCall = h.calls[1];
  assert.equal(bridgeCall.options.env.VIZS_LOCAL_API, "http://127.0.0.1:8787/api/v1/evaluate-message");
  assert.equal(bridgeCall.options.env.PROJECT_SECRET, SECRETS.PROJECT_SECRET);
  assert.equal(h.calls[0].options.env.PROJECT_SECRET, undefined, "API process does not receive Photon secrets");
  assert.ok(!fs.existsSync(h.deps.lockPath));
});

test("bridge failure exit code propagates", async () => {
  const h = harness({ onBridge: (b) => b.exit(1) });
  assert.equal(await run([], h.deps), EXIT.failed);
  assert.deepEqual(h.api.kills, ["SIGTERM"]);
});

test("API crash stops the bridge", async () => {
  const h = harness({ onBridge: (_b, hh) => hh.api.exit(1) });
  assert.equal(await run([], h.deps), EXIT.failed);
  assert.match(h.text(), /API exited while bridge running/);
  assert.deepEqual(h.bridge.kills, ["SIGTERM"]);
});

test("signal stops both processes", async () => {
  const h = harness({ onBridge: (_b, hh) => hh.signal("SIGINT") });
  assert.equal(await run([], h.deps), 130);
  assert.deepEqual(h.bridge.kills, ["SIGTERM"]);
  assert.deepEqual(h.api.kills, ["SIGTERM"]);
  assert.ok(!fs.existsSync(h.deps.lockPath));
});

test("unresponsive child is force-killed after the grace period", async () => {
  const h = harness({ onBridge: (b, hh) => { b.kill = (s) => { b.kills.push(s); if (s === "SIGKILL") b.exit(null, s); }; hh.signal("SIGTERM"); } });
  h.deps.setTimer = (fn) => { setImmediate(fn); return () => {}; };
  assert.equal(await run([], h.deps), 143);
  assert.deepEqual(h.bridge.kills, ["SIGTERM", "SIGKILL"]);
});

test("--live is passed only when requested and verified via healthz", async () => {
  const offline = harness({ onBridge: (b) => b.exit(0) });
  await run([], offline.deps);
  assert.ok(!offline.calls[0].args.includes("--live"));
  const live = harness({ onBridge: (b) => b.exit(0) });
  await run(["--live", "--port", "9123"], live.deps);
  assert.deepEqual(live.calls[0].args.slice(-3), ["--port", "9123", "--live"]);
  const mismatch = harness({ mode: "live" });
  assert.equal(await run([], mismatch.deps), EXIT.failed);
  assert.match(mismatch.text(), /unexpected health/);
  assert.equal(mismatch.calls.length, 1, "bridge not started on mode mismatch");
  assert.throws(() => parseArgs(["--check", "--live"]));
});

test("secrets, phone numbers and message text never appear in output", async () => {
  const h = harness({ onBridge: (b) => {
    b.stdout.write(`READY: ok\nincoming text from ${SECRETS.VIZS_REGISTERED_RECIPIENT}: buy this product\nREPLY_FAILED ${SECRETS.PROJECT_SECRET}\n`);
    b.stderr.write(`Error: auth failed for ${SECRETS.PROJECT_ID}\n`);
    setImmediate(() => b.exit(0));
  } });
  assert.equal(await run([], h.deps), EXIT.ok);
  const text = h.text();
  for (const value of Object.values(SECRETS)) assert.ok(!text.includes(value));
  assert.ok(!text.includes("buy this product"));
  assert.match(text, /PROJECT_SECRET=present/);
  assert.match(text, /3 non-status bridge line\(s\) suppressed/);
  for (const call of h.calls) for (const value of Object.values(SECRETS)) assert.ok(!call.args.join(" ").includes(value));
});

test("spectrum .env values are used when env vars are absent; env wins", async () => {
  const h = harness({ env: { PROJECT_ID: "from-env-project", VIZS_PYTHON: "/fake/python" }, onBridge: (b) => b.exit(0) });
  h.deps.exists = () => true;
  h.deps.readFile = () => "PROJECT_ID=from-file-project\nPROJECT_SECRET=file-secret-value\nVIZS_REGISTERED_RECIPIENT=+15550002222\n";
  assert.equal(await run([], h.deps), EXIT.ok);
  assert.equal(h.calls[0].command, "/fake/python");
  assert.equal(h.calls[1].options.env.PROJECT_ID, "from-env-project");
  assert.equal(h.calls[1].options.env.PROJECT_SECRET, "file-secret-value");
  assert.ok(!h.text().includes("+15550002222"));
});

test("python resolution: VIZS_PYTHON, then repo .venv, then platform default", () => {
  const root = "/r";
  assert.equal(resolvePython({ env: { VIZS_PYTHON: "/x/py" }, platform: "darwin", exists: () => true, root }).command, "/x/py");
  assert.equal(resolvePython({ env: {}, platform: "darwin", exists: () => true, root }).command, path.join(root, ".venv", "bin", "python"));
  assert.equal(resolvePython({ env: {}, platform: "win32", exists: () => true, root }).command, path.join(root, ".venv", "Scripts", "python.exe"));
  assert.deepEqual(resolvePython({ env: {}, platform: "win32", exists: () => false, root }), { command: "py", args: ["-3"], source: "PATH" });
  assert.equal(resolvePython({ env: {}, platform: "linux", exists: () => false, root }).command, "python3");
});

test("port already serving refuses before spawning", async () => {
  const h = harness();
  h.deps.fetch = async () => ({ ok: true, json: async () => ({ status: "ok" }) });
  assert.equal(await run([], h.deps), EXIT.busy);
  assert.equal(h.calls.length, 0);
});

test("bridge gets a least-privilege env and every credential is redacted (QA-04)", async () => {
  const token = "synthetic-extension-token-456";
  const rootKey = "synthetic-root-env-xai-321";
  const h = harness({
    env: { ...SECRETS, PATH: "/usr/bin", HOME: "/fake/home", XAI_API_KEY: "synthetic-xai-key-111",
      TAVILY_API_KEY: "synthetic-tavily-key-222", VIZS_EXTENSION_TOKEN: token, OTHER_SECRET: "synthetic-other-999",
      GRPC_VERBOSITY: "ERROR" },
    onBridge: (b) => {
      b.stdout.write(`DELIVERY_STATUS ok\nDELIVERY_STATUS ${token}\nREPLY_SENT ${rootKey}\n`);
      setImmediate(() => b.exit(0));
    },
  });
  const rootEnv = path.join("/fake/repo", ".env");
  const exists = h.deps.exists;
  h.deps.exists = (p) => p === rootEnv || exists(p);
  h.deps.readFile = (p) => (p === rootEnv ? `XAI_API_KEY=${rootKey}\n` : "");
  assert.equal(await run([], h.deps), EXIT.ok);
  const env = h.calls.find((c) => !c.args.includes("app.workflow.dev_server")).options.env;
  assert.deepEqual(Object.keys(env).sort(), ["GRPC_VERBOSITY", "HOME", "PATH", "PROJECT_ID", "PROJECT_SECRET",
    "VIZS_LOCAL_API", "VIZS_REGISTERED_RECIPIENT"]);
  const text = h.text();
  for (const value of [token, rootKey, "synthetic-xai-key-111", "synthetic-tavily-key-222"]) assert.ok(!text.includes(value));
  assert.match(text, /BRIDGE: DELIVERY_STATUS ok/);
  assert.match(text, /2 non-status bridge line\(s\) suppressed/);
});
