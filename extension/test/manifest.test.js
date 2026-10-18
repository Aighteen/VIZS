import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { test } from "node:test";
import { EXT_ROOT } from "./helpers.js";

const manifest = JSON.parse(readFileSync(join(EXT_ROOT, "manifest.json"), "utf8"));

test("manifest is MV3 with a module service worker and user-triggered action", () => {
  assert.equal(manifest.manifest_version, 3);
  assert.equal(manifest.background.service_worker, "src/background.js");
  assert.equal(manifest.background.type, "module");
  assert.ok(manifest.action);
  assert.ok(existsSync(join(EXT_ROOT, manifest.background.service_worker)));
  assert.ok(existsSync(join(EXT_ROOT, manifest.options_ui.page)));
});

test("permissions are minimal: activeTab, scripting, storage; loopback backend hosts only", () => {
  assert.deepEqual([...manifest.permissions].sort(), ["activeTab", "scripting", "storage"]);
  assert.deepEqual(manifest.host_permissions, ["http://127.0.0.1:8000/*", "http://localhost:8000/*"]);
  const text = JSON.stringify(manifest);
  assert.doesNotMatch(text, /<all_urls>|\*:\/\/\*\/|"tabs"|"history"|"webRequest|"cookies"|"downloads"/);
  assert.equal(manifest.content_scripts, undefined, "no auto-injected content scripts");
  assert.equal(manifest.web_accessible_resources, undefined);
  assert.equal(manifest.externally_connectable, undefined, "web pages cannot message the worker");
  assert.equal(manifest.optional_permissions, undefined);
  assert.doesNotMatch(manifest.content_security_policy.extension_pages, /unsafe-eval|unsafe-inline|http/);
});

test("background injects exactly the content files that exist", () => {
  const bg = readFileSync(join(EXT_ROOT, "src/background.js"), "utf8");
  const files = JSON.parse(/CONTENT_FILES = (\[[^\]]+\])/.exec(bg)[1]);
  for (const f of files) assert.ok(existsSync(join(EXT_ROOT, f)), f);
  assert.match(bg, /chrome\.action\.onClicked\.addListener/);
  assert.doesNotMatch(bg, /tabs\.onUpdated[\s\S]{0,200}executeScript/, "no injection on navigation");
  assert.match(bg, /"debug"|lib\/controller\.js/);
});

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

test("source never uses HTML-string sinks, eval or remote code", () => {
  for (const file of walk(join(EXT_ROOT, "src"))) {
    if (!/\.(js|html)$/.test(file)) continue;
    const src = readFileSync(file, "utf8");
    const rel = relative(EXT_ROOT, file);
    assert.doesNotMatch(src, /\.innerHTML|\.outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function\(/, rel);
    assert.doesNotMatch(src, /<script[^>]+src=["']https?:/i, rel);
    assert.doesNotMatch(src, /fonts\.googleapis|cdn\.|unpkg|jsdelivr/i, rel);
  }
});

test("only the service worker and options page touch the pairing token storage", () => {
  for (const file of walk(join(EXT_ROOT, "src", "content"))) {
    const src = readFileSync(file, "utf8");
    assert.doesNotMatch(src, /chrome\.storage|pairingToken|Bearer/, relative(EXT_ROOT, file));
  }
});

test("no runtime dependencies", () => {
  const pkg = JSON.parse(readFileSync(join(EXT_ROOT, "package.json"), "utf8"));
  assert.equal(pkg.dependencies, undefined);
  assert.equal(pkg.devDependencies, undefined);
});
