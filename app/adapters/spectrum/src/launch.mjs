// Bounded VIZS Photon launcher (ACCEPTANCE PH-03). Starts the loopback Python API, waits for
// /healthz, then runs the bounded shopping bridge (test-bridge.mjs). One instance at a time
// (PID lock), and when either process stops, the launcher stops the other. Prints presence
// only, never credential values, phone numbers or message text.
import { spawn as nodeSpawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseEnv } from "node:util";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const SPECTRUM_DIR = path.resolve(HERE, "..");
export const REPO_ROOT = path.resolve(SPECTRUM_DIR, "../../..");
export const DEFAULT_PORT = 8787;
export const REQUIRED_KEYS = ["PROJECT_ID", "PROJECT_SECRET", "VIZS_REGISTERED_RECIPIENT"];
// Credentials the bridge never needs; also redacted from any forwarded output (QA-04).
export const REDACT_KEYS = ["XAI_API_KEY", "TAVILY_API_KEY", "VIZS_EXTENSION_TOKEN"];
// Least-privilege bridge environment (QA-04): basic OS/Node variables, network
// proxy/CA settings, and the variables the Spectrum SDK and its gRPC transport read
// (SPECTRUM_IMESSAGE_ADDRESS, GRPC_*). Everything else, including provider keys and
// the extension token, is withheld. REQUIRED_KEYS and VIZS_LOCAL_API are added after.
export const BRIDGE_ENV_KEYS = [
  "PATH", "Path", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
  "SYSTEMROOT", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
  "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "SYSTEMDRIVE",
  "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy", "grpc_proxy", "no_grpc_proxy",
  "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR", "SPECTRUM_IMESSAGE_ADDRESS",
];

export function bridgeEnvironment(env, cfg, localApi) {
  const picked = {};
  for (const [key, value] of Object.entries(env)) {
    if (value !== undefined && (BRIDGE_ENV_KEYS.includes(key) || /^GRPC_[A-Z_]+$/.test(key))) picked[key] = value;
  }
  return { ...picked, ...cfg, VIZS_LOCAL_API: localApi };
}

export const EXIT = { ok: 0, failed: 1, config: 2, busy: 3 };
const SIGNAL_EXIT = { SIGINT: 130, SIGTERM: 143, SIGHUP: 129, SIGBREAK: 130 };
// Only the bridge's own privacy-safe status lines are forwarded.
export const FORWARD = /^(READY|EVALUATION_STATUS|DELIVERY_STATUS|REPLY_[A-Z_]+|BOUNDED_TEST_FINISHED|TEST_WINDOW_EXPIRED|BRIDGE_(STOPPED|FAILED|SIGNALLED))\b/;

export const USAGE = `Usage: node src/launch.mjs [--check] [--live] [--port N]
  (no flags)  offline API + bounded iMessage bridge (sends real iMessage replies; no provider credits)
  --live      allow paid Grok/Tavily calls in the API (only when authorized)
  --check     offline dry run: config presence + API start + /healthz, no Spectrum connection
  --port N    loopback API port 1024-65535 (default ${DEFAULT_PORT}, or VIZS_LAUNCH_PORT)
Env: VIZS_PYTHON (python executable), VIZS_REGISTERED_RECIPIENT, PROJECT_ID, PROJECT_SECRET
     (env wins over app/adapters/spectrum/.env), VIZS_LAUNCH_HEALTH_TIMEOUT_MS, VIZS_LAUNCH_LOCK.`;

class UsageError extends Error {}

export function parseArgs(argv) {
  const opts = { check: false, live: false, port: undefined, help: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--check" || arg === "--dry-run") opts.check = true;
    else if (arg === "--live") opts.live = true;
    else if (arg === "--help" || arg === "-h") opts.help = true;
    else if (arg === "--port") opts.port = argv[++i];
    else if (arg.startsWith("--port=")) opts.port = arg.slice(7);
    else throw new UsageError(/^--[a-z-]{1,30}$/.test(arg) ? `unknown option ${arg}` : "unknown argument");
  }
  if (opts.check && opts.live) throw new UsageError("--check always runs offline; do not combine with --live");
  return opts;
}

export function parsePort(value) {
  const port = Number(value);
  return Number.isInteger(port) && port >= 1024 && port <= 65535 ? port : null;
}

export function resolvePython({ env, platform, exists, root }) {
  if (env.VIZS_PYTHON?.trim()) return { command: env.VIZS_PYTHON.trim(), args: [], source: "VIZS_PYTHON" };
  const venv = platform === "win32" ? path.join(root, ".venv", "Scripts", "python.exe") : path.join(root, ".venv", "bin", "python");
  if (exists(venv)) return { command: venv, args: [], source: ".venv" };
  return platform === "win32" ? { command: "py", args: ["-3"], source: "PATH" } : { command: "python3", args: [], source: "PATH" };
}

