# Prompt: P3 UI implementation from the P1 design (Matchday Companion)

You are working in the repository at `the repository root` (Windows, PowerShell, Python 3.11 venv in `.venv`). You have an Azure login and a filled `.env`. Read `CLAUDE.md` first; its hard rules apply.

## Goal

Restyle the single page (`frontend/index.html`, `frontend/style.css`) to the "floodlight broadcast" design from P1 so it reads as a broadcast product with a visible trust layer, in the 2-minute video and on the public URL. Behaviour stays the same: this is a presentation change, not a feature change.

## Inputs (read all of them before the first change)

- `docs/design/style-guide.md`: every token, size, icon, motion rule and the pitch recipe. Use its values; do not invent new colours.
- `docs/design/p3-notes.md`: the 15 changes in priority order, one commit each. **This is your task list.** Items marked [video] come first.
- `docs/design/mockups/*.dc.html`: the five mockup boards as HTML with inline styles (Main 1440x900, Phone 390x844, PushToTalk, Drawer, StyleGuide). Copy layout and values from them. Their images point at `/_blob/...` (the design canvas); in the app use `/static/assets/crest-kby-256.png`, `/static/assets/crest-iva-256.png`, `/static/assets/league-mark-256.png` (check how `app/api/main.py` mounts `frontend/`, and use the matching URL).
- `docs/demo-script.md`: the video scenes the page must serve.

## Limits

- One HTML page, Vue 3 from the CDN, one CSS file. No build step, no npm, no new JS libraries.
- Icons: Lucide (MIT) pasted as inline SVG, 2 px stroke; decorative icons `aria-hidden="true"`, icon-only buttons `aria-label` and `title`.
- Fonts: Google Fonts link for Barlow Condensed (500, 600, 700) and Barlow (400, 500, 600) only.
- Pitch stays SVG with `viewBox="0 0 105 68"`; texture with SVG patterns and gradients, no raster image.
- English UI text, no em dashes, fictional league only. Sentence case in the UI ("Hold to talk", not "hold to talk").
- No backend changes. If a mockup shows a value the API does not send (for example a cue subline), hide that element rather than make up the value. Agents never compute numbers, and neither does the page.

## Must keep working (check after every commit)

Voice toggle; push-to-talk (pointer press and hold, release, Space key, barge-in that drops playback at press time, "I didn't catch that" on an empty press); profile selects applying on change; Q&A cards with verdict, tools, "spoken verbatim" and timing; timeline filters; offline-agents and busy notices; phone width 390 px with no sideways scroll; 1440x900.

## Tests

`tests/frontend/test_page.py` pins strings from the current page. Some pins are behaviour (handlers such as `@pointerdown.prevent="pressTalk"`, `class PushToTalk`, `class PlaybackGate`, `bargeIn`, `talkOutcome`, the single `getUserMedia(`, pointer events only, no em dash, the viewport meta). Keep those passing unchanged. Others are copy or old CSS (`"hold to talk"`, `"speech audit"`, `"text only (voice off)"`, `font-size: 2.2px`, the `@media (max-width: 480px)` rules). When a design change breaks a copy or CSS pin, update that pin in the same commit to the new text or rule and say so in the commit message. Never delete a behaviour pin; never weaken a test to make it pass. Add a pin for anything new that the video depends on (for example the verdict chip with an icon, the cue banner crest, the phone tab bar).

Before every commit: `.venv\Scripts\python.exe -m pytest tests -q` must pass.

## Browser verification (required, with evidence)

Run the app locally (`.venv\Scripts\python.exe -m uvicorn app.api.main:app --port 8010`) and check in a real browser at 1440x900 and at 390 px width:

1. A match on seed 30 plays; cue banners enter and leave with the new motion; the ball moves smoothly with a coloured trail.
2. Voice on: a cue is spoken and the voice bar shows the line and the audit.
3. Push-to-talk: hold, ask "How is my player doing?", release; each state from the PushToTalk board appears; one answer card, spoken verbatim, with the timing bar.
4. Empty press: "I didn't catch that, try again", no card.
5. Switch to Türkçe and ask "skor ne"; the answer card shows the Türkçe meta line.
6. Open the timeline drawer and check the filters and the step layout from the Drawer board. The page cannot start a planted-error run today (planting is CLI only, `app/agents/run_match.py --plant`; a demo switch is a separate task, T12c). So check the rejected layout with a rejected or skipped moment if one occurs, or by temporarily feeding one recorded rejected moment into the timeline from the browser console; do not add backend code for it. Report which way you checked.
7. Keyboard only: Tab reaches start, voice, talk (Space works), the text box and the drawer, with a visible focus ring.
8. `prefers-reduced-motion` (DevTools rendering emulation): no slide, no ball tween.

If you cannot operate a microphone, do the rest and hand checks 3 to 5 to Oguz, saying so plainly. Save 1440x900 and 390 px screenshots of the live match with a cue on screen and of the open drawer to `docs/design/screenshots/` (PNG, no personal data in view).

## Reporting rule

Only report something as done when you ran it and can show the evidence (test output, what was on screen). Say "not done" or "handed to Oguz" otherwise.

## Rules

- Branch `p3-ui` from `main`; push it; do not push to `main`; no pull request.
- One commit per item in `p3-notes.md` (combine two small items only if they touch the same lines). No Co-Authored-By trailers.
- Do not touch `app/`, `infra/` or the deployed Container App. The image rebuilds when `main` changes; Oguz merges.
- Update `task_state.md` and `tasks/todo.md` (P3 result line) in the last commit.

## Done when

- Items 1 to 9 of `p3-notes.md` are committed and the 8 browser checks have a recorded result; items 10 to 15 are committed or listed as not done with the reason.
- The test suite passes.
- Report back: the branch, the commit list (one line each), the browser check table with evidence, the screenshots saved, any test pins you changed and why, and anything that differs from the mockups and why.
