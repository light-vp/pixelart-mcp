"""Benchmark demo: 'clear glass bottle with water and light reflection', 40x64.
Glass recipe from pixel_guide materials: background shows through a pale tint,
dark rims, vertical specular streaks, water with its own ramp + meniscus."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

OUT = f"{_REPO}/benchmarks/examples/bottle.png"


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    W, H = 40, 64
    # Stage 1 — palettes
    water = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#4d7fae", steps=6, hue_shift_deg=15))))["ramp"]
    wood = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#8a6a4b", steps=5, hue_shift_deg=15))))["ramp"]
    cork = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#a97e52", steps=5, hue_shift_deg=12))))["ramp"]
    print("water:", water)

    GLASS = "#d9e4dc"       # pale green-cyan tint of the backdrop
    GLASS_RIM = "#8fa9a0"   # darker glass edge
    GLASS_IN = "#c3d4cb"    # inner shadow tint

    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=W, height=H, overwrite=True)))
    # backdrop: warm wall, light falls from top-left
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=0, width=W, height=52,
        colors=["#f2ead6", "#e4d9c0", "#cfc2a4"], kind="linear", angle_deg=115, dither="bayer4")))
    # table
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=52, width=W, height=2, color=wood[3])))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=54, width=W, height=10, color=wood[2])))
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=54, width=W, height=10,
        colors=[wood[2], wood[1]], kind="linear", angle_deg=90, dither="bayer2", target=wood[2])))

    # cast shadow on wall+table, opposite the light (to bottle's right)
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=22, y=50, width=16, height=5, color=wood[1])))

    # bottle silhouette in flat glass tint: lip, neck, shoulders, body
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=15, y=4, width=10, height=3, color=GLASS)))   # lip
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=17, y=7, width=6, height=10, color=GLASS)))   # neck
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=11, y=14, width=18, height=12, color=GLASS)))  # shoulders
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=11, y=20, width=18, height=28, color=GLASS)))  # body
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=11, y=44, width=18, height=8, color=GLASS)))   # base

    # water: fill lower 60% of the body interior, then gradient-shade only it
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=13, y=30, width=14, height=17, color=water[3])))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=13, y=43, width=14, height=7, color=water[3])))
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=13, y=30, width=14, height=20,
        colors=[water[4], water[3], water[2], water[1]], kind="linear", angle_deg=90,
        dither="checker", target=water[3])))
    # meniscus: light surface line + brighter far edge
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=13, y0=30, x1=26, y1=30, color=water[5])))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=14, y0=31, x1=25, y1=31, color=water[4])))

    # glass rims: dark 1px edges of the silhouette
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=15, y=4, rows=["rrrrrrrrrr"], legend={"r": GLASS_RIM})))
    for x0, y0, x1, y1 in [(15, 5, 15, 6), (24, 5, 24, 6),          # lip sides
                           (17, 7, 17, 16), (22, 7, 22, 16),        # neck sides
                           (11, 20, 11, 47), (28, 20, 28, 47)]:     # body sides
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=x0, y0=y0, x1=x1, y1=y1, color=GLASS_RIM)))
    # shoulder curves + base curve
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=11, y=14,
        rows=["......rr..........",
              "....rr..rr........",
              "..rr......rr......",
              ".r..........r.....",
              "r............r...."],
        legend={"r": GLASS_RIM})))
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=11, y=48,
        rows=["r................r",
              ".rr............rr.",
              "...rrrrrrrrrrrr..."],
        legend={"r": GLASS_RIM})))
    # inner shadow tint on the dark side (right), above the water line
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=25, y=21, width=3, height=9, color=GLASS_IN)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=23, y=8, width=1, height=8, color=GLASS_IN)))

    # SPECULAR: long bright streak on the lit side + short companion, through everything
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=13, y0=21, x1=13, y1=46, color="#ffffff")))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=14, y0=24, x1=14, y1=40, color="#eef6ee")))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=18, y0=8, x1=18, y1=15, color="#ffffff")))
    # sparkle pixels
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=16, y=18), S.PixelPoint(x=26, y=33), S.PixelPoint(x=20, y=5)], color="#ffffff")))

    # cork, plugged into the mouth (overlaps the lip's top row)
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=17, y=0,
        rows=[".LDDd.",
              "LLDDDd",
              "LLDDDd",
              "LLDDDd",
              ".LDDd."],
        legend={"L": cork[3], "D": cork[2], "d": cork[1]})))

    # contact shadow + caustic light spot the glass focuses onto the table
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=12, y=51, width=16, height=3, color=wood[0])))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=30, y=55, width=7, height=3, color="#f5e6b8")))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=32, y=56), S.PixelPoint(x=33, y=56)], color="#fdf6d8")))

    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=OUT.replace(".png", "@8x.png"), scale=8)))
    print("done")

asyncio.run(main())
