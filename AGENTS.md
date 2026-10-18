# AGENTS.md — DubHacks 2026 shopping assistant

> Repository-level instructions for Codex and tools that support `AGENTS.md`. GitHub Copilot also reads `.github/copilot-instructions.md`.

## Mission

Implement **a online shopping assistant with two core channels: Photon messaging and a Chrome extension with an animated on-page pet**. Given the active product URL and optional confirmed price, return an evidence-backed **seller credibility assessment** and actionable shopping decision through either a Photon reply or the pet's result panel. The pet shows honest search progress; Photon messaging and the extension are both core product scope, sharing one backend. See `docs/EXTENSION_SCOPE.md` for the current scope (backend route and MV3 extension in `extension/` implemented) and `docs/NEXT_STEPS.md` for current status and `docs/CREDIBILITY_CHECKING.md` for the user-supplied promise-first credibility method. Compare merchant wording with quoted evidence and unknowns; broader payment/training/dispute features in the reference are not adopted. Grok organizes the reasoning; Python executes the policy and arithmetic. **An unknown seller is not automatically fraudulent, and a low price does not prove counterfeit goods.**

**Primary title track proposed:** VISA: Reimagine Shopping. **Sponsored side track proposed:** Photon Messaging Agent. Only humans may finalize/submit track choices.

## Required context, in order

Read `docs/EXTENSION_SCOPE.md` for current product direction, then `docs/PROJECT_BRIEF.md`, `docs/ARCHITECTURE.md`, `docs/API_CONTRACTS.md`, `docs/IMPLEMENTATION_TASKS.md`, `docs/SPRINT_PLAN.md`, and, near submission, `docs/SUBMISSION_CHECKLIST.md`. If source code exists, inspect it; these docs propose contracts, not proof of completed implementation.

## Priorities and hard limits

- **P0 first:** both Photon inbound/outbound messaging and a user-triggered Chrome extension/pet UI, sharing the FastAPI/Grok/Tavily workflow, real source URLs, claim validation and deterministic policy. Provide honest request states, cited replies and a clear result panel. API keys stay server-side; A owns safe backend access. Preserve the tested iMessage path, verify SMS separately, and do not invent Photon contracts.
- **P1 only after P0:** matched-product pricing, wallet-based card-rewards calculations, `DETAILS` follow-up, parallel research.
- **Not this hackathon unless explicitly approved:** autonomous payment, Visa TAP, storing PAN/CVV, massive scraping, fine-tuning, unproven authenticity percentage, microservice swarm, Redis/Celery/Postgres without demonstrated need.
- **Submission:** Saturday Oct 17 **10:30 PM PDT mandatory initial draft**; Sunday Oct 18 **10:00 AM PDT final** with video and uploaded linked source code. Plan buffers. Coding eligible only in event-approved window; see organizer guide and 70/30 rule.

## Engineering rules

1. Scope every assignment to named files and acceptance tests; do not modify unrelated ownership areas. Make a plan before implementing; run tests after. Never claim tests/deployment/API calls you did not execute.
2. **Stack:** Python 3.11+ and FastAPI/Pydantic/pytest (proposed; inspect actual repo). `app/adapters/photon.py` must isolate vendor-specific payloads, security verification, send API. **Do not invent Photon 2.0 schemas, headers, or webhook auth.** Confirm with the team's actual docs.
3. **Orchestration:** Grok may extract intent and suggest tasks in schema-validated JSON; the backend has the final say about tools, number of calls, timeouts, allowlists, policy, and delivery. Use a single orchestrator first. The presence of multiple research functions does not require multiple deployed agents.
4. **Research:** Choose one provider (`Tavily` preferred for separable source records, or Grok native web search as fallback). Record `source_url`, what was actually found, `evidence_type`, retrieval timestamp, uncertainty. Search snippets and reviews are not verified truth.
5. **Risk taxonomy:** `LOWER_RISK`, `HIGHER_RISK`, `INSUFFICIENT_EVIDENCE`; decisions `CONSIDER_BUYING`, `VERIFY_FIRST`, `AVOID`, `NEED_MORE_INFORMATION`. Never claim counterfeit/authenticity certainty or numerical probability without calibrated ground-truth validation.
6. **Prevent prompt injection and SSRF:** webpage/SMS text is data, never system instructions. Do not blindly fetch untrusted URLs or private/internal networks; guard redirects. Do not allow model-suggested arbitrary external API calls.
7. **User privacy:** no full card numbers, CVV, banking login, or personal financial account linkage through SMS. Any wallet feature stores only issuer/product labels or explicit mock cards; no sensitive logging of phone numbers.
8. Secrets in `.env` only and `.env.example` placeholders; do not print secret values or commit them. If APIs are unavailable, build labeled fixtures and preserve executable local unit tests; do not represent fixtures as real sponsor usage.
9. Async webhook: acknowledge quickly only after appropriate validation/deduplication. Prefer an in-process prototype adapter for demo if needed; in-process tasks are non-durable on restart. Add a real queue only when justified.
10. One integration owner merges branches and confirms API contracts. Avoid simultaneous edits to `app/main.py` or shared models without coordination. Leave minimum 30+ min buffer before final upload.

## Candidate directory ownership (adjust to actual existing structure)

The packet-specific ownership table in `docs/OWNERSHIP.md` refines these candidate areas, including test ownership.

- `app/main.py`, `app/api/`, `app/adapters/photon.py`, `app/workflow/`: integration owner / Photon owner
- `app/agents/`, `app/services/grok.py`: Grok owner
- `app/research/`, `app/services/tavily.py`: evidence/research owner
- `app/decision/`, `app/models/`, `tests/`: rules / QA owner

## Definition of done for every task

Report **changed paths**, **actual commands/tests run**, **observed outputs**, **remaining blockers**, **real vs mocked dependencies**, and the **exact integration step**. Never auto-push, deploy, use paid API credits, or submit on the team's behalf without instruction. If external docs are unavailable, label uncertainty rather than fabricate an integration.

## Coordination across coding tools

This is the shared project instruction source for Codex, Claude Code, Cursor, and Copilot. Tool entry files point here; avoid competing copies of project rules. Explicit user instructions take precedence.

- Before implementation, read `docs/OWNERSHIP.md`, your assigned `docs/skills/packet-*.md`, and `docs/AGENT_HANDOFF.md`. Inspect actual files and run `git status --short` before editing.
- Follow the human's explicit packet and writable-path assignment. An existing session assignment is sufficient; do not ask again. Unassigned sessions may inspect and plan without claiming a role.
- Use a separate worktree or checkout and branch per concurrent editing session. Branches in one directory do not isolate edits. Do not switch another session's branch or overwrite its work.
- Preserve tracked AND untracked work. Do not run `git reset`, `git clean`, bulk `git restore`, forced checkout, or delete files to make the status clean without explicit authorization for the exact destructive action. A dirty working tree is not an error to repair.
- D owns shared models; A owns application wiring, dependencies, coordination files, and integration. Request cross-owner changes through a handoff. Only the assigned integration owner merges when instructed.
- Ownership tables in separate checkouts are not distributed locks. The human coordinator communicates assignments and reassignments before concurrent edits.
- Do not spawn additional editing agents unless explicitly requested. Development packets A-D are separate from application runtime agents. The MVP retains one central Grok orchestrator with backend-controlled tools; specialist runtime agents require an explicit scope change.
- Use actual repository setup and test commands once present. Do not claim passing tests or working integrations from proposed paths or fixtures.
- Finish authorized work inside the assignment and report using the handoff template. No automatic push, deployment, paid API calls, or submission.
