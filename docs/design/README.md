# Design (P1 output)

- Canvas (rendered mockups, private to Oguz until shared): https://claude.ai/artifact/WmraTuZ3UZf28R3QNLHxra
- `style-guide.md`: tokens, type, spacing, icons, motion, pitch recipe.
- `p3-notes.md`: the numbered change list P3 implements.
- `mockups/`: canvas sources, one per artboard:
  - `Main.dc.html`: live match, 1440x900, cue on screen, voice speaking (demo scene 1)
  - `Phone.dc.html`: the same at 390x844
  - `PushToTalk.dc.html`: the six push-to-talk states and the answer card with timing (demo scene 4)
  - `Drawer.dc.html`: agent timeline open on the planted false claim, rejected by the code check and never aired (demo scene 5)
  - `StyleGuide.dc.html`: the style guide as a board

The mockups load crests from the canvas asset store (`/_blob/...`); in the app use `frontend/assets/crest-kby-256.png`, `crest-iva-256.png` and `league-mark-256.png` instead.
