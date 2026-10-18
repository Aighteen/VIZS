# Registered-phone inbound test

> Historical record of an earlier run; test counts, paths and statuses below are not current. See [NEXT_STEPS.md](NEXT_STEPS.md).

Packet A added app/adapters/spectrum/src/bridge-handler.mjs, test-bridge.mjs and bridge-handler.test.mjs, plus the A-owned /api/v1/evaluate-message route and tests/test_api.py check. Existing echo src/index.ts was preserved. The route uses the actual runtime assessment and D formatter, adding the assessment clarification when necessary.

Acceptance run: existing project venv python -m pytest -q => 104 passed, one dependency warning. node --test app/adapters/spectrum/src/bridge-handler.test.mjs => 3 passed. npm.cmd run typecheck => exit 0; node --check src/test-bridge.mjs => exit 0; git diff --check => exit 0. npm.cmd ci --ignore-scripts --no-audit --no-fund installed A-local dependencies; package manifests unchanged.

User authorized one registered-phone inbound live test. No existing Node/Python listeners were found. Temporary hidden supervisor launched a live loopback API plus Spectrum iMessage listener; registered recipient was verified using Photon CLI without displaying numbers or credentials. Provider mode is overridden only in the temporary API process; .env was not changed. Accept exactly one nonempty direct inbound text <=4000 characters from the registered recipient; ignore outbound/group/other-recipient events and duplicate IDs. Reply attempts are not retried by application code. Listener expires after ten minutes; supervisor stops the API when the listener finishes. SDK retry behavior remains vendor-managed.

Ready was observed. Actual inbound/reply/handset receipt remains pending user action. Local status directory: C:\Users\haoka\AppData\Local\Temp\vizs-inbound-test-zzhzv5ka. Inspect status.json and privacy-filtered bridge.log on follow-up; do not print credentials, phone numbers or private incoming text. A ready listener is not proof of a successful shopping conversation. FastAPI /webhooks/photon remains disabled; this bridge uses the verified Spectrum SDK stream over iMessage, not a claimed SMS webhook.

Next user action: send a real product listing URL (optional price) in the existing Photon iMessage conversation. Keyword-only input requests a listing URL. Expect conservative results; snippets cannot establish seller authorization. After an attempted reply inspect status and obtain handset receipt confirmation. No commit, push or deployment performed.

## Observed after user sent message

Supervisor status: finished, reply_request_completed true, reply_failed false, window_expired false. Bridge logged REPLY_REQUEST_COMPLETED and ONE_MESSAGE_TEST_FINISHED. This establishes that one registered inbound event was handled and a reply send request completed. Handset receipt remains unconfirmed. Privacy-filtered logs do not record the assessment or per-provider outcomes, so this event alone does not prove successful live Grok/Tavily evaluation; controlled clarification/error replies follow the same send path. No automatic retry or additional paid probe was run.

## Non-receipt investigation and bounded restart

User reported no visible reply. Read-only Photon SDK messages.listInChat for the registered DM returned an outbound clarification at 2026-10-18T03:11:42.816Z, isSent true, isDelivered true, dateDelivered 2026-10-18T03:11:42.995Z, sendErrorCode 0. Another inbound message was recorded later at 03:11:56.959Z, after the one-message handler stopped. Message bodies, recipient and IDs were not displayed. This provider receipt is not user confirmation; visibility discrepancy remains unresolved. No resend was attempted.

Fixed the test budget to allow up to three inbound events, with at most one containing a URL; a clarification no longer immediately shuts down the test. Added regression test; Node bridge suite => 4 passed; syntax check and diff --check exit 0. Added privacy-safe evaluation outcome logs and SDK-returned delivery status reads (up to three reads, no send retry). No provider credentials/config files edited.

Restart observed ready at new status directory C:\Users\haoka\AppData\Local\Temp\vizs-inbound-test-v0lrepuv. Test expires in ten minutes; request the user resend only the actual product listing URL and optional price in the existing Photon iMessage conversation. Investigate fresh evaluation/delivery outcome on follow-up. Existing log/state directory preserved.

## Second inbound outcome and timeout correction

The v0lrepuv test received a URL but evaluation status was NEED_MORE_INFORMATION / partial, timedOut true, evidenceCount 0. This means Grok extraction hit its eight-second deadline before research. Send returned messageIdPresent true, isSent true, isDelivered false, sendErrorCode 0, deliveredAt null during the short poll. No claim of handset delivery or successful shopping research.

A-owned configuration/runtime now applies a bounded 30-second Grok deadline, 55-second workflow deadline, 60-second bridge deadline. Environment overrides VIZS_GROK_TIMEOUT_SECONDS and VIZS_EVALUATION_TIMEOUT_SECONDS supported; no real .env edited. Added mocked timeout propagation regression. Full Python suite 105 passed, one dependency warning; Node bridge suite 4 passed; diff --check clean. No paid request rerun or pending reply resend during this fix.

Fresh listener status directory: C:\Users\haoka\AppData\Local\Temp\vizs-inbound-test-dydl01jv. Startup status above must be checked; the user must send a fresh URL to trigger the next evaluation.

## Third inbound result and user receipt confirmation

The dydl01jv run returned VERIFY_FIRST / partial with evidenceCount 0; no extraction timeout, unavailable, or invalid-output flag. Reply send request completed. User subsequently reported seeing insufficient evidence, confirming a reply was received on the handset despite the short SDK delivery poll remaining false. Do not claim a positive seller conclusion. The current logs count only assessment-retained evidence, not Tavily records; they cannot distinguish empty/failed/filtered research. Current C always emits neutral unknown snippets and D drops such records from assessment.evidence, so zero retained evidence is not proof of zero search results. Next work is research-status observability, retaining useful citations with uncertainty, and grounded source validation through C/D ownership. No additional paid calls are needed merely to repeat this result.

## Improved research-output test window

User authorized a fresh bounded phone test of the source-retention/status changes. No existing test listener/API processes were found. Hidden supervisor status directory: C:\Users\haoka\AppData\Local\Temp\vizs-inbound-test-2x3nujc9. Startup ready observed: True. One URL evaluation, up to three admitted inbound messages total, ten-minute expiry; credentials and phone number remain undisplayed. Previous test artifacts preserved. No provider request triggered until registered user sends a fresh message. Inspect bridge.log for EVALUATION_STATUS.research counts/status and DELIVERY_STATUS, then obtain user receipt confirmation.

## Improved research-output live result

The 2x3nujc9 listener received the registered inbound message and completed evaluation: VERIFY_FIRST, partial, evidenceCount 2. Tavily report: provider_called true, status partial, records_received 5, records_retained 2, records_filtered 3. Extraction flags unavailable/timedOut/invalidOutput all false. Reply send completed without failure; messageIdPresent true, isSent true, isDelivered false, sendErrorCode 0 during the short delivery poll. Test stopped after the bounded URL evaluation. This establishes a live research result with retained references, not source truth or handset delivery. Ask user whether the new reply arrived with unverified source links. No duplicate resend attempted and private content/URLs were not logged.

## Handset confirmation and publish checkpoint

The user confirmed receiving the improved reply with unverified source links. This completes the registered-phone iMessage round trip: inbound listing, valid Grok extraction, Tavily five records/two retained/three filtered, VERIFY_FIRST, and handset receipt. The short SDK delivery poll remained false; receipt is established by user confirmation. No authenticity conclusion or SMS transport claim follows.

Human requested committing and pushing the tested local runtime, bridge and research-output changes to GitHub main. Earlier uncommitted/pending statements above are historical. Default mode remains offline; no continuous listener or deployment is enabled by publishing.
