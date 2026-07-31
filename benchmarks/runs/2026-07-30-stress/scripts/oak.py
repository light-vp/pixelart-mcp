"""Stress test: large oak tree in summer — 64x64, transparent background.

FOLIAGE recipe: leaf clusters (not single leaves), sphere-shade each cluster,
darkest green in the gaps, sparse bright pixels on lit clusters only.
Trunk: cylinder_upright + bark grain + root flares. Light: top_left.
"""
import asyncio, json, math, sys

import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S
from PIL import Image

OUT = f"{_REPO}/benchmarks/runs/2026-07-30-stress/oak.png"
VIEW = f"{_REPO}/benchmarks/runs/2026-07-30-stress/oak@view.png"


def chk(res):
    txt = res if isinstance(res, str) else res[0]
    assert not txt.startswith("Error"), txt
    return txt


def poly_pts(verts):
    ys = [v[1] for v in verts]
    out = set()
    for y in range(math.floor(min(ys)), math.ceil(max(ys)) + 1):
        xs = []
        n = len(verts)
        for i in range(n):
            x0, y0 = verts[i]
            x1, y1 = verts[(i + 1) % n]
            if (y0 <= y < y1) or (y1 <= y < y0):
                t = (y - y0) / (y1 - y0)
                xs.append(x0 + t * (x1 - x0))
        xs.sort()
        for j in range(0, len(xs) - 1, 2):
            for x in range(round(xs[j]), round(xs[j + 1]) + 1):
                out.add((x, y))
    return out


async def paint(points, color):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, y0 = min(xs), min(ys)
    rows = ["".join("#" if (x, y) in points else "." for x in range(x0, max(xs) + 1))
            for y in range(y0, max(ys) + 1)]
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=x0, y=y0, rows=rows,
                                                  legend={"#": color})))


async def main():
    # Stage 1 — palettes
    green = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#4e8f3a", steps=6, hue_shift_deg=18))))["ramp"]
    brown = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#7a5a38", steps=5, hue_shift_deg=18))))["ramp"]
    print("green:", green, "\nbrown:", brown)

    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=64, height=64, overwrite=True)))

    # Stage 2/3 — trunk silhouette + flats (drawn first; canopy overlaps its top)
    await paint(poly_pts([(27, 26), (37, 26), (39, 54), (40, 62), (24, 62), (25, 54)]), brown[2])
    await paint(poly_pts([(26, 50), (28, 62), (13, 62)]), brown[2])   # left root flare
    await paint(poly_pts([(38, 50), (48, 62), (36, 62)]), brown[2])   # right root flare

    # canopy backing: darkest green — this is what shows in the gaps
    for ex, ey, ew, eh in [(2, 10, 26, 20), (16, 2, 30, 20), (36, 6, 26, 20),
                           (8, 18, 26, 18), (28, 16, 28, 18), (1, 16, 16, 14)]:
        chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=ex, y=ey, width=ew, height=eh, color=green[0])))

    # leaf clusters in temp marker colors (so each gets its own sphere shade).
    # Tiered sub-ramps keep ONE global top_left light: lit upper-left clusters
    # reach paler greens, lower-right clusters stay darker. No near-white tops.
    clusters = [((5, 13, 20, 14), "#010101", green[0:5]),   # upper left, lit
                ((19, 4, 22, 16), "#020202", green[0:5]),   # top, lit
                ((39, 9, 20, 14), "#030303", green[0:4]),   # upper right, mid
                ((12, 21, 18, 12), "#040404", green[0:3]),  # lower centre, shade
                ((31, 19, 22, 14), "#050505", green[0:3]),  # lower right, shade
                ((3, 19, 12, 10), "#060606", green[0:4])]   # left lump, mid
    for (ex, ey, ew, eh), tmp, _ in clusters:
        chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=ex, y=ey, width=ew, height=eh, color=tmp)))

    # Stage 4 — shading, ONE light (top_left)
    for _, tmp, ramp in clusters:
        chk(await S.pixel_shade_region(S.ShadeRegionInput(path=OUT, mode="sphere", light="top_left",
                                                          target=tmp, ramp=ramp)))
    chk(await S.pixel_shade_region(S.ShadeRegionInput(path=OUT, mode="cylinder_upright", light="top_left",
                                                      target=brown[2], ramp=brown[0:4])))

    # Stage 5 — details
    img = Image.open(OUT).convert("RGBA")
    px = img.load()

    def hexat(x, y):
        r, g, b, a = px[x, y]
        return None if a == 0 else "#%02x%02x%02x" % (r, g, b)

    # bark grain: wavy 1px vertical lines on the trunk's mid/lit tones
    grain = []
    for gx in (27, 31, 35):
        for y in range(33, 62):
            x = gx + ((y // 5) % 2)
            if hexat(x, y) in (brown[2], brown[3]):
                grain.append(S.PixelPoint(x=x, y=y))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=grain, color=brown[1])))
    # knot
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=30, y=44, width=3, height=4, color=brown[1])))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[S.PixelPoint(x=31, y=45)], color=brown[0])))
    # crevices where root flares meet the trunk
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=26, y0=56, x1=25, y1=61, color=brown[0])))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=38, y0=56, x1=39, y1=61, color=brown[0])))
    # sparse bright pixels on the LIT (upper-left) clusters only
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=11, y=17), S.PixelPoint(x=15, y=15), S.PixelPoint(x=22, y=9),
        S.PixelPoint(x=27, y=7), S.PixelPoint(x=32, y=10), S.PixelPoint(x=8, y=23),
        S.PixelPoint(x=43, y=12)], color=green[5])))

    # Stage 6 — finish (no outline: soft foliage look)
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=VIEW, scale=8)))
    print(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))


asyncio.run(main())
