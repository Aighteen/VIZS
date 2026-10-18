// Response validation and error mapping. Mirrors app/models Assessment bounds closely enough
// that a malformed or hostile payload becomes an error state, never a "finished" state.

const RISKS = ["LOWER_RISK", "HIGHER_RISK", "INSUFFICIENT_EVIDENCE"];
const DECISIONS = ["CONSIDER_BUYING", "VERIFY_FIRST", "AVOID", "NEED_MORE_INFORMATION"];
const ALLOWED_DECISIONS = {
  LOWER_RISK: ["CONSIDER_BUYING"],
  HIGHER_RISK: ["AVOID"],
  INSUFFICIENT_EVIDENCE: ["VERIFY_FIRST", "NEED_MORE_INFORMATION"],
};
const DATA_MODES = ["live", "partial", "mock"];
const EVIDENCE_TYPES = ["official", "directory", "regulatory", "investigation", "complaint", "community", "unverified_review", "search_snippet"];
const CLAIM_STATUSES = ["verified_fact", "allegation", "inference", "unknown"];
const RESEARCH_STATUSES = ["partial", "empty", "filtered", "unavailable", "timeout", "unsafe_url", "skipped"];
const TOPICS = ["shipping_origin", "processing_time", "transit_time", "arrival", "returns", "return_cost", "domain_history", "photos", "domain_registration", "photo_reuse", "ai_photo"];
const PROMISE_STATUSES = ["supported_as_statement", "independently_corroborated", "conflicting", "not_disclosed", "unavailable"];
const CONTEXT_STATUSES = ["unavailable", "unknown", "context_only", "available"];
const CONTENT_KINDS = ["merchant_page", "search_snippet", "independent_page"];

export class PayloadError extends Error {}

function fail(path, why) {
  throw new PayloadError(`${path}: ${why}`);
}
function isObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}
function str(v, path, { max, min = 1, optional = false } = {}) {
  if (v === undefined || v === null) {
    if (optional) return null;
    fail(path, "missing");
  }
  if (typeof v !== "string") fail(path, "not a string");
  const t = v.trim();
  if (t.length < min) fail(path, "empty");
  if (max && t.length > max) fail(path, "too long");
  return t;
}
function oneOf(v, allowed, path) {
  if (!allowed.includes(v)) fail(path, "unexpected value");
  return v;
}
function arr(v, path, max) {
  if (v === undefined || v === null) return [];
  if (!Array.isArray(v)) fail(path, "not a list");
  if (v.length > max) fail(path, "too many items");
  return v;
}
function count(v, path) {
  if (v === undefined) return 0;
  if (!Number.isInteger(v) || v < 0 || v > 5) fail(path, "invalid count");
  return v;
}
function obj(v, path, optional = false) {
  if (v === undefined || v === null) {
    if (optional) return null;
    fail(path, "missing");
  }
  if (!isObject(v)) fail(path, "not an object");
  return v;
}

function evidence(e, p) {
  obj(e, p);
  return {
    claim: str(e.claim, `${p}.claim`, { max: 1000 }),
    source_url: str(e.source_url, `${p}.source_url`, { max: 2048 }),
    source_title: str(e.source_title, `${p}.source_title`, { max: 300, optional: true }),
    evidence_type: oneOf(e.evidence_type, EVIDENCE_TYPES, `${p}.evidence_type`),
    claim_status: oneOf(e.claim_status, CLAIM_STATUSES, `${p}.claim_status`),
    data_mode: e.data_mode === undefined ? "partial" : oneOf(e.data_mode, DATA_MODES, `${p}.data_mode`),
  };
}

function research(r, p) {
  obj(r, p);
  const out = {
    provider: str(r.provider ?? "tavily", `${p}.provider`, { max: 40 }),
    status: oneOf(r.status, RESEARCH_STATUSES, `${p}.status`),
    provider_called: r.provider_called === true,
    records_received: count(r.records_received, `${p}.records_received`),
    records_retained: count(r.records_retained, `${p}.records_retained`),
    records_filtered: count(r.records_filtered, `${p}.records_filtered`),
  };
  if (out.records_received !== out.records_retained + out.records_filtered) fail(p, "research counts disagree");
  return out;
}

