// Human-readable labels. Wording avoids accusations, certainty and percentages.

export const RISK_LABELS = Object.freeze({
  LOWER_RISK: "Lower risk",
  HIGHER_RISK: "Higher risk",
  INSUFFICIENT_EVIDENCE: "Not enough evidence",
});

export const DECISION_LABELS = Object.freeze({
  CONSIDER_BUYING: "Consider buying",
  VERIFY_FIRST: "Verify before buying",
  AVOID: "Avoid for now",
  NEED_MORE_INFORMATION: "More information needed",
});

export const DATA_MODE_LABELS = Object.freeze({
  mock: { label: "Simulation", note: "SIMULATION: this result uses mock data. It is not a real seller check." },
  partial: { label: "Partial data", note: "Partial data: some checks were unavailable or limited." },
  live: { label: "Live research", note: "Live research results from sources retrieved for this check." },
});

export const TOPIC_LABELS = Object.freeze({
  shipping_origin: "Shipping origin",
  processing_time: "Processing time",
  transit_time: "Transit time",
  arrival: "Arrival",
  returns: "Returns",
  return_cost: "Return cost",
  domain_history: "Domain history",
  photos: "Photos",
  domain_registration: "Domain registration",
  photo_reuse: "Photo reuse",
  ai_photo: "AI-photo signal",
});

export const PROMISE_STATUS_LABELS = Object.freeze({
  supported_as_statement: "Stated by merchant (not independently confirmed)",
  independently_corroborated: "Independently corroborated",
  conflicting: "Conflicting terms",
  not_disclosed: "Not disclosed in the sources checked",
  unavailable: "Could not be checked",
});

export const CONTEXT_STATUS_LABELS = Object.freeze({
  unavailable: "Not available",
  unknown: "Unknown",
  context_only: "Context only",
  available: "Available",
});

export const RESEARCH_STATUS_LABELS = Object.freeze({
  partial: "partial results",
  empty: "no results found",
  filtered: "all results were filtered out",
  unavailable: "research unavailable",
  timeout: "research timed out",
  unsafe_url: "listing address was not safe to research",
  skipped: "research skipped",
});

export const EVIDENCE_TYPE_LABELS = Object.freeze({
  official: "Official source",
  directory: "Directory listing",
  regulatory: "Regulatory record",
  investigation: "Investigation",
  complaint: "Complaint",
  community: "Community post",
  unverified_review: "Unverified review",
  search_snippet: "Search snippet",
});

export const CONTENT_KIND_LABELS = Object.freeze({
  merchant_page: "Merchant's own page",
  search_snippet: "Search snippet",
  independent_page: "Independent page",
});

export const UNVERIFIED_LABEL = "Unverified source";

export function label(map, key, fallback = "Unknown") {
  return Object.prototype.hasOwnProperty.call(map, key) ? map[key] : fallback;
}
