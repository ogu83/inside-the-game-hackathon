# PROJECT DOSSIER: Matchday Companion

## README.md (current)
# Matchday Companion

A live co-commentator you can interrupt, and that can't lie: every number it says is checked against the match data before it is spoken.

Entry for the Microsoft + Premier League "Inside the Game: Developer Hackathon" (category: Best Use of Microsoft Foundry). Built on Microsoft Foundry models, Microsoft Agent Framework, Foundry Voice Live and MCP. Everything in this repository is fictional: the Meridian League, its clubs and its players are invented, and any resemblance to real people is accidental.

This README is a work in progress until submission; see [SPEC.md](SPEC.md) for the design and [tasks/plan.md](tasks/plan.md) for the plan.

## Quick start

```
python3 -m venv .venv && . .venv/bin/activate      # Windows: py -3.11 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests/ -q                          # no model calls
python -m uvicorn app.api.main:app --port 8010      # open http://localhost:8010, offline agents unless AGENT_MODE=foundry
```

## Synthetic match dataset

The simulator (`app/simulator`) generates a full 90-minute match of the fictional Meridian League from a seed. Same seed, same match. Three sample matches are committed under `data/` and can be regenerated with `python -m app.simulator.export --seed <seed>`:

| File | Seed | Note |
| --- | --- | --- |
| `data/match_7.jsonl` | 7 | development default |
| `data/match_30.jsonl` | 30 | demo seed: three notable moments in the first five minutes |
| `data/match_42.jsonl` | 42 | |

Each line is one `MatchEvent` as JSON (schema in `app/simulator/models.py`):

| Field | Type | Meaning |
| --- | --- | --- |
| `match_id` | string | `<home>-<away>-<seed>`, e.g. `kby-iva-30` |
| `seq` | int | strictly increasing per match, starts at 1 |
| `minute`, `second` | int | match clock since kickoff; the second half starts at 45:00, no added time |
| `type` | string | `pass`, `shot`, `tackle`, `interception`, `pressure`, `possession_change`, `substitution`, `foul`, `goal`, `kickoff`, `half_time`, `full_time` |
| `team_id` | string | acting club: `kby` Kestrel Bay FC, `iva` Ironvale Athletic |
| `player_id` | string or absent | `<club>-<shirt number>`, e.g. `kby-07`; absent for `half_time` and `full_time` |
| `x`, `y` | float 0-100 | position in the **acting team's frame**: that team always attacks from x = 0 towards x = 100, y = 0 is its right touchline. To draw both teams on one pitch, mirror the away team: `(100 - x, 100 - y)` |
| `end_x`, `end_y` | float or absent | where a pass or shot ended, same frame |
| `outcome` | `success`, `fail` or absent | pass completed or not, shot scored or not, tackle or interception won |
| `meta` | object | per type: `pass_length_m`, `phase` (`build_up`, `transition`), `pressured` (`yes`/`no`), `restart` (`free_kick`) for passes; `xg`, `speed_kmh`, `distance_m` for shots; `player_off`, `player_on`, `position` for substitutions; `home_goals`, `away_goals` on `half_time` and `full_time` |

Notes for analysts: possession is computed as pass-attempt share (the common broadcast method), pitch dimensions are 105 m by 68 m, and `pressure` events are emitted by the defending club at the ball carrier's mirrored position. No real match data was used; the event schema is our own and the data is generated.

## Licence of the data

Generated, fictional, and part of this repository's submission. No third-party data.


## Demo video script (docs/demo-script.md)
# Demo Script: Matchday Companion (under 2 minutes)

Pitch: **a live co-commentator you can interrupt, and that can't lie: every number it says is checked against the match data before it is spoken.**

Rules for the recording: fictional Meridian League only (Kestrel Bay FC vs Ironvale Athletic); no real clubs, players, crests, sponsors or broadcaster branding; no music (or only self-made audio); English narration and on-screen text, English captions burned in for every Turkish spoken line (rules 4.8: all materials in English). Record a local in-process run (`python -m uvicorn app.api.main:app --port 8010`) with a fixed seed at 3x to 4x speed so 3 to 4 cues land in the first 70 seconds (the delay is in match seconds, so the delayed clock still works); warm the hosted agent before showing it. Record app audio and voiceover as separate tracks and mix them, so the co-commentator and Oguz never talk over each other. Voiceover is Oguz; the co-commentator voice is the app.

