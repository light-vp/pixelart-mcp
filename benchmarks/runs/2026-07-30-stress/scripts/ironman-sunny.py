"""Stress test: 'Iron Man standing in a sunny environment', 96x96 full scene.
Pipeline: warm ramps (hue_shift 26+) -> sky/sun/hills/ground back-to-front ->
sprite on its own canvas (mirrored halves, bevel plates, emissive details,
solid outline) -> hard cast shadow -> composite -> texture."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

RUN = f"{_REPO}/benchmarks/runs/2026-07-30-stress"
OUT = f"{RUN}/ironman-sunny.png"
SPR = f"{RUN}/ironman-sunny.sprite.png"

# fixed scene colors
SKY = ["#4a72ae", "#6b93c4", "#8fb2d6", "#b6cfe3", "#dbe8ef"]  # top -> horizon
SUN_GLOW = ["#ffe9ac", "#f6d489", "transparent"]
SUN_DISC = "#fff2c8"
HILL_FAR, HILL_NEAR = "#a3b8a1", "#93ab90"
GROUND = ["#a9bd7f", "#84a45c", "#68923f"]  # far/light -> near/dark
SHADOW = "#3d5a2b"
DARK = "#2b2f3e"        # gunmetal joints / neck / slits
EYE = "#f2feff"         # near-white eye slits
ARC_RING = "#7deeff"    # arc reactor cyan ring
ARC_CORE = "#ffffff"    # brightest pixel in frame
OUTLINE = "#231a30"

# Iron Man half-rows (14 cols, mirrored to 28). R=red G=gold N=dark E=eye
HALF = [
    "..........RRRR",  # 0  helmet crown
    ".........RRRRR",
    "........RRRRRR",
    "........RRGGGG",  # 3  faceplate top
    "........RRNEEN",  # 4  dark band + glowing eye slits
    "........RRGGGG",
    "........RRGGGG",
    ".........RGGGN",  # 7  mouth slit
    "..........RGGG",  # 8  jaw
    "..........NNNN",  # 9  neck
    "...RRRRRRRRRRR",  # 10 shoulder top
    ".RRRRRRRRRRRRR",  # 11 widest
    ".RRRRRRRRRRRRR",
    ".RRRR.RRRRRRRR",  # 13 arm | gap | chest
    ".RRRR.RRRRRRRR",
    ".RRRR.RRRRRRRR",
    ".RRRR.RRRRRRRR",
    ".RRRR.RRRRRRRR",
    "..RRR.RRRRRRRR",  # 18 arm taper
    "..GGG.RRRRRRRR",  # 19 gauntlet
    "..GGG..RRRRRRR",  # 20 torso taper
    "..GGG..RRRRRRR",
    "..GGG..GGGGGGG",  # 22 ab band
    "..GGG..GGGGGGG",
    "..GGG...RRRRRR",  # 24 waist
    "..GGG...RRRRRR",
    "...GG...RRRRRR",  # 26 hand
    "...GG..RRRRRRR",  # 27 pelvis
    "...GG..RRRRRRR",
    ".......RRRRRR.",  # 29 thighs, crotch gap
    ".......RRRRRR.",
    ".......RRRRRR.",
    ".......RRRRRR.",
    ".......RRRRRR.",
    ".......RRRRRR.",
    "........RRRRR.",  # 35 taper
    "........GGGGG.",  # 36 knee
    "........GGGGG.",
    "........RRRRR.",  # 38 shin
    "........RRRRR.",
    "........RRRR..",
    "........RRRR..",
    "........RRRR..",
    "........RRRR..",
    "........RRRR..",
    "........RRRR..",
    ".......RRRRR..",  # 46 boot flare
    ".......RRRRR..",
    ".......RRRRR..",
    "......RRRRRR..",
    "......RRRRRR..",
    ".....RRRRRRR..",  # 51 foot
    ".....RRRRRRR..",
    "....RRRRRRRR..",  # 53 foot
]

PASTE_X, PASTE_Y = 34, 30  # sprite canvas -> scene


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    # Stage 1 — warm sunny ramps
    red = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#b3232c", steps=5, hue_shift_deg=26))))["ramp"]
    gold = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#d19a26", steps=5, hue_shift_deg=28))))["ramp"]
    print("red:", red, "\ngold:", gold)

    # ---------------- background ----------------
    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=96, height=96, overwrite=True)))
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=0, width=96, height=66, colors=SKY, kind="linear",
        angle_deg=90, dither="bayer4")))
    # sun top-left: dithered glow fading to transparent, then disc
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=2, y=0, width=30, height=26, colors=SUN_GLOW, kind="radial",
        center_x=16, center_y=12, radius=14, dither="bayer4")))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=11, y=7, width=10, height=10, color=SUN_DISC)))
    # distant desaturated hills, no outline
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=-12, y=56, width=64, height=22, color=HILL_FAR)))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=52, y=58, width=58, height=18, color=HILL_NEAR)))
    # ground plane
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=66, width=96, height=30, color=GROUND[1])))
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=66, width=96, height=30, colors=GROUND, kind="linear",
        angle_deg=90, dither="bayer4", target=GROUND[1])))

    # ---------------- sprite ----------------
    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=SPR, width=32, height=58, overwrite=True)))
    rows = [h + h[::-1] for h in HALF]
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=SPR, x=2, y=2, rows=rows,
        legend={"R": red[2], "G": gold[2], "N": DARK, "E": EYE})))
    # bevel-shade the plates, sun top-left
    chk(await S.pixel_shade_region(S.ShadeRegionInput(
        path=SPR, mode="bevel", light="top_left", target=red[2], ramp=red, levels=2, band_px=1)))
    chk(await S.pixel_shade_region(S.ShadeRegionInput(
        path=SPR, mode="bevel", light="top_left", target=gold[2], ramp=gold, levels=2, band_px=1)))
    # hand-authored head over the bevel output: controlled faceplate, eye band,
    # mouth slit, lit left crown / shaded right rim
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=SPR, x=10, y=2,
        rows=[
            "..hRRRRRRd..",
            ".hRRRRRRRRd.",
            "hRRRRRRRRRRd",
            "RRgGGGGGGoRd",
            "RRNEENNEENRd",
            "RRgGGGGGGoRd",
            "RRgGGGGGGoRd",
            ".RGGGNNGGGd.",
            "..oGGGGGGo..",
            "..NNNNNNNN..",
        ],
        legend={"R": red[2], "h": red[3], "d": red[1],
                "G": gold[2], "g": gold[3], "o": gold[1],
                "N": DARK, "E": EYE})))
    # panel seams (darkest red) under the pecs + ab center line
    chk(await S.pixel_draw_line(S.DrawLineInput(path=SPR, x0=9, y0=19, x1=14, y1=19, color=red[0])))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=SPR, x0=17, y0=19, x1=22, y1=19, color=red[0])))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=SPR, x0=15, y0=26, x1=16, y1=26, color=red[1])))
    # arc reactor: lit-metal ring, cyan ring, white core (brightest in frame)
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=SPR, x=13, y=15,
        rows=["..ll..", ".llll.", "llllll", "llllll", ".llll.", "..ll.."],
        legend={"l": red[3]})))
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=SPR, x=14, y=16,
        rows=[".AA.", "AWWA", "AWWA", ".AA."],
        legend={"A": ARC_RING, "W": ARC_CORE})))
    # solid dark outline (fills the 1px arm gaps as seams too)
    chk(await S.pixel_outline_sprite(S.OutlineInput(path=SPR, mode="solid", color=OUTLINE, corners=False)))

    # ---------------- composite ----------------
    # hard cast shadow away from the top-left sun (to the bottom-right)
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=44, y=82, width=36, height=6, color=SHADOW)))
    chk(await S.pixel_copy_region(S.CopyRegionInput(
        path=SPR, x=0, y=0, width=32, height=58, dest_path=OUT,
        dest_x=PASTE_X, dest_y=PASTE_Y, mode="over")))
    # contact occlusion right under the boots
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=39, y0=87, x1=48, y1=87, color=SHADOW)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=51, y0=87, x1=60, y1=87, color=SHADOW)))

    # ---------------- ground texture ----------------
    # sparse horizontal dashes, sparser with distance
    for (x, y, w, c) in [
        (14, 70, 3, GROUND[0]), (70, 71, 4, GROUND[0]),
        (30, 75, 4, GROUND[2]), (82, 76, 4, GROUND[0]), (6, 78, 4, GROUND[2]),
        (24, 82, 5, GROUND[2]), (72, 84, 5, GROUND[2]), (10, 86, 5, GROUND[2]),
        (30, 90, 6, GROUND[2]), (66, 91, 6, GROUND[2]), (14, 93, 6, GROUND[2]),
    ]:
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=x, y0=y, x1=x + w, y1=y, color=c)))
    # foreground grass tufts
    for gx, gy in [(9, 91), (25, 93), (70, 92), (87, 90)]:
        chk(await S.pixel_paint_grid(S.PaintGridInput(
            path=OUT, x=gx, y=gy,
            rows=["X..X..X", "X..X..X", ".X.X.X."],
            legend={"X": SHADOW})))

    info = json.loads(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))
    print("colors:", info.get("color_count", info))
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=OUT.replace(".png", "@view.png"), scale=6)))
    print("done")

asyncio.run(main())
