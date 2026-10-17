# Prompt: P5 performance diagnosis and fixes (Matchday Companion)

You are working in the repository at `C:\Users\oguz\source\repos\inside-the-game-hackathon` (Windows, PowerShell, Python 3.11 venv in `.venv`). You have an Azure login and a filled `.env`. Read `CLAUDE.md` and `SPEC.md` first; their hard rules apply. Run this after T10 (it adds tracing, which this task uses to measure).

## Why (observed by Oguz on 2026-10-17, local live run, seed 30, 1x, Foundry agents, voice on)

- **Answers were slow:** "answered in" 10.2 s, 12.1 s and 15.9 s; metrics `qa_answer_p50_ms = 11756`. On 2026-10-16 the p50 was 3.7 s (SPEC criterion 9 asks for about 3 s median).
- **Cues missed the 20 s broadcast delay:** `cues_dropped_late = 3` of `moments_detected = 4`; only 1 cue aired in the first minutes.
- **Analyst depth never spoke;** Casual did. The voice speaks exactly the profile's narrative (`app/api/voice_ws.py` `_feed`, channel `fan:<profile_key>`), so a likely cause is that Analyst renderings (frontier model, longer text) finish after the moment's display time and are never published. Unconfirmed.
- **Credential churn:** in a few minutes the server log shows 36 lines "DefaultAzureCredential acquired a token from AzureCliCredential". Each one starts an `az` process (often 1 to 3 s on Windows). Tokens normally last about an hour, so something creates new credentials or clients per call. Candidates: `app/agents/run_match.py` line ~106 (`FoundryChatClient(..., credential=DefaultAzureCredential())` per client) and line ~155, `app/voice/session.py` line ~212, `app/eval/run_eval.py`.
- **Managed-identity probe on a PC:** the T10 moment trace contains `GET /metadata/identity/oauth2/token`: `DefaultAzureCredential` tries managed identity before the Azure CLI. Locally use a credential that skips it (for example `DefaultAzureCredential(exclude_managed_identity_credential=True)` when not in Azure, or `AzureCliCredential` locally and `ManagedIdentityCredential` in the Container App), chosen once at startup.
- **4x start blocks:** `POST /api/match/start` with speed 4 and live agents did not return within 8 minutes, because precomputed mode works through every moment before kick-off. The video (T15) is recorded at 3x to 4x, so this must start quickly: precompute in the background ahead of the playback clock, or start playback once the first moments are ready.
- **Transcription mis-hear:** with Türkçe selected, "skor ne" was transcribed as "Scorned, did?" (the answer was still right, but by luck). Check that the listening session uses the selected language and the phrase list.
- Local note: the Azure CLI broker (WAM) on this PC fails with 0x800704cf; run the app with `AZURE_CORE_ENABLE_BROKER_ON_WINDOWS=false` in the environment (process only, do not change `az config`).

## Tasks (in this order; measure before and after each fix)

1. **Baseline, with evidence.** Run seed 30 at 1x with Foundry agents and voice, locally and on the public Container App (use the T10 traces in App Insights). Ask 3 fixed questions ("How is my player doing?", "What's the score?", "skor ne" in Türkçe) with Casual and with Analyst. Record per stage: transcription, agent and MCP tools, check, first audio for Q&A; moment close to cue ready (Analyst, Commentator attempts, Fact-Checker, Producer per profile) for cues; how many cues and narratives were late, per depth. Put the table in `docs/performance.md`.
2. **One shared credential.** Create the credential once per process (and the Foundry clients once per model, reused across moments and questions). Show the token-fetch count before and after (it should be a handful per hour, not dozens).
3. **Analyst voice.** Confirm the cause with traces. Fix within the design: for example render Analyst and Casual in parallel as today but start the Producer as soon as the verdict is in, use the small model for the narrative if quality holds, or speak the Casual line as a fallback when the Analyst line is late (say which one and why; a late line is never shown or spoken late).
4. **Cue lateness.** From the traces, find the slowest step per moment. Fix the cheapest wins first: reuse clients and HTTP connections, run independent calls in parallel, cap output tokens, trim prompts, use the small model where SPEC allows. Do not raise `BROADCAST_DELAY_S` above 20 s without asking Oguz.
5. **Q&A latency.** Same approach for the answer path (`app/voice/qa.py`, MCP tools, the Q&A agent). Target p50 about 3 s locally and on the public app.
6. **Transcription language.** Make sure the listening connection uses the selected language and the phrase list; add the mis-heard case as a test if it is a code issue.
7. **Re-measure** with the same runs as task 1 and add the after-numbers to `docs/performance.md`.

## Rules

- Branch `p5-performance` from `main`; push it; do not push to `main`; no pull request.
- One commit per fix, each with its before/after numbers in the message. Tests for any logic change.
- Before every commit: `.venv\Scripts\python.exe -m pytest tests -q` must pass; run `-m live` once at the end.
- Never trade correctness for speed: every number still checked by code, every spoken line still audited, nothing shown late.
- No em dashes, no Co-Authored-By trailers, fictional league only, Azure spend unchanged (no new resources, no higher tiers) unless Oguz agrees.

## Reporting rule

Only report something as done when you ran it and can show the evidence (trace ids, query output, the before/after table). Say "not done" otherwise.

## Done when

- `docs/performance.md` has the before and after tables, local and public.
- Token fetches are a handful per hour; Analyst lines are spoken (or a documented fallback is spoken) when on time; late cues are the exception, with the numbers to show it; Q&A p50 is about 3 s or the remaining gap is explained.
- Report back: the branch, the commit list with before/after numbers, the tables, and anything not fixed with the reason.
