# Current checkpoint and next assignment

Packets A-D are merged on `feat/packet-a-integration` in `C:\Github\VIZS-packet-a`. This is the branch to continue from. GitHub main was fast-forwarded to checkpoint `ecee580`; its original checkout contains preserved uncommitted work. Do not reset/clean it or switch its branch. Do not blindly commit copied dependency files in B/C worktrees. Old packet handoffs are historical.

## Completed

- FastAPI scaffold, bounded in-process workflow/jobs and independent mock transport.
- Shared Pydantic contracts, synthetic fixtures, deterministic seller policy and SMS formatter.
- Injectable Grok extraction and bounded Tavily provider, provenance and URL admission checks.
- B-D merged into A without conflicts; latest combined offline check passed 116 tests, one installed Starlette/httpx deprecation warning.

Runtime wiring is now implemented locally. Startup assembles the shared workflow; offline requests return partial assessments/clarifications rather than the earlier unwired 503. The real Photon callback remains disabled. A live keyword probe passed Grok/Tavily. A registered-phone URL test returned VERIFY_FIRST and the user confirmed receiving the insufficient-evidence reply; old diagnostics did not distinguish research failures from filtered results. The improved cited response also passed one live phone test; the user confirmed receiving the unverified source links. The separate Spectrum iMessage echo is not the shopping flow or SMS proof.

## Implemented locally: Packet A runtime wiring

Writable scope: `app/main.py`, `app/config.py`, `app/workflow/`, A-owned `tests/test_api.py`, `.env.example`, dependency manifests if needed, README and coordination docs. Consume B/C/D modules; request changes to their implementation/tests through the respective owners.

1. Assemble `Contracts(ShoppingRequest, OrchestratorPlan, Assessment)` from `app.models`.
2. Inject `GrokExtractor.extract`, `SellerResearch(TavilyProvider(api_key))`, and `app.decision.decide` into `EvaluationWorkflow`; pass `format_sms` into `create_app` when using the message simulator.
3. Define explicit offline/live configuration. A owns `httpx.AsyncClient` lifetime for `XAICompletionClient`, using `XAI_API_KEY` and an explicit `XAI_MODEL`. Supply Tavily's key via secure configuration (suggested name `TAVILY_API_KEY`). Root `.env` loading now uses python-dotenv without mutating process environment; environment overrides file values. `VIZS_PROVIDER_MODE=offline` is default, `live` explicitly enables provider requests, and `VIZS_ENABLE_MOCK_SMS` controls the simulator. Preserve unavailable and mock labels; never silently enable paid calls.
4. Add offline API-level checks using the real shared contracts/policy and mocked provider HTTP: successful request, missing listing, unavailable key, provider timeout/failure, insufficient evidence, and simulation labeling/deduplication. Verify lifecycles close cleanly.
5. Run the full suite and exercise the local endpoint. Record exact commands and observed outputs. Live provider probes require separate instruction to spend credits.

C currently emits unknown/unverified search snippets only. Those snippets cannot yield confirmed authorization or substantial adverse facts. Conservative `INSUFFICIENT_EVIDENCE` is expected; do not weaken policy to obtain a positive demo.

## Next: authorized live verification

The new phone test completed: five Tavily records, two retained, three filtered, and user-confirmed cited reply receipt. Next build a reproducible bounded launcher and strengthen official-source validation. Latest offline suite passed 116 tests. A bounded Spectrum iMessage bridge exists; verify account-specific Photon callback/auth/send behavior before implementing the FastAPI webhook; do not invent schemas or treat iMessage echo as SMS. Then run an authorized live end-to-end flow with real citations and handset receipt. In-process jobs are non-durable. Keep P1 pricing/cards behind P0 gates. Review Devpost deadlines in SPRINT_PLAN.md; humans submit.

## Reproduce current checks

From the integration worktree, the verified local command is:

```powershell
& C:\Github\VIZS\.venv\Scripts\python.exe -m pytest -q
```

A fresh checkout can use README's Python 3.11+ venv setup and `pip install -e '.[test]'`. Do not copy secret `.env` files into Git. Checkpoint `ecee580` is on GitHub main. The current authorized publish includes runtime wiring, the bounded bridge, research status/citation improvements and test evidence. Nothing has been deployed.

See RESEARCH_OUTPUT_HANDOFF.md for the source-retention fix and exact report contract. The previous bounded listener has stopped. The initial improvement used offline tests; a subsequent explicitly authorized phone test passed, with user-confirmed receipt.
