# Task State

<!-- Claude maintains this file during the session.
     Update it after every significant step so the state survives compaction.
     The compaction_save.ps1 hook timestamps each compaction automatically. -->

## Current task
T2 done 2026-10-15. Plan revised the same day after review (walking skeleton first). Next: D1 (demo script), then S1 to S5.

## Done
- [x] Registered for the hackathon (2026-10-14), confirmation email received
- [x] IDEA.md one-pager (idea-refine skill)
- [x] SPEC.md, requirements.md, tasks/plan.md, tasks/todo.md, CLAUDE.md, hooks, .claude/settings.json
- [x] Access email received 2026-10-15; B2B Connect terms (docs/document.md) and Event Confidentiality Agreement accepted; rules recorded in CLAUDE.md

- [x] 2026-10-15: Innovation Studio profile + registration done; project "Matchday Companion" created (project 126542), minimal public text, not open to join, Gemini-generated cover image (docs/assets/thumbnail.jpg)
- [x] 2026-10-15: competition scan (docs/private/competition.md, gitignored) -> voice-first pivot written into SPEC.md, IDEA.md, tasks/todo.md
- [x] 2026-10-15: T1 repo scaffold: app/{simulator,ledger,agents,api} packages, requirements.txt, .env.example, tests/test_placeholder.py (5 pass), .venv (3.11), git init on `main`, private repo ogu83/inside-the-game-hackathon. docs/document.{md,pdf} gitignored (agreement text stays local).
- [x] 2026-10-15: T2 Foundry spike: eastus2 rg-matchday with Foundry resource + project `matchday`, Foundry User role, App Insights linked, $50/month budget alert (`hackathon-monthly`). gpt-5.4-mini deployed. Local 2-agent workflow with reject edge, same workflow deployed as hosted agent `t2-spike` via azd and invoked remotely, spans in App Insights, Voice Live hello world (cancel ~0.4 s). Findings + pins in SPEC.md.
- [x] 2026-10-15: post-T2 review applied: SPEC.md (pitch line, pipeline design rules: broadcast delay, two-layer Fact-Checker, Analyst as director, ledger over MCP, parallel Producer; Verdict gains layer/attempt; criteria 3, 8, 10 revised/added), tasks/plan.md rewritten with Must/Should/Cut table, tasks/todo.md reordered (D1, S1-S5 skeleton), IDEA.md annotated.
- [x] 2026-10-15: second review applied: number check at every gate (insight, Producer incl. Turkish, speech) with en/tr parser and `NumberCheck` records; voice speaks only approved text via Voice Live `pre_generated_assistant_message` (verified verbatim in en and tr), speech transcript audit; planted errors at the translation step; T16 adds tenant ID and Foundry resource name cleanup.

## Next step
D1 demo script, then walking skeleton S1 (thin simulator) to S5 (thin voice) by Oct 19. Then deepen T3 to T12b. T7+ use `FOUNDRY_PROJECT_ENDPOINT` from .env (local, gitignored) and `az login --tenant ...`; azd reuses the az login.

## Blockers / open decisions
- Azure: subscription is **Enabled** again (2026-10-15). CLI login needs `az login --tenant 09c5e5e8-d9dd-4923-bbf2-9749f2e8082c` (MFA; plain `az login` skips the tenant). Ignore the "Microsoft" tenant (hackathon B2B guest). Budget alert set 2026-10-15. Still open: find what drove the July bill (Portal > Cost analysis, Jun-Jul by service). SPEC approved 2026-10-15.
- Innovation Studio submission form fields still to be noted in requirements.md
- Pre-publish (T16): squash to fresh history before going public (c28e1c0 has billing details) and remove text from entrants-only hackathon pages; checklist in tasks/todo.md T16
- Hosted agent confirmed in T2 (see SPEC.md). Frontier quota: gpt-5.5 has 0 quota in eastus2; Oguz to file a quota request. Until then FRONTIER_MODEL_DEPLOYMENT=gpt-5.4-mini.
- Trace screenshot from the Foundry portal Tracing tab: Oguz, manual.

## Notes
- Deadline 2026-10-27 23:59 PT; internal target 2026-10-26
- Fictional league only; no StatsBomb data; no trademarks in video
