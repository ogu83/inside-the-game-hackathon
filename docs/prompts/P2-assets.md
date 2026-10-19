# Prompts: P2 original assets (club crests, league mark, hero image, thumbnail)

Image-generator prompts for the fictional Meridian League. Generate, pick the best of a few variations, then save to the paths below. P3 places them in the page; T14 and T15 use the hero image and thumbnail.

## Before you start: licence and rules

- **Commercial use:** Microsoft receives a commercial licence to the submission. Check that the generator's current terms allow commercial use of the output and that you own or may license it. Record the generator, model and date in `docs/assets/CREDITS.md`.
- **Fictional only:** no real clubs, crests, kits, sponsors, leagues, broadcasters or stadiums, and no lookalikes. If an output resembles a real crest (shape plus animal plus colours), discard it.
- **No text in the images.** Generators misspell; names are added in HTML or in the video edit. Ask for "no text, no letters, no numbers" every time.
- **Background:** most generators cannot output transparency. Ask for a plain flat background (pure white for crests) and remove it afterwards (any background-removal tool), saving PNG with transparency.
- **Consistency:** same style family for both crests (they appear side by side on the cue banner).

## Shared style line (append to every crest prompt)

> Modern flat vector sports emblem, clean geometric shapes, bold silhouette that reads at 32 pixels, two to three flat colours plus white, no gradients, no texture, no 3D, no text, no letters, no numbers, centred on a plain pure white background, generous margin, symmetrical shield or roundel composition.

## 1. Kestrel Bay FC crest

Save: `frontend/assets/crest-kby.png` (512x512, transparent) and a 64x64 copy `frontend/assets/crest-kby-64.png`.

> A football club emblem for a fictional coastal club: a stylised kestrel hovering with wings spread above three gentle wave lines of a bay, inside a rounded shield. Colours: bay blue #2F8FD8, white, sand #E9D8A6 accent. Calm, confident, coastal. [shared style line]

Variations to try: kestrel in profile diving; roundel instead of shield; waves as a single curved line.

## 2. Ironvale Athletic crest

Save: `frontend/assets/crest-iva.png` (512x512, transparent) and `frontend/assets/crest-iva-64.png`.

> A football club emblem for a fictional industrial valley club: a stylised anvil with three rising forge sparks, two simple mountain peaks behind it forming a valley, inside an angular shield. Colours: ember orange #E8833A, charcoal #2B2F36, white. Strong, energetic, hard-working. [shared style line]

Variations to try: hammer crossed over the anvil; hexagonal shield; sparks as a small flame.

## 3. Meridian League mark (optional, for the README header and video end card)

Save: `docs/assets/league-mark.png` (512x512, transparent).

> A league emblem for a fictional football league called Meridian: a circle crossed by a single vertical meridian line with a small star where they meet, suggesting a globe and a centre line of a pitch. Colours: deep navy #14213D and white with one thin gold #E0B04F accent. [shared style line]

## 4. Hero image (README header, Innovation Studio project page, video opening)

Save: `docs/assets/hero.png` (1920x1080 or wider, 16:9).

> Cinematic wide shot of a modern football stadium at dusk from a high broadcast camera angle, floodlights on, a match in progress between a team in bay blue and white kits and a team in ember orange and charcoal kits, players small in frame, crisp green pitch with mowing stripes. Subtle translucent broadcast graphics floating over the pitch: a clean lower-third panel and a small data card with abstract bars, but no readable text, no letters, no numbers, no logos, no sponsors, no advertising boards with words, no real stadium. Cool blue evening sky with warm stadium light. Photorealistic, sharp, high dynamic range.

Variations: lower camera behind one goal; close-up of a ball on the centre spot with a faint glowing data line.

## 5. YouTube thumbnail background

Save: `docs/assets/thumbnail-bg.png` (1280x720).

> Dramatic close-up of a football on a floodlit pitch at night with a soft glowing waveform line rising from it like a voice, bay blue and ember orange rim light, shallow depth of field, large empty dark area on the left third for a title. No text, no letters, no numbers, no logos, no real clubs. Photorealistic.

The title ("A co-commentator that can't lie") is added in an image editor or the video tool, not by the generator.

## 6. Player avatar silhouettes (optional)

Save: `frontend/assets/avatar-kby.png` and `frontend/assets/avatar-iva.png` (256x256, transparent).

> A minimal flat vector head-and-shoulders silhouette of a football player in a [bay blue and white | ember orange and charcoal] kit with a plain crew neck, faceless, no number, no logo, no text, on a plain pure white background. [shared style line]

## After generating

1. Remove backgrounds where needed; export PNG; keep the crest files under about 60 KB each (compress).
2. Check each crest at 32 px and 64 px next to the other: both must be recognisable and distinct.
3. Look for accidental text, letters or numbers, and for resemblance to real crests or broadcasters; regenerate if in doubt.
4. Fill in `docs/assets/CREDITS.md`: tool, model, date, prompt number, licence note.
5. Commit the files on a branch (for example `p2-assets`) so P3 can use them; I review them here before merge.
