# Review 2026-10-15: what wins a category, what loses it

Reviewer: cloud session (frontier-model review), 12 days before the deadline, 11 build days left for one person.
Scope: IDEA.md, SPEC.md, tasks/plan.md, tasks/todo.md, docs/demo-script.md, and the S1/S2 code in `app/simulator` and `app/ledger`.
Question asked of everything: does this raise or lower the chance of placing in Best Use of Microsoft Foundry (primary) or Best Multi-Agent System (secondary)?

Legend: **[Proposal]** means the recommendation changes a SPEC.md interface, boundary or success criterion and needs Oguz's approval; SPEC.md was not edited. **[Done]** means this session applied it. Everything else is a plan or code recommendation.

## Headline verdict

The concept is strong and well differentiated: a spoken co-commentator you can interrupt, whose every number is checked by code before it is spoken, with Foundry tracing and evaluation as the proof. The walking-skeleton plan is the right shape. Three things could lose a category and are cheap to fix now: (1) the Analyst's 60 s window contradicts the 10 s broadcast delay, so most cues would be dropped as late; (2) the judge path as specified cannot work for a judge, because keyless auth needs an identity inside Oguz's tenant; (3) the Foundry evaluation, the single most category-specific proof point, is scheduled last and depends on everything else. Below, ranked by impact.

## 1. Analyst window versus broadcast delay (would break criterion 3 and scene 2)

SPEC.md:57 (rule 1) shows the match `BROADCAST_DELAY_S` = 10 s behind the event stream and drops any cue not ready when its moment plays. SPEC.md:60 (rule 3) runs the Analyst once per 60 s window over the batch of moments. A moment that closes at second 5 of a window waits up to 55 s for the Analyst, then 6 to 9 s for Commentator, Fact-Checker and Producer (SPEC.md:184). It is ready about a minute after its moment aired and is dropped. Criterion 3 (SPEC.md:262, 90% ready before display) is unreachable with these defaults, and scene 2 of the demo (docs/demo-script.md:12) claims the opposite.

Recommendation **[Proposal]**: make the director decision per moment, not per batch. The Analyst is called when a moment closes and returns `say | skip` plus an angle, with pacing state passed in (seconds since the last spoken cue, cues in the last 2 minutes). Pacing then needs no waiting. Set `BROADCAST_DELAY_S` default to 20 s to leave headroom for one retry. If a batch director is kept, the window must be at most `BROADCAST_DELAY_S - 10 s`. Add a `DirectorDecision` model to the Interfaces (see section 7).

Related: criterion 1 (SPEC.md:260) runs at 30x and criterion 3 at 1x. At 30x, 10 s of match time is 0.3 s of wall time, so live agents can never be ready. Define that speeds above 1x run in **precomputed mode**: the whole match is processed first (verdicts, cues, narratives recorded), then played back on the delayed clock. Live mode (agents racing the clock) is for 1x and the video. This also gives the evaluation (section 3) and the planted-error harness a deterministic, replayable input, and it is what the S4 API implements: `precompute=true` by default, live mode when agents are attached.

## 2. The judge path cannot work as written (criterion 6)

SPEC.md:265 (criterion 6) says `docker compose up --build` runs the full demo with only `.env` filled in. All model calls use keyless `DefaultAzureCredential` (SPEC.md:13), which needs an Azure identity with the Foundry User role on Oguz's project. A judge has no such identity, so the compose path fails at the first agent call. Rules 4.8 require a working project available to judges for free until judging ends.

Recommendations:
- **[Proposal]** Promote the public Azure Container App URL from Should to Must in SPEC.md:51 and tasks/plan.md:43. The container runs with a managed identity that holds Foundry User, so judges need nothing. Keep it on the smallest plan with scale-to-zero off during judging (Oct 27 to Nov 10).
- **[Proposal]** Reword criterion 6: `docker compose up --build` from a clean clone runs the demo in **offline mode** (template agents: deterministic Commentator and Producer that fill fixed sentences from the ledger evidence) with no Azure at all; with `.env` filled in and an Azure login it runs the live agents. **[Done]** S3 ships `TemplateCommentator`, `TemplateProducer` and `AlwaysVerifies` wording judge in `app/agents/fakes.py`; S4 uses them when no model is configured. Offline mode is also the recording fallback if a 429 or quota problem hits during the video.
- Add a judge section to the README: public URL, what to click in 60 seconds, and the compose path.

## 3. Pull the Foundry evaluation forward; it is the category proof point

