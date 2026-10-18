// Converts a validated Assessment into plain display data for the content script.
// Output contains only strings/booleans/arrays; links are pre-filtered to http(s).
import {
  CONTENT_KIND_LABELS, CONTEXT_STATUS_LABELS, DATA_MODE_LABELS, DECISION_LABELS, EVIDENCE_TYPE_LABELS,
  PROMISE_STATUS_LABELS, RESEARCH_STATUS_LABELS, RISK_LABELS, TOPIC_LABELS, UNVERIFIED_LABEL, label,
} from "./labels.js";
import { displayHost, safeHttpUrl } from "./safe-url.js";

export const MAX_SOURCE_LINKS = 2;

function link(rawUrl, title) {
  const href = safeHttpUrl(rawUrl);
  return { href, text: title || (href ? displayHost(href) || href : "Link hidden (unsafe address)") };
}

function researchLine(r) {
  const name = r.provider === "tavily" ? "Tavily" : r.provider;
  let line = `Research (${name}): ${label(RESEARCH_STATUS_LABELS, r.status, r.status)}`;
  if (r.records_received) {
    line += ` — ${r.records_retained} of ${r.records_received} results kept, ${r.records_filtered} filtered`;
  }
  return line + ".";
}

function promiseSourceLink(source) {
  if (!source) return { href: null, text: "Source not returned", kind: "Unknown source", unverified: true };
  const l = link(source.url, source.title);
  const unverified = source.content_kind !== "merchant_page";
  return { ...l, kind: label(CONTENT_KIND_LABELS, source.content_kind), unverified };
}

function conditionsText(c) {
  const parts = [];
  if (c.region) parts.push(`Region: ${c.region}`);
  if (c.time) parts.push(`Timing: ${c.time}`);
  if (c.eligibility) parts.push(`Eligibility: ${c.eligibility}`);
  return parts.join(" · ");
}

function contextView(title, ctx) {
  const c = ctx || { status: "unavailable", explanation: "This check is not available; no conclusion was drawn.", source_url: null };
  return {
    title,
    status: c.status,
    statusLabel: label(CONTEXT_STATUS_LABELS, c.status),
    explanation: c.explanation,
    source: c.source_url ? { ...link(c.source_url, null), unverified: true } : null,
  };
}

/** @param {ReturnType<import('./response.js').validateAssessment>} a */
export function buildPanelViewModel(a) {
  const mode = DATA_MODE_LABELS[a.data_mode] || DATA_MODE_LABELS.partial;
  const sheet = a.promise_sheet;
  const sourcesById = new Map((sheet?.sources || []).map((s) => [s.source_id, s]));

  const seen = new Set();
  const sources = [];
  for (const e of a.evidence) {
    if (sources.length >= MAX_SOURCE_LINKS) break;
    const l = link(e.source_url, e.source_title);
    if (!l.href || seen.has(l.href)) continue;
    seen.add(l.href);
    const verified = e.claim_status === "verified_fact";
    sources.push({
      ...l,
      kind: label(EVIDENCE_TYPE_LABELS, e.evidence_type),
      unverified: !verified,
      badge: verified ? "Verified fact" : UNVERIFIED_LABEL,
      claim: e.claim,
    });
  }

  return {
    requestId: a.request_id,
    dataMode: { value: a.data_mode, label: mode.label, note: mode.note, isSimulation: a.data_mode === "mock" },
    risk: { value: a.seller_risk, label: label(RISK_LABELS, a.seller_risk) },
    decision: { value: a.decision, label: label(DECISION_LABELS, a.decision) },
    insufficient: a.seller_risk === "INSUFFICIENT_EVIDENCE",
    summary: a.summary,
    missingInformation: [...a.missing_information],
    research: a.research.length ? a.research.map(researchLine) : ["Research: no research report was returned."],
    promises: (sheet?.records || []).map((r) => ({
      topic: label(TOPIC_LABELS, r.topic),
      status: r.status,
      statusLabel: label(PROMISE_STATUS_LABELS, r.status),
      merchantStatement: r.merchant_statement,
      explanation: r.explanation,
      conditions: conditionsText(r.conditions),
      quotes: r.quotes.map((q) => {
        const source = promiseSourceLink(sourcesById.get(q.source_id));
        return { text: q.quote, source: { ...source, badge: source.unverified ? UNVERIFIED_LABEL : source.kind } };
      }),
    })),
    contexts: sheet
      ? [contextView("Domain registration", sheet.domain_context), contextView("Photo checks", sheet.image_context)]
      : [],
    sources,
    disclaimer: "VIZS does not certify authenticity. An unknown seller is not automatically fraudulent, and a low price does not prove counterfeit goods.",
  };
}
