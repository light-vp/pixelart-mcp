"""Benchmark demo: 'highly detailed apple', 48x48 — drawn with the v0.3.0 craft
pipeline: ramps -> silhouette -> flats -> auto-shade -> details -> finish."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

OUT = f"{_REPO}/benchmarks/examples/apple.png"


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    # Stage 1 — palette
    red = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#c22e2e", steps=7, hue_shift_deg=18))))["ramp"]
    green = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#4e8f3a", steps=5, hue_shift_deg=18))))["ramp"]
    brown = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#6b4a2f", steps=5, hue_shift_deg=15))))["ramp"]
    print("red:", red, "\ngreen:", green, "\nbrown:", brown)

    # Stage 2 — silhouette (flat base red), classic apple: two lobes + waist
    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=48, height=48, overwrite=True)))
    base = red[3]
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=5, y=12, width=22, height=24, color=base)))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=21, y=12, width=22, height=24, color=base)))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=7, y=16, width=34, height=26, color=base)))
    # bottom lobes
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=9, y=26, width=15, height=16, color=base)))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=24, y=26, width=15, height=16, color=base)))
    # top dip: carve a notch between the lobes
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=20, y=10, width=8, height=6, color="transparent")))

    # Stage 4 — shading (light top_left), sphere for the fruit body
    chk(await S.pixel_shade_region(S.ShadeRegionInput(
        path=OUT, mode="sphere", light="top_left", target=base, ramp=red)))

    # Stage 5 — details
    # stem well shadow (ambient occlusion around the dip)
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=18, y=13,
        rows=["..dddddd..",
              ".dd....dd."],
        legend={"d": red[1]})))
    # stem, curving right, with lit left edge
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=21, y=4,
        rows=["...LD",
              "..LD.",
              "..LD.",
              ".LD..",
              ".LDD.",
              ".LDD.",
              "..DD."],
        legend={"D": brown[1], "L": brown[3]})))
    # leaf on the right of the stem, two-tone along its spine
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=26, y=6,
        rows=["....gGG...",
              "..gGGGGG..",
              ".gGGgggGG.",
              "..ggg..gg.",
              "....2....."],
        legend={"G": green[2], "g": green[3], "2": green[1]})))
    # specular highlights (shiny skin): crescent + dots near the light
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=12, y=17,
        rows=["..ww",
              ".ww.",
              "ww..",
              "w...",
              "w..."],
        legend={"w": red[6]})))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(
        path=OUT, pixels=[S.PixelPoint(x=17, y=16), S.PixelPoint(x=11, y=24)], color=red[6])))
    # bounce light: thin cool rim at the bottom right shadow edge
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=26, y=39,
        rows=["......bb",
              "...bbbb.",
              "bbbb...."],
        legend={"b": red[3]})))

    # Stage 6 — finish
    chk(await S.pixel_outline_sprite(S.OutlineInput(path=OUT, mode="selective", corners=False)))
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=OUT.replace(".png", "@10x.png"), scale=10)))
    info = chk(await S.pixel_canvas_info(S.InfoInput(path=OUT)))
    print(info)

asyncio.run(main())
