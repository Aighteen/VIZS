# AGENTS.md — DubHacks 2026 shopping assistant

> Repository-level instructions for Codex and tools that support `AGENTS.md`. GitHub Copilot also reads `.github/copilot-instructions.md`.

## Mission

Implement **an SMS-first AI shopping decision assistant for fragrance purchases**. Given a product URL and optional price, return an evidence-backed **seller credibility assessment** and actionable shopping decision by SMS. Grok organizes the reasoning; Python executes the policy and arithmetic. **An unknown seller is not automatically fraudulent, and a low price does not prove counterfeit goods.**

**Primary title track proposed:** VISA: Reimagine Shopping. **Sponsored side track proposed:** Photon Messaging Agent. Only humans may finalize/submit track choices.

## Required context, in order

Read `docs/PROJECT_BRIEF.md`, `docs/ARCHITECTURE.md`, `docs/API_CONTRACTS.md`, `docs/IMPLEMENTATION_TASKS.md`, `docs/SPRINT_PLAN.md`, and, near submission, `docs/SUBMISSION_CHECKLIST.md`. If source code exists, inspect it; these docs propose contracts, not proof of completed implementation.

## Priorities and hard limits

- **P0 first:** Photon inbound/outbound SMS, FastAPI webhook adapter, Grok classification, seller research with real source URLs, source/claim validation, deterministic risk decision, concise SMS response.
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

- `app/main.py`, `app/api/`, `app/adapters/photon.py`, `app/workflow/`: integration owner / Photon owner
- `app/agents/`, `app/services/grok.py`: Grok owner
- `app/research/`, `app/services/tavily.py`: evidence/research owner
- `app/decision/`, `app/models/`, `tests/`: rules / QA owner

## Definition of done for every task

Report **changed paths**, **actual commands/tests run**, **observed outputs**, **remaining blockers**, **real vs mocked dependencies**, and the **exact integration step**. Never auto-push, deploy, use paid API credits, or submit on the team's behalf without instruction. If external docs are unavailable, label uncertainty rather than fabricate an integration.

## Coordination across coding tools

This file is the shared project instruction source for Codex, Claude Code, Cursor, and Copilot. Tool entry files must point here rather than maintain competing project rules. Explicit user instructions take precedence; report conflicts between repository documents before dependent work.

- Before implementation, read `docs/OWNERSHIP.md`, your assigned `docs/skills/packet-*.md`, and `docs/AGENT_HANDOFF.md`. Inspect actual code and `git status --short`; proposed paths are not proof of implementation.
- A human assigns a packet and exact writable paths to each session. An unassigned session may inspect and plan; it must not claim a role or start unrelated implementation. An existing explicit session assignment is sufficient; do not ask again.
- Use one branch and separate worktree/checkout per concurrent editing session. Branches in one directory do not isolate edits. Do not switch another session's branch, overwrite its work, reset its changes, or resolve its conflicts without coordination.
- `docs/OWNERSHIP.md` refines the candidate ownership above, including per-packet test ownership. D owns shared models; A owns wiring and merges. Request contract changes through a handoff rather than editing another owner's files.
- Keep shared coordination files under A's control after initial setup; report proposed updates in your handoff. Never assume ownership edits in one worktree are visible in another; the human coordinator communicates active assignments.
- Do not spawn additional editing agents unless explicitly requested. These are development roles, not a deployed multi-agent architecture.
- Use the repository's actual dependency manifest and test commands once present. Until then, report setup/testing as unavailable; do not claim a passing test suite.
- Complete authorized work inside your assignment, then provide `docs/AGENT_HANDOFF.md`'s report. Do not auto-push, merge, deploy, spend API credits, or submit without the applicable instruction.
