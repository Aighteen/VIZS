# Research output follow-up handoff

> Historical record of an earlier run; test counts, paths and statuses below are not current. See [NEXT_STEPS.md](NEXT_STEPS.md).

## Assignment and outcome

Human asked root to continue C/D research-response improvements after receiving INSUFFICIENT_EVIDENCE. Work stayed in C:\Github\VIZS-packet-a on feat/packet-a-integration, based on ecee580 plus preserved local runtime/bridge changes. Scope recorded in OWNERSHIP.md. Other packet checkouts, local secrets and .vscode were preserved. No agents spawned, no paid calls, no messages sent, no commit/push/deployment.

## Changed paths and behavior

- app/models/__init__.py: Evidence accepts search_snippet; Assessment adds backwards-compatible default-empty research reports. Counts bounded to five records per call, at most three reports, extra fields forbidden and count/status consistency validated.
- app/research/provider.py and app/services/tavily.py: retain bounded raw-result counts before normalization; distinguish provider timeouts from unavailability. Existing search(query)->list[SourceRecord] remains supported; new search_with_status exposes records and bounded received count without extra requests.
- app/research/evidence.py: propagate per-call status, called flag, received/filtered counts; distinguish truly empty results from relevance/safety filtering. Normalize www seller aliases. Snippets remain unknown, neutral, other findings; no automatic authorization/adverse classification.
- app/decision/rules.py: preserve relevant unverified references for VERIFY_FIRST and conflicts; unrelated seller records excluded. Lower/higher risk triggers unchanged.
- app/decision/sms.py: cite up to two intact links, explicitly label unverified sources, preserve data-mode/authenticity uncertainty, explain empty/filtered/timeout/unavailable states, maintain character cap. No invented DETAILS feature when links exceed the budget.
- app/workflow/service.py: copy reports and gaps into assessment without mutable cross-request status.
- app/adapters/spectrum/src/test-bridge.mjs: privacy-safe logs now include the validated research reports, so API-retained evidence count is not confused with Tavily result count.
- tests/test_{api,contracts,policy,research,sms}.py: regression and integrated mocked HTTP coverage for sources, filtering, count consistency, empty results, failures/timeouts, aliases, prompt-injection text, conservative decisions, SMS links/labels/limits.

## Actual checks

`& C:\Github\VIZS\.venv\Scripts\python.exe -m pytest -q` => 116 passed, one installed Starlette/httpx deprecation warning, exit 0.

`node --test app/adapters/spectrum/src/bridge-handler.test.mjs` => 4 passed; `node --check app/adapters/spectrum/src/test-bridge.mjs` and `npm.cmd run typecheck` in the Spectrum directory, plus `git diff --check`, are recorded after execution in this turn's final report.

All search/provider content in these tests is synthetic/mocked. Prior handset receipt was reported by the user; the new cited response has not been live-tested. Source links cite returned records, not independent verification of their contents. No brand/region validation or manufacturer authorization proof was invented.

## Contract details and exact integration

No further wiring is required: runtime already calls SellerResearch.research_with_status; workflow invokes result.report(), decision retains relevant evidence, formatter consumes assessment.research, and evaluate-message returns the formatted body. `records_received` counts Tavily results considered within max_results, `records_retained` counts normalized relevant evidence before policy selection, and `records_filtered` is the difference (includes invalid/duplicate/unrelated results). The assessment evidence list is selected by policy and can differ for strong conclusions. Missing-key paths report provider_called false; network/provider failures report an attempted call with zero retained records. No raw errors, keys, phone numbers, or SMS content enter diagnostic logs.

## Next step and limitations

Run one fresh registered-phone fragrance URL test when requested and inspect research status plus counts. Listener from the previous test has stopped; do not claim it is running. An insufficient conclusion should now include relevant unverified links when any survive. If results are empty/filtered/failed, the reply explains that state rather than suggesting fraud. Still needed for stronger conclusions: grounded official-source validation with matching seller/brand/region; never lower thresholds to force a favorable result. Latest implementation and docs remain local and uncommitted; GitHub main remains ecee580 until a requested commit/push.

## Subsequent authorized live check

User requested a fresh phone test. Registered inbound evaluation produced two retained references from five Tavily records (three filtered), VERIFY_FIRST / partial, with no extraction timeout/error flag. Photon reply send completed; SDK short poll did not yet confirm delivery. Handset confirmation for the new cited reply remains pending. See INBOUND_TEST_HANDOFF.md for privacy-safe evidence and test state.

## Handset confirmation and publish checkpoint

The user confirmed receiving the improved reply with unverified source links. This completes the registered-phone iMessage round trip: inbound listing, valid Grok extraction, Tavily five records/two retained/three filtered, VERIFY_FIRST, and handset receipt. The short SDK delivery poll remained false; receipt is established by user confirmation. No authenticity conclusion or SMS transport claim follows.

Human requested committing and pushing the tested local runtime, bridge and research-output changes to GitHub main. Earlier uncommitted/pending statements above are historical. Default mode remains offline; no continuous listener or deployment is enabled by publishing.
