# Brief: P1 design review with Claude Design (Matchday Companion)

Use this brief in Claude Design to review the current page and produce a mockup plus a short style guide. No code changes in this step; P3 implements the result after T13 (deploy) is merged.

## The product in one line

A live co-commentator you can interrupt, and that can't lie: every number it says is checked against the match data before it is spoken. Built on Microsoft Foundry agents for the Microsoft + Premier League "Inside the Game" hackathon (target category: Best Use of Microsoft Foundry).

## Who looks at it

- **Judges, mostly through a 2-minute video** (scene list in `docs/demo-script.md`), sometimes on the public URL. UX and presentation is 20% of the score. Every screen must read clearly at 1080p in a video and be understood in seconds.
- **Broadcast producer** (left side): overlay cues timed to the delayed match clock, and trust that every cue was verified.
- **Fan** (right side): the same match told for them (club, player, depth, language), spoken aloud, interruptible with push-to-talk.

The look should say "broadcast product with a trust layer", not "developer dashboard".

## What exists today (single page, `frontend/index.html` + `frontend/style.css`, Vue 3 from a CDN, no build step)

- **Header:** title, seed / speed / delay inputs, start and stop buttons, voice on/off toggle, badges (broadcast delay 20 s, precompute or live, offline agents), match clock.
- **Voice bar** under the header: "speaking: ...", microphone status, speech audit counter ("13/13 exact, 6 interrupted").
- **Broadcast panel (left):** SVG pitch (flat green, white lines) with a ball dot and a small player-name label, team names in the corners, an overlay **cue banner** at the bottom of the pitch (headline, big metric number, "verified by llm layer, attempt 1"), and an event ticker below in monospace.
- **Co-commentator panel (right):** club, player, depth and language selects (they apply on change), "hold to talk" button and a text question box, Q&A cards (question, answer, "verified", tools used "via player_stats, score, ...", "spoken verbatim", "answered in 2.4 s, spoken after 2.4 s"), the narrative list.
- **Agent timeline drawer (bottom):** metric chips (cues shown, skipped, rejected, late, number checks, speech checks, interrupted, questions, p50 times), filter chips, and per moment the steps Analyst (say/skip, angle), Commentator, Fact-Checker (layer, verdict), Producer, and what aired.
- **Palette today:** dark (`--bg #0e1116`, panels `#171c24` / `#1d2430`), text `#e8edf3`, muted `#8a94a3`, accent and home `#5ad17a` (green), away `#f0a848` (amber), bad `#e35d6a`, info `#6ea8fe`. Problem: the home colour is green on a green pitch.

## Fixed constraints

- **Fictional league only:** Meridian League, Kestrel Bay FC vs Ironvale Athletic. No real clubs, crests, players, sponsors, broadcaster branding or trademarks anywhere, including lookalike styles of real broadcasters.
- **Proposed club colours** (P2 crests use these, adopt or adjust them consistently): Kestrel Bay = bay blue `#2F8FD8`, white, sand accent `#E9D8A6`; Ironvale = ember orange `#E8833A`, charcoal `#2B2F36`. Team markers, cue banner edges and timeline tags use them; neither may be green.
- **Implementation limits for P3:** one HTML page with Vue 3 from a CDN and one CSS file, no build step, no npm. Pitch stays SVG (texture with SVG patterns and CSS gradients, not a raster image). Icons from Lucide (MIT, inline SVG). Crests from P2 as PNG or SVG. Web fonts: Google Fonts only, at most two families.
- **Must keep working:** voice toggle, push-to-talk (press and hold, release), profile selects applying on change, Q&A cards, timeline filters, phone width (about 400 px) and 1440x900. Accessible contrast (WCAG AA for text), visible focus, nothing conveyed by colour alone (the Fact-Checker verdict also needs an icon or word).
- **English UI text**, no em dashes. Turkish appears only in spoken lines and narratives (English captions are burned into the video).

## What to review

1. Hierarchy and first impression at 1080p: what does a judge see in the first 3 seconds of the video?
2. The "trust layer" made visible: how verified, rewritten and rejected look; how "spoken verbatim" and the speech audit read; the planted false claim being rejected (demo scene 5) must be dramatic and obvious.
3. The pitch: texture (mowing stripes, subtle gradient, vignette), ball and player label legibility, team colour markers, a short ball trail.
4. The cue banner as a broadcast graphic: crest, headline, big metric, verified mark, enter and exit motion.
5. The fan panel: profile selection, push-to-talk states (idle, held and listening, transcribing, answering, speaking, "I didn't catch that"), Q&A cards with timing.
6. The agent timeline drawer: readable as the "four Foundry agents at work" story for demo scene 2, not a log dump.
7. Status and errors: offline agents notice, live-run limit reached, "the demo is busy", voice unavailable, microphone denied.
8. Text versus icons: which labels become Lucide icons (with tooltips and accessible names) and which stay words.

## Deliverables

1. **Mockups:** the main screen at 1440x900 during a live match with a cue on screen and the voice speaking; the same at about 400 px wide; push-to-talk held and the answer card; the drawer open on one moment with a rejected planted claim.
2. **Style guide (one page):** colour tokens (background, panels, text, muted, accent, both club colours, verified, rewritten, rejected, warning, info), type scale and font choice, spacing scale, radius and shadow, icon list (UI element to Lucide icon name), motion rules (durations, easing, what animates), and the pitch treatment recipe.
3. **P3 implementation notes:** a numbered list of concrete changes for `frontend/index.html` and `frontend/style.css`, in priority order, each small enough for one commit, marking which ones matter most for the video.

Save the outputs (exported images and the style guide as markdown) to `docs/design/` so P3 can follow them.
