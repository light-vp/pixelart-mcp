"""Assemble every stress-run piece into one labeled contact sheet."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

RUN = Path(__file__).resolve().parent.parent
ORDER = [
    "apple", "glass-bottle", "knight", "spiderman", "ironman-sunny",
    "campfire", "chest", "sword", "oak", "skull",
    "sunset-ocean", "potion", "barrel", "dragon", "astronaut",
    "cottage", "phoenix", "koi", "pirate-ship", "ice-cave",
]
COLS = 5
CELL = 300          # art area per cell (px)
LABEL_H = 22
PAD = 8

found = [(pid, RUN / f"{pid}.png") for pid in ORDER if (RUN / f"{pid}.png").exists()]
missing = [pid for pid in ORDER if not (RUN / f"{pid}.png").exists()]
if missing:
    print("missing:", ", ".join(missing))

rows = (len(found) + COLS - 1) // COLS
W = COLS * (CELL + PAD) + PAD
H = rows * (CELL + LABEL_H + PAD) + PAD
sheet = Image.new("RGB", (W, H), (18, 18, 24))
draw = ImageDraw.Draw(sheet)
font = ImageFont.load_default()

for i, (pid, path) in enumerate(found):
    art = Image.open(path).convert("RGBA")
    scale = max(1, min(CELL // art.width, CELL // art.height))
    scaled = art.resize((art.width * scale, art.height * scale), Image.Resampling.NEAREST)
    cx = PAD + (i % COLS) * (CELL + PAD)
    cy = PAD + (i // COLS) * (CELL + LABEL_H + PAD)
    # checkerboard backdrop so transparency reads
    cellbg = Image.new("RGBA", (CELL, CELL), (52, 52, 60, 255))
    cbd = ImageDraw.Draw(cellbg)
    for by in range(0, CELL, 12):
        for bx in range(0, CELL, 12):
            if (bx // 12 + by // 12) % 2 == 0:
                cbd.rectangle([bx, by, bx + 11, by + 11], fill=(62, 62, 70, 255))
    cellbg.alpha_composite(scaled, ((CELL - scaled.width) // 2, (CELL - scaled.height) // 2))
    sheet.paste(cellbg.convert("RGB"), (cx, cy))
    label = f"{pid}  {art.width}x{art.height} @{scale}x"
    draw.text((cx + 2, cy + CELL + 5), label, fill=(210, 210, 220), font=font)

out = RUN / "contact-sheet.png"
sheet.save(out)
print(f"wrote {out} ({len(found)} pieces, {W}x{H})")
