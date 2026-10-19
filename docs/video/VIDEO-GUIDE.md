# Making the video: step by step

Published: https://youtu.be/wi6E7SjbZjQ

The video is about 1:40. It is built from short pieces of screen recordings ("takes"), two picture slides, and your voice recorded separately on top. Nothing is narrated live: you first record the screen, then you put the pieces in order, then you read the narration while watching that sequence.

## 1. What is already recorded and what is left

| Take | What it shows | Status |
| --- | --- | --- |
| A | The timeline with the planted false claim rejected ("6 shots does not match...", "Never aired") | Done |
| B | The pitch with the 22-pass cue spoken, your question "How is my player doing?" with the verified answer about Jory Calloway, then the Turkish Analyst line | Done (final take, 2026-10-18) |
| C | The Foundry portal trace of one moment | To record |

### Record take C (about 30 seconds)

1. Open the Foundry portal (ai.azure.com), project **matchday**, **Tracing**.
2. Open one recent trace that shows the agents (Analyst, Commentator, Fact-Checker, Producer).
3. Before recording, make sure no account name, email, subscription ID or tenant ID is visible (zoom so only the trace tree shows, or blur later).
4. Record about 20 seconds of slowly scrolling the trace tree.

## 2. Put the pieces in order (in your video editor)

Import take A, take B, take B2, take C and the two slides (`docs/video/scene4-numbers.png`, `docs/video/scene5-endcard.png`). Cut each take down to only the part listed here and place them in this order. Everything else in the takes is thrown away.

| Clip | Use this part | From | About |
| --- | --- | --- | --- |
| 1 | The rejected claim, the reason line, "Never aired" | Take A | 14 s |
| 2 | The pitch with the "Ironvale: 22-pass move" banner appearing and the app voice speaking it | Take B | 24 s |
| 3 | You pressing the button, your question, the answer card, the spoken answer (cut the wait while it thinks) | Take B | 15 s |
| 4 | The Turkish line playing (add the English captions below) | Take B, the end | 12 s |
| 5 | The trace tree | Take C | 6 s |
| 6 | Numbers slide | `scene4-numbers.png` | 16 s |
| 7 | Architecture diagram (a screenshot of the diagram in the README on GitHub) | screenshot | 6 s |
| 8 | End slide | `scene5-endcard.png` | 8 s |

## 3. Record the narration (your voice, on top of the sequence)

Play the sequence from step 2 and read each part below while its clips are on screen. Record it as one audio file (or one file per part) with only your mic, then place it on its own audio track under the clips. Where the app is speaking (clip 2 start, clip 3 answer, clip 4), stay silent or turn the app voice down while you talk.

### Part 1: over clip 1 (the rejected claim)

> This is an AI commentator catching itself. A false statistic was planted on purpose. Code checked it against the match data, and it never reached the screen, or the voice.

### Part 2: over clip 2 (start talking after the app voice finishes its line)

> Four Microsoft Foundry agents watch a synthetic match. An analyst picks the moment, a commentator writes it, a fact-checker verifies every number, and a producer tells it for each fan. Like a real broadcast, playback runs twenty seconds behind, so nothing airs unverified.

### Part 3: over clips 3 and 4 (start after the answer has been spoken)

> And you can interrupt it. Answers come from the match ledger over MCP, and pass the same checks before they are spoken. Same truth, in your language.

### Part 4: over clips 5 and 6 (trace, then the numbers slide)

> Every step is traced in Foundry. In our evaluation, planted errors reached air four times out of four without the fact-checker, and zero times with it. Every spoken word is audited against the approved text.

### Part 5: over clips 7 and 8 (architecture, then the end slide)

> Broadcasters can't put an AI voice on air if it might invent a statistic. This is the trust layer that makes it possible. It's live, it's open source, and it runs with one command.

## 4. Captions for clip 4 (the Turkish line)

From the final take B (2026-10-18). Show these one after another while the Turkish line plays:

1. "Kestrel Bay built a 12-pass sequence in 53 seconds with 7 players, carrying the ball 55.6 metres forward;"
2. "Caden Holloway made 3 of those passes."
3. "The move did not end in a shot,"
4. "but it gained Kestrel Bay 55.6 metres of ground in Ironvale's half."

## 5. Finish

1. Check the total length is under 2:00.
2. Export 1080p MP4.
3. Upload to YouTube, set the thumbnail to `docs/video/youtube-thumbnail.jpg`, title "Matchday Companion: the AI commentator that can't lie".
4. Send the YouTube link to Claude: it goes into the README and the Innovation Studio project page.
