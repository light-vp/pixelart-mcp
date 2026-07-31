"""Stress test: 'Medieval knight with sword and shield', 48x64, transparent bg.
v0.3.0 craft pipeline: ramps -> silhouette/flats (left half) -> mirror ->
per-part auto-shade (one light: top_left) -> details -> selective outline ->
palette snap. Per-part shading uses near-identical color variants so each
part gets its own shade mask (color masks are canvas-wide by exact color)."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

RUN = f"{_REPO}/benchmarks/runs/2026-07-30-stress"
OUT = RUN + "/knight.png"
DARK = "#10131c"


def tweak(hex_color, delta):
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    b = max(0, min(255, b + delta))
    return f"#{r:02x}{g:02x}{b:02x}"


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    async def rect(x, y, w, h, c):
        chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=x, y=y, width=w, height=h, color=c)))

    async def ell(x, y, w, h, c):
        chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=x, y=y, width=w, height=h, color=c)))

    async def line(x0, y0, x1, y1, c):
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=x0, y0=y0, x1=x1, y1=y1, color=c)))

    async def pxs(pts, c):
        chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[S.PixelPoint(x=a, y=b) for a, b in pts], color=c)))

    async def grid(x, y, rows, legend):
        chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=x, y=y, rows=rows, legend=legend)))

    async def fill(x, y, c):
        chk(await S.pixel_flood_fill(S.FloodFillInput(path=OUT, x=x, y=y, color=c)))

    async def shade(mode, target, ramp, levels=2, band=1):
        chk(await S.pixel_shade_region(S.ShadeRegionInput(
            path=OUT, mode=mode, light="top_left", target=target, ramp=ramp,
            levels=levels, band_px=band)))

    async def rep(f, r):
        chk(await S.pixel_replace_color(S.ReplaceColorInput(path=OUT, find=f, replace=r)))

    # Stage 1 — ramps (steel hero 6, cloth red 5, leather 5 but only 3 used)
    steel = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#8fa0b4", steps=6, hue_shift_deg=10))))["ramp"]
    red = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#a83240", steps=5, hue_shift_deg=18))))["ramp"]
    lea = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#7a5230", steps=5, hue_shift_deg=15))))["ramp"]
    print("steel:", steel)
    print("red:", red)
    print("lea:", lea)

    sBase, rBase = steel[3], red[2]
    vHelm, vTorso = tweak(sBase, 1), tweak(sBase, 2)
    vPauL, vPauR = tweak(sBase, 3), tweak(sBase, 4)
    vArmL, vArmR = tweak(sBase, 5), tweak(sBase, 6)
    vLegL, vLegR, vFeet = tweak(sBase, -1), tweak(sBase, -2), tweak(sBase, -3)
    vCloth = tweak(rBase, 1)

    # Stage 2+3 — silhouette + flats, left half & symmetric center
    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=48, height=64, overwrite=True)))
    await rect(17, 44, 5, 15, vLegL)        # left greave
    await rect(15, 59, 7, 3, vFeet)         # left sabaton
    await rect(14, 19, 20, 18, vTorso)      # breastplate
    await rect(18, 20, 12, 17, vCloth)      # tabard front
    await rect(17, 37, 14, 10, vCloth)      # tabard skirt
    await rect(14, 36, 20, 3, lea[2])       # belt
    await rect(10, 25, 4, 14, vArmL)        # left arm
    await ell(10, 18, 10, 8, vPauL)         # left pauldron
    await rect(20, 16, 8, 3, DARK)          # dark shadow under helm
    await ell(17, 2, 14, 10, vHelm)         # helm dome
    await rect(17, 7, 14, 10, vHelm)        # helm body

    chk(await S.pixel_mirror_canvas(S.MirrorInput(path=OUT, direction="left_to_right")))
    await fill(34, 21, vPauR)               # right pauldron -> own shade group
    await fill(36, 30, vArmR)               # right arm
    await fill(28, 50, vLegR)               # right greave

    # Shield flats (asymmetry #1) — heater over the left arm
    await grid(4, 26, [
        "TTTTTTTTTTTTTT",
        "RffffffffffffR", "RffffffffffffR", "RffffffffffffR", "RffffffffffffR",
        "RffffffffffffR", "RffffffffffffR", "RffffffffffffR", "RffffffffffffR",
        "RffffffffffffR",
        ".RffffffffffR.", ".RffffffffffR.",
        "..RffffffffR..", "..RffffffffR..",
        "...RffffffR...",
        "....RffffR....", "....RffffR....",
        ".....RffR.....", ".....RffR.....",
        "......RR......",
    ], {"R": steel[2], "T": steel[4], "f": vCloth})

    # Stage 4 — shading, ONE light: top_left
    await shade("cylinder_upright", vHelm, steel)
    await shade("sphere", vPauL, steel)
    await shade("sphere", vPauR, steel)
    await shade("cylinder_upright", vArmL, steel)
    await shade("cylinder_upright", vArmR, steel)
    await shade("cylinder_upright", vLegL, steel)
    await shade("cylinder_upright", vLegR, steel)
    await shade("bevel", vTorso, steel, levels=2)
    await shade("bevel", vFeet, steel, levels=1)
    await shade("bevel", vCloth, red, levels=2)
    await rep(vTorso, sBase)
    await rep(vFeet, sBase)
    await rep(vCloth, rBase)

    # Material tweak: build_ramp shadows are too saturated for steel —
    # desaturate the dark steps toward blue-gray, canvas-wide.
    st = ["#20263a", "#42506a", "#5c6b8c", steel[3], steel[4], steel[5]]
    await rep(steel[0], st[0])
    await rep(steel[1], st[1])
    await rep(steel[2], st[2])
    steel = st

    # Stage 5 — details
    await grid(19, 9, ["KKKK..KKKK", "KKKK..KKKK"], {"K": DARK})   # visor slits
    await pxs([(20, 13), (22, 13), (25, 13), (27, 13)], steel[1])  # breath holes
    await line(17, 36, 33, 36, lea[3])                             # belt top edge
    await line(17, 38, 33, 38, lea[1])                             # belt bottom edge
    await rect(23, 36, 2, 2, steel[5])                             # buckle
    await line(17, 39, 30, 39, red[0])                             # AO under belt
    await pxs([(23, 44), (24, 44), (22, 45), (23, 45), (24, 45), (25, 45)], red[0])  # skirt split
    await line(17, 47, 21, 47, steel[1])                           # AO under skirt hem L
    await line(26, 47, 30, 47, steel[1])                           # AO under skirt hem R
    await line(30, 26, 37, 26, steel[1])                           # AO under right pauldron
    # shield cross emblem (painted over shaded field)
    await rect(10, 29, 2, 13, steel[5])
    await rect(7, 32, 8, 2, steel[5])
    # Sword (asymmetry #2), right side, blade up
    await pxs([(39, 4)], steel[5])
    await line(39, 5, 39, 31, steel[5])                            # lit blade edge
    await line(40, 5, 40, 31, steel[3])                            # blade body
    await rect(37, 32, 7, 1, steel[4])                             # crossguard lit
    await rect(37, 33, 7, 1, steel[1])                             # crossguard dark
    await rect(39, 34, 2, 6, lea[2])                               # grip
    await line(40, 34, 40, 39, lea[1])
    await rect(37, 34, 4, 3, sBase)                                # gauntlet fist
    await line(37, 34, 37, 36, steel[4])                           # fist lit edge
    await pxs([(40, 36), (40, 34)], steel[2])                      # fist dark side
    await pxs([(38, 35), (39, 35)], steel[2])                      # knuckle line
    await pxs([(40, 40), (39, 41)], steel[3])                      # pommel
    await pxs([(39, 40)], steel[5])
    await pxs([(40, 41)], steel[1])
    await rect(34, 37, 4, 2, "transparent")                        # trim arm stub

    # Stage 6 — finish
    chk(await S.pixel_outline_sprite(S.OutlineInput(path=OUT, mode="selective", corners=False)))
    palette = steel + red + [lea[1], lea[2], lea[3]] + [DARK]
    chk(await S.pixel_apply_palette(S.ApplyPaletteInput(path=OUT, palette=palette)))
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=RUN + "/knight@view.png", scale=8)))
    print(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))

asyncio.run(main())
