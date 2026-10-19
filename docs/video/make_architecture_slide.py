"""Architecture slide (1920x1080) in the app's floodlight style, matching docs/architecture.md."""
import sys
from PIL import Image, ImageDraw, ImageFont

root = sys.argv[1]
W, H = 1920, 1080
BG, PANEL, LINE, TEXT, MUTED = (11, 18, 32), (18, 27, 46), (52, 66, 96), (238, 242, 247), (154, 167, 187)
GREEN, RED, KBY, IVA, GOLD, INFO = (61, 214, 140), (255, 93, 108), (47, 143, 216), (232, 131, 58), (224, 176, 79), (122, 180, 255)
FONT = "C:/Windows/Fonts/bahnschrift.ttf"


def font(size, style="Regular"):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name(style)
    except Exception:
        pass
    return f


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
mark = Image.open(f"{root}/frontend/assets/league-mark-256.png").convert("RGBA").resize((64, 64))
img.paste(mark, (90, 60), mark)
d.text((172, 62), "How it works", font=font(50, "Bold Condensed"), fill=TEXT)
d.text((174, 118), "Four Microsoft Foundry agents, numbers checked by code, every spoken word audited", font=font(26, "SemiLight"), fill=MUTED)


def box(x, y, w, h, title, sub, accent):
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=PANEL, outline=accent, width=3)
    d.text((x + 22, y + 16), title, font=font(30, "SemiBold"), fill=TEXT)
    yy = y + 58
    for line in sub:
        d.text((x + 22, yy), line, font=font(22, "SemiLight"), fill=MUTED)
        yy += 30


def arrow(x1, y1, x2, y2, color=LINE):
    d.line([x1, y1, x2, y2], fill=color, width=4)
    if x2 > x1:
        d.polygon([(x2, y2), (x2 - 16, y2 - 9), (x2 - 16, y2 + 9)], fill=color)
    elif y2 > y1:
        d.polygon([(x2, y2), (x2 - 9, y2 - 16), (x2 + 9, y2 - 16)], fill=color)
    else:
        d.polygon([(x2, y2), (x2 - 9, y2 + 16), (x2 + 9, y2 + 16)], fill=color)


# Row 1: the broadcast pipeline
y = 210
box(90, y, 300, 170, "Synthetic match", ["seeded 90-minute feed", "fictional Meridian League"], MUTED)
arrow(390, y + 85, 450, y + 85)
box(450, y, 300, 170, "Match ledger", ["metrics computed by code", "ledger tools over MCP"], GOLD)
arrow(750, y + 85, 810, y + 85)
# Foundry agents group
gx, gy, gw, gh = 810, 180, 760, 380
d.rounded_rectangle([gx, gy, gx + gw, gy + gh], radius=26, outline=KBY, width=2)
d.text((gx + 24, gy + 14), "Microsoft Foundry agents (Agent Framework workflow)", font=font(24, "SemiBold"), fill=INFO)
ax = gx + 30
box(ax, gy + 60, 220, 130, "Analyst", ["picks the moment", "say or skip"], KBY)
arrow(ax + 220, gy + 125, ax + 260, gy + 125)
box(ax + 260, gy + 60, 220, 130, "Commentator", ["writes the claim", "cites ledger keys"], KBY)
arrow(ax + 480, gy + 125, ax + 500, gy + 125)
box(ax + 500, gy + 60, 220, 130, "Fact-Checker", ["1. code: numbers", "2. model: wording"], GREEN)
d.text((ax, gy + 202), "rejected: rewrite once, then drop", font=font(22, "SemiLight"), fill=RED)
d.line([ax + 610, gy + 190, ax + 610, gy + 215], fill=RED, width=3)
d.line([ax + 370, gy + 215, ax + 610, gy + 215], fill=RED, width=3)
arrow(ax + 370, gy + 215, ax + 370, gy + 192, RED)
box(ax + 260, gy + 240, 460, 120, "Producer", ["cue + fan narrative per club, player, depth", "English and Turkish, numbers re-checked"], KBY)
arrow(ax + 610, gy + 190, ax + 610, gy + 238, GREEN)
# Output
arrow(gx + gw, gy + 300, 1600, gy + 300)
box(1600, 210, 260, 170, "20 s delay", ["verified in time,", "or dropped", "(never shown late)"], GOLD)
box(1600, 420, 260, 170, "On air", ["broadcast cue", "Voice Live verbatim", "speech audited"], GREEN)
arrow(1730, 380, 1730, 418)

# Row 2: fan questions
y2 = 660
box(90, y2, 300, 170, "Fan holds to talk", ["Voice Live listens", "barge-in stops the voice"], IVA)
arrow(390, y2 + 85, 450, y2 + 85)
box(450, y2, 360, 170, "Q&A agent", ["calls ledger tools over MCP", "same number checks"], KBY)
arrow(810, y2 + 85, 870, y2 + 85)
box(870, y2, 300, 170, "Spoken answer", ["verified or", "\"I don't have data\""], GREEN)
arrow(600, 380, 600, y2 - 2, GOLD)

# Footer: platform
d.rounded_rectangle([1240, 660, 1850, 830], radius=18, fill=PANEL, outline=LINE, width=2)
d.text((1262, 676), "Platform", font=font(30, "SemiBold"), fill=TEXT)
for i, line in enumerate(["Foundry tracing in Application Insights", "Foundry cloud evaluation, hosted agent", "Azure Container Apps, managed identity"]):
    d.text((1262, 722 + i * 32), line, font=font(22, "SemiLight"), fill=MUTED)
d.text((90, H - 90), "Every statistic comes from deterministic code; agents only cite ledger keys.", font=font(28, "SemiLight"), fill=MUTED)
img.save(f"{root}/docs/video/scene5-architecture.png", optimize=True)
print("ok")