function promiseContext(c, p) {
  if (c === undefined || c === null) return null;
  obj(c, p);
  return {
    status: oneOf(c.status ?? "unavailable", CONTEXT_STATUSES, `${p}.status`),
    explanation: str(c.explanation ?? "This check is not available; no conclusion was drawn.", `${p}.explanation`, { max: 500 }),
    source_url: str(c.source_url, `${p}.source_url`, { max: 2048, optional: true }),
  };
}

function promiseSheet(s, p) {
  if (s === undefined || s === null) return null;
  obj(s, p);
  const sources = arr(s.sources, `${p}.sources`, 8).map((src, i) => {
    const q = `${p}.sources[${i}]`;
    obj(src, q);
    return {
      source_id: str(src.source_id, `${q}.source_id`, { max: 80 }),
      url: str(src.url, `${q}.url`, { max: 2048 }),
      title: str(src.title, `${q}.title`, { max: 300, optional: true }),
      content_kind: oneOf(src.content_kind, CONTENT_KINDS, `${q}.content_kind`),
      data_mode: src.data_mode === undefined ? "partial" : oneOf(src.data_mode, DATA_MODES, `${q}.data_mode`),
    };
  });
  const records = arr(s.records, `${p}.records`, 12).map((r, i) => {
    const q = `${p}.records[${i}]`;
    obj(r, q);
    const conditions = obj(r.conditions, `${q}.conditions`, true) || {};
    return {
      topic: oneOf(r.topic, TOPICS, `${q}.topic`),
      status: oneOf(r.status, PROMISE_STATUSES, `${q}.status`),
      merchant_statement: str(r.merchant_statement, `${q}.merchant_statement`, { max: 1200, optional: true }),
      explanation: str(r.explanation, `${q}.explanation`, { max: 700 }),
      quotes: arr(r.quotes, `${q}.quotes`, 6).map((qt, j) => {
        obj(qt, `${q}.quotes[${j}]`);
        return {
          source_id: str(qt.source_id, `${q}.quotes[${j}].source_id`, { max: 80 }),
          quote: str(qt.quote, `${q}.quotes[${j}].quote`, { max: 1200 }),
        };
      }),
      conditions: {
        region: str(conditions.region, `${q}.conditions.region`, { max: 120, optional: true }),
        time: str(conditions.time, `${q}.conditions.time`, { max: 200, optional: true }),
        eligibility: str(conditions.eligibility, `${q}.conditions.eligibility`, { max: 300, optional: true }),
      },
    };
  });
  return {
    seller_domain: str(s.seller_domain, `${p}.seller_domain`, { max: 253, optional: true }),
    sources,
    records,
    domain_context: promiseContext(s.domain_context, `${p}.domain_context`),
    image_context: promiseContext(s.image_context, `${p}.image_context`),
  };
}

/** Validates an Assessment object. Throws PayloadError. Returns a normalized copy. */
export function validateAssessment(a) {
  obj(a, "assessment");
  const seller_risk = oneOf(a.seller_risk, RISKS, "assessment.seller_risk");
  const decision = oneOf(a.decision, DECISIONS, "assessment.decision");
  if (!ALLOWED_DECISIONS[seller_risk].includes(decision)) fail("assessment", "risk and decision disagree");
  return {
    request_id: str(a.request_id, "assessment.request_id", { max: 128 }),
    seller_risk,
    decision,
    summary: str(a.summary, "assessment.summary", { max: 500 }),
    evidence: arr(a.evidence, "assessment.evidence", 30).map((e, i) => evidence(e, `assessment.evidence[${i}]`)),
    promise_sheet: promiseSheet(a.promise_sheet, "assessment.promise_sheet"),
    research: arr(a.research, "assessment.research", 3).map((r, i) => research(r, `assessment.research[${i}]`)),
    missing_information: arr(a.missing_information, "assessment.missing_information", 10).map((m, i) =>
      str(m, `assessment.missing_information[${i}]`, { max: 1000 })),
    data_mode: oneOf(a.data_mode, DATA_MODES, "assessment.data_mode"),
  };
}

