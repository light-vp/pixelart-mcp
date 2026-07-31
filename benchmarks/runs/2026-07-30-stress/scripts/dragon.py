"""Stress test: red dragon, wings spread — 96x96, transparent background.

Pipeline: ramps -> silhouette (left half + mirror) -> flats -> one top_left
shade pass per material -> details (wing bones, scales, belly plates) -> finish.
"""
import asyncio, json, math, sys

import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S
from PIL import Image

OUT = f"{_REPO}/benchmarks/runs/2026-07-30-stress/dragon.png"
VIEW = f"{_REPO}/benchmarks/runs/2026-07-30-stress/dragon@view.png"


def chk(res):
    txt = res if isinstance(res, str) else res[0]
    assert not txt.startswith("Error"), txt
    return txt


# ---- deterministic shape rasterizers (feed pixel_paint_grid) ----

def poly_pts(verts):
    """Even-odd scanline fill of a polygon; verts = [(x, y), ...]."""
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


def bezier(p0, p1, p2, p3, t):
    u = 1 - t
    return (u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1])


def tube_pts(p0, p1, p2, p3, r0, r1):
    out = set()
    for i in range(51):
        t = i / 50.0
        x, y = bezier(p0, p1, p2, p3, t)
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


# ---- geometry (left half; mirror axis x=47.5) ----

LWING = [(46, 24), (24, 8), (2, 20), (8, 29), (5, 40), (14, 42), (16, 52),
         (24, 49), (30, 56), (36, 49), (44, 46)]
LHORN = [(41, 11), (35, 1), (38, 1), (45, 12)]
WRIST = (24, 8)
FINGERTIPS = [(5, 40), (16, 52), (30, 56)]  # bones fan out to these


async def main():
    # Stage 1 — palettes (light: top_left everywhere)
    body = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#c03028", steps=7, hue_shift_deg=12))))["ramp"]
    memb = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#e0824e", steps=5, hue_shift_deg=18))))["ramp"]
    belly = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#d8b088", steps=4, hue_shift_deg=18))))["ramp"]
    print("body:", body, "\nmemb:", memb, "\nbelly:", belly)
    B = body[3]   # body base (midtone)
    M = memb[2]   # membrane base
    P = belly[2]  # belly-plate base

    # Stage 2 — silhouette, left half in flat body base
    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=96, height=96, overwrite=True)))
    await paint(poly_pts(LWING), B)                                                     # wing
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=38, y=26, width=20, height=38, color=B)))  # body
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=43, y=18, width=10, height=10, color=B)))        # neck
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=39, y=8, width=18, height=13, color=B)))   # skull
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=43, y=16, width=10, height=8, color=B)))   # jaw
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=38, y=54, width=10, height=12, color=B)))  # thigh
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=40, y=64, width=5, height=7, color=B)))          # shin
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=37, y=69, width=8, height=5, color=B)))    # foot

    # Stage 3 — flats (still left half / symmetric center)
    await paint(poly_pts(LWING), M)                              # membrane fill
    arm = set()                                                  # arm along leading edge, body color
    for a, b in [((46, 24), WRIST), (WRIST, (2, 20))]:
        for i in range(25):
            t = i / 24.0
            arm |= disc_pts(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, 1.7)
    wing_mask = poly_pts(LWING)
    await paint(arm & wing_mask, B)
    await paint(poly_pts(LHORN), P)                              # horns in bone color
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=44, y=28, width=8, height=34, color=P)))  # belly band
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=45, y=22, width=6, height=6, color=P)))         # neck belly

    # Mirror left -> right, then add the asymmetric tail
    chk(await S.pixel_mirror_canvas(S.MirrorInput(path=OUT, direction="left_to_right")))
    tail = tube_pts((50, 58), (72, 66), (76, 82), (58, 86), 4.2, 1.2)
    await paint(tail, B)
    # spade tip: dart/arrowhead pointing down-left, tail enters at the notch
    await paint(poly_pts([(44, 90), (58, 79), (54, 86), (62, 93)]), B)

    # Stage 4 — shading, ONE light (top_left)
    chk(await S.pixel_shade_region(S.ShadeRegionInput(path=OUT, mode="bevel", light="top_left",
                                                      target=B, ramp=body, levels=2, band_px=1)))
    chk(await S.pixel_shade_region(S.ShadeRegionInput(path=OUT, mode="bevel", light="top_left",
                                                      target=M, ramp=memb, levels=2, band_px=1)))
    chk(await S.pixel_shade_region(S.ShadeRegionInput(path=OUT, mode="cylinder_upright", light="top_left",
                                                      target=P, ramp=belly)))

    # Stage 5 — details
    # wing finger bones, 1px darker, radiating from each wrist
    for tip in FINGERTIPS:
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=WRIST[0], y0=WRIST[1],
                                                    x1=tip[0], y1=tip[1], color=memb[1])))
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=95 - WRIST[0], y0=WRIST[1],
                                                    x1=95 - tip[0], y1=tip[1], color=memb[1])))

    img = Image.open(OUT).convert("RGBA")
    px = img.load()

    def hexat(x, y):
        r, g, b, a = px[x, y]
        return None if a == 0 else "#%02x%02x%02x" % (r, g, b)

    # scale texture: sparse staggered darker pixels ONLY where the torso is midtone
    scales = []
    for y in range(24, 71):
        for x in range(34, 63):
            if hexat(x, y) == B and y % 3 == 0 and (x + (y // 3) * 2) % 3 == 0:
                scales.append(S.PixelPoint(x=x, y=y))
    print("scale pixels:", len(scales))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=scales, color=body[2])))

    # belly plate separators: 1px darkest-belly lines across the belly band
    seps = []
    for y in range(30, 61, 4):
        for x in range(42, 54):
            if hexat(x, y) in (belly[0], belly[1], belly[2], belly[3]):
                seps.append(S.PixelPoint(x=x, y=y))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=seps, color=belly[0])))

    # face: eyes + nostrils
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=43, y=13), S.PixelPoint(x=44, y=13),
        S.PixelPoint(x=51, y=13), S.PixelPoint(x=52, y=13)], color=body[0])))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=46, y=21), S.PixelPoint(x=49, y=21)], color=body[1])))
    # claws, 2px each
    claw_pts = []
    for cx, cy in [(37, 74), (40, 75), (43, 74)]:
        for mx in (cx, 95 - cx):
            claw_pts += [S.PixelPoint(x=mx, y=cy), S.PixelPoint(x=mx, y=cy + 1)]
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=claw_pts, color=belly[3])))

    # Stage 6 — finish: solid outline in the darkest body step (keeps budget)
    chk(await S.pixel_outline_sprite(S.OutlineInput(path=OUT, mode="solid", color=body[0], corners=False)))
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=VIEW, scale=6)))
    print(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))


asyncio.run(main())
