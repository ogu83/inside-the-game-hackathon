"""Builds the 2-minute demo video from the takes, slides and narration parts (see docs/video/VIDEO-GUIDE.md)."""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(sys.argv[1])
VID = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.home() / "Videos"  # folder with the takes and narration
B = VID / "build"
B.mkdir(exist_ok=True)
OUT = VID / "MatchdayCompanion.mp4"
FONT = "C:/Windows/Fonts/bahnschrift.ttf"
V = "crop=1712:1008:6:6,scale=1834:1080,pad=1920:1080:43:0:color=0x0B1220,fps=30,format=yuv420p,setsar=1"
AUD = "aresample=48000,aformat=channel_layouts=stereo"


def run(args):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-3000:])


def caption(name, text, label=None):
    img = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, 46)
    try:
        f.set_variation_by_name("SemiBold")
    except Exception:
        pass
    w = d.textlength(text, font=f)
    x, y = (1920 - w) / 2, 930
    d.rounded_rectangle([x - 28, y - 18, x + w + 28, y + 66], radius=14, fill=(11, 18, 32, 225))
    d.text((x, y), text, font=f, fill=(238, 242, 247, 255))
    if label:
        lf = ImageFont.truetype(FONT, 28)
        lw = d.textlength(label, font=lf)
        d.rounded_rectangle([(1920 - lw) / 2 - 16, y - 66, (1920 + lw) / 2 + 16, y - 26], radius=10, fill=(47, 143, 216, 235))
        d.text(((1920 - lw) / 2, y - 62), label, font=lf, fill=(7, 20, 34, 255))
    img.save(B / f"{name}.png")


caption("cap_q", '"How is my player doing?"', "FAN ASKS, HOLDING HOLD TO TALK")
caption("cap_tr1", "Kestrel Bay built a 12-pass sequence lasting 53 seconds, with 7 players involved;", "TURKISH, ANALYST DEPTH")
caption("cap_tr2", "the ball moved 55.6 metres and Caden Holloway stood out with 3 passes.", "TURKISH, ANALYST DEPTH")
caption("cap_sk", "\"Skor ne?\"  (What is the score?)", "FAN ASKS IN TURKISH")
caption("cap_ska", "Minute 6: Kestrel Bay 0, Ironvale 0.", "ANSWER, VERIFIED AND SPOKEN")


def take(name, src, start, dur, mute=False):
    a = ["-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=48000:cl=stereo"] if mute else []
    amap = ["-map", "1:a"] if mute else ["-map", "0:a"]
    run(["-ss", str(start), "-t", str(dur), "-i", str(VID / src), *a, "-map", "0:v", *amap, "-vf", V, "-af", AUD,
         "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "aac", "-b:a", "192k", "-shortest", str(B / f"{name}.mp4")])


def still(name, png, dur):
    run(["-loop", "1", "-t", str(dur), "-i", str(png), "-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=48000:cl=stereo",
         "-vf", "scale=1920:1080,fps=30,format=yuv420p,setsar=1", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-tune", "stillimage",
         "-c:a", "aac", "-b:a", "192k", "-shortest", str(B / f"{name}.mp4")])


# Segments (seconds in the source files), mapped from the final takes on 2026-10-19
take("s1", "TakeA.mkv", 0, 13.6, mute=True)          # rejected planted claim
take("s2", "TakeB.mkv", 89.9, 30.6)                   # 22-pass cue spoken, then pitch under narration 2
take("s3a", "TakeB.mkv", 232.5, 8.0)                  # line speaking, fan asks, barge-in, "Got it"
take("s3b", "TakeB.mkv", 247.6, 12.0)                 # verified answer card and spoken answer (thinking cut)
take("s4", "TakeB.mkv", 329.0, 13.8)                  # switch to Turkish Analyst, Turkish line
take("s5a", "TakeB.mkv", 357.8, 3.2)                  # fan holds to talk in Turkish (voice from SkorNe.mp3)
take("s5b", "TakeB.mkv", 365.0, 5.4)                  # Turkish answer, spoken
take("s6a", "TakeC.mkv", 2, 6, mute=True)            # Foundry trace tree
take("s6b", "TakeC.mkv", 46, 3.5, mute=True)         # Foundry graph view
still("s7", REPO / "docs/video/scene4-numbers.png", 7.5)
still("s8", REPO / "docs/video/scene5-architecture.png", 5.5)
still("s9", REPO / "docs/video/scene5-endcard.png", 10.3)

order = ["s1", "s2", "s3a", "s3b", "s4", "s5a", "s5b", "s6a", "s6b", "s7", "s8", "s9"]
(B / "list.txt").write_text("".join(f"file '{(B / f'{n}.mp4').as_posix()}'\n" for n in order), encoding="utf-8")
run(["-f", "concat", "-safe", "0", "-i", str(B / "list.txt"), "-c", "copy", str(B / "joined.mp4")])

# Narration slots and ducking windows (global seconds in the joined video)
parts = [("Part1.mp3", 0.4), ("Part2.mp3", 24.0), ("Part3.mp3", 64.5), ("SkorNe.mp3", 79.8), ("Part4.mp3", 86.9), ("Part5.mp3", 103.9)]
duck = "volume='if(between(t,23.9,47.2),0.45,if(between(t,64.2,78.0),0.55,2.5))':eval=frame"
caps = [("cap_q", 47.5, 52.0), ("cap_tr1", 66.0, 71.3), ("cap_tr2", 71.3, 77.6), ("cap_sk", 79.6, 82.6), ("cap_ska", 83.0, 86.4)]
END = 119.4

inputs = ["-i", str(B / "joined.mp4")]
for f, _ in parts:
    inputs += ["-i", str(VID / f)]
for c, _, _ in caps:
    inputs += ["-i", str(B / f"{c}.png")]
fc = []
v = "[0:v]"
for i, (c, t0, t1) in enumerate(caps):
    idx = 1 + len(parts) + i
    fc.append(f"{v}[{idx}:v]overlay=0:0:enable='between(t,{t0},{t1})'[v{i}]")
    v = f"[v{i}]"
fc.append(f"{v}fade=t=in:st=0:d=0.4,fade=t=out:st={END - 0.5}:d=0.5[vout]")
fc.append(f"[0:a]{duck}[app]")
mix = ["[app]"]
for i, (_, t) in enumerate(parts):
    ms = int(t * 1000)
    fc.append(f"[{i + 1}:a]{AUD},adelay={ms}|{ms},volume=1.25[n{i}]")
    mix.append(f"[n{i}]")
fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.95[aout]")
run([*inputs, "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
     "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(OUT)])
print("wrote", OUT)
