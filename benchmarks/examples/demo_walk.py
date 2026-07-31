"""Benchmark demo: an 8-frame walk cycle generated from ONE drawing (v0.6.0).

The point of the rig layer: the character is drawn once and the frames are
composited from those pixels, so eight frames cost one drawing. The limbs live
in a parts bin off to the right of the sprite — a part is a rectangle of source
pixels, so limbs drawn on top of each other could never be boxed apart, but a
side view needs them to overlap once placed. Draw apart, place together.
"""
import asyncio, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from PIL import Image, ImageDraw
from pixelart_mcp import server as S

HERE = f"{_REPO}/benchmarks/examples"
SHEET = f"{HERE}/walker.png"
RIG = f"{HERE}/walker.rig.json"

SKIN, SKIN_D = "#eec39a", "#b86f50"
TUNIC, TUNIC_D = "#3978a8", "#28527e"
TROUSER, TROUSER_D = "#5d4a3a", "#3d2f26"
BOOT, BOOT_D = "#333c57", "#23293c"
HAIR, LINE = "#a24b3a", "#1a1c2c"


def draw_sheet():
    """48x48 parts sheet: body in place (left), limbs in a bin (right)."""
    img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = lambda x0, y0, x1, y1, c: d.rectangle([x0, y0, x1, y1], fill=c)

    # body, at its frame position
    box(11, 5, 20, 12, SKIN)
    box(10, 2, 21, 5, HAIR)
    box(10, 4, 12, 8, HAIR)
    box(18, 7, 19, 8, LINE)          # eye, facing right
    box(11, 11, 20, 12, SKIN_D)      # jaw shadow
    box(11, 13, 20, 30, TUNIC)       # torso runs over the hips
    box(11, 13, 20, 14, TUNIC_D)     # collar
    box(11, 26, 20, 28, TUNIC_D)     # belt
    box(11, 15, 12, 26, TUNIC_D)     # far-side form shadow

    # parts bin — back limbs one ramp step darker so depth reads on overlap
    box(33, 0, 36, 12, TROUSER_D); box(32, 12, 37, 17, BOOT_D)    # leg_back
    box(40, 0, 43, 12, TROUSER);   box(39, 12, 44, 17, BOOT)      # leg_front
    box(32, 20, 35, 28, TUNIC_D);  box(32, 28, 35, 32, SKIN_D)    # arm_back
    box(38, 20, 41, 28, TUNIC);    box(38, 28, 41, 32, SKIN)      # arm_front
    img.save(SHEET)


PARTS = [
    {"name": "arm_back",  "x": 32, "y": 20, "width": 4, "height": 13,
     "at_x": 10, "at_y": 15, "z": 0, "anchor": "center"},
    {"name": "leg_back",  "x": 32, "y": 0, "width": 6, "height": 18,
     "at_x": 12, "at_y": 28, "z": 1},
    {"name": "leg_front", "x": 39, "y": 0, "width": 6, "height": 18,
     "at_x": 14, "at_y": 28, "z": 2},
    {"name": "torso",     "x": 11, "y": 13, "width": 10, "height": 18, "z": 3},
    {"name": "head",      "x": 10, "y": 2, "width": 12, "height": 11, "z": 4,
     "anchor": "center"},
    {"name": "arm_front", "x": 38, "y": 20, "width": 4, "height": 13,
     "at_x": 17, "at_y": 15, "z": 5, "anchor": "center"},
]


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    draw_sheet()

    chk(await S.pixel_define_rig(S.DefineRigInput(
        rig_path=RIG, source=SHEET, parts=[S.RigPart(**p) for p in PARTS],
        frame_width=32, frame_height=48, notes="side-on walker demo",
        overwrite=True, preview=False)))

    out = chk(await S.pixel_render_motion(S.RenderMotionInput(
        rig_path=RIG, out_dir=f"{HERE}/walk", motion="walk", prefix="walk",
        overwrite=True, preview=False)))
    import json
    frames = json.loads(out)["frame_paths"]

    chk(await S.pixel_export_gif(S.ExportGifInput(
        frame_paths=frames, out_path=f"{HERE}/walk@6x.gif", duration_ms=110, scale=6)))
    chk(await S.pixel_export_spritesheet(S.ExportSpritesheetInput(
        frame_paths=frames, out_path=f"{HERE}/walk_sheet.png")))
    print(f"walker.png -> 8 frames -> walk@6x.gif  ({len(PARTS)} parts, 1 drawing)")


asyncio.run(main())