Every scene maps to a Must item in [tasks/plan.md](../tasks/plan.md). If a scene changes, update the scope table too.

| # | Time | On screen | Voiceover / audio | Must item |
| --- | --- | --- | --- | --- |
| 1 | 0:00-0:10 | Full app: SVG pitch with the ball moving, an overlay cue pops up; the co-commentator voice is heard speaking it. Title: "Matchday Companion" | App voice speaks a verified line (e.g. "Kestrel Bay have strung together 14 passes..."). VO: "This co-commentator is live, you can interrupt it, and it can't lie. Broadcasters cannot put an AI voice on air if it invents a statistic; this is the trust layer." | Pitch + cues, voice, impact sentence |
| 2 | 0:10-0:28 | Broadcast panel close-up: cues appearing on the delayed clock with a small "broadcast delay 20 s" badge; the verdict drawer shows the agent timeline for one moment (Analyst say/skip, Commentator attempt, Fact-Checker layer and verdict, Producer per profile); caption: "synthetic Meridian League feed, about 1,900 events per match, exported as JSONL" | VO: "A synthetic match feed runs through four Microsoft Foundry agents. Like a real broadcast, playback runs a few seconds behind, so every cue is verified before its moment airs." | Pitch + cues on the delayed clock, agent timeline |
| 3 | 0:28-0:46 | Fan panel: switch profile from "Kestrel Bay fan, casual, English" to "Ironvale fan, analyst, Turkish"; the latest moment re-renders immediately in Turkish and the voice speaks it; English caption burned in | App voice speaks Turkish (e.g. "Ironvale son 5 dakikada %62 topa sahip..."). VO: "Same truth, told for you: your club, your player, your depth, your language." | Profile switch en to tr |
| 4 | 0:46-1:06 | Fan presses talk, interrupts mid-sentence: "Why does that matter?" Voice stops at once; answer plays; the trace panel shows the ledger MCP tool call | App voice answers from ledger numbers. VO: "Interrupt it any time. Answers come from the match ledger over MCP, then pass the same checks." | Barge-in + "why?" via MCP |
| 5 | 1:06-1:26 | Debug drawer: a planted false claim ("Ironvale have had six shots") arrives; Fact-Checker layer "code" rejects it: "6 shots does not match the cited shots value (away_shots_last_10min = 0)"; it never reaches the screen or the voice | VO: "Numbers are checked by code, not by another model's opinion: after the Commentator, after every translation, and before every spoken word. Even the voice is audited." | Fact-Checker rejecting a planted claim |
| 6 | 1:26-1:44 | Foundry portal, pre-recorded clips (no live clicking): trace of one moment (Analyst, Commentator, Fact-Checker, Producer spans); then the evaluation result page | VO: "Every step is traced in Foundry. Across three matches: Groundedness with the Fact-Checker on vs off, and X of N planted errors caught, zero reached air." | Foundry trace, eval headline |
| 7 | 1:44-1:58 | Architecture diagram (simulator, ledger, agents, Foundry, Voice Live), repo URL and public URL | VO: "Microsoft Foundry, Agent Framework, Voice Live and MCP. Open source, runs with one command, and live for you to try." | Close |

Total: about 1:58. Trim scene 2 first if long.

## Recording checklist

- [x] Seed chosen: **seed 30** (`DEMO_SEED` in app/simulator/engine.py) gives a 22-pass Ironvale move ending in a shot in minute 1, then Ironvale at minute 3 and Kestrel Bay at minute 4; plant the false claim on one of these (T8); recording speed 3x to 4x (`speed` on match start), delay 20 s
- [ ] Hosted agent invoked once before recording (cold start is about 29 s); offline mode is the fallback if Foundry errors during the take
- [ ] Browser zoom so text is readable at 1080p; mic tested; system notifications off
- [ ] Eval numbers filled in from docs/eval-results.md (scene 6); portal clips pre-recorded
- [ ] English captions on every Turkish line; app audio and voiceover on separate tracks
- [ ] No trademarks visible anywhere: browser bookmarks bar hidden, OS taskbar hidden


