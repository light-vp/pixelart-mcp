"""Stress test: 'Spider-Man, standing', 48x64, transparent bg.
v0.3.0 craft pipeline: ramps -> flats (left half) -> mirror -> per-part
auto-shade (light top_left, per-part color variants) -> details (eyes,
curvature-following webbing, emblem) -> selective outline -> palette snap."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

RUN = f"{_REPO}/benchmarks/runs/2026-07-30-stress"
OUT = RUN + "/spiderman.png"
WHITE = "#f4f6f8"
K = "#101018"


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

    # Stage 1 — ramps (red hero 6, blue 5)
    red = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#c62f35", steps=6, hue_shift_deg=18))))["ramp"]
    blue = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#2f55b0", steps=5, hue_shift_deg=18))))["ramp"]
    print("red:", red)
    print("blue:", blue)

    rB, bB = red[3], blue[2]
    web = red[1]  # darker red for web lines
    vHead, vTorso = tweak(rB, 1), tweak(rB, 2)
    vArmL, vArmR = tweak(rB, 3), tweak(rB, 4)
    vBootL, vBootR = tweak(rB, -1), tweak(rB, -2)
    vSides, vHips = tweak(bB, 1), tweak(bB, 2)
    vLegL, vLegR = tweak(bB, -1), tweak(bB, -2)

    # Stage 2+3 — flats, left half & symmetric center
    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=48, height=64, overwrite=True)))
    await rect(17, 34, 14, 5, vHips)        # pelvis (blue)
    await rect(18, 38, 5, 13, vLegL)        # left leg (blue)
    await rect(18, 50, 5, 7, vBootL)        # left boot shin (red)
    await rect(17, 57, 6, 3, vBootL)        # left foot flare
    await rect(16, 18, 16, 16, vTorso)      # torso (red)
    await rect(16, 21, 2, 13, vSides)       # blue side panel
    await pxs([(16, 18), (17, 18), (16, 19)], "transparent")  # shoulder slope
    await rect(16, 30, 1, 4, "transparent")                   # waist taper
    await rect(21, 15, 6, 3, rB)            # neck
    await ell(12, 18, 4, 5, vArmL)          # deltoid
    await rect(12, 22, 3, 14, vArmL)        # arm hanging
    await rect(11, 36, 4, 5, vArmL)         # fist
    await ell(18, 2, 12, 14, vHead)         # head

    chk(await S.pixel_mirror_canvas(S.MirrorInput(path=OUT, direction="left_to_right")))
    await fill(34, 30, vArmR)
    await fill(27, 45, vLegR)
    await fill(27, 53, vBootR)

    # Stage 4 — shading, ONE light: top_left.
    # Limbs get SHORT ramp slices: fewer cylinder bands = less candy-striping.
    await shade("sphere", vHead, red)
    await shade("cylinder_upright", vTorso, red[1:5])
    await shade("bevel", vSides, blue, levels=1)
    await shade("cylinder_upright", vArmL, red[2:5])
    await shade("cylinder_upright", vArmR, red[2:5])
    await shade("cylinder_upright", vHips, blue[1:4])
    await shade("cylinder_upright", vLegL, blue[0:4])
    await shade("cylinder_upright", vLegR, blue[0:4])
    await shade("cylinder_upright", vBootL, red[1:4])
    await shade("cylinder_upright", vBootR, red[1:4])
    await rep(vSides, bB)

    # Material tweak: pull the built ramps' magenta/indigo darks back toward
    # crimson and navy, canvas-wide.
    newred = ["#360b16", "#77161f", "#a02028", red[3], red[4], red[5]]
    newblue = ["#16203f", "#24387a", blue[2], blue[3], blue[4]]
    for old, new in list(zip(red, newred)) + list(zip(blue, newblue)):
        if old != new:
            await rep(old, new)
    red, blue = newred, newblue
    web = red[1]

    # Stage 5 — details
    # Mask: webbing spokes/arcs following the dome + big bordered eyes
    await grid(18, 2, [
        ".....ww.....",
        "...w.ww.w...",
        "..w..ww..w..",
        ".KKK....KKK.",
        "KWWWK..KWWWK",
        "KWWWWKKWWWWK",
        "KWWWWKKWWWWK",
        ".KWWWKKWWWK.",
        ".KWWK..KWWK.",
        "..KK....KK..",
        "..w..ww..w..",
        ".w...ww...w.",
        "..ww.ww.ww..",
        "....wwww....",
    ], {"K": K, "W": WHITE, "w": web})
    # Torso webbing: center spokes + arcs bowing with the chest
    await grid(18, 18, [
        "ww...ww...ww",
        "..ww.ww.ww..",
        "..w.wwww.w..",
        "ww.w.ww.w.ww",
        "..ww.ww.ww..",
        "..w.wwww.w..",
        ".w...ww...w.",
        ".w...ww...w.",
        ".w...ww...w.",
        ".ww..ww..ww.",
    ], {"w": web})
    # Spider emblem
    await pxs([(23, 22), (24, 22), (23, 23), (24, 23), (23, 24), (24, 24)], K)
    await pxs([(22, 21), (25, 21), (21, 22), (26, 22), (21, 24), (26, 24), (22, 25), (25, 25)], K)
    # AO + suit seams
    await line(21, 16, 26, 16, red[1])                  # chin shadow on neck
    await line(11, 35, 14, 35, red[1])                  # left glove cuff
    await line(33, 35, 36, 35, red[1])                  # right glove cuff
    await pxs([(23, 37), (24, 37)], blue[1])            # crotch AO
    await pxs([(20, 49), (27, 49)], red[3])             # boot-top V points

    # Stage 6 — finish
    chk(await S.pixel_outline_sprite(S.OutlineInput(path=OUT, mode="selective", corners=False)))
    palette = red + blue + [WHITE, K]
    chk(await S.pixel_apply_palette(S.ApplyPaletteInput(path=OUT, palette=palette)))
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=RUN + "/spiderman@view.png", scale=8)))
    print(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))

asyncio.run(main())
