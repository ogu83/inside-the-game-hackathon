# Demo Script: Matchday Companion (under 2 minutes)

Pitch: **a live co-commentator you can interrupt, and that can't lie: every number it says is checked against the match data before it is spoken.**

Revised 2026-10-18 from the judgement-day simulation (`docs/review/judgement-day/REPORT.md`): cold open on the proof, then three beats, one fast proof screen, close. Every judge said the risk is a crowded video, so each scene has one idea.

Rules for the recording: fictional Meridian League only (Kestrel Bay FC vs Ironvale Athletic); no real clubs, players, crests, sponsors or broadcaster branding; no music (or only self-made audio); English narration and on-screen text, English captions burned in for every Turkish spoken line (rules 4.8). App audio and voiceover on separate tracks, mixed so they never overlap. Voiceover is Oguz; the co-commentator voice is the app.

## Shot list (target 1:50)

| # | Time | On screen | Audio | Take |
| --- | --- | --- | --- | --- |
| 1 | 0:00-0:14 | **Cold open.** Timeline drawer open on the planted claim: "Ironvale have had 6 shots." struck through, red "rejected, layer code", reason "6 shots does not match the cited shots value (away_shots_last_10min = 0)", "Never aired". Slow zoom on the reason line. Title card for 1 s: "Matchday Companion". | VO 1 | A |
| 2 | 0:14-0:38 | **Beat 1: verified cue, spoken.** Full app, pitch moving, lower-third "Ironvale: 22-pass move" with green "Verified" chip and "numbers by code, wording by model"; header chips "Broadcast delay 20 s" and "Foundry agents live"; voice bar shows the spoken line. Cut to the drawer for 3 s on this moment: Analyst, Commentator, Fact-Checker, Producer. | App voice speaks the line, then VO 2 | B |
| 3 | 0:38-1:02 | **Beat 2: interrupt it.** While it speaks, hold "Hold to talk": the voice stops at once, the button turns blue. Ask "How is my player doing?", release: answer card with Verified, Spoken verbatim, the timing bar. Then switch to Turkce, Analyst: the next line plays in Turkish with an English caption. | App voice answers; VO 3 over the switch; Turkish line with caption | B |
| 4 | 1:02-1:24 | **Proof screen.** Pre-recorded Foundry portal: one moment trace with the agent spans (4 s), then a numbers card (static slide in the app's style): "Planted errors on air: 0 of 4 with the Fact-Checker, 4 of 4 without" / "Groundedness 4.75 vs 3.83" / "Offline gates: 38 of 38 caught" / "Every spoken word audited". | VO 4 | C (portal), slide |
| 5 | 1:24-1:46 | **Why it matters and close.** Phone view for 2 s, then the architecture diagram from the README for 4 s, then end card: hero image, "Try it: <public URL>", "Code: <repo URL>", "Built on Microsoft Foundry, Agent Framework, Voice Live and MCP". | VO 5 | B, slide |

Total about 1:46; spare 10 s for breathing room. If long, cut the Turkish switch in scene 3 to its first sentence.

## Voiceover (about 170 words, read at a calm pace)

- **VO 1 (cold open):** "This is an AI commentator catching itself. A false statistic was planted on purpose. Code checked it against the match data and it never reached the screen, or the voice."
- **VO 2 (beat 1):** "Four Microsoft Foundry agents watch a synthetic match: an analyst picks the moment, a commentator writes it, a fact-checker verifies every number, and a producer tells it for each fan. Like a real broadcast, playback runs twenty seconds behind, so nothing airs unverified."
- **VO 3 (beat 2):** "And you can interrupt it. Answers come from the match ledger over MCP and pass the same checks before they are spoken. Same truth, in your language."
- **VO 4 (proof):** "Every step is traced in Foundry. In our evaluation, planted errors reached air four times out of four without the fact-checker, and zero times with it. Every spoken word is audited against the approved text."
- **VO 5 (close):** "Broadcasters can't put an AI voice on air if it might invent a statistic. This is the trust layer that makes it possible. It's live, it's open source, and it runs with one command."

## Recording runbook

Setup (local, PowerShell, repo root):

```powershell
Get-Content .env | ? {$_ -match '^[A-Z_]+='} | % {$k,$v=$_ -split '=',2; Set-Item "env:$k" $v}
$env:AGENT_MODE='foundry'; $env:VOICE_MODE='live'; $env:DEMO_PLANT='1'; $env:TRACE_SENSITIVE='1'
$env:PUBLIC_LIVE_RUNS_PER_DAY='100'; $env:PUBLIC_LIVE_RUNS_TOTAL_PER_DAY='0'
.venv\Scripts\python.exe -m uvicorn app.api.main:app --port 8010
```

- **Take A (cold open):** seed 30, 4x, match settings "Plant a false claim" on, voice off. Open the timeline, filter Rejected, select the planted moment (about 01:00 on the clock). Record 20 s of the drawer, including a slow scroll over the reason.
- **Take B (beats 1 to 3 and the phone shot):** new match, seed 30, 4x, plant off, voice on, profile English Casual. The 22-pass cue lands around 01:30 on the clock. Do the barge-in on a later spoken line, then switch to Turkce Analyst and let one Turkish line play. Do 2 or 3 takes; keep the cleanest. For the phone shot, use the browser's device toolbar at 390 px.
- **Take C (portal):** Foundry portal, project `matchday`, Tracing: open the trace of one moment from take B (TRACE_SENSITIVE shows the prompts, which reads well). Hide or blur subscription and tenant IDs, the account name and anything outside the project.
- Window 1920x1080, browser at 100% to 110% zoom, bookmarks bar hidden, notifications off, taskbar hidden, only the app tab open.
- Audio: app audio on its own track, microphone on another (for example OBS with desktop audio and mic on separate tracks). Record VO after the screen takes, to picture.
- Captions: after take B, copy the Turkish lines from the narrative feed and answer card; Claude translates them for the burned-in English captions. Always captioned: "skor ne" = "What's the score?".
- After recording: export 1080p, check length under 2:00, upload to YouTube (public or unlisted per the rules), put the URL in README `VIDEO_URL` and on the project page.

## OBS setup (separate audio tracks)

1. Settings, Video: base and output 1920x1080, 30 fps. Settings, Output, Recording: format MKV (remux to MP4 after), encoder hardware if available, quality "High".
2. Settings, Output, Recording, Audio Track: tick tracks 1 and 2.
3. Edit, Advanced Audio Properties: Desktop Audio on track 1 only (the app voice), Mic/Aux on track 2 only (you). Mute the mic during screen takes if you record the VO later.
4. Scene: one Window Capture of the browser (Chrome window at 1920x1080, only the app tab), or Display Capture with the taskbar hidden.
5. Remux MKV to MP4 (File, Remux Recordings), edit in any editor that keeps both tracks (Clipchamp, DaVinci Resolve, Shotcut), lower the app voice under the VO where they meet, burn in the captions, export 1080p.

## Checklist

- [x] Seed 30: 22-pass Ironvale move ending in a shot in minute 1, then moments at minutes 3, 4 and 8
- [x] Planted-claim switch for the cold open (T12c, `DEMO_PLANT=1`)
- [x] Proof numbers (docs/eval-results.md, README): 0 of 4 vs 4 of 4, Groundedness 4.75 vs 3.83, offline 38 of 38
- [x] Numbers card: `docs/video/scene4-numbers.png`
- [x] End card: `docs/video/scene5-endcard.png` (public URL and repo URL); YouTube thumbnail: `docs/video/youtube-thumbnail.jpg` (1280x720)
- [ ] Portal trace clip recorded, IDs hidden
- [ ] Takes A, B, C recorded; VO recorded; captions burned in
- [ ] Under 2:00, no trademarks or real people visible, no music
- [ ] YouTube URL in README and on the Innovation Studio project page