Criterion 8 (SPEC.md:267) and demo scene 6 (docs/demo-script.md:16) carry the Foundry story: Groundedness with the Fact-Checker on versus off, plus planted errors caught. Every entry will have Foundry models and traces. Few will have a cloud evaluation that measures their own safety layer. In tasks/todo.md:107 T10b starts only after T10 (all four agents, hosted deployment, recap), on Oct 21 to 23 at best. If T10 slips, the Foundry category is left with "we used the models".

Recommendations:
- Start T10b right after S3: the evaluation needs `query` (moment evidence), `context` (evidence), `response` (claim + why_it_matters) and a label (verified or rejected). S3 already produces those. Record 3 seeded matches through the S3 workflow with the live agents (local session, about 75 Commentator calls), export JSONL, submit one Groundedness evaluation, poll it. Half a day, and it removes the biggest category risk. **[Done]** `app/agents/run_match.py` writes one JSONL row per moment (evidence, insight, verdict, number checks) so the export exists from S3.
- Define the two eval conditions precisely: "on" = only `verified`/`rewritten` insights; "off" = every attempt-1 insight before the Fact-Checker, including rejected ones. Keep the same moments in both so the comparison is paired.
- Decide now which built-in evaluators run: Groundedness (claims vs evidence) is the headline; Task Adherence is cheap to add; Intent Resolution does not fit a commentary task, drop it.
- Show the evaluation result page in the Foundry portal in scene 6, not only a table in the README; judges score what they see.

## 4. Real-world impact is 20% and the demo never states it

docs/demo-script.md:11-17: the voiceover explains what the system does but never who needs it or why. Judging criterion 3 (requirements.md:41) is real-world impact and applicability.

Recommendation: one sentence in scene 1 or 7, for example: "Broadcasters cannot put an AI voice on air if it invents a statistic. This is the trust layer that makes live AI commentary and second-screen personalisation possible, in any language." Add an "Impact" paragraph to the README with the same three points: broadcaster trust, accessibility for fans in other languages, lower cost of per-fan commentary. Map the five pipeline stages the rules name (ingest, interpret, explain, render, personalise) to modules in one table; it is a free category-adherence point.

## 5. Demo mechanics that can sink the UX score

- **Not enough moments in 2 minutes at 1x.** S2 yields 17 to 26 pass_streak moments per 90 minutes, one every 3.5 to 5 minutes. Scenes 1 to 4 need 3 to 4 cues in 70 seconds. Either record at 3x to 4x (the delayed clock keeps working because the delay is in match seconds), choose a seed with a dense opening, or cut between moments. Add `--speed` to the recording checklist (docs/demo-script.md:23). **[Done]** S4 takes `speed` and `delay_s` on `POST /api/match/start`.
- **Turkish audio in an English-only submission.** Rules 4.8 require all materials in English. Scene 3 speaks Turkish. Keep it (it is the personalisation proof) but burn in English captions for every Turkish line and keep the on-screen UI in English. Add to the recording checklist.
- **Scene 2 claims four agents but shows a ticker.** Show the agent timeline for one moment (Analyst say/skip, Commentator attempt, Fact-Checker layer and verdict, Producer per profile) in a compact drawer instead of the event ticker. The ticker proves nothing a judge scores; the timeline proves multi-agent orchestration for the secondary category.
- **Profile switch must re-render immediately.** Scene 3 says "the next narrative changes". At one moment every 4 minutes that is a long wait on camera. On profile change, re-render the most recent verified insight for the new profile right away, then continue. Note it in T9/T11.
- **Scene 6 shows two portal screens in 18 s.** Pre-record both as video clips; do not click live.
- **Record app audio and voiceover separately** and mix; otherwise the co-commentator and Oguz talk over each other in scene 1.

## 6. Scope versus 11 days: what to cut before it cuts you

Phase B (tasks/plan.md:65-72) packs ten tasks into Oct 19 to 23, including a full simulator, four detectors, four agents, hosted deployment, cloud evaluation, SVG pitch, voice barge-in and an MCP server. For one person that is 2 to 3 days over. Suggested cuts, in order:

1. **T3 (tasks/todo.md:67)**: drop "4 clubs" and set pieces; the demo shows one match. Two clubs, substitutions and goals are enough. Remove Duneport and Ashgrove from docs/demo-script.md:5.
2. **T6 (tasks/todo.md:82)**: two detectors are enough on screen: pass_streak (done) and pressing_trap (a different kind of story). Player-level numbers belong in ledger queries (MCP tools, T12b) rather than a `player_milestone` detector; that is what "how is my player doing?" needs.
3. **T10 hosted deployment**: timebox to half a day. T2 already proved it and the video records the in-process run. If it fights back, show the T2 hosted agent in the portal and move on.
4. **T12b**: build the ledger MCP server and the text Q&A agent first (both run in a cloud session with fake models), so only the audio plumbing is left for the local session. Push-to-talk only; open mic is a stretch.
5. **T12 SVG pitch**: ball dot and cues only; player dots are a Should. Note that events are in the acting team's frame (app/simulator/models.py:13), so the UI needs a `to_pitch_frame(event, home_id)` flip for the away team.

