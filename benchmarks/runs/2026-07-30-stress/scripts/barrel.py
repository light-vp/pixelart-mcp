"""Stress test: wooden barrel with iron hoops, upright, 40x48.
Workflow: ramps -> silhouette -> flats -> auto-shade -> details -> finish."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

OUT = f"{_REPO}/benchmarks/runs/2026-07-30-stress/barrel.png"
OUT_VIEW = f"{_REPO}/benchmarks/runs/2026-07-30-stress/barrel@view.png"


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    # Stage 1 — palette: wood and iron ramps
    wood = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(
        color="#6b4a2f", steps=5, hue_shift_deg=15))))["ramp"]
    iron = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(
        color="#5a5a5a", steps=4, hue_shift_deg=15))))["ramp"]
    print("wood:", wood)
    print("iron:", iron)

    # Stage 2 — silhouette: flat barrel body
    chk(await S.pixel_create_canvas(S.CreateCanvasInput(
        path=OUT, width=40, height=48, overwrite=True)))
    base_wood = wood[3]  # mid-tone wood for silhouette

    # Main barrel body: central bulge ellipse + tapered top/bottom
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(
        path=OUT, x=6, y=8, width=28, height=32, color=base_wood)))

    # Stage 3 — flat colors: fill barrel with wood base color
    # (ellipse already filled above)

    # Stage 4 — shading: cylinder_upright for the barrel body
    chk(await S.pixel_shade_region(S.ShadeRegionInput(
        path=OUT, mode="cylinder_upright", light="top_left",
        target=base_wood, ramp=wood)))

    # Stage 5 — details: stave seams, hoops, rim

    # Stave seams: 1px darker lines that curve with barrel bulge
    # Barrel bulges in middle (y~20), so seams shift outward at bulge
    stave_dark = wood[0]  # use darkest wood for visibility

    # Define seam center x positions (at y=20 mid-bulge)
    seam_centers = [8, 11, 15, 19, 23, 27, 30]  # closer at edges, spread in middle

    for center_x in seam_centers:
        # Build a curved path: straighter at top/bottom, shift outward at bulge
        pixels = []
        for y in range(8, 41):
            # Bulge curve: maximum shift at y=20, zero at top/bottom
            progress_from_center = abs(y - 20) / 16.0  # 0 at y=20, ~1 at edges
            # Increase shift for more pronounced curve
            shift = int(2.0 * (1.0 - progress_from_center * progress_from_center))
            # Shift outward for left seams, inward for right seams
            if center_x < 20:
                x = center_x - shift
            else:
                x = center_x + shift
            pixels.append(S.PixelPoint(x=x, y=y))
        chk(await S.pixel_draw_pixels(S.DrawPixelsInput(
            path=OUT, pixels=pixels, color=stave_dark)))

    # Iron hoops: 3 horizontal bands with highlights
    # Position: top, middle, bottom
    hoop_dark = iron[0]
    hoop_light = iron[3]  # brightest for highlights

    hoop_positions = [10, 20, 35]  # y-positions for hoops
    for y_pos in hoop_positions:
        # Draw hoop band (2px tall)
        chk(await S.pixel_draw_rect(S.DrawRectInput(
            path=OUT, x=4, y=y_pos, width=32, height=2, color=hoop_dark)))
        # Highlight: 1-2px bright lines where hoop crosses the bright cylinder band
        # For top_left lighting, bright area is roughly x=6-16, y=10-28
        chk(await S.pixel_draw_line(S.DrawLineInput(
            path=OUT, x0=6, y0=y_pos, x1=17, y1=y_pos, color=hoop_light)))
        if y_pos < 30:  # add a companion bright line for more definition
            chk(await S.pixel_draw_line(S.DrawLineInput(
                path=OUT, x0=7, y0=y_pos+1, x1=15, y1=y_pos+1, color=iron[2])))

    # Barrel top rim: slightly elliptical, with dark interior
    # Outer rim (light wood):
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(
        path=OUT, x=7, y=6, width=26, height=4, color=wood[4])))
    # Inner shadow (darker):
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(
        path=OUT, x=9, y=7, width=22, height=2, color=wood[0])))

    # Stage 6 — finish: consolidate stray colors to ramps, then outline
    # Snap all colors to nearest palette color (wood + iron ramps) BEFORE outline
    palette_colors = wood + iron
    chk(await S.pixel_apply_palette(S.ApplyPaletteInput(
        path=OUT, palette=palette_colors)))

    # Now outline on the cleaned palette (using solid for efficiency)
    chk(await S.pixel_outline_sprite(S.OutlineInput(
        path=OUT, mode="solid", corners=False, color="#1a1c2c")))
    info = json.loads(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))
    print("Canvas info:", info)
    print(f"Color count: {info.get('unique_colors', '?')}")

    # Export at 10x scale for viewing (400x480)
    chk(await S.pixel_export_png(S.ExportPngInput(
        path=OUT, out_path=OUT_VIEW, scale=10)))
    print(f"Saved: {OUT} and {OUT_VIEW}")

asyncio.run(main())