## Evaluation results (docs/eval-results.md)
# Evaluation results: Fact-Checker on versus off

Generated 2026-10-16 17:20 UTC by `python -m app.eval.run_eval`. Seeds 7, 30, 42, first 12 moments each, agents live (Foundry), exported 2026-10-16T17:15:18+00:00.

**Headline:** With planted errors, the Fact-Checker kept Groundedness at 4.75 (100% pass) against 3.83 (75% pass) without it, and 0 of 4 planted errors reached air against 4 of 4; in normal play both conditions scored about 4.6 because first drafts were already accurate.

Foundry evaluators (judge model from `SMALL_MODEL_DEPLOYMENT`): Groundedness, Relevance, Coherence, scored 1 to 5 by the service; pass rate is the service's threshold. Our own deterministic metric over the same aired texts: the layer 1 number and actor check, and for the planted conditions how many planted insights reached air.

| Condition | Items | Groundedness mean | pass | Relevance mean | pass | Coherence mean | pass | Layer 1 pass (numbers and actors) | Planted caught / reached air | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fact-Checker on (what aired) | 35 | 4.57 | 100% | 4.49 | 100% | 4.06 | 100% | 100% | no plants | completed |
| Fact-Checker off (first drafts aired) | 35 | 4.60 | 97% | 4.51 | 100% | 4.14 | 100% | 97% | no plants | completed |
| Planted errors, Fact-Checker on | 12 | 4.75 | 100% | 4.50 | 100% | 4.00 | 100% | 100% | 4 / 0 of 4 | completed |
| Planted errors, Fact-Checker off | 12 | 3.83 | 75% | 4.67 | 100% | 4.08 | 100% | 67% | 0 / 4 of 4 | completed |

## Runs

