"""Stress test: 'Campfire at night', 48x48 — emissive-light subject.
FIRE recipe: white-hot core -> yellow -> orange -> deep red, NO outline.
The fire is the light source: radial warm glow tints ground + log ends,
fading to untouched night darkness. Logs = cylinder_side, fire-facing
ends brightest. Deterministic, rerunnable."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

OUT = f"{_REPO}/benchmarks/runs/2026-07-30-stress/campfire.png"
VIEW = f"{_REPO}/benchmarks/runs/2026-07-30-stress/campfire@view.png"

# ---- palette (16 colors total) ----
NIGHT1 = "#0a0d1a"   # deep sky
NIGHT2 = "#121a2e"   # lower sky
STAR = "#c9d6ec"
GROUND1 = "#221a2c"  # ground base (dark desaturated violet)
GROUND2 = "#151020"  # ground foreground shadow
GLOW1 = "#7a4420"    # inner warm glow tint
GLOW2 = "#472818"    # outer warm glow tint
LOG = ["#241710", "#3c2718", "#573a22", "#7a5433"]  # dark->light
RED = "#8c2408"      # flame outer
ORG1 = "#d64a10"     # red-orange
ORG2 = "#f5891c"     # orange
YEL = "#ffcc44"      # yellow
WHT = "#fff4c8"      # near-white core


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=48, height=48, overwrite=True)))

    # ---- Stage A: night background (dither only in a narrow horizon band) ----
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=0, width=48, height=14, color=NIGHT1)))
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=14, width=48, height=12,
        colors=[NIGHT1, NIGHT2], kind="linear", angle_deg=90, dither="bayer4")))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=26, width=48, height=8, color=NIGHT2)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=34, width=48, height=14, color=GROUND1)))
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=34, width=48, height=14,
        colors=[GROUND1, GROUND2], kind="linear", angle_deg=90, dither="bayer2", target=GROUND1)))
    # stars (kept away from the glow zone)
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=4, y=3), S.PixelPoint(x=11, y=7), S.PixelPoint(x=7, y=14),
        S.PixelPoint(x=40, y=4), S.PixelPoint(x=44, y=10), S.PixelPoint(x=36, y=8),
        S.PixelPoint(x=20, y=2), S.PixelPoint(x=30, y=5), S.PixelPoint(x=45, y=18),
        S.PixelPoint(x=2, y=22)], color=STAR)))

    # ---- Stage B: warm glow from the fire, fading to untouched dark ----
    # tight dome in the sky hugging the flame
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=12, y=18, width=25, height=16,
        colors=[GLOW1, GLOW2, "transparent"], kind="radial",
        center_x=24, center_y=33, radius=11.0, dither="bayer4")))
    # stronger pool on the ground
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=6, y=34, width=36, height=14,
        colors=[GLOW1, GLOW2, "transparent"], kind="radial",
        center_x=24, center_y=37, radius=16.0, dither="bayer2")))

    # ---- Stage C: logs (side-lying cylinders), flanking the fire pit ----
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=4, y=38, width=15, height=5, color=LOG[2])))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=29, y=38, width=15, height=5, color=LOG[2])))
    chk(await S.pixel_shade_region(S.ShadeRegionInput(
        path=OUT, mode="cylinder_side", light="top", target=LOG[2], ramp=LOG)))
    # contact shadows so the logs sit on the ground
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=5, y=43, width=14, height=1, color=GROUND2)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=29, y=43, width=14, height=1, color=GROUND2)))
    # fire-facing end caps: brightest, tinted by the fire
    chk(await S.pixel_paint_grid(S.PaintGridInput(   # left log, right end
        path=OUT, x=17, y=38,
        rows=["oy",
              "yO",
              "yO",
              "oy",
              "ro"],
        legend={"o": ORG1, "O": ORG2, "y": YEL, "r": RED})))
    chk(await S.pixel_paint_grid(S.PaintGridInput(   # right log, left end
        path=OUT, x=29, y=38,
        rows=["yo",
              "Oy",
              "Oy",
              "yo",
              "or"],
        legend={"o": ORG1, "O": ORG2, "y": YEL, "r": RED})))
    # cool far ends: darkest step caps away from the fire
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=4, y=38, width=1, height=5, color=LOG[0])))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=43, y=38, width=1, height=5, color=LOG[0])))

    # ---- Stage D: ember bed, fused with the flame base and the logs ----
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=19, y=34,
        rows=["..oOyyOo..",
              ".oOyyyyOo.",
              "roOyyyyOor",
              "rroOOOOorr"],
        legend={"r": RED, "o": ORG1, "O": ORG2, "y": YEL})))

    # ---- Stage E: the flames (NO outline, hottest at the core/base) ----
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=18, y=15,
        rows=["......r......",
              ".....rr......",
              ".....ro......",
              "....rro......",
              "....roo..r...",
              "...rroO..r...",
              "...roOO.rr...",
              "..rroOOOro...",
              "..roOOyOOo...",
              "..roOyyyOor..",
              ".rroOyyyOOor.",
              ".roOyywyyOor.",
              ".roOywwwyOor.",
              "roOOywwwyOOor",
              "roOyywwwyyOor",
              "roOyywwwyyOor",
              ".roOyywwyOor.",
              ".rroOyyyOOr..",
              "..roOOOOOor..",
              "...rooOoor..."],
        legend={"r": RED, "o": ORG1, "O": ORG2, "y": YEL, "w": WHT})))

    # ---- Stage F: detached sparks above the flames ----
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=27, y=10)], color=YEL)))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=21, y=12), S.PixelPoint(x=30, y=7)], color=ORG2)))

    info = json.loads(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))
    print("colors:", info.get("color_count", info))
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=VIEW, scale=10)))
    print("done")

asyncio.run(main())
