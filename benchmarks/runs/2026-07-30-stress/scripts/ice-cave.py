"""Stress test: 'Glowing crystal in an ice cave', 48x48 full scene.
Emissive subject: faceted crystal with cyan-white core is the light source.
Its glow tints nearby ice; walls read glassy (1px rims, vertical streaks,
GLASS recipe); deep blue shadows, cool palette, sparkles.
Deterministic, rerunnable."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

OUT = f"{_REPO}/benchmarks/runs/2026-07-30-stress/ice-cave.png"
VIEW = f"{_REPO}/benchmarks/runs/2026-07-30-stress/ice-cave@view.png"

# ---- palette: one cyan-ice ramp + white (9 colors) ----
I0 = "#0a1226"   # deepest blue shadow
I1 = "#14224a"   # deep blue
I2 = "#1f3a6e"   # mid-deep ice
I3 = "#2f5a94"   # mid ice / glow tint
I4 = "#4384b8"   # light-mid / crystal dim facet
I5 = "#62b8d6"   # light cyan / crystal facet, rims
I6 = "#9fe0ea"   # pale cyan / bright facet
I7 = "#d8f6f8"   # near-white cyan / hero facet
WHT = "#ffffff"  # core + sparkles
TMP = "#20396f"  # temp flat for the right wall (replaced at the end)


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=48, height=48, overwrite=True)))

    # ---- Stage A: cave shell ----
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=0, width=48, height=48, color=I0)))
    # floor
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=10, y=36, width=28, height=12, color=I1)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=10, y0=36, x1=37, y1=36, color=I2)))
    # ceiling band between the walls
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=11, y=0, width=26, height=2, color=I1)))

    # ---- Stage B: glassy ice walls (zigzag inner edge, bevel-shaded) ----
    # left wall, lit from the right (the crystal)
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=0, width=11, height=16, color=I2)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=16, width=8, height=16, color=I2)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=32, width=10, height=16, color=I2)))
    chk(await S.pixel_shade_region(S.ShadeRegionInput(
        path=OUT, mode="bevel", light="right", target=I2,
        ramp=[I0, I1, I2, I3, I4], levels=2, band_px=1)))
    # right wall, lit from the left — flat TMP color so the bevel targets only it
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=37, y=0, width=11, height=14, color=TMP)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=40, y=14, width=8, height=18, color=TMP)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=38, y=32, width=10, height=16, color=TMP)))
    chk(await S.pixel_shade_region(S.ShadeRegionInput(
        path=OUT, mode="bevel", light="left", target=TMP,
        ramp=[I0, I1, TMP, I3, I4], levels=2, band_px=1)))

    # ---- Stage C: crystal glow — radial, fading to untouched darkness ----
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=8, y=10, width=32, height=34,
        colors=[I3, I2, "transparent"], kind="radial",
        center_x=24, center_y=26, radius=15.0, dither="bayer4")))
    # pool of light on the floor
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=10, y=36, width=28, height=12,
        colors=[I3, I2, "transparent"], kind="radial",
        center_x=24, center_y=38, radius=10.0, dither="bayer4")))

    # ---- Stage D: glassy details on the walls (rims + streaks) ----
    # left wall inner rims (1px)
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=10, y0=0, x1=10, y1=15, color=I4)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=7, y0=16, x1=7, y1=31, color=I4)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=9, y0=32, x1=9, y1=47, color=I4)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=8, y0=16, x1=10, y1=16, color=I4)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=7, y0=32, x1=9, y1=32, color=I4)))
    # glow-facing rim segment turns brighter near the crystal
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=7, y0=22, x1=7, y1=28, color=I5)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=9, y0=34, x1=9, y1=40, color=I5)))
    # right wall inner rims (1px)
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=37, y0=0, x1=37, y1=13, color=I4)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=40, y0=14, x1=40, y1=31, color=I4)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=38, y0=32, x1=38, y1=47, color=I4)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=37, y0=14, x1=40, y1=14, color=I4)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=38, y0=32, x1=40, y1=32, color=I4)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=40, y0=22, x1=40, y1=28, color=I5)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=38, y0=34, x1=38, y1=40, color=I5)))
    # vertical streak highlights inside the ice (GLASS recipe)
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=4, y0=19, x1=4, y1=27, color=I4)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=5, y0=22, x1=5, y1=25, color=I5)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=43, y0=21, x1=43, y1=29, color=I4)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=42, y0=24, x1=42, y1=27, color=I5)))

    # ---- Stage E: icicles from the ceiling ----
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=12, y=2,
        rows=["eE", "eE", ".E"], legend={"e": I1, "E": I2})))
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=17, y=2,
        rows=["eE", "eE", ".E", ".E"], legend={"e": I1, "E": I2})))
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=22, y=2,
        rows=["eE", "eE", "eE", ".E", ".E", ".t"], legend={"e": I1, "E": I2, "t": I3})))
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=28, y=2,
        rows=["Ee", "Ee", "E.", "E."], legend={"e": I1, "E": I2})))
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=33, y=2,
        rows=["Ee", "Ee", "Ee", "E.", "E."], legend={"e": I1, "E": I2})))

    # ---- Stage F: floor cracks ----
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=12, y0=41, x1=16, y1=41, color=I0)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=30, y0=43, x1=35, y1=43, color=I0)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=19, y0=45, x1=24, y1=45, color=I0)))

    # ---- Stage G: the crystal cluster (hand-cut facets, one ramp step per face) ----
    # main shard: left face I5, ridge I7, white core, right face I4, tip faces I6/I5
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=20, y=14,
        rows=["....d....",
              "...cdb...",
              "...cdb...",
              "..ccdbb..",
              "..ccdbb..",
              ".cccdbbb.",
              ".cccdbbb.",
              "bbbdWdaaa",
              "bbbdWdaaa",
              "bbbdWdaaa",
              "bbbdWdaaa",
              "bbbdWdaaa",
              "bbbdWdaaa",
              "bbbdWdaaa",
              "bbbdWdaaa",
              "bbbdWdaaa",
              "bbbdWdaaa",
              "bbbdWdaaa",
              "bbbdWdaaa",
              "bbbdddaaa",
              "bbbdddaaa",
              ".bbdddaa.",
              ".bbdddaa.",
              "..bddda..",
              "...ddd..."],
        legend={"a": I4, "b": I5, "c": I6, "d": I7, "W": WHT})))
    # left small shard (dimmer, its right edge lit by the main crystal)
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=14, y=26,
        rows=["..b..",
              ".eba.",
              ".eba.",
              "eebac",
              "eebac",
              "eebac",
              "eebac",
              "eebac",
              "eebac",
              "eebac",
              ".eba.",
              ".eba.",
              "..ba."],
        legend={"e": I3, "b": I5, "a": I4, "c": I6})))
    # right small shard (left edge lit by the main crystal)
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=30, y=29,
        rows=["..b..",
              ".cbe.",
              ".cbe.",
              "cbbee",
              "cbbee",
              "cbbee",
              "cbbee",
              "cbbee",
              ".bbe.",
              "..b.."],
        legend={"c": I6, "b": I5, "e": I3})))

    # ---- Stage H: contact glow on the floor + sparkles ----
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=21, y0=39, x1=27, y1=39, color=I4)))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=17, y=39), S.PixelPoint(x=31, y=39),
        S.PixelPoint(x=19, y=38), S.PixelPoint(x=29, y=38)], color=I3)))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=27, y=11), S.PixelPoint(x=17, y=17),
        S.PixelPoint(x=32, y=21), S.PixelPoint(x=7, y=24)], color=WHT)))

    # ---- Stage I: retire the temp color ----
    chk(await S.pixel_replace_color(S.ReplaceColorInput(path=OUT, find=TMP, replace=I2)))

    info = json.loads(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))
    print("colors:", info.get("unique_colors"), info.get("top_colors"))
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=VIEW, scale=10)))
    print("done")

asyncio.run(main())
