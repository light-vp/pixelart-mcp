"""Stress test: 'Glowing green potion bottle in a dark cellar', 32x40.
Emissive subject: the liquid is the light source (near-white green core).
GLASS recipe: backdrop shows through pale tint, 1px rims, vertical streak,
sparkle pixels. Radial green glow tints wall + table, fades to transparent.
Deterministic, rerunnable."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

OUT = f"{_REPO}/benchmarks/runs/2026-07-30-stress/potion.png"
VIEW = f"{_REPO}/benchmarks/runs/2026-07-30-stress/potion@view.png"

# ---- palette (16 colors) ----
W0 = "#12141c"   # mortar / darkest wall
W1 = "#1a1d26"   # wall base
W2 = "#232734"   # stone face hint
T1 = "#2e2222"   # table top
T2 = "#1c1515"   # table front / shadow
G1 = "#2e4d2a"   # outer glow tint
G2 = "#4a7a38"   # inner glow tint
L0 = "#1e6414"   # liquid darkest edge
L1 = "#3a9c1c"   # liquid dark
L2 = "#6cd42c"   # liquid mid
L3 = "#b0f060"   # liquid bright
L4 = "#eaffd2"   # near-white core / sparkle
GT = "#2c3a36"   # glass tint (pale over dark wall)
RIM = "#141c1a"  # glass rim
C1 = "#8a6038"   # cork lit
C2 = "#5a3c22"   # cork dark


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=32, height=40, overwrite=True)))

    # ---- Stage A: cellar backdrop ----
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=0, width=32, height=32, color=W1)))
    # stone face hints (staggered blocks, a few lighter faces)
    for bx, by, bw, bh in [(0, 0, 10, 8), (22, 0, 10, 8), (4, 16, 12, 8), (16, 24, 12, 8)]:
        chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=bx, y=by, width=bw, height=bh, color=W2)))
    # mortar lines
    for my in (8, 16, 24):
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=0, y0=my, x1=31, y1=my, color=W0)))
    for mx, y0, y1 in [(10, 0, 7), (22, 0, 7), (4, 9, 15), (26, 9, 15),
                       (16, 17, 23), (6, 25, 31), (28, 25, 31)]:
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=mx, y0=y0, x1=mx, y1=y1, color=W0)))
    # table
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=32, width=32, height=2, color=T1)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=34, width=32, height=6, color=T2)))

    # ---- Stage B: green glow radiating from the liquid, fading out ----
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=8, width=32, height=30,
        colors=[G2, G1, "transparent"], kind="radial",
        center_x=15, center_y=22, radius=14.0, dither="bayer4")))

    # ---- Stage C: bottle silhouette in glass tint ----
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=12, y=6, width=8, height=2, color=GT)))    # lip
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=13, y=8, width=6, height=6, color=GT)))    # neck
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=8, y=13, width=16, height=8, color=GT)))  # shoulders
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=8, y=16, width=16, height=14, color=GT)))  # body
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=8, y=27, width=16, height=5, color=GT)))  # base
    # liquid glow shining through the glass just above the surface + lower neck
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=9, y=16, width=14, height=3, color=G1)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=14, y=11, width=4, height=3, color=G1)))
    # rising light in the shoulder, centered under the neck
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=13, y=14, width=6, height=2, color=G1)))

    # ---- Stage D: the glowing liquid (brightest thing in frame) ----
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=9, y=19, width=14, height=11, color=L2)))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=9, y=26, width=14, height=5, color=L2)))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=11, y=21, width=10, height=8, color=L3)))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=13, y=23, width=6, height=5, color=L4)))
    # darker greens hugging the glass at the edges
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=9, y0=20, x1=9, y1=28, color=L1)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=22, y0=20, x1=22, y1=28, color=L1)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=11, y0=30, x1=20, y1=30, color=L1)))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=10, y=29), S.PixelPoint(x=21, y=29)], color=L0)))
    # meniscus: bright surface line
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=10, y0=19, x1=21, y1=19, color=L3)))
    # rising bubbles
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=12, y=21), S.PixelPoint(x=18, y=20)], color=L4)))

    # ---- Stage E: glass rims (dark 1px edges) ----
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=8, y0=16, x1=8, y1=29, color=RIM)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=23, y0=16, x1=23, y1=29, color=RIM)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=13, y0=8, x1=13, y1=12, color=RIM)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=18, y0=8, x1=18, y1=12, color=RIM)))
    # shoulder curve rims
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=8, y=13,
        rows=[".....r....r.....",
              "...rr......rr...",
              ".rr..........rr.",
              "r..............r"],
        legend={"r": RIM})))
    # base curve rim
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=8, y=30,
        rows=["r..............r",
              ".rrrrrrrrrrrrrr."],
        legend={"r": RIM})))
    # lip rims
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=12, y=6), S.PixelPoint(x=19, y=6),
        S.PixelPoint(x=19, y=7)], color=RIM)))

    # ---- Stage F: emissive touches on the glass ----
    # lit-side rim catches the glow (1px wide, short, left side)
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=8, y0=20, x1=8, y1=22, color=L3)))
    # dim catch on the far rim
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=23, y0=21, x1=23, y1=23, color=L1)))
    # vertical specular streak on the glass just above the liquid
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=12, y0=16, x1=12, y1=17, color=L3)))
    # faint light climbing the neck interior
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=15, y=12), S.PixelPoint(x=15, y=13)], color=L1)))
    # sparkle on the lit rim
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=8, y=19)], color=L4)))

    # ---- Stage G: cork stopper ----
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=13, y=2,
        rows=[".dddd.",
              "CCCCCd",
              "CCCCCd",
              "CCCCCd",
              "CCCCCd"],
        legend={"C": C1, "d": C2})))

    # ---- Stage H: light pooling on the table under the glass base ----
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=10, y0=32, x1=21, y1=32, color=G2)))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=8, y=32), S.PixelPoint(x=9, y=32),
        S.PixelPoint(x=22, y=32), S.PixelPoint(x=23, y=32)], color=G1)))
    # glow leaking through the base rim
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=14, y0=31, x1=17, y1=31, color=L1)))

    info = json.loads(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))
    print("colors:", info.get("unique_colors"), info.get("top_colors"))
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=VIEW, scale=12)))
    print("done")

asyncio.run(main())