/**
 * Validates the extension endpoint response {assessment, message_text}.
 * Returns { ok:true, assessment, messageText } or { ok:false, error }.
 */
export function validateEvaluateResponse(payload, expectedRequestId) {
  try {
    obj(payload, "response");
    const assessment = validateAssessment(payload.assessment);
    const messageText = str(payload.message_text, "response.message_text", { max: 4000, optional: true });
    if (expectedRequestId && assessment.request_id !== expectedRequestId) fail("assessment.request_id", "does not match this request");
    return { ok: true, assessment, messageText };
  } catch (err) {
    if (err instanceof PayloadError) return { ok: false, error: err.message };
    throw err;
  }
}

export const ERROR_CODES = Object.freeze({
  NOT_PAIRED: "not_paired",
  PAIRING: "pairing",
  ORIGIN: "origin",
  BUSY: "busy",
  UNAVAILABLE: "unavailable",
  SERVER_TIMEOUT: "server_timeout",
  CLIENT_TIMEOUT: "client_timeout",
  DEPENDENCY: "dependency",
  REJECTED: "rejected",
  SERVER: "server",
  NETWORK: "network",
  INVALID_RESPONSE: "invalid_response",
  UNSUPPORTED_PAGE: "unsupported_page",
  INVALID_INPUT: "invalid_input",
});

const SETTINGS_CODES = new Set([ERROR_CODES.NOT_PAIRED, ERROR_CODES.PAIRING, ERROR_CODES.ORIGIN]);

export function makeError(code, message) {
  return { code, message, showSettings: SETTINGS_CODES.has(code), retryable: code !== ERROR_CODES.UNSUPPORTED_PAGE };
}

/** Maps a non-2xx HTTP status to a user-facing error. */
export function errorForStatus(status) {
  switch (status) {
    case 401:
      return makeError(ERROR_CODES.PAIRING, "The backend rejected the pairing token. Open VIZS options and paste the current VIZS_EXTENSION_TOKEN.");
    case 403:
      return makeError(ERROR_CODES.ORIGIN, "The backend does not allow this extension yet. Open VIZS options and add the extension origin shown there to VIZS_EXTENSION_ORIGINS.");
    case 429:
      return makeError(ERROR_CODES.BUSY, "VIZS is busy with another check. Please try again in a minute.");
    case 503:
      return makeError(ERROR_CODES.UNAVAILABLE, "The VIZS backend is unavailable or not configured for the extension right now.");
    case 504:
      return makeError(ERROR_CODES.SERVER_TIMEOUT, "The seller check timed out on the backend.");
    case 502:
      return makeError(ERROR_CODES.DEPENDENCY, "A research service the backend depends on failed.");
    default:
      if (status >= 400 && status < 500) return makeError(ERROR_CODES.REJECTED, `The backend rejected the request (HTTP ${status}).`);
      return makeError(ERROR_CODES.SERVER, `The backend returned an unexpected error (HTTP ${status}).`);
  }
}

export function networkError() {
  return makeError(ERROR_CODES.NETWORK, "Could not reach the VIZS backend. Check that it is running and that the backend URL in options is correct.");
}
export function clientTimeoutError() {
  return makeError(ERROR_CODES.CLIENT_TIMEOUT, "The seller check took too long and VIZS stopped waiting.");
}
export function invalidResponseError() {
  return makeError(ERROR_CODES.INVALID_RESPONSE, "The backend sent a response VIZS could not understand, so no result is shown.");
}
export function notPairedError() {
  return makeError(ERROR_CODES.NOT_PAIRED, "VIZS is not paired with a backend yet. Open VIZS options to add the backend URL and pairing token.");
}