export function isAlive(pid) {
  try { process.kill(pid, 0); return true; } catch (error) { return error?.code === "EPERM"; }
}

// Exclusive lock file holding the owner's PID; a lock whose PID is not running is reclaimed.
export function acquireLock(lockPath, { pid, alive = isAlive, fsApi = fs }) {
  let reclaimed = false;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const fd = fsApi.openSync(lockPath, "wx");
      try { fsApi.writeSync(fd, JSON.stringify({ pid, startedAt: new Date().toISOString() })); } finally { fsApi.closeSync(fd); }
      return { acquired: true, reclaimed, release() {
        try { if (JSON.parse(fsApi.readFileSync(lockPath, "utf8")).pid === pid) fsApi.unlinkSync(lockPath); } catch { /* already gone */ }
      } };
    } catch (error) {
      if (error?.code !== "EEXIST") throw error;
      let owner = null;
      try { owner = JSON.parse(fsApi.readFileSync(lockPath, "utf8")).pid; } catch { /* corrupt lock: treat as stale */ }
      if (Number.isInteger(owner) && owner > 0 && owner !== pid && alive(owner)) return { acquired: false, owner };
      try { fsApi.unlinkSync(lockPath); } catch (err) { if (err?.code !== "ENOENT") throw err; }
      reclaimed = true;
    }
  }
  return { acquired: false, owner: null };
}

function defaultKillTree(d) {
  return (child, signal) => {
    if (d.platform === "win32") {
      // Kill the whole tree: py.exe / venv python.exe launchers spawn the real interpreter.
      const killer = d.spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
      killer.on?.("error", () => { try { child.kill(); } catch { /* ignore */ } });
    } else {
      try { child.kill(signal); } catch { /* already exited */ }
    }
  };
}

function defaultOnSignal(platform) {
  return (handler) => {
    const names = ["SIGINT", "SIGTERM", "SIGHUP", ...(platform === "win32" ? ["SIGBREAK"] : [])];
    const pairs = names.map((name) => { const fn = () => handler(name); process.on(name, fn); return [name, fn]; });
    return () => { for (const [name, fn] of pairs) process.off(name, fn); };
  };
}

function defaults(env) {
  return {
    env, platform: process.platform, pid: process.pid, nodePath: process.execPath,
    spawn: nodeSpawn, fetch: globalThis.fetch, now: Date.now,
    sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    setTimer: (fn, ms) => { const t = setTimeout(fn, ms); return () => clearTimeout(t); },
    out: (line) => process.stdout.write(line + "\n"),
    exists: (p) => fs.existsSync(p), readFile: (p) => fs.readFileSync(p, "utf8"),
    alive: isAlive, root: REPO_ROOT, spectrumDir: SPECTRUM_DIR,
    lockPath: env.VIZS_LAUNCH_LOCK || path.join(os.tmpdir(), "vizs-photon-launcher.lock"),
    healthTimeoutMs: Number(env.VIZS_LAUNCH_HEALTH_TIMEOUT_MS) > 0 ? Number(env.VIZS_LAUNCH_HEALTH_TIMEOUT_MS) : 30_000,
    pollMs: 250, graceMs: 5_000, maxRunMs: 12 * 60_000,
  };
}

function track(child) {
  const t = { child, exited: false, code: null, signal: null, error: false };
  t.done = new Promise((resolve) => {
    const finish = (code, signal, error = false) => {
      if (t.exited) return;
      Object.assign(t, { exited: true, code, signal, error });
      resolve(t);
    };
    child.once("exit", (code, signal) => finish(code, signal));
    child.once("error", () => finish(null, null, true));
  });
  return t;
}

