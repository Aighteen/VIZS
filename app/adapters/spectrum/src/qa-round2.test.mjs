// QA round 2: adversarial checks of the QA-04 fix (bridge env allowlist and redaction).
// SYNTHETIC values only; fake children, fetch and timers. No network, no messages.
import test from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { PassThrough } from "node:stream";
import { run, EXIT, bridgeEnvironment } from "./launch.mjs";

const SPECTRUM = { PROJECT_ID: "qa-r2-project-0001", PROJECT_SECRET: "qa-r2-secret-0002", VIZS_REGISTERED_RECIPIENT: "+15550004444" };
const EXTRA = {
  XAI_API_KEY: "qa-r2-xai-0003", TAVILY_API_KEY: "qa-r2-tavily-0004", VIZS_EXTENSION_TOKEN: "qa-r2-token-0005",
  NODE_OPTIONS: "--require /tmp/evil.js", AWS_SECRET_ACCESS_KEY: "qa-r2-aws-0006", GITHUB_TOKEN: "qa-r2-gh-0007",
  npm_config_registry: "https://registry.example", VIZS_PROVIDER_MODE: "live", XAI_MODEL: "qa-model", OPENAI_API_KEY: "qa-r2-oa-0008",
};

class FakeChild extends EventEmitter {
  static nextPid = 12000;
  constructor() { super(); this.pid = FakeChild.nextPid++; this.stdout = new PassThrough(); this.stderr = new PassThrough(); this.kills = []; this.done = false; }
  kill(signal) { this.kills.push(signal); this.exit(null, signal); return true; }
  exit(code, signal = null) { if (this.done) return; this.done = true; this.stdout.end(); this.stderr.end(); this.emit("exit", code, signal); }
}

function harness({ env, files = {}, onBridge }) {
  const out = [];
  const calls = [];
  let api = null;
  const deps = {
    env, platform: "darwin", pid: 888_001, nodePath: "/fake/node", root: "/fake/repo", spectrumDir: "/fake/spectrum",
    lockPath: path.join(fs.mkdtempSync(path.join(os.tmpdir(), "vizs-qa-r2-")), "l.lock"),
    exists: (p) => p in files || p.endsWith("test-bridge.mjs") || p.endsWith(path.join("node_modules", "spectrum-ts")),
    readFile: (p) => files[p] ?? "", out: (line) => out.push(line), alive: () => false,
    now: (() => { let t = 0; return () => (t += 100); })(), sleep: () => new Promise((r) => setImmediate(r)),
    setTimer: () => () => {}, onSignal: () => () => {}, healthTimeoutMs: 2_000, pollMs: 1, graceMs: 1,
    spawn: (command, args, options) => {
      const child = new FakeChild();
      calls.push({ command, args, options });
      if (args.includes("app.workflow.dev_server")) api = child; else setImmediate(() => onBridge?.(child));
      return child;
    },
    fetch: async () => {
      if (!api || api.done) throw new Error("ECONNREFUSED");
      return { ok: true, json: async () => ({ status: "ok", evaluation_ready: true, provider_mode: "offline" }) };
    },
  };
  return { deps, out, calls, text: () => out.join("\n") };
}

test("QA-04: bridge env withholds provider keys, extension token, NODE_OPTIONS and unrelated secrets", async () => {
  const h = harness({ env: { ...SPECTRUM, ...EXTRA, PATH: "/usr/bin", GRPC_VERBOSITY: "ERROR" }, onBridge: (b) => b.exit(0) });
  assert.equal(await run([], h.deps), EXIT.ok);
  const bridge = h.calls.find((c) => !c.args.includes("app.workflow.dev_server"));
  for (const key of Object.keys(EXTRA)) assert.equal(bridge.options.env[key], undefined, key);
  for (const key of Object.keys(SPECTRUM)) assert.equal(bridge.options.env[key], SPECTRUM[key]);
  assert.match(bridge.options.env.VIZS_LOCAL_API, /^http:\/\/127\.0\.0\.1:\d+\/api\/v1\/evaluate-message$/);
  assert.ok(!h.calls[0].args.includes("--live"), "VIZS_PROVIDER_MODE=live in env never implies --live");
});

test("QA-04: credentials from env, spectrum .env or root .env are never printed, even inside status lines", async () => {
  const files = {
    [path.join("/fake/spectrum", ".env")]: "XAI_API_KEY=qa-r2-spectrum-file-xai-0009\n",
    [path.join("/fake/repo", ".env")]: "VIZS_EXTENSION_TOKEN=qa-r2-root-file-token-0010\nTAVILY_API_KEY=qa-r2-root-tavily-0011\n",
  };
  const values = ["qa-r2-spectrum-file-xai-0009", "qa-r2-root-file-token-0010", "qa-r2-root-tavily-0011", EXTRA.XAI_API_KEY, ...Object.values(SPECTRUM)];
  const h = harness({ env: { ...SPECTRUM, XAI_API_KEY: EXTRA.XAI_API_KEY }, files, onBridge: (b) => {
    b.stdout.write(values.map((v) => `DELIVERY_STATUS:{"x":"${v}"}`).join("\n") + "\nREADY: ok\n");
    setImmediate(() => b.exit(0));
  } });
  assert.equal(await run([], h.deps), EXIT.ok);
  const text = h.text();
  for (const v of values) assert.ok(!text.includes(v), "credential printed");
  assert.match(text, /BRIDGE: READY: ok/);
  assert.match(text, new RegExp(`${values.length} non-status bridge line\\(s\\) suppressed`));
});

test("QA-04: bridgeEnvironment is a pure allowlist (unit)", () => {
  const env = bridgeEnvironment({ PATH: "/bin", HOME: "/h", GRPC_TRACE: "x", grpc_lower: "y", XAI_API_KEY: "k", SECRET: "s", HTTPS_PROXY: "http://proxy" },
    SPECTRUM, "http://127.0.0.1:8787/api/v1/evaluate-message");
  assert.deepEqual(Object.keys(env).sort(), ["GRPC_TRACE", "HOME", "HTTPS_PROXY", "PATH", "PROJECT_ID", "PROJECT_SECRET", "VIZS_LOCAL_API", "VIZS_REGISTERED_RECIPIENT"]);
});
