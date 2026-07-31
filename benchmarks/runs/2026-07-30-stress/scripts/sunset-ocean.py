"""Stress test: 'Sunset over the ocean', 96x64 full scene on the slso8 palette.
Pipeline: bayer4 sky gradient -> radial sun glow fading to transparent -> sun
disc on the horizon -> silhouette cloud streaks -> cooler dark water gradient ->
broken, widening reflection streaks -> wave dashes -> birds -> palette snap."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

RUN = f"{_REPO}/benchmarks/runs/2026-07-30-stress"
OUT = f"{RUN}/sunset-ocean.png"

# slso8, dark -> light
P = ["#0d2b45", "#203c56", "#544e68", "#8d697a", "#d08159", "#ffaa5e", "#ffd4a3", "#ffecd6"]

W, H = 96, 64
HORIZON = 40
SUN_X = 58


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=W, height=H, overwrite=True)))

    # sky: dark violet top -> hot band at the horizon, bayer4 (no hard bands)
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=0, width=W, height=HORIZON, kind="linear", angle_deg=90,
        colors=[P[1], P[2], P[3], P[4], P[5], P[6]], dither="bayer4")))
    # radial glow around the setting sun, fading to untouched sky (kept one step
    # below the disc's value so the disc stays crisp)
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=SUN_X - 18, y=18, width=36, height=HORIZON - 18, kind="radial",
        center_x=SUN_X, center_y=38, radius=16,
        colors=[P[6], "transparent"], dither="bayer4")))
    # sun disc sitting on the horizon (lower half hidden by the sea, drawn later)
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=SUN_X - 7, y=31, width=14, height=14, color=P[7])))

    # silhouette cloud streaks, warm-lit on the sunward side
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=6, y=9, width=32, height=4, color=P[2])))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=16, y=12, width=18, height=2, color=P[2])))
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=56, y=18, width=26, height=3, color=P[3])))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=60, y0=20, x1=74, y1=20, color=P[5])))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=28, y0=26, x1=46, y1=26, color=P[3])))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=32, y0=27, x1=42, y1=27, color=P[4])))

    # ocean: reflected warmth at the horizon cooling to near-black at the viewer
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=HORIZON, width=W, height=H - HORIZON, kind="linear", angle_deg=90,
        colors=[P[3], P[2], P[1], P[0]], dither="bayer4")))
    # crisp, level horizon line
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=0, y0=HORIZON, x1=W - 1, y1=HORIZON, color=P[3])))

    # sun reflection: broken vertical streaks, widening + dimming toward viewer
    skip = {43, 46, 47, 51, 52, 55, 56, 59, 60, 62}
    for y in range(41, H):
        if y in skip:
            continue
        t = (y - HORIZON) / (H - 1 - HORIZON)
        half = 1 + t * 4.0
        shift = ((y * 5) % 3) - 1
        x0 = int(SUN_X - half) + shift
        x1 = int(SUN_X + half) + shift
        color = P[7] if y <= 45 else (P[6] if y <= 49 else (P[5] if y <= 56 else P[4]))
        if half < 2.5:
            chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=x0, y0=y, x1=x1, y1=y, color=color)))
        else:
            # split into two dashes with a drifting dark gap
            gap = SUN_X + ((y * 7) % 5) - 2
            chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=x0, y0=y, x1=max(x0, gap - 2), y1=y, color=color)))
            chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=min(x1, gap + 1), y0=y, x1=x1, y1=y, color=color)))
    # a couple of far-flung stray sparkles beside the path
    for (x, y, w) in [(48, 44, 1), (68, 48, 2), (50, 54, 2), (67, 58, 2)]:
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=x, y0=y, x1=x + w, y1=y, color=P[5])))
    # brightest touch where sun meets sea
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=SUN_X - 5, y0=41, x1=SUN_X + 5, y1=41, color=P[7])))

    # wave hints away from the reflection (one step lighter than local water)
    for (x, y, w, c) in [
        (8, 42, 6, P[4]), (78, 43, 6, P[4]), (22, 45, 5, P[3]),
        (70, 47, 6, P[2]), (10, 50, 6, P[2]), (30, 53, 5, P[2]),
        (80, 55, 6, P[1]), (14, 58, 7, P[1]), (34, 61, 6, P[1]),
    ]:
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=x, y0=y, x1=x + w, y1=y, color=c)))

    # gulls, small then smaller (scale cue)
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=20, y=10,
        rows=["X....X", ".X..X.", "..XX.."], legend={"X": P[1]})))
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=34, y=7,
        rows=["X..X", ".XX."], legend={"X": P[1]})))

    # snap any stray colors to the palette
    chk(await S.pixel_apply_palette(S.ApplyPaletteInput(path=OUT, palette=P)))

    info = json.loads(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))
    print("colors:", info["unique_colors"])
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=OUT.replace(".png", "@view.png"), scale=6)))
    print("done")

asyncio.run(main())
