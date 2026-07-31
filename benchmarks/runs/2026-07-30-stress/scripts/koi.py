"""Stress test: koi pond seen from above with lily pads, 64x64, <=24 colors.
Layers back-to-front: water base -> koi (blue-shifted, subdued, UNDER water)
-> radial depth gradient (targets base water only) -> surface ripples ->
lily pads (two-tone, notched) + blossom. Light: top_left."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

OUT = f"{_REPO}/benchmarks/runs/2026-07-30-stress/koi.png"
VIEW = OUT.replace(".png", "@view.png")


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    # Stage 1 — palettes
    water = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(
        color="#3f6d8e", steps=7, hue_shift_deg=18))))["ramp"]
    green = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(
        color="#4e8f3a", steps=5, hue_shift_deg=18))))["ramp"]
    print("water:", water, "\ngreen:", green)
    WBASE = water[3]

    # koi seen THROUGH water: blue-shifted, subdued (no sharp outlines)
    KA, KAQ = "#93756b", "#6e5559"   # muted orange koi + darker markings
    KB, KBQ = "#8ea8bf", "#55708c"   # pale koi + gray-blue patches
    KC = "#3d5670"                   # shadow koi, deepest
    FL, FLC = "#e8b6c8", "#f3e6a8"   # blossom petals + center

    chk(await S.pixel_create_canvas(S.CreateCanvasInput(
        path=OUT, width=64, height=64, overwrite=True)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=0, width=64, height=64, color=WBASE)))

    # Stage 2 — koi under the surface
    chk(await S.pixel_paint_grid(S.PaintGridInput(  # koi A: heads left, forked tail right
        path=OUT, x=8, y=30,
        rows=["......PPPP........",
              "...PPPPPPPPP....P.",
              "..PPPQQQPPPPP..PP.",
              ".PPPPQQQQPPPPPPPP.",
              "..PPPQQQPPPPP..PP.",
              "...PPPPPPPPP....P.",
              "......PPPP........"],
        legend={"P": KA, "Q": KAQ})))
    chk(await S.pixel_paint_grid(S.PaintGridInput(  # koi B: tail up, head down
        path=OUT, x=24, y=5,
        rows=[".R...R.",
              ".RR.RR.",
              "..RRR..",
              ".RRRRR.",
              ".RRRRR.",
              "RRRRRRR",
              "RRSRRRR",
              "RRSSRRR",
              ".RSSRR.",
              ".RRSRR.",
              ".RRRRR.",
              ".RRRRR.",
              ".RRRRR.",
              "..RRR.."],
        legend={"R": KB, "S": KBQ})))
    chk(await S.pixel_paint_grid(S.PaintGridInput(  # koi C: dark, heading NE
        path=OUT, x=44, y=46,
        rows=["......TTT.",
              ".....TTTTT",
              "....TTTTT.",
              "...TTTTTT.",
              "..TTTTTT..",
              ".TTTTTT...",
              ".TTTTT....",
              "..TTT.....",
              ".TT..T....",
              "TT....T..."],
        legend={"T": KC})))

    # Stage 3 — depth: radial gradient, lighter shallow center, darker edges.
    # target=WBASE so only open water is repainted; koi keep their colors.
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=0, width=64, height=64,
        colors=[water[4], water[3], water[2], water[1]],
        kind="radial", center_x=32, center_y=32, radius=44,
        dither="bayer4", target=WBASE)))

    # Stage 4 — surface ripples: concentric 1px light rings around (24,46)
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=21, y=43, width=7, height=7, color=water[5], filled=False)))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=17, y=39, width=15, height=15, color=water[5], filled=False)))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=13, y=35, width=23, height=23, color=water[5], filled=False)))
    # break the rings into arcs (dabs of deep water at NE / SW)
    for bx, by in [(30, 41), (19, 52), (32, 38), (16, 54), (27, 40), (21, 53)]:
        chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=bx, y=by, width=2, height=1, color=water[2])))

    # Stage 5 — lily pads (surface: full contrast, above ripples)
    def pad_discs(x, y, w, h):
        return [S.DrawEllipseInput(path=OUT, x=x, y=y, width=w, height=h, color=green[1]),
                S.DrawEllipseInput(path=OUT, x=x - 1, y=y - 1, width=w, height=h, color=green[2])]

    for inp in pad_discs(38, 26, 21, 17):   # pad 1, big, right-middle
        chk(await S.pixel_draw_ellipse(inp))
    for inp in pad_discs(3, 2, 15, 12):     # pad 2, top-left
        chk(await S.pixel_draw_ellipse(inp))
    for inp in pad_discs(52, 3, 11, 9):     # pad 3, top-right
        chk(await S.pixel_draw_ellipse(inp))
    for inp in pad_discs(2, 54, 13, 10):    # pad 4, bottom-left
        chk(await S.pixel_draw_ellipse(inp))

    # notches: V-wedge of deep water cut from rim toward the pad center
    chk(await S.pixel_paint_grid(S.PaintGridInput(  # pad 1: notch opens left
        path=OUT, x=37, y=32,
        rows=["N........",
              "NNN......",
              "NNNNNNN..",
              "NNN......",
              "N........"],
        legend={"N": water[2]})))
    chk(await S.pixel_paint_grid(S.PaintGridInput(  # pad 2: notch opens right
        path=OUT, x=10, y=6,
        rows=["...NN.",
              "NNNNNN",
              "...NN."],
        legend={"N": water[2]})))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=56, y0=7, x1=55, y1=11, color=water[2])))   # pad 3 notch
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=56, y0=7, x1=57, y1=11, color=water[2])))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=8, y0=58, x1=14, y1=57, color=water[2])))   # pad 4 notch
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=8, y0=58, x1=14, y1=59, color=water[2])))

    # blossom on pad 1
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=49, y=28,
        rows=["..F.F..",
              ".FFFFF.",
              ".FFCFF.",
              ".FFFFF.",
              "..F.F.."],
        legend={"F": FL, "C": FLC})))

    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=VIEW, scale=8)))
    print(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))

asyncio.run(main())