- Fact-Checker on (what aired): eval `eval_7715e42d8fbf4e25867a0248bc0b9bba`, run `evalrun_47c210b2c1ea4ee786d68c8a79bcf699`, status completed [portal](https://ai.azure.com/nextgen/r/dD2eNplVR0O3Y7tFFMlrjQ,rg-matchday,,matchday-foundry-ok,matchday/build/evaluations/eval_7715e42d8fbf4e25867a0248bc0b9bba/run/evalrun_47c210b2c1ea4ee786d68c8a79bcf699)
- Fact-Checker off (first drafts aired): eval `eval_85c5ca41f8984d4ba4337566d4f5f4f4`, run `evalrun_c187d7838852412089c0d40336d962ee`, status completed [portal](https://ai.azure.com/nextgen/r/dD2eNplVR0O3Y7tFFMlrjQ,rg-matchday,,matchday-foundry-ok,matchday/build/evaluations/eval_85c5ca41f8984d4ba4337566d4f5f4f4/run/evalrun_c187d7838852412089c0d40336d962ee)
- Planted errors, Fact-Checker on: eval `eval_fffc023824b64e4a8bd7b5c4f347529f`, run `evalrun_cea904e7398e4bfbb5500244158b342c`, status completed [portal](https://ai.azure.com/nextgen/r/dD2eNplVR0O3Y7tFFMlrjQ,rg-matchday,,matchday-foundry-ok,matchday/build/evaluations/eval_fffc023824b64e4a8bd7b5c4f347529f/run/evalrun_cea904e7398e4bfbb5500244158b342c)
- Planted errors, Fact-Checker off: eval `eval_602530cf9272400c903cc07316dac80e`, run `evalrun_45301bcfe1364fc888eedbefe124d468`, status completed [portal](https://ai.azure.com/nextgen/r/dD2eNplVR0O3Y7tFFMlrjQ,rg-matchday,,matchday-foundry-ok,matchday/build/evaluations/eval_602530cf9272400c903cc07316dac80e/run/evalrun_45301bcfe1364fc888eedbefe124d468)

## Export

Rejected by the Fact-Checker (did not air, so absent from the on conditions): {'7': 0, '30': 0, '42': 0}. Skipped by the director: {'7': 1, '30': 0, '42': 0}. Planted run: {'insight_plants': 4, 'rendering_plants': 22, 'caught': 26, 'reached_air': 0}.

Rejected moments do not air and are therefore not evaluated in the on conditions; the off conditions evaluate every first draft the director let through. Items are the aired text as `response`, a short task as `query`, and the ledger evidence with team and player labels as `context`.

## Latency from traces

Telemetry extracted from Azure Application Insights (`appi-matchday`, operation id `840499343095f9544b921f75c730cf5c` for live moment, `f135de636c7820ee5ce4e810202362fe` for Q&A):

- Moment-to-cue latency (Analyst + Commentator + Fact-Checker + Producer):
  - p50: 13.6 s
  - p90: 14.8 s
  - Share of cues ready before display in live mode at 1x (broadcast delay 20.0 s): 100% (cues ready 5.2 to 6.4 s ahead of broadcast display time).
- Q&A latency (ledger query + answer synthesis + fact check gate):
  - Rule-based ledger Q&A: 3 ms
  - Live Foundry agent Q&A: median 2.8 s (within SPEC success criterion 9 of about 3 s median from press to spoken answer).



## Performance after fixes (docs/performance.md, summary)
st-Optimization)

Measured with token capping (Director: 100, Commentator: 250, Fact-Checker: 250, Cue: 120, Narrative: 180) and analyst depth number inclusion in prompts.

| Moment ID | Minute | Kind | Analyst (s) | Workflow (s) | Producer (s) | Total Time (s) | Status (<20s) | Dropped Profiles |
|---|---|---|---|---|---|---|---|---|
| `kby-iva-30-31-pass_streak` | 1 | pass_streak | 5.89 | 12.50 | 3.36 | 15.86 | ON TIME (4.14s margin) | none |
| `kby-iva-30-69-pass_streak` | 3 | pass_streak | 1.06 | 6.76 | 2.42 | 9.18 | ON TIME (10.82s margin) | none |
| `kby-iva-30-84-pass_streak` | 4 | pass_streak | 1.31 | 6.74 | 2.01 | 8.76 | ON TIME (11.24s margin) | none |
| `kby-iva-30-114-pass_streak` | 6 | pass_streak | 1.44 | 5.84 | 2.15 | 7.99 | ON TIME (12.01s margin) | none |

- **Late Moments:** 0 of 4 (0%, down from 25% isolated and 75% in full live baseline).
- **Worst-case Moment 2 Latency:** 8.76 s (down from 47.72 s, an 82% latency reduction).
- **Dropped Profiles:** 0 across all profiles.
- **Analyst Voice Delivery:** Narrative prompts now explicitly enumerate insight numbers, passing gate check on attempt 1 without regeneration. Casual fallback in streams guarantees voice delivery under any edge case.

---

### Azure Credential and Process Overhead (Post-Optimization)

- **Token Churn:** Exactly 1 initial token fetch per process (1879 ms); all subsequent calls hit the in-memory token cache in 0.001 to 0.009 ms.
- **Process Spawning:** 0 `az` child processes spawned during match play (down from 36 per match).
- **IMDS Probe on PC:** Skipped via `exclude_managed_identity_credential=True` on non-Azure environments, eliminating 14 probe failures and socket timeouts.
- **HTTP Connection Reuse:** Persistent `FoundryChatClient` instances cached per `(project_endpoint, model)` keep TLS sessions warm.
- **VoiceLive Compatibility:** Subclassed `AsyncTokenCredential` on `AsyncCachedTokenCredential` ensuring VoiceLive WebSocket handshake awaits token retrieval properly.

---

### 4x Accelerated Start (Post-Optimization)

- **Start Response Latency:** 0.04 s (down from >8 minutes blocking timeout).
- **Precomputation:** Runs in a background task buffer ahead of the delayed playback clock when live agents are used, keeping `POST /api/match/start` immediately responsive.

---

### Summary of Improvements

| Metric | Baseline | Post-Optimization | Improvement |
|---|---|---|---|
| Q&A p50 Answer Latency | 8.92 s (11.76 s observed) | 4.66 s | 2.5x faster |
| Turkish Q&A "skor ne" (Analyst) | 32.41 s | 4.19 s | 7.7x faster |
| Moment 2 Latency | 47.72 s (LATE) | 8.76 s (ON TIME) | 82% faster |
| Cues Dropped Late | 1 to 3 of 4 | 0 of 4 | 100% on-time delivery |
| Token Fetches per Hour | 36+ | 1 | 97% reduction |
| Token Fetch Latency (cached) | 1.18 s to 1.88 s | 0.001 to 0.009 ms | 100,000x faster |
| 4x Match Start Response | >8 min (timeout) | 0.04 s | Instant start |
| Analyst Voice Delivery | Silent (dropped) | Spoken & Audited | 100% speech accuracy |



## SPEC objective
## Objective

Pitch: **a live co-commentator you can interrupt, and that can't lie: every number it says is checked against the match data before it is spoken.**

Build an AI pipeline that ingests a live stream of synthetic football events and produces commentator-grade intelligence: what happened, why it matters, verified against the data, then said two ways from one truth: a timed broadcast overlay cue and a personalized fan narrative that a voice co-commentator speaks in the fan's language and answers questions about.

Users (both shown in the 2-minute demo):
- **Broadcast producer:** wants machine-readable overlay cues timed to play, and trusts them because every claim is verified.
- **Fan:** wants the same match told for them: favourite club, favourite player, casual vs analyst depth, language.

Primary goal: place in **Best Use of Microsoft Foundry** (judges may reassign to Best Multi-Agent System). Secondary goal: real hands-on Foundry and Agent Framework experience.

### User stories

- As a producer, I see overlay cues appear in sync with the simulated match clock, each with text, metric, duration and priority.
- As a producer, I never see a cue whose claim the Fact-Checker rejected, and I can open a trace showing why a claim passed.
- As a fan, I switch my profile (club, player, depth, language) and the next narrative visibly changes in focus, depth and language.
- As a fan, I hear the co-commentator speak verified moments live in my language, and I can interrupt it ("why was that pass important?", "how is my player doing?"); it stops talking within a beat and answers from ledger evidence, or says it does not know.
- As a fan, I get a full-time recap tailored to my profile.
- As a judge, I can run the whole thing with one command, or open a public URL.



## SPEC pipeline design rules
## Pipeline design rules

1. **Broadcast delay.** The simulator emits events ahead of playback; the UI and voice show the match `BROADCAST_DELAY_S` (default 20 s of match time) behind the event stream, like a real broadcast delay. Agents work on events as they arrive, so a cue is ready before its moment is displayed. `OverlayCue.show_at_seq` ties the cue to the display clock. A cue that is not ready when its moment plays is dropped, never shown late (counted in metrics as `cues_dropped_late`). Two playback modes: **live** at 1x (agents race the delayed clock; the video and the public URL) and **precomputed** above 1x (every moment is processed before playback starts, then replayed on the delayed clock; tests, evaluation runs and the 30x end-to-end criterion). The delay is in match seconds, so the wall-clock delay is `delay_s / speed`.
2. **Two-layer Fact-Checker.** Layer 1 is deterministic code: every `evidence_refs` key must exist in the moment's evidence, and every number in `claim` and `why_it_matters` must match a cited evidence value (after rounding and unit normalisation). Any failure is an immediate `rejected` with machine-readable reasons, no LLM call. Layer 2 is an LLM that judges only the qualitative wording ("dominated", "one-way") against the evidence and may return `rewritten`. Numbers are verified by code, wording by a model.
   **Rounding rule:** a number in text matches a cited evidence value when that value, rounded half-up to the text's number of decimals, equals it (68 matches 67.6; 52.5 matches "53" and "52.5" but not "52"). Keys ending in `_s` also match in minutes when the text says minutes. Qualified approximations ("over 50 metres" against 52.5) fail by design; prompts ask for exact ledger numbers. **Digits-only rule:** number words in English and Turkish fail the check, except "one" and "bir" (articles and pronouns) and ordinal words ("second half", "ikinci yarı"). Parser formats: `68%`, `%68`, `yüzde 68`, `68.5` and `1,250` (en), `68,5` and `1.250` (tr), ordinals `23rd` and `23.`, Turkish suffixes `14'ü`, `%68'lik`; a number glued to a letter or a `letter-` prefix is an identifier, not a number.
   **The code check runs at every gate where a number can change, not only after the Commentator:** (a) the Commentator's `Insight`; (b) every Producer output, i.e. each `OverlayCue` headline/metric and each `FanNarrative` per profile and language, because per-profile rewrites and translation can change or drop numbers; (c) every text sent to the voice, including Q&A answers. The number parser handles English and Turkish formats: `68%`, `%68`, `yüzde 68`, `68.5`, `68,5`. The Producer and Q&A prompts require numbers as digits; a number written as a word fails the check. A failed Producer rendering is regenerated once, then dropped for that profile only (other profiles still get the cue). Every gate result is recorded as a `NumberCheck`. **Coverage rule at gate (b):** a rendering is also compared with its verified source text: with coverage `all` (analyst depth and the overlay metric) every number in the source claim must survive, with coverage `any` (casual depth) at least one must survive when the source has numbers; a failure is recorded as `dropped number: 14` in the `NumberCheck`.
3. **Analyst as director.** The Analyst is called once per candidate moment as it closes and returns a `DirectorDecision`: say or skip, the angle to take, and a reason. It receives a `PacingState` computed by code (seconds since the last spoken cue, cues and moments in the last 2 minutes, the moment's rank among recent moments and its interest score; an internal contract between code and the Analyst, not a cross-module payload) so it can stay quiet when commentary would pile up, without waiting for a batch window. It never computes numbers. Skipped moments are logged and shown in the verdict drawer.
4. **Ledger over MCP.** The ledger exposes read-only queries (team stats, player stats, recent moments) as an MCP server (`mcp` Python package, streamable HTTP). The voice Q&A agent calls these tools to answer open questions ("how is my player doing?"); its answer then passes the Fact-Checker like any other claim. The main moment pipeline gets evidence inline in `CandidateMoment` and does not need MCP.
5. **One truth, many renderings.** The Producer renders each verified insight once per active profile; per-profile calls run in parallel.
6. **The voice only speaks approved text.** Narrations and Q&A answers are sent to Voice Live as `response.create` with `pre_generated_assistant_message`, which synthesizes audio for the exact text with no model rewording (verified 2026-10-15 in en and tr, including `%68`). The realtime model is used only to listen: server VAD, transcription of the fan's question, barge-in. It never authors spoken words. Q&A is therefore text first: question transcript -> Q&A agent (ledger over MCP) -> Fact-Checker gate (c) -> verbatim speech. As an audit, the transcript of every spoken response is compared with the approved text and run through the number check; any mismatch is counted as an error (target 0). Pitch line for the demo: "even the voice is audited".
7. **Offline mode and the judges' budget.** With no model configured (`AGENT_MODE=template`), the same pipeline runs with deterministic template agents that fill fixed sentences from the ledger evidence; every gate still runs. This is what `docker compose` runs from a clean clone and the recording fallback if Foundry returns errors. The public Container App runs live agents under a per-visitor run limit (default `PUBLIC_LIVE_RUNS_PER_DAY=2` live matches per visitor per day, by client IP or cookie); after the limit, and on any Foundry error, the app continues in offline mode and says so in the UI. Reason: judges' clicks spend Foundry tokens against a 50 USD/month budget.



## Architecture decision records
- 0001-per-visitor-sessions: ADR 0001: Per-Visitor Match Sessions
- 0002-numbers-by-code: ADR 0002: Deterministic Statistics and Two-Layer Fact-Checker
- 0003-verbatim-voice: ADR 0003: Verbatim Voice Speech and Transcript Auditing
- 0004-broadcast-delay: ADR 0004: Broadcast Delay for Agent Processing and Verification
- 0005-mcp-ledger-tools: ADR 0005: Ledger Tools over Model Context Protocol for Fan Q&A
- 0006-transient-retry: ADR 0006: Transient Error Retry Policy with Exponential Backoff

## Deployment facts
Public URL on Azure Container Apps (managed identity, Foundry User role), per-visitor and daily live-run limits with offline fallback, docker compose offline mode, GHCR image built by GitHub Actions.
### Verification Results (2026-10-16)

| Check | Target | Result | Evidence / Details |
|---|---|---|---|
| 1. Health Probe | `GET /api/health` | **PASSED** | HTTP 200: `{"status":"ok","agent_mode":"foundry","voice":true,"running":false,"active_runs":0}` |
| 2. Live Match Start | `POST /api/match/start` | **PASSED** | HTTP 200 in 0.47s: `match_id: kby-iva-30`, `mode: live`, `agent_mode: foundry`. Live supersteps 1 to 3 completed. |
| 3. Voice Live Stream | `WSS /api/voice` | **PASSED** | Connected with MSI credentials. Received `speaking` frame, 18 PCM chunks (386,400 bytes), and `spoken` frame with exact verbatim audit transcript match (`check: true`). |
| 4. Push-to-Talk / Q&A | `WSS /api/voice` (ask frame) | **PASSED** | Sent `{"type":"ask","transcript":"How is my player doing?"}`. FastMCP called tools `['player_stats', 'score', 'recent_moments', 'team_stats']`. Answer received, spoken, and audited verbatim. |
| 5. Multi-Visitor Isolation | `POST /api/match/start` | **PASSED** | Visitor A received `kby-iva-7`, Visitor B received `iva-kby-42`. States isolated via `mc_session` cookies. |
| 6. Rate Limit & Fallback | `POST /api/match/start` (3rd run) | **PASSED** | Fallback triggered after 2 runs: `agent_mode: template`, `fallback_reason: "live-run limit reached (2 per visitor per day); continuing with offline agents"`. |
| 7. Telemetry & Traces | App Insights | **PASSED** | App configured with Azure Monitor OpenTelemetry tracing (`app/observability.py`). Traces stream to linked resource `appi-matchday` (workspace `law-matchday`). Live moment trace operation id `840499343095f9544b921f75c730cf5c` captures full hierarchy: `moment kby-iva-30-31-pass_streak` -> `workflow.run` (`analyst`, `commentator`, `fact_checker`) -> child `producer.render`. Live Q&A trace operation id `f135de636c7820ee5ce4e810202362fe` captures `qa.answer` with child `mcp.tool` spans (`score`, `team_stats`, `recent_moments`). |
| 8. Docker Compose Offline | `docker compose up --build -d` | **PASSED** | Clean clone build, offline health check 200, started match `kby-iva-7`, received `event: cue` SSE stream, clean teardown. |


## Repository
Top-level entries: .claude, .dockerignore, .env.example, .github, .gitignore, .hooks, CLAUDE.md, Dockerfile, IDEA.md, README.md, SPEC.md, app, data, docker-compose.yml, docs, frontend, hosted, infra, pytest.ini, requirements.md, requirements.txt, scripts, spikes, task_state.md, tasks, tests. Test functions: 264 (offline suite runs without model calls; a live suite calls Foundry). Hosted agent project in hosted/ (built and unit-tested; live deployment blocked by a local sign-in issue).

UI screenshots (described, from docs/design/screenshots/, a real seed 30 match):
- Desktop 1440x900, one screen: dark navy 'floodlight broadcast' theme; header with league mark, scoreboard pill (Kestrel Bay 0:0 Ironvale, gold clock), chips 'Broadcast delay 20 s' and 'Foundry agents live', Stop and Voice buttons. Left: SVG pitch with mowing stripes, a ball with a club-coloured dotted trail and a player name pill; a broadcast lower-third cue 'Ironvale: 22-pass move' with crest block, green 'Verified' chip, 'numbers by code, wording by model, attempt 1' and a big '22 PASSES'. Three ticker cards under the pitch. Right: fan panel with club and player selects, Casual/Analyst and English/Turkce toggles, 'Hold to talk' button, an answer card. Footer: agent timeline summary (cues aired, skipped, rejected, number checks, answer p50) and 'Open timeline'.
- Agent timeline drawer: list of moments with verdict chips; selected moment shows steps Analyst (say it, cited ledger keys), Commentator attempts, Fact-Checker verdict and layer, Producer per profile, aired.
- Scene 5 screenshot: a planted false claim 'Ironvale have had 6 shots.' struck through, Fact-Checker 'rejected, layer code', reason '6 shots does not match the cited shots value (away_shots_last_10min = 0)', 'Never aired: no overlay, no voice, no fan narrative'.
- Phone 390 px: stacked header, pitch with the cue overlapping, profile controls, bottom tabs Live / Feed / Agents.