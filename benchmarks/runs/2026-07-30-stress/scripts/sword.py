"""Stress test: 'Steel longsword lying diagonally', 48x48, transparent bg.
Pipeline: ramps -> flats -> bevel/sphere auto-shade (top_left) -> paint_grid
details (hard specular line along the ridge) -> selective outline -> palette snap.

Geometry note: the sword lies at exactly 45 deg. Regions are defined in rotated
integer coordinates p = x+y-47 (across the blade) and a = x-y (along it), so the
bands are contiguous (no parity holes) and the edges are perfect 1:1 stairs."""
import asyncio, json, sys

import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
REPO = f"{_REPO}"
sys.path.insert(0, REPO)
from pixelart_mcp import server as S

RUN = REPO + "/benchmarks/runs/2026-07-30-stress"
OUT = RUN + "/sword.png"
VIEW = RUN + "/sword@view.png"

W = H = 48
CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"

TIP_A = 43          # a = x - y at the tip (45,2)
BLADE_A_MIN = -12   # blade meets the guard here
GUARD_A = (-17, -13)
GRIP_A = (-28, -18)


def chk(res):
    txt = res if isinstance(res, str) else res[0]
    assert not txt.startswith("Error"), txt
    return txt


def grid_call(pixmap):
    """dict {(x,y): hex} -> (rows, legend) for pixel_paint_grid at origin."""
    legend, rows, color_char = {}, [], {}
    for y in range(H):
        row = []
        for x in range(W):
            c = pixmap.get((x, y))
            if c is None:
                row.append(".")
            else:
                ch = color_char.get(c)
                if ch is None:
                    ch = CHARS[len(color_char)]
                    color_char[c] = ch
                    legend[ch] = c
                row.append(ch)
        rows.append("".join(row))
    return rows, legend


def blade_halfwidth(a):
    """Taper to a 1px point at the tip over ~6px (symmetric longsword point)."""
    return min(4, max(0, (44 - a) // 2))


def cells():
    """Yield (x, y, p, a) for every canvas cell."""
    for y in range(H):
        for x in range(W):
            yield x, y, x + y - 47, x - y


async def main():
    # Stage 1 -- ramps (dark -> light). Steel is the hero: 7 steps, high contrast.
    steel = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#8a9099", steps=7, hue_shift_deg=12))))["ramp"]
    gold = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#c08a2a", steps=5, hue_shift_deg=15))))["ramp"]
    leather = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#7a4f30", steps=5, hue_shift_deg=15))))["ramp"]
    print("steel:", steel, "\ngold:", gold, "\nleather:", leather)

    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=W, height=H, overwrite=True)))

    # Stage 2+3 -- silhouette in flat material base colors.
    flats = {}
    for x, y, p, a in cells():
        if BLADE_A_MIN <= a <= TIP_A and abs(p) <= blade_halfwidth(a):
            flats[(x, y)] = steel[3]
        elif GRIP_A[0] <= a <= GRIP_A[1] and abs(p) <= 2:
            flats[(x, y)] = leather[2]
    rows, legend = grid_call(flats)
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=0, y=0, rows=rows, legend=legend)))
    # pommel ball
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=6, y=37, width=5, height=5, color=gold[2])))
    # crossguard bar, perpendicular to the blade, painted last so it overlaps cleanly
    guard = {}
    for x, y, p, a in cells():
        amin, amax = GUARD_A
        if abs(p) >= 9:  # chamfered ends
            amin, amax = amin + 1, amax - 1
        if amin <= a <= amax and abs(p) <= 10:
            guard[(x, y)] = gold[3]
    rows, legend = grid_call(guard)
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=0, y=0, rows=rows, legend=legend)))

    # Stage 4 -- auto-shade, ONE light: top_left.
    chk(await S.pixel_shade_region(S.ShadeRegionInput(path=OUT, mode="bevel", light="top_left", target=steel[3], ramp=steel)))
    chk(await S.pixel_shade_region(S.ShadeRegionInput(path=OUT, mode="bevel", light="top_left", target=gold[3], ramp=gold)))
    chk(await S.pixel_shade_region(S.ShadeRegionInput(path=OUT, mode="sphere", light="top_left", target=gold[2], ramp=gold)))

    # Stage 5 -- details via paint_grid.
    det = {}
    # Blade: light side of the central ridge (p <= 0) vs dark side (p > 0), a hard
    # 3-step jump at the ridge (metal recipe: skip steps), specular line at p = -3
    # running the blade's full length.
    pcolor = {-4: steel[4], -3: steel[6], -2: steel[5], -1: steel[5], 0: steel[5],
              1: steel[2], 2: steel[2], 3: steel[1], 4: steel[1]}
    for x, y, p, a in cells():
        if BLADE_A_MIN <= a <= TIP_A and abs(p) <= blade_halfwidth(a):
            det[(x, y)] = pcolor[p]
        elif GRIP_A[0] <= a <= GRIP_A[1] and abs(p) <= 2:
            # leather grip: hand-banded cylinder + darker wrap lines every ~2px
            band = {-2: leather[3], -1: leather[2], 0: leather[2], 1: leather[1], 2: leather[1]}
            wrap = {-2: leather[2], -1: leather[1], 0: leather[1], 1: leather[0], 2: leather[0]}
            det[(x, y)] = wrap[p] if a in (-20, -23, -26) else band[p]
    det[(45, 2)] = steel[6]  # glinting tip
    # Pommel: hand-shaded gold ball (the 5px auto-sphere was mud against leather)
    for x, y, p, a in cells():
        dx, dy = x - 8, y - 39
        if dx * dx + dy * dy <= 5:
            if dx + dy <= -1:
                det[(x, y)] = gold[3]
            elif dx + dy >= 2:
                det[(x, y)] = gold[1]
            else:
                det[(x, y)] = gold[2]
    rows, legend = grid_call(det)
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=0, y=0, rows=rows, legend=legend)))
    # pommel glint: one pixel toward the light
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[S.PixelPoint(x=7, y=38)], color=steel[6])))

    # Stage 6 -- finish.
    chk(await S.pixel_outline_sprite(S.OutlineInput(path=OUT, mode="selective", corners=False)))
    chk(await S.pixel_apply_palette(S.ApplyPaletteInput(path=OUT, palette=steel + gold + leather)))

    print(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))
    print(chk(await S.pixel_ascii_view(S.AsciiViewInput(path=OUT, x=24, y=0, width=24, height=24))))
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=VIEW, scale=10)))
    print("done")


asyncio.run(main())
