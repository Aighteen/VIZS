# Integration runbook — verify in this order

This is an action plan, not a record of successful API access. Update PASS/BLOCKED only after observing real results.

| Probe | How to check | Pass evidence | Status |
|---|---|---|---|
| Local Python/FastAPI | Create isolated env, install documented repo deps, `pytest`, `uvicorn` | `/healthz`, local `/api/v1/evaluate` responds | UNTESTED |
| Grok API | Use approved model and vendor SDK/Responses client; test small structured response | Valid parsed `OrchestratorPlan` | UNTESTED |
| Research provider | Tavily API key/search request, or xAI supported native web search | Real source record URLs logged without sensitive info | UNTESTED |
| Photon 2.0 Beta | Confirm beta account access, channel/phone provision, precise callback auth/send docs | Visible inbound message and accepted outbound SMS | UNTESTED |
| Deployment | Public HTTPS webhook URL reachable, env vars configured securely | Real callback reached remote service | UNTESTED |
| End-to-end | Send test SMS, inspect trace ID, receive reply | Real inbound/outbound proof and no duplicate SMS | UNTESTED |

## Photon warnings

- The public Photon 2.0 announcement describes a unified multi-channel messaging API. It does **not** establish that your account is enabled, that SMS is provisioned, or exactly which incoming callback fields/auth signature header your beta endpoint uses.
- Several unrelated products are also named Photon; do not accidentally integrate Photon Engine game-chat, Photon Health, or another vendor's `/webhooks` API.
- Photon public API/SDK sources exist (`photon-hq/api`), but verify version, endpoint mapping, provisioning, and webhook security against **your Photon 2.0 Beta account** before copying examples.
- If beta access is denied or SMS is unavailable, the local debug API and a labeled simulation remain valid for software testing, **but do not meet the described live-channel Photon side-track requirement**.

## xAI / Tavily notes

- xAI currently documents Responses API web-search tools and structured output on supported model families. Verify which model and feature combination your key can actually call. Check how server-side citation/source records are returned before relying on them.
- Tavily offers search/extract and explicit URLs. Check response fields and actual 200/4xx behavior; keep a normalized wrapper so Grok provider can be replaced without rewriting policy.
- A citation must come from an actually returned search record; avoid asking Grok to hallucinate a URL. Only scrape/visit pages in compliance with permissions and secure URL controls.

## Fallback matrix

| Failure | Safe immediate action | What must not be claimed |
|---|---|---|
| No Photon access | Use `/api/v1/evaluate` + clearly labeled message simulator; contact sponsor | Live Photon integration/Photon track eligibility |
| No Grok key/limit | Use canned structured plans in fixture mode to continue policy/tests | Real Grok orchestration |
| No Tavily key | Use Grok native search if available, otherwise source-free `INSUFFICIENT_EVIDENCE` | Verified live web research |
| Search no credible evidence | Respond `INSUFFICIENT_EVIDENCE`, `VERIFY_FIRST` | Seller is fraudulent or genuine |
| Slow webhook / duplicate delivery | Idempotent key and quick ACK, capped work; consider queue if needed | Exactly-once or durable delivery unless tested |
| Hosting down | Test local backend and record when previously working | Live public availability |
| Late Saturday | Stop P1; save mandatory Devpost draft | Full feature completeness |
| Late Sunday | Freeze and submit tested code/video with limitations | An untested change is deployable |

## Information to avoid collecting

No full credit-card numbers, CVV, account password, banking API tokens through SMS; no unjustified storing of SMS phone numbers and listing URLs in public log files.
