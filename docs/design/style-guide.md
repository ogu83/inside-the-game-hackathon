# Style guide: floodlight broadcast

Result of P1 (design review with Claude Design, 2026-10-16). Mockups: `docs/design/mockups/*.dc.html` (canvas sources; images load from the canvas, so open the canvas link in `docs/design/README.md` to see them rendered).

The idea: a night match under lights. Dark navy chrome, the pitch is the only large area of colour, club colours say who did what, and status colours mean the same thing everywhere. It should read as a broadcast product with a trust layer, not a developer dashboard.

## Colour tokens

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#0B1220` | page background |
| `--chrome` | `#0E1626` | header, footer, drawer |
| `--panel` | `#121B2E` | cards, inputs, segmented controls |
| `--chip` | `#182339` | neutral chips |
| `--line` | `#26324A` | borders, selected segment |
| `--text` | `#EEF2F7` | primary text |
| `--text-2` | `#CFD8E6` | secondary text |
| `--muted` | `#9AA7BB` | labels, meta |
| `--clock` | `#E0B04F` | match clock and event times only |
| `--kby` | `#2F8FD8` | Kestrel Bay (home); also the primary action colour (voice on, listening) |
| `--kby-sand` | `#E9D8A6` | accent only, never text on dark |
| `--iva` | `#E8833A` | Ironvale (away) |
| `--info` | `#7AB4FF` | info icons, links |
| `--verified` | `#3DD68C` | verified, passed checks |
| `--rewritten` | `#F2B33D` | rewritten, warnings |
| `--rejected` | `#FF5D6C` | rejected, errors |
| `--pitch-a` / `--pitch-b` | `#1F6E3D` / `#237A44` | mowing stripes |

Rules:
- Club colours never carry status; status colours never mark a team. No team is green.
- Text contrast meets WCAG AA: `--text` on `--bg` about 16.8:1, `--muted` on `--panel` about 6.9:1. Status chips use dark text (`--bg`) on the status colour.

## Status, always colour plus icon plus word

| State | Chip | Icon (Lucide) | Meaning |
| --- | --- | --- | --- |
| Verified | `--verified` fill, dark text | `check` | passed both layers |
| Rewritten | `--rewritten` fill, dark text | `pencil` | passed on attempt 2 |
| Rejected | `--rejected` fill, dark text | `x` | never aired |
| Skipped | `--line` fill, `--text-2` text | `minus` | the director chose silence |
| No data | `--chip`, `--info` icon | `info` | "I don't have data on that" is an answer, not an error |
| Offline agents | `--chip`, `--rewritten` icon | `triangle-alert` | live quota used or Foundry unreachable, with the reason |
| Spoken verbatim | `--chip`, `--info` icon | `volume-2` | shown only after the speech audit matched |

## Type

Google Fonts, two families: **Barlow Condensed** 500/600/700 for display and numbers, **Barlow** 400/500/600 for body. Use `font-variant-numeric: tabular-nums` on the clock and score.

| Role | Spec |
| --- | --- |
| Cue metric | Condensed 700, 60 px, line-height 0.9, club colour |
| Cue headline | Condensed 700, 32 px |
| Score and clock | Condensed 700, 24 px |
| Section label | Condensed 600, 16 to 18 px, uppercase, letter-spacing 1.5 px, `--muted` |
| Answer text | Barlow 19 px, line-height 1.35 |
| Body and controls | Barlow 15 px |
| Meta and chips | Barlow 13 px; never below 12 px |

The ticker drops monospace and uses Barlow 13 px with the time in `--clock`.

## Space, shape, touch

- Spacing scale: 4, 8, 12, 16, 24, 32. Page gutter 24 px desktop, 16 px phone (12 px inside phone cards).
- Radius: 8 inner controls, 10 inputs and buttons, 14 cards and the pitch, pill (999 px) for chips.
- Shadow only on floating things: cue banner `0 10px 30px rgba(0,0,0,.45)`, drawer `0 -12px 30px rgba(0,0,0,.45)`.
- Touch targets at least 44 px. Push-to-talk 56 px tall on desktop, 64 px full width on phone.
- Visible focus: `outline: 2px solid var(--info); outline-offset: 2px` on every interactive element.