What not to cut: the evaluation (section 3), the planted-error drawer (scene 5), the public URL (section 2), the Turkish voice line (scene 3).

## 7. SPEC.md gaps and errors

- **[Proposal] Names for the Commentator.** `CandidateMoment.evidence` is `dict[str, float]` (SPEC.md:91) and `team_id` is `kby`. The Commentator must write "Kestrel Bay" and player names, so the prompt needs labels. Options: add `labels: dict[str, str]` to `CandidateMoment` (team_name, player names) or resolve from `app.simulator.league` in the agents layer. S3 resolves names in the agents layer (`app/agents/prompts.py`) so the interface is unchanged for now; if Oguz prefers labels on the moment, that is a one-line model change plus S2 detector update.
- **[Proposal] Player-level evidence for "your player".** pass_streak evidence has no player keys, so a `FanNarrative` focused on the fan's favourite player cannot cite a number about them. Add `top_player_id` (as a label) and `top_player_passes` to the pass_streak evidence, and define that the Producer may only mention the fan's player when the moment or a ledger query has a number for them.
- **[Proposal] `DirectorDecision` model** (see section 1): `moment_id`, `say: bool`, `angle: str | None`, `reason: str`. Without it the Analyst has no contract and T7 will invent one.
- **[Proposal] Q&A and speech contracts**: `Question(profile_key, transcript, asked_at_seq)`, `Answer(question_id, text, evidence_refs, tool_calls)`, and the speech gate as `SpeechAudit(approved_text, transcript, ok, mismatches)`. The NumberCheck gate Literal (SPEC.md:110) already covers speech; the comparison contract is missing.
- **`profile_key` is undefined** (SPEC.md:135). **[Done]** S3 defines it as `f"{club_id or '-'}|{player_id or '-'}|{depth}|{language}"` on `FanProfile.key()`; add the one-liner to SPEC.md when approving.
- **Rounding rule is underspecified** (SPEC.md:58 "after rounding and unit normalisation"). **[Done]** S3 implements: a number in text matches a cited value when the value, rounded half-up to the text's number of decimals, equals the text number; seconds-valued keys (`*_s`) also match in minutes; percent markers are ignored for matching. Qualified approximations ("over 50 metres" against 52.5) fail by design; the prompts ask for exact ledger numbers. If Oguz wants approximations allowed, that is a rule change, not a parser change.
- **Digits-only rule has two necessary exceptions**: "one" and "bir" are articles and pronouns in both languages ("one-way traffic", "bir pas"). **[Done]** The parser flags every other number word in en and tr and lists them in `mismatches` as `number written as word: ...`. Ordinal words ("second half", "ikinci yarı") are not flagged.
- **Commands are Windows-only** (SPEC.md:188-206). Add the Linux lines (`python3 -m venv .venv && . .venv/bin/activate`) since the cloud session and the container both run Linux.
- **requirements.txt lacks the API stack** although SPEC.md:150 and the run commands use FastAPI, uvicorn and sse-starlette. **[Done]** Added in S4.
- The README should pre-empt the obvious question "if code checks the numbers, why an LLM Fact-Checker?": numbers are facts, wording is judgment ("dominated", "one-way"); the code layer makes the number guarantee absolute, the model layer keeps the wording honest, and the Groundedness evaluation measures both together.

## 8. Code review: `app/simulator` (S1)

Overall: compact, deterministic, readable; the phase model produces plausible text and the stat ranges in tests/simulator/test_simulator.py:48-61 are the right kind of guard. Findings:

