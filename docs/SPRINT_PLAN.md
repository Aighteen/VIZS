# Sprint plan — Saturday Oct 17 to Sunday Oct 18, 2026 (PDT)

Current scope update: both Photon messaging and the Chrome extension with an animated on-page pet are core channels. Read EXTENSION_SCOPE.md and NEXT_STEPS.md for the current critical path. The timeline below is the original SMS-first plan, not a fresh schedule or proof of completion. Event deadlines, coding-window constraints and upload buffers remain unchanged. Limit the new UI to the minimal pet/result flow; do not let optional pet cosmetics or unrelated work consume the submission buffer.


**Status at 8:50 PM Saturday:** backend, promise sheet and extension route merged; extension UI and Photon launcher not built. The 9:30 PM freeze-concept and 10:00 PM draft targets below are next. Overnight: extension against fixtures, launcher, then authorized live runs before the 7:30 AM freeze.

**Time source:** organizers' Hacker Guide. Adjust remaining work to actual current time; never miss submission to finish a feature.

## Absolute deadlines

- **Saturday 10:30 PM:** **mandatory initial Devpost draft** (submit earlier; designate an owner; include team/track information required by Devpost).
- **Sunday 10:00 AM:** **final Devpost**, including uploaded public repository link and demonstration video. Aim for completion by 9:15–9:30 AM; reserve emergency buffer.
- Saturday coding commenced in permitted window from **12:30 PM**; only hackathon-window work should be submitted.

## Milestones and go/no-go gates

| Target PDT | Work | Gate / fallback |
|---|---|---|
| Sat 5:30 PM | Confirm MVP, title track and Photon candidate; lock contract and owners | If Photon docs inaccessible, build debug API while another teammate pursues access |
| Sat 6:15 PM | FastAPI local endpoint returns a Pydantic `Assessment` from a labeled test fixture | If not, cut optional components |
| Sat 7:30 PM | Grok + chosen research provider return typed findings, URL citations; policy evaluates them | If API not working, diagnose provider independently; maintain local mock for QA only |
| Sat 8:30 PM | Photon inbound/outbound proof or documented access blocker; one end-to-end live attempt | If Photon blocked, do not claim sponsor fit; consider safe alternative demonstrable path |
| Sat 9:30 PM | Freeze demo concept, review tracks, repository link, Devpost inputs, backup video plan | Submit mandatory draft early (target 10:00 PM) |
| **Sat 10:30 PM** | **MANDATORY Devpost draft due** | Never let last feature delay it |
| Sat 11 PM–Sun 5:30 AM | Stabilize and improve evidence/error cases; stagger team rests | No infrastructure rewrites for optional features |
| Sun 5:30 AM | Decision on P1 — only if all P0 live tests pass | Otherwise fix live loop and sources |
| Sun 7:30 AM | Feature freeze; test good and insufficient-evidence examples; prepare evidence | Only bugfixes after this |
| Sun 8:30 AM | Record and verify demo video; README instructions and sponsor proof; public code committed | If live services fail, use recorded *real* execution; mock explicitly labeled |
| Sun 9:15 AM | **Target final submit**, verify actual Devpost receipt and repo accessible | Buffer until official 10:00 AM deadline |
| **Sun 10:00 AM** | **FINAL hard deadline** | No late additions |

## Team accountability

- **Integration + Devpost owner:** `TBD` — owns merges, API contract, deployment, submissions, video check.
- **Photon owner:** `TBD` — beta account, verified webhook, send SMS and log evidence.
- **Grok / research owner:** `TBD` — model, provider, citations.
- **Rules + QA owner:** `TBD` — deterministic mapping, tests, safety and demo narrative.

## One-hour standup format

- What actually works **live**? What only works as a **mock**?
- Did our latest working commit pass tests?
- What is the blocker with the highest time-to-demo impact?
- Which P1 feature can we drop right now?
- Is Devpost draft/final information already saved?

**Golden rule:** a real narrow product beats a sophisticated architecture that can't receive and send one message.
