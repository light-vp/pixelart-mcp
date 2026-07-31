"""Stress test: phoenix rising, wings spread — 64x64, transparent background.

FIRE recipe: white-hot core -> yellow -> orange -> deep red, radial, NO outline,
NO black. Head/beak read as darkest-red negative space; detached ember pixels.
"""
import asyncio, json, math, sys

import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

OUT = f"{_REPO}/benchmarks/runs/2026-07-30-stress/phoenix.png"
VIEW = f"{_REPO}/benchmarks/runs/2026-07-30-stress/phoenix@view.png"


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


def disc_pts(cx, cy, r):
    out = set()
    for y in range(math.floor(cy - r), math.ceil(cy + r) + 1):
        for x in range(math.floor(cx - r), math.ceil(cx + r) + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                out.add((x, y))
    return out


def tube_pts(p0, p1, p2, p3, r0, r1):
    out = set()
    for i in range(51):
        t = i / 50.0
        u = 1 - t
        x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
        out |= disc_pts(x, y, r0 + (r1 - r0) * t)
    return out


async def paint(points, color):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, y0 = min(xs), min(ys)
    rows = ["".join("#" if (x, y) in points else "." for x in range(x0, max(xs) + 1))
            for y in range(y0, max(ys) + 1)]
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=x0, y=y0, rows=rows,
                                                  legend={"#": color})))


# left wing: leading edge shoulder->tip, trailing edge with flame licks
LWING = [(29, 24), (16, 10), (4, 4), (9, 12), (6, 20), (13, 18), (11, 28),
         (17, 24), (16, 34), (22, 28), (21, 38), (26, 32), (29, 33)]


async def main():
    # Stage 1 — fire ramp (dark deep-red -> white-hot)
    fire = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#f07020", steps=7, hue_shift_deg=12))))["ramp"]
    # FIRE-recipe correction: build_ramp desaturates highlights toward beige,
    # but fire must stay vivid white -> yellow -> orange. Keep the deep-red dark
    # half, splice vivid hot steps on top.
    fire[3:] = ["#f57f1a", "#ffae2a", "#ffd94e", "#fff8dc"]
    print("fire:", fire)
    F = fire[3]

    # Stage 2/3 — silhouette as ONE flat flame mass (left half, then mirror)
    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=64, height=64, overwrite=True)))
    await paint(poly_pts(LWING), F)
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=27, y=22, width=10, height=18, color=F)))  # body
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=28, y=14, width=8, height=8, color=F)))    # head
    chk(await S.pixel_mirror_canvas(S.MirrorInput(path=OUT, direction="left_to_right")))

    # asymmetric flame parts: crest licks + three trailing tail plumes
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=28, y=9, rows=[
        "##......",
        "##....##",
        ".##...##",
        ".##..##.",
        "..#..##."], legend={"#": F})))
    await paint(tube_pts((29, 38), (22, 46), (27, 55), (23, 62), 1.8, 0.8), F)
    await paint(tube_pts((32, 38), (33, 48), (29, 56), (31, 60), 2.0, 0.9), F)
    await paint(tube_pts((35, 38), (41, 48), (37, 56), (39, 58), 1.8, 0.8), F)

    # Stage 4 — the FIRE gradient: radial from the chest, ends deep red, no outline
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=0, width=64, height=64,
        colors=[fire[6], fire[5], fire[4], fire[3], fire[2], fire[1]],
        kind="radial", center_x=31, center_y=26, radius=36,
        dither="checker", paint_over="opaque")))

    # Stage 5 — details: dark beak + eye as negative space against the pale head
    await paint(poly_pts([(33, 17), (39, 19), (33, 21)]), fire[0])
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[S.PixelPoint(x=30, y=17)], color=fire[0])))
    # detached floating embers (clear of the silhouette)
    for x, y, c in [(7, 36, 4), (7, 35, 5), (56, 36, 4), (20, 4, 5), (43, 4, 4),
                    (2, 10, 4), (61, 10, 4), (18, 54, 5), (18, 53, 4), (44, 52, 5)]:
        chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[S.PixelPoint(x=x, y=y)], color=fire[c])))

    # Stage 6 — finish (deliberately NO outline pass)
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=VIEW, scale=8)))
    print(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))


asyncio.run(main())