- **app/simulator/engine.py:184** `half = minutes * 30`: correct (seconds per half) but reads like a bug. Name it `half_seconds = minutes * 60 // 2`.
- **app/simulator/engine.py:120-121** after a saved shot, `_change_possession` already sets `phase` to `build_up` for x = 6; line 121 is redundant. Remove it.
- **app/simulator/engine.py:139-142** a foul adds dead time but play resumes with the fouled team at the same spot with no restart event. Acceptable for S1; in T3 emit a `pass` from a standing position or a `set_piece` meta so the ticker can show it.
- **app/simulator/engine.py:130** pressing intensity is a constant per zone. For a `pressing_trap` detector (T6) to fire, add a per-club pressing trait so one club presses more; otherwise the detector finds nothing distinctive.
- **app/simulator/engine.py:95** kickoff always picks the first `ST`; fine. `substitution` is in the event Literal (app/simulator/models.py:5-9) but never emitted; squads already have subs (app/simulator/league.py:60,67). T3.
- **app/simulator/models.py:13** the per-team coordinate frame is a good choice for the engine but must be documented for the UI and the dataset export (T4 README: "x, y are in the acting team's frame").
- **app/simulator/league.py:41-47** the shirt-number list is longer than the formation and is indexed by position in the names list; it works because both lists are the same length. A `zip(strict=True)` would catch a future mismatch.
- Names: all invented, none matches a well-known footballer. Keep a one-line note in the README that names were generated and any resemblance is accidental.
- Tests: good. Missing: a test that `goal` events increment the `half_time`/`full_time` meta score, and a test that no event has `x`/`y` outside the clamp with `end_x` beyond 100 (shots use `end=(100.0, ...)`, fine, but `clamp` is not applied to `end`).

## 9. Code review: `app/ledger` (S2)

Overall: the detector protocol (`on_event(event, history)`) is simple and testable; the evidence dict is exactly what the Fact-Checker needs. Findings:

- **app/ledger/moments.py:50-51** `team_possession_pct_window` is 100.0 at minute 0 with `window_minutes` 0.9 (seed 7, first moment). A cue saying "100% possession" at kickoff looks broken on camera. Omit the possession keys when `window_minutes < 3`, or the Commentator prompt must be told to prefer streak facts early. The S3 template Commentator avoids the possession sentence when the window is short.
- **app/ledger/metrics.py:13-18** `possession_pct` is pass-attempt share. That is the standard broadcast method (pass-count based), so it is defensible, but say so in the README and in the MCP tool description so a football-literate judge does not call it wrong.
- **app/ledger/moments.py:48** `pass_streak_progress_m` is start of first pass to end of last pass in the team's frame; negative values are possible when a streak retreats. Fine, but the Commentator prompt should say "progress can be negative, meaning the team moved backwards".
- **app/ledger/moments.py:49** `pass_streak_ended_in_shot` as 1.0/0.0 is a boolean in a float dict. It lets a Commentator legitimately write "1" or "0", which the number check will accept. Harmless now; when evidence grows, consider a `flags: dict[str, bool]` field so booleans never masquerade as citable numbers.
- **app/ledger/moments.py:36** `in_window(history, ...)` scans the whole history per moment: O(n) with n about 1,900, fine. If T5 adds rolling metrics per event, keep a deque instead.
- **app/ledger/state.py:14** `detectors: list` is untyped; use `list[PassStreakDetector]` or a `Detector` Protocol so T6 detectors share a contract.
- **app/ledger/models.py:4** `CandidateMoment` lives in `ledger` while SPEC.md:84 lists it under "ledger -> agents"; consistent. S3 puts the agent-side models (`Insight`, `Verdict`, `NumberCheck`, `OverlayCue`, `FanProfile`, `FanNarrative`) in `app/agents/models.py`.
- Tests: good coverage of the streak rules. Missing: a seeded test that moments are sorted by `window[1]` and never overlap, which the API relies on for `show_at_seq`.

## 10. Housekeeping

- `.claude/settings.json` hard-codes `C:/Users/oguz/...`. Use `$CLAUDE_PROJECT_DIR/.hooks/...` so the hooks work in any checkout that has `pwsh`.
- "Premier League" appears only as the hackathon's name in internal docs. Keep it that way in the README (naming the event is fine); no league or club marks in the UI or video.
- The Innovation Studio project id and the competition-scan framing are already on the T16 removal list; good.
- Before going public, also remove the Gemini mention for the thumbnail from task_state.md or confirm the image licence allows commercial use (Microsoft takes a commercial licence to the submission).

## Decisions requested from Oguz (all [Proposal])

1. Director per moment with pacing state, delay default 20 s, precomputed mode above 1x (section 1).
2. Public Container App URL becomes Must; criterion 6 becomes "offline mode without Azure, live mode with `.env`" (section 2).
3. Interfaces: `DirectorDecision`, Q&A and speech contracts, `profile_key` definition, optional `labels` and `top_player_*` on `CandidateMoment` (section 7).
4. Scope cuts in section 6 (2 clubs, 2 detectors, hosted agent timeboxed).

## Applied in this session

- S3 and S4 implemented as described in task_state.md and tasks/todo.md, with the offline template agents, the JSONL run log for the evaluation export, and `speed`/`delay_s` on match start.
- tasks/todo.md: T10b gets a note that it can start from S3 outputs; S4 acceptance gains the precompute note. No SPEC.md edits.
