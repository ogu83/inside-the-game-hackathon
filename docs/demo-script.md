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
| 5 | 1:06-1:26 | Debug drawer: a planted false claim ("Ironvale have had six shots") arrives; Fact-Checker layer "code" rejects it: "6 not in cited evidence (away_shots_last_10min = 0)"; it never reaches the screen or the voice | VO: "Numbers are checked by code, not by another model's opinion: after the Commentator, after every translation, and before every spoken word. Even the voice is audited." | Fact-Checker rejecting a planted claim |
| 6 | 1:26-1:44 | Foundry portal, pre-recorded clips (no live clicking): trace of one moment (Analyst, Commentator, Fact-Checker, Producer spans); then the evaluation result page | VO: "Every step is traced in Foundry. Across three matches: Groundedness with the Fact-Checker on vs off, and X of N planted errors caught, zero reached air." | Foundry trace, eval headline |
| 7 | 1:44-1:58 | Architecture diagram (simulator, ledger, agents, Foundry, Voice Live), repo URL and public URL | VO: "Microsoft Foundry, Agent Framework, Voice Live and MCP. Open source, runs with one command, and live for you to try." | Close |

Total: about 1:58. Trim scene 2 first if long.

## Recording checklist

- [ ] Seed chosen where a pass streak and a planted error land in the first 5 match minutes; recording speed 3x to 4x (`speed` on match start), delay 20 s
- [ ] Hosted agent invoked once before recording (cold start is about 29 s); offline mode is the fallback if Foundry errors during the take
- [ ] Browser zoom so text is readable at 1080p; mic tested; system notifications off
- [ ] Eval numbers filled in from docs/eval-results.md (scene 6); portal clips pre-recorded
- [ ] English captions on every Turkish line; app audio and voiceover on separate tracks
- [ ] No trademarks visible anywhere: browser bookmarks bar hidden, OS taskbar hidden
