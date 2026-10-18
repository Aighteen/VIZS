// Shared test helpers (not a test file). Fixtures are SYNTHETIC; see test/fixtures/.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

export const EXT_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

export function fixture(name, requestId) {
  const data = JSON.parse(readFileSync(join(EXT_ROOT, "test", "fixtures", name), "utf8"));
  if (!/SYNTHETIC/.test(data._fixture) || !name.startsWith("synthetic-")) throw new Error("Fixtures must be labeled synthetic");
  const response = structuredClone(data.response);
  if (requestId) response.assessment.request_id = requestId;
  return response;
}

export const RUNTIME_ID = "abcdefghijklmnopabcdefghijklmnop";
export const LISTING = "https://shop.synthetic.example/product?id=1";

export function contentSender(overrides = {}) {
  return { id: RUNTIME_ID, frameId: 0, url: LISTING, tab: { id: 7, url: LISTING }, ...overrides };
}

export function jsonResponse(body, status = 200) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return { ok: status >= 200 && status < 300, status, text: async () => text };
}

/** Minimal fake DOM: enough for render.js. innerHTML and friends throw so any use fails tests. */
class FakeNode {
  constructor(nodeName, ownerDocument) {
    this.nodeName = nodeName;
    this.ownerDocument = ownerDocument;
    this.childNodes = [];
    this.parentNode = null;
  }
  appendChild(child) {
    if (child.parentNode) child.parentNode.childNodes.splice(child.parentNode.childNodes.indexOf(child), 1);
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }
  append(...nodes) {
    for (const n of nodes) this.appendChild(typeof n === "string" ? this.ownerDocument.createTextNode(n) : n);
  }
  get firstChild() {
    return this.childNodes[0] ?? null;
  }
  get textContent() {
    return this.childNodes.map((c) => c.textContent).join("");
  }
  set textContent(value) {
    for (const c of this.childNodes) c.parentNode = null;
    this.childNodes = value === "" ? [] : [this.ownerDocument.createTextNode(String(value))];
  }
}

class FakeText extends FakeNode {
  constructor(data, doc) {
    super("#text", doc);
    this.data = data;
  }
  get textContent() {
    return this.data;
  }
  set textContent(v) {
    this.data = String(v);
  }
}

class FakeElement extends FakeNode {
  constructor(tagName, doc, namespaceURI = null) {
    super(tagName.toUpperCase(), doc);
    this.tagName = tagName.toLowerCase();
    this.namespaceURI = namespaceURI;
    this.attributes = new Map();
  }
  setAttribute(name, value) {
    if (/^on/i.test(name)) throw new Error(`event handler attribute set: ${name}`);
    this.attributes.set(name, String(value));
  }
  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }
  hasAttribute(name) {
    return this.attributes.has(name);
  }
  get children() {
    return this.childNodes.filter((c) => c instanceof FakeElement);
  }
  querySelectorAll(tag) {
    const out = [];
    const walk = (n) => {
      for (const c of n.children) {
        if (c.tagName === tag) out.push(c);
        walk(c);
      }
    };
    walk(this);
    return out;
  }
  set innerHTML(_) {
    throw new Error("innerHTML must not be used");
  }
  get innerHTML() {
    throw new Error("innerHTML must not be used");
  }
  set outerHTML(_) {
    throw new Error("outerHTML must not be used");
  }
  insertAdjacentHTML() {
    throw new Error("insertAdjacentHTML must not be used");
  }
}

export function fakeDocument() {
  const doc = {
    createElement: (tag) => new FakeElement(tag, doc),
    createElementNS: (ns, tag) => new FakeElement(tag, doc, ns),
    createTextNode: (text) => new FakeText(String(text), doc),
  };
  return doc;
}

/** Loads a classic content script into an isolated vm context, like Chrome's isolated world. */
export function loadClassicScripts(files, extraGlobals = {}) {
  const context = vm.createContext({ URL, ...extraGlobals });
  for (const f of files) vm.runInContext(readFileSync(join(EXT_ROOT, f), "utf8"), context, { filename: f });
  return context;
}
