# Task State

<!-- Claude maintains this file during the session.
     Update it after every significant step so the state survives compaction.
     The compaction_save.ps1 hook timestamps each compaction automatically. -->

## Current task
T1 (repo scaffold) done 2026-10-15. Next: T2 (Foundry spike, needs Azure enabled) and T3 (simulator) side by side.

## Done
- [x] Registered for the hackathon (2026-10-14), confirmation email received
- [x] IDEA.md one-pager (idea-refine skill)
- [x] SPEC.md, requirements.md, tasks/plan.md, tasks/todo.md, CLAUDE.md, hooks, .claude/settings.json
- [x] Access email received 2026-10-15; B2B Connect terms (docs/document.md) and Event Confidentiality Agreement accepted; rules recorded in CLAUDE.md

- [x] 2026-10-15: Innovation Studio profile + registration done; project "Matchday Companion" created (project 126542), minimal public text, not open to join, Gemini-generated cover image (docs/assets/thumbnail.jpg)
- [x] 2026-10-15: competition scan (docs/private/competition.md, gitignored) -> voice-first pivot written into SPEC.md, IDEA.md, tasks/todo.md
- [x] 2026-10-15: T1 repo scaffold: app/{simulator,ledger,agents,api} packages, requirements.txt, .env.example, tests/test_placeholder.py (5 pass), .venv (3.11), git init on `main`, private repo ogu83/inside-the-game-hackathon. docs/document.{md,pdf} gitignored (agreement text stays local).

## Next step
T2 (Foundry spike) once `az account show` is Enabled; T3 (simulator) can start now, it needs no Azure.

## Blockers / open decisions
- Azure "Azure subscription 1" is Disabled because of a past-due balance: invoice G176399317 ($63.96, July 2026, "Auto pay failed"). Default card MasterCard ending 2728 is active (exp 11/2029), so the charge was likely declined by the bank. Oguz paid it on 2026-10-15; reactivation can take up to 24 h. Before T2: re-run `az login` (CLI token refresh failed with a provider/account-hint mismatch) and confirm `az account show` state is Enabled. SPEC approved 2026-10-15.
- Innovation Studio invite pending (~2026-10-16)
- Hosted agents (Foundry Agent Service) vs in-container agents: decide in T2

## Notes
- Deadline 2026-10-27 23:59 PT; internal target 2026-10-26
- Fictional league only; no StatsBomb data; no trademarks in video
