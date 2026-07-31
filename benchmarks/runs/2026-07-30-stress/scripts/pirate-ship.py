"""Stress test: pirate ship on rough seas, 96x64, <=32 colors.
Sky/sea flat bases -> ship (hull+planks, masts, bellied sails, flag, rigging)
-> gradients that target only the base colors -> wave bands + foam OVER the
hull waterline so the ship sits IN the water. Light: top_left."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

OUT = f"{_REPO}/benchmarks/runs/2026-07-30-stress/pirate-ship.png"
VIEW = OUT.replace(".png", "@view.png")


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    # Stage 1 — palettes
    sky = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#8fa3b8", steps=5, hue_shift_deg=12))))["ramp"]
    sea = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#2e5f6e", steps=7, hue_shift_deg=18))))["ramp"]
    wood = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#6b4a2f", steps=5, hue_shift_deg=15))))["ramp"]
    cloth = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#cfc4a8", steps=6, hue_shift_deg=8))))["ramp"]
    print("sky:", sky, "\nsea:", sea, "\nwood:", wood, "\ncloth:", cloth)

    SKY, SEA = sky[2], sea[3]
    K, D, M, L, H = wood                       # hull darks -> rail highlight
    C1, C2, C3, C4, C5 = cloth[1], cloth[2], cloth[3], cloth[4], cloth[5]
    FLAG, FOAM = "#232733", "#eef4ee"

    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=96, height=64, overwrite=True)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=0, width=96, height=38, color=SKY)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=38, width=96, height=26, color=SEA)))

    # ---- Stage 2 — ship (bow points right) -------------------------------
    # hull slab + sterncastle + low forecastle
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=28, y=36, width=40, height=13, color=M)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=27, y=33, width=9, height=4, color=M)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=60, y=34, width=7, height=2, color=M)))
    # strake tones: lit top strake, shadowed lower hull
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=28, y=36, width=40, height=2, color=L)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=28, y=44, width=40, height=5, color=D)))
    # raked bow (carve front edge back toward the keel)
    for y, x0 in [(39, 67), (40, 67), (41, 66), (42, 66), (43, 65), (44, 65), (45, 64), (46, 64)]:
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=x0, y0=y, x1=67, y1=y, color=SEA)))
    # raked stern (carve below the overhanging castle)
    for y, x1 in [(39, 28), (40, 28), (41, 29), (42, 29), (43, 30), (44, 30), (45, 31), (46, 31)]:
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=28, y0=y, x1=x1, y1=y, color=SEA)))
    # gunwale highlight following the sheer; castle rail; wale + plank seams
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=29, y0=36, x1=40, y1=37, color=H)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=41, y0=37, x1=54, y1=37, color=H)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=55, y0=37, x1=66, y1=35, color=H)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=27, y0=33, x1=35, y1=33, color=H)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=29, y0=39, x1=44, y1=40, color=K)))   # wale
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=45, y0=40, x1=66, y1=38, color=K)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=30, y0=42, x1=46, y1=43, color=K)))   # seam
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=47, y0=43, x1=65, y1=41, color=K)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=31, y0=45, x1=47, y1=46, color=K)))   # seam low
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=48, y0=46, x1=64, y1=44, color=K)))
    # gunports + stern windows
    for gx in (37, 45, 53):
        chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=gx, y=41, width=2, height=2, color=K)))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=29, y=34), S.PixelPoint(x=31, y=34), S.PixelPoint(x=33, y=34)], color=C4)))

    # masts (1px lit edge + 1px dark edge), yards, bowsprit
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=44, y=4, width=1, height=33, color=L)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=45, y=4, width=1, height=33, color=D)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=57, y=9, width=1, height=28, color=L)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=58, y=9, width=1, height=28, color=D)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=35, y0=11, x1=51, y1=11, color=K)))    # main yard
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=50, y0=12, x1=65, y1=12, color=K)))    # fore yard
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=66, y0=35, x1=75, y1=31, color=D)))    # bowsprit
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=66, y0=34, x1=74, y1=31, color=L)))

    # sails: flat -> corner cuts (restored by sky gradient) -> belly bands
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=36, y=12, width=15, height=17, color=C3)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=51, y=13, width=14, height=15, color=C3)))
    for gx, gy, rows in [
        (36, 26, ["S..", "SS.", "SSS"]), (48, 26, ["..S", ".SS", "SSS"]),   # main bottom
        (36, 12, ["SS", "S."]), (49, 12, ["SS", ".S"]),                      # main top
        (51, 25, ["S..", "SS.", "SSS"]), (62, 25, ["..S", ".SS", "SSS"]),   # fore bottom
        (51, 13, ["SS", "S."]), (63, 13, ["SS", ".S"]),                      # fore top
    ]:
        chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=gx, y=gy, rows=rows, legend={"S": SKY})))
    for x, y, w, h in [(36, 12, 15, 17), (51, 13, 14, 15)]:
        chk(await S.pixel_draw_gradient(S.DrawGradientInput(
            path=OUT, x=x, y=y, width=w, height=h,
            colors=[C2, C4, C3, C2], kind="linear", angle_deg=0,
            dither="checker", target=C3)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=39, y0=28, x1=47, y1=28, color=C1)))   # hems
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=54, y0=27, x1=61, y1=27, color=C1)))

    # flag: dark pennant streaming right, white skull + crossbone dots
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=44, y=3), S.PixelPoint(x=45, y=3)], color=K)))
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=46, y=3,
        rows=["FFFFFFFFFFF.",
              "FFWWWWWFFFF.",
              "FFWFWFWFFFFF",
              "FFWWWWWFFFF.",
              "FFWFFFWFFFF.",
              "FFFFFFFFFF.."],
        legend={"F": FLAG, "W": C5})))

    # rigging: 1px stays
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=44, y0=4, x1=29, y1=33, color=K)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=46, y0=4, x1=74, y1=31, color=K)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=58, y0=9, x1=64, y1=35, color=K)))

    # ---- Stage 3 — submerge the keel, then atmosphere gradients ----------
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=47, width=96, height=17, color=SEA)))
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=0, width=96, height=38,
        colors=[sky[4], sky[3], sky[2], sky[1]], kind="linear", angle_deg=115,
        dither="bayer4", target=SKY)))
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=38, width=96, height=26,
        colors=[sea[4], sea[3], sea[2], sea[1]], kind="linear", angle_deg=90,
        dither="bayer2", target=SEA)))

    # ---- Stage 4 — rough sea: wave bands, foam, hull sitting IN water ----
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=0, y0=38, x1=95, y1=38, color=sea[4])))  # horizon
    # ship shadow in the water
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=30, y=46, width=36, height=4, color=sea[2])))
    wob = [0, -1, 0, 1]
    for band_i, by in enumerate([45, 51, 57, 62]):
        for i, x0 in enumerate(range(0, 96, 8)):
            yy = by + wob[i % 4]
            chk(await S.pixel_draw_line(S.DrawLineInput(
                path=OUT, x0=x0, y0=yy, x1=min(x0 + 7, 95), y1=yy, color=sea[4])))
            chk(await S.pixel_draw_line(S.DrawLineInput(
                path=OUT, x0=x0, y0=yy + 1, x1=min(x0 + 7, 95), y1=yy + 1, color=sea[1])))
        # foam: brightest step, broken dashes on the two nearest-ship bands
        if band_i < 2:
            for j, fx in enumerate(range(2 + band_i * 5, 93, 12)):
                yy = by + wob[(fx // 8) % 4]
                chk(await S.pixel_draw_line(S.DrawLineInput(
                    path=OUT, x0=fx, y0=yy, x1=fx + 2, y1=yy, color=FOAM)))
    # bow wave + stern wake foam at the waterline
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=60, y=42,
        rows=["........ff.",
              "......fff..",
              "...ffff.f..",
              "ffff....ff."],
        legend={"f": FOAM})))
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=25, y=44,
        rows=["ff.f....",
              ".fff...."],
        legend={"f": FOAM})))

    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=VIEW, scale=6)))
    print(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))

asyncio.run(main())