export async function run(argv, overrides = {}) {
  const d = { ...defaults(overrides.env ?? process.env), ...overrides };
  d.killTree ??= defaultKillTree(d);
  d.onSignal ??= defaultOnSignal(d.platform);
  const secrets = [];
  const redact = (text) => secrets.reduce((s, v) => s.split(v).join("[REDACTED]"), String(text));
  const say = (text) => d.out(redact(text));

  let opts;
  try { opts = parseArgs(argv); } catch (error) {
    if (!(error instanceof UsageError)) throw error;
    say("LAUNCHER_USAGE_ERROR: " + error.message); say(USAGE); return EXIT.config;
  }
  if (opts.help) { say(USAGE); return EXIT.ok; }
  const port = parsePort(opts.port ?? d.env.VIZS_LAUNCH_PORT ?? DEFAULT_PORT);
  if (port === null) { say("LAUNCHER_USAGE_ERROR: port must be an integer in 1024..65535"); return EXIT.config; }

  const envFile = path.join(d.spectrumDir, ".env");
  const envFileFound = d.exists(envFile);
  let fileValues = {};
  if (envFileFound) { try { fileValues = parseEnv(d.readFile(envFile)); } catch { say("LAUNCHER_WARNING: spectrum .env unreadable"); } }
  const cfg = Object.fromEntries(REQUIRED_KEYS.map((k) => [k, String(d.env[k] || fileValues[k] || "").trim()]));
  for (const value of Object.values(cfg)) if (value.length >= 4) secrets.push(value);
  // Provider keys and the extension token are redacted too, from the process env,
  // the spectrum .env, or the repo-root .env the Python API reads (values never printed).
  let rootValues = {};
  const rootEnv = path.join(d.root, ".env");
  try { if (d.exists(rootEnv)) rootValues = parseEnv(d.readFile(rootEnv)); } catch { /* redaction is best effort */ }
  for (const key of REDACT_KEYS) {
    for (const source of [d.env, fileValues, rootValues]) {
      const value = String(source[key] ?? "").trim();
      if (value.length >= 4 && !secrets.includes(value)) secrets.push(value);
    }
  }
  const bridgeScript = path.join(d.spectrumDir, "src", "test-bridge.mjs");
  const bridgePresent = d.exists(bridgeScript);
  const sdkPresent = d.exists(path.join(d.spectrumDir, "node_modules", "spectrum-ts"));
  say(`LAUNCHER_CONFIG: mode=${opts.check ? "check" : "run"} provider=${opts.live ? "live" : "offline"} port=${port} ` +
      `spectrum_env_file=${envFileFound ? "found" : "absent"} ` + REQUIRED_KEYS.map((k) => `${k}=${cfg[k] ? "present" : "missing"}`).join(" "));
  say(`LAUNCHER_CONFIG: bridge_script=${bridgePresent ? "present" : "missing"} spectrum_sdk=${sdkPresent ? "installed" : "missing (run npm ci)"}`);
  const missing = REQUIRED_KEYS.filter((k) => !cfg[k]);
  if (!opts.check && (missing.length || !bridgePresent || !sdkPresent)) {
    say("LAUNCHER_REFUSED: live bridge configuration incomplete" + (missing.length ? `; missing ${missing.join(", ")}` : "") + ". Nothing started.");
    return EXIT.config;
  }
  if (opts.check && missing.length) say(`LAUNCHER_CHECK_NOTE: a real run would refuse until ${missing.join(", ")} are set.`);

  const python = resolvePython({ env: d.env, platform: d.platform, exists: d.exists, root: d.root });
  if (python.source !== "PATH" && /[\\/]/.test(python.command) && !d.exists(python.command)) {
    say(`LAUNCHER_REFUSED: python from ${python.source} not found. Nothing started.`); return EXIT.config;
  }
  say(`LAUNCHER_PYTHON: source=${python.source} command=${python.command}`);

  const lock = acquireLock(d.lockPath, { pid: d.pid, alive: d.alive });
  if (!lock.acquired) { say(`LAUNCHER_REFUSED: another launcher holds the lock${lock.owner ? ` (pid ${lock.owner})` : ""}. Nothing started.`); return EXIT.busy; }
  if (lock.reclaimed) say("LAUNCHER_LOCK: stale lock reclaimed");
  let signalName = null;
  let onStopRequested;
  const stopRequested = new Promise((resolve) => { onStopRequested = resolve; });
  const unsubscribe = d.onSignal((name) => {
    if (signalName) return;
    signalName = name; say(`LAUNCHER_SIGNAL: ${name}; stopping`); onStopRequested();
  });
  try {
    return await supervise({ d, opts, port, cfg, python, bridgeScript, say, secrets, stopRequested, signal: () => signalName });
  } finally {
    unsubscribe();
    lock.release();
    say("LAUNCHER_LOCK: released");
  }
}

