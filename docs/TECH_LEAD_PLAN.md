# Tech lead implementation plan

Human requested separate worktrees, delegated agents and completion of the agreed two-channel scope. Root coordinates the local release and integration; no pushes, deployments, store publishing, paid API calls or outbound messages without further instruction. Existing dirty original and packet checkouts are preserved. New worktrees share a scope/test-plan baseline commit.

## Assignments and exclusive paths

| Session | Worktree / branch | Owned implementation |
|---|---|---|
| Root A | C:\Github\VIZS-packet-a / feat/packet-a-integration | app/main.py, app/config.py, app/api/, app/workflow/, app/adapters/, A tests, manifests, shared docs; merges/review |
| Promise contracts/policy | C:\Github\VIZS-promises / feat/promise-contracts | app/models/, app/decision/, tests/test_contracts.py, tests/test_policy.py, tests/test_sms.py, tests/fixtures/, tests/test_e2e.py, docs/API_CONTRACTS.md |
| Research/extraction | C:\Github\VIZS-research / feat/promise-research | app/research/, app/services/tavily.py, app/services/grok.py, app/agents/, tests/test_research.py, tests/test_url_safety.py, tests/test_grok.py |
| Pet extension | C:\Github\VIZS-extension / feat/pet-extension | extension/ including assets/tests/docs/package configuration |

## Common agent prompt

Read AGENTS.md, required project context, CREDIBILITY_CHECKING.md, EXTENSION_SCOPE.md, ACCEPTANCE_TESTS.md, OWNERSHIP.md and AGENT_HANDOFF.md. Inspect git status and actual code. Use only the assigned checkout and named paths. Plan before editing. Preserve other work. Confirm official docs for provider/browser behavior; no paid calls, deployment, pushes or sending messages. Do not spawn agents. Run meaningful focused offline tests. Make local commits of owned paths only; report hashes and exact root integration steps. Send interface decisions early and coordinate changes through root. Shared installed Python test interpreter: C:\Github\VIZS\.venv\Scripts\python.exe. Always set workdir explicitly.

## Contract gate and integration

Promise agent establishes and commits bounded Pydantic contracts/fixtures first; root reviews/distributes the gate before research relies on it. Preserve old models/clients and seller risk rules. Extension consumes documented assessment JSON and uses fixtures until live integration. Root wires research/extraction/policy, implements paired-token extension API and bounded access, and reproducible Photon launch/stop; then merges named local branches in dependency order. Tests and handoff document actual vs mocked behavior. No new frontend frameworks required: code-native mascot and standard extension files preferred. No fake progress, paid call retries, unverified authenticity confidence or page-wide scraping.

## Status at `62f1ac8` (Oct 17)

Merged to `main`: promise contracts/fixtures, research/extraction (Tavily Extract, Grok promise rows, RDAP), root A wiring, paired-token extension API with bounded access. 159 Python tests pass. Not merged or pushed: the pet extension (`feat/pet-extension` is not on the remote) and a reproducible Photon launcher. Remote branches are `main`, `feat/packet-a-integration` (older, at `f5af5ba`) and two Copilot planning branches. Windows worktree paths above refer to the original machine.

## Definition of complete for this build

Locally installable Chrome pet extension, functional protected local backend with quote-validated promise sheet, both channel formatters, reproducible bounded Photon launcher, meaningful automated regression and future-reference acceptance matrix. Domain registration is context only; unsupported image matching/AI-photo detection must explicitly remain unavailable. Public hosting/store installation/live new channel tests require external verification and are reported honestly, not fabricated. Payments/training/dispute platform remains excluded.