## Icons

Lucide (MIT), inline SVG, 2 px stroke, `stroke-linecap/linejoin: round`. Decorative icons get `aria-hidden="true"`; icon-only buttons get `aria-label` and a `title`. No emoji.

| UI element | Lucide icon | Label kept as text? |
| --- | --- | --- |
| Hold to talk | `mic` | yes |
| Voice on/off | `volume-2` / `volume-x` | yes on desktop, icon-only on phone |
| Stop match | `square` | icon-only |
| Start match | `play` | yes |
| Broadcast delay chip | `clock` | yes |
| Foundry agents chip | `shield-check` | yes |
| Speech audit | `shield-check` | yes |
| Ask (text box submit) | `arrow-right` | icon-only |
| Try again | `rotate-ccw` | yes |
| Open/close timeline | `chevron-up` / `chevron-down` | yes / icon-only |
| Agents tab (phone) | `activity` | yes |
| Feed tab (phone) | `list` (or three lines) | yes |
| Live tab (phone) | `columns-2` (or rectangle split) | yes |
| Verdicts | `check`, `pencil`, `x`, `minus`, `info` | always with the word |

## Pitch recipe (SVG only, no raster)

1. Keep the real proportions: `viewBox="0 0 105 68"`.
2. Background: an SVG `<pattern>` of vertical stripes, 10.5 units wide, half `--pitch-a`, half `--pitch-b` (10 stripes across).
3. Lines: white at opacity 0.82, stroke 0.3 (0.45 on phone so they survive scaling).
4. Vignette: a full-size rect with a radial gradient, transparent to 60%, then black at 0.45 at the edge.
5. Ball: white circle r 1.05 with a 0.35 stroke in the possessing club's colour, a soft white radial glow (r 3.2) behind it.
6. Trail: the last 6 touches as a polyline in the possessing club's colour, opacity 0.75, dotted (`stroke-dasharray: 0.1 1.1`, round caps).
7. Player label: an HTML pill over the SVG (not SVG text): `rgba(11,18,32,.82)` background, 1 px border in the club colour, Barlow 600 13 px.
8. Team direction legend above the pitch with a colour dot plus the team name (not inside the pitch corners).

## Cue banner (lower third)

Layout left to right: a 92 px club-colour block with the crest (64 px), then headline (Condensed 32) over the subline (15 px `--text-2`) over the verdict row (Verified chip plus "numbers by code, wording by model, attempt N"), then a 150 px metric column (big number in club colour, label in Condensed 15 caps). Background `rgba(11,18,32,.92)`, radius 12, 20 px from the pitch edges. On phone: an 8 px colour edge instead of the crest block, headline 22 px, metric 38 px, overlapping the bottom of the pitch.

## Motion

| What | How |
| --- | --- |
| Cue banner | enter: translateY(16px) to 0 plus fade, 220 ms ease-out; exit: fade 160 ms |
| Ball | 250 ms linear tween between events, never a jump |
| Push-to-talk | state change under 50 ms, no animation that delays feedback |
| Verdict chips | no motion; a rejected moment never flashes on the main view |
| Drawer | slide up 240 ms ease-out |
| `prefers-reduced-motion` | fades only; the ball steps without a tween |

## Club identity

- Kestrel Bay (KBY): bay blue, white, sand accent. Crest `frontend/assets/crest-kby-256.png`.
- Ironvale (IVA): ember orange, charcoal, white. Crest `frontend/assets/crest-iva-256.png`.
- Meridian League mark: `frontend/assets/league-mark-256.png` (header, favicon, video end card).
- The 256 px PNGs are transparent cut-outs of the 2048 px P2 originals in `docs/assets/`. All fictional.