async function supervise({ d, opts, port, cfg, python, bridgeScript, say, secrets, stopRequested, signal }) {
  const healthUrl = `http://127.0.0.1:${port}/healthz`;
  const expectedMode = opts.live ? "live" : "offline";
  const within = (promise, ms) => new Promise((resolve) => {
    const cancel = d.setTimer(() => resolve(false), ms);
    promise.then(() => { cancel(); resolve(true); });
  });
  const getHealth = async () => {
    try {
      const response = await d.fetch(healthUrl, { redirect: "error", signal: AbortSignal.timeout(2_000) });
      return response.ok ? await response.json() : null;
    } catch { return null; }
  };
  const stop = async (t, name) => {
    if (!t || t.exited) return;
    d.killTree(t.child, "SIGTERM");
    if (await within(t.done, d.graceMs)) return say(`LAUNCHER_${name}: stopped`);
    d.killTree(t.child, "SIGKILL");
    if (await within(t.done, d.graceMs)) return say(`LAUNCHER_${name}: killed after grace period`);
    say(`LAUNCHER_WARNING: ${name} pid ${t.child.pid} did not confirm exit`);
  };
  const signalCode = () => SIGNAL_EXIT[signal()] ?? EXIT.failed;

  if (await getHealth()) { say(`LAUNCHER_REFUSED: something already answers on port ${port}. Nothing started.`); return EXIT.busy; }

  const apiEnv = { ...d.env };
  for (const key of REQUIRED_KEYS) delete apiEnv[key];
  const apiArgs = [...python.args, "-m", "app.workflow.dev_server", "--port", String(port), ...(opts.live ? ["--live"] : [])];
  say(`LAUNCHER_API: starting provider=${expectedMode} on 127.0.0.1:${port}; API output suppressed`);
  const api = track(d.spawn(python.command, apiArgs, { cwd: d.root, env: apiEnv, stdio: "ignore", windowsHide: true }));
  let bridge = null;
  try {
    const started = d.now();
    let health = null;
    while (!api.exited && !signal() && d.now() - started < d.healthTimeoutMs) {
      health = await getHealth();
      if (health) break;
      await Promise.race([d.sleep(d.pollMs), api.done, stopRequested]);
    }
    if (signal()) return signalCode();
    if (api.exited) {
      say(`LAUNCHER_API_FAILED: exited before ready (${api.error ? "spawn error" : `code=${api.code} signal=${api.signal}`}). ` +
          "Run python -m app.workflow.dev_server directly from the repo root to diagnose.");
      return EXIT.failed;
    }
    if (!health) { say(`LAUNCHER_API_FAILED: /healthz not ready within ${d.healthTimeoutMs} ms`); return EXIT.failed; }
    if (health.status !== "ok" || health.evaluation_ready !== true || health.provider_mode !== expectedMode) {
      say(`LAUNCHER_API_FAILED: unexpected health status=${health.status} evaluation_ready=${health.evaluation_ready} provider_mode=${health.provider_mode}`);
      return EXIT.failed;
    }
    say(`LAUNCHER_API_READY: status=ok evaluation_ready=true provider_mode=${health.provider_mode}`);
    if (opts.check) { say("LAUNCHER_CHECK_OK: offline API started and answered /healthz; Spectrum not started"); return EXIT.ok; }

    const bridgeEnv = bridgeEnvironment(d.env, cfg, `http://127.0.0.1:${port}/api/v1/evaluate-message`);
    say("LAUNCHER_BRIDGE: starting bounded iMessage bridge (registered recipient, <=3 messages, 1 URL evaluation, 10-minute expiry)");
    bridge = track(d.spawn(d.nodePath, [bridgeScript], { cwd: d.spectrumDir, env: bridgeEnv, stdio: ["ignore", "pipe", "pipe"], windowsHide: true }));
    let suppressed = 0;
    const streams = [];
    const watch = (stream, forward) => {
      if (!stream) return;
      const lines = readline.createInterface({ input: stream, crlfDelay: Infinity });
      streams.push(new Promise((resolve) => lines.once("close", resolve)));
      lines.on("line", (line) => {
        const safe = forward && line.length <= 4000 && FORWARD.test(line) && !secrets.some((v) => line.includes(v));
        if (safe) say("BRIDGE: " + line); else suppressed++;
      });
    };
    watch(bridge.child.stdout, true);
    watch(bridge.child.stderr, false);
    let cancelMax;
    const maxRun = new Promise((resolve) => { cancelMax = d.setTimer(() => resolve("max"), d.maxRunMs); });
    const first = await Promise.race([bridge.done.then(() => "bridge"), api.done.then(() => "api"), stopRequested.then(() => "signal"), maxRun]);
    cancelMax();
    let code;
    if (signal()) code = signalCode();
    else if (first === "bridge") {
      say(`LAUNCHER_BRIDGE_EXITED: code=${bridge.code} signal=${bridge.signal}${bridge.error ? " (spawn error)" : ""}`);
      code = bridge.code === 0 ? EXIT.ok : EXIT.failed;
    } else if (first === "api") { say(`LAUNCHER_API_FAILED: API exited while bridge running (code=${api.code} signal=${api.signal})`); code = EXIT.failed; }
    else { say("LAUNCHER_TIMEOUT: hard cap reached; stopping"); code = EXIT.failed; }
    await stop(bridge, "BRIDGE");
    await within(Promise.all(streams), 1_000);
    if (suppressed) say(`LAUNCHER_PRIVACY: ${suppressed} non-status bridge line(s) suppressed`);
    return code;
  } finally {
    await stop(bridge, "BRIDGE");
    await stop(api, "API");
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  run(process.argv.slice(2)).then((code) => { process.exitCode = code; }, () => {
    process.stdout.write("LAUNCHER_FAILED: unexpected error; details omitted for privacy\n");
    process.exitCode = EXIT.failed;
  });
}
