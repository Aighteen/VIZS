// Loopback smoke test against a locally running VIZS backend in OFFLINE mode.
// Uses the extension's real request builder and response validator. Makes no provider calls by
// itself; run the backend with VIZS_PROVIDER_MODE=offline. Never point this at a live-mode server.
//
//   VIZS_SMOKE_URL=http://127.0.0.1:8765 VIZS_SMOKE_TOKEN=<token> node scripts/backend-smoke.mjs
import { randomUUID } from "node:crypto";
import { validateBackendUrl } from "../src/lib/config.js";
import { buildEvaluateRequest } from "../src/lib/request.js";
import { errorForStatus, validateEvaluateResponse } from "../src/lib/response.js";
import { buildPanelViewModel } from "../src/lib/view-model.js";

const backend = validateBackendUrl(process.env.VIZS_SMOKE_URL || "http://127.0.0.1:8765");
const token = process.env.VIZS_SMOKE_TOKEN || "";
if (!backend.ok || !/^http:\/\/(127\.0\.0\.1|localhost):/.test(backend.value)) {
  console.error("Smoke test only runs against a loopback backend.");
  process.exit(2);
}
const listing = "https://shop.synthetic.example/perfume"; // SYNTHETIC listing URL

const health = await (await fetch(backend.value + "/healthz")).json();
console.log("healthz:", JSON.stringify(health));
if (health.provider_mode !== "offline") {
  console.error("Refusing to continue: backend is not in offline mode.");
  process.exit(2);
}

async function attempt(label, tokenValue, extraHeaders = {}) {
  const requestId = randomUUID();
  const req = buildEvaluateRequest({ backendUrl: backend.value, token: tokenValue || "x", listingUrl: listing, price: "89.99", requestId });
  if (!tokenValue) delete req.init.headers.Authorization;
  req.init.headers = { ...req.init.headers, ...extraHeaders };
  const res = await fetch(req.url, req.init);
  const text = await res.text();
  if (!res.ok) {
    console.log(`${label}: HTTP ${res.status} -> extension error code "${errorForStatus(res.status).code}"`);
    return res.status;
  }
  const result = validateEvaluateResponse(JSON.parse(text), requestId);
  if (!result.ok) {
    console.log(`${label}: HTTP ${res.status} but payload INVALID: ${result.error}`);
    return -1;
  }
  const vm = buildPanelViewModel(result.assessment);
  console.log(`${label}: HTTP ${res.status} valid assessment risk=${vm.risk.value} decision=${vm.decision.value} data_mode=${vm.dataMode.value} research=${JSON.stringify(vm.research)}`);
  return res.status;
}

const results = {
  valid: await attempt("valid token", token),
  missing: await attempt("missing token", ""),
  wrong: await attempt("wrong token", "wrong-token"),
  badOrigin: await attempt("valid token + unlisted Origin", token, { Origin: "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }),
};
const pass = results.valid === 200 && results.missing === 401 && results.wrong === 401 && results.badOrigin === 403;
console.log(pass ? "SMOKE PASS" : "SMOKE FAIL", JSON.stringify(results));
process.exit(pass ? 0 : 1);
