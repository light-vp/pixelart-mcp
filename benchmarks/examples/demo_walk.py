"""Benchmark demo: an 8-frame walk cycle generated from ONE drawing (v0.7.0).

The point of the rig layer: the character is drawn once and the frames are
composited from those pixels, so eight frames cost one drawing. The limbs live
in a parts bin off to the right of the sprite — a part is a rectangle of source
pixels, so limbs drawn on top of each other could never be boxed apart, but a
side view needs them to overlap once placed. Draw apart, place together.

Limbs are two segments joined at the knee/elbow. The walk preset swings the
upper segments from the hip and shoulder and folds the lower ones, and ground
lock keeps the planted foot on the floor — the body bob is not keyed at all.
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
    """48x48 parts sheet: body in place (left), limb segments in a bin (right)."""
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

    # parts bin — back limbs one ramp step darker so depth reads on overlap.
    # Each limb is two segments: the upper hangs from the hip/shoulder, the
    # lower from the knee/elbow, so the joint can fold.
    def thigh(x, c, cd):
        box(x, 0, x + 3, 8, c); box(x, 0, x, 8, cd)
    def shin(x, c, cd, boot, boot_d):
        box(x, 0, x + 3, 7, c); box(x, 0, x, 7, cd)
        box(x, 8, x + 5, 10, boot); box(x, 10, x + 5, 10, boot_d)
    def upper_arm(x, c, cd):
        box(x, 14, x + 3, 21, c); box(x, 14, x, 21, cd)
    def forearm(x, c, skin):
        box(x, 14, x + 3, 17, c); box(x, 18, x + 3, 20, skin)

    thigh(24, TROUSER_D, TROUSER_D);      shin(29, TROUSER_D, TROUSER_D, BOOT_D, LINE)
    thigh(36, TROUSER, TROUSER_D);        shin(41, TROUSER, TROUSER_D, BOOT, BOOT_D)
    upper_arm(24, TUNIC_D, TUNIC_D);      forearm(29, TUNIC_D, SKIN_D)
    upper_arm(34, TUNIC, TUNIC);          forearm(39, TUNIC, SKIN)
    img.save(SHEET)


# Upper segments hang from the hip/shoulder (default pivot: top-center). Lower
# segments only name their parent: with no at_x/at_y their joint snaps onto the
# parent's bottom row, so the knee/elbow pixel is shared and never opens.
PARTS = [
    {"name": "arm_back",      "x": 24, "y": 14, "width": 4, "height": 8,
     "at_x": 10, "at_y": 15, "z": 0},
    {"name": "forearm_back",  "x": 29, "y": 14, "width": 4, "height": 7,
     "z": 0, "parent": "arm_back"},
    {"name": "leg_back",      "x": 24, "y": 0, "width": 4, "height": 9,
     "at_x": 12, "at_y": 27, "z": 1},
    {"name": "shin_back",     "x": 29, "y": 0, "width": 6, "height": 11,
     "z": 1, "pivot_x": 2, "parent": "leg_back"},
    {"name": "leg_front",     "x": 36, "y": 0, "width": 4, "height": 9,
     "at_x": 15, "at_y": 27, "z": 2},
    {"name": "shin_front",    "x": 41, "y": 0, "width": 6, "height": 11,
     "z": 2, "pivot_x": 2, "parent": "leg_front"},
    {"name": "torso",         "x": 11, "y": 13, "width": 10, "height": 18, "z": 3},
    {"name": "head",          "x": 10, "y": 2, "width": 12, "height": 11, "z": 4,
     "anchor": "center"},
    {"name": "arm_front",     "x": 34, "y": 14, "width": 4, "height": 8,
     "at_x": 16, "at_y": 15, "z": 5},
    {"name": "forearm_front", "x": 39, "y": 14, "width": 4, "height": 7,
     "z": 5, "parent": "arm_front"},
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
