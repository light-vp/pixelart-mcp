"""Stress test: 'Cozy stone cottage at dusk, lit windows', 64x64 full scene.
Pipeline: bayer4 dusk sky + stars -> treeline -> cool ground -> roof triangle,
chimney, smoke -> flat stone wall -> warm window glow tinted BEFORE the bevel
pass (so glow zones stay warm-lit) -> windows/door -> bevel wall -> stone
texture -> radial light pools on the ground fading to transparent."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

RUN = f"{_REPO}/benchmarks/runs/2026-07-30-stress"
OUT = f"{RUN}/cottage.png"

SKY = ["#131832", "#2c2a52", "#54406e", "#8a5471", "#c47862"]  # dusk, top -> horizon
STAR = "#c9d4e8"
GROUND = ["#3a4051", "#262c3d", "#181d2b"]  # cool, far -> near
ROOF, ROOF_DK, RIDGE = "#262038", "#1f1b30", "#4d4260"
SMOKE = "#6b6478"
FRAME = "#2b2331"
PANE, PANE_DIM, PANE_HOT = "#ffdf9e", "#e8a65f", "#fff1c9"
GLOW_A, GLOW_B = "#b98a5c", "#8f6b58"   # warm-lit stone / dim warm stone
DOOR, DOOR_DK = "#4a3226", "#2b1d16"

PEAK_X, PEAK_Y = 30, 18
WALL_X, WALL_W = 14, 34          # wall x 14..47
WALL_TOP, WALL_BOT = 34, 56      # wall rows
GROUND_Y = 45


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    stone = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#565a6b", steps=5, hue_shift_deg=15))))["ramp"]
    print("stone:", stone)

    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=64, height=64, overwrite=True)))

    # ---------- background ----------
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=0, width=64, height=GROUND_Y, kind="linear", angle_deg=90,
        colors=SKY, dither="bayer4")))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=6, y=4), S.PixelPoint(x=15, y=9), S.PixelPoint(x=26, y=3),
        S.PixelPoint(x=38, y=6), S.PixelPoint(x=52, y=10), S.PixelPoint(x=58, y=4),
        S.PixelPoint(x=45, y=13)], color=STAR)))
    # distant treeline silhouette on the horizon
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=0, y=42, width=64, height=3, color=GROUND[1])))
    for tx, th in [(3, 2), (9, 1), (20, 2), (33, 1), (44, 2), (54, 1), (60, 2)]:
        chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=tx, y=42 - th, width=3, height=th, color=GROUND[1])))
    # ground
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=0, y=GROUND_Y, width=64, height=64 - GROUND_Y, kind="linear", angle_deg=90,
        colors=GROUND, dither="bayer4")))

    # ---------- cottage ----------
    # gabled roof: triangle from the peak down to overhanging eaves
    for y in range(PEAK_Y, WALL_TOP):
        half = round((y - PEAK_Y + 1) * 1.55)
        chk(await S.pixel_draw_rect(S.DrawRectInput(
            path=OUT, x=PEAK_X - half, y=y, width=2 * half + 2, height=1, color=ROOF)))
    # slate courses + lit ridge cap
    for y in (22, 25, 28, 31):
        half = round((y - PEAK_Y + 1) * 1.55) - 1
        chk(await S.pixel_draw_rect(S.DrawRectInput(
            path=OUT, x=PEAK_X - half, y=y, width=2 * half + 2, height=1, color=ROOF_DK)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=PEAK_X - 1, y=PEAK_Y - 1, width=4, height=2, color=RIDGE)))
    # chimney + smoke
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=39, y=13, width=5, height=11, color=stone[2])))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=38, y=12, width=7, height=2, color=stone[3])))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=40, y=12, width=3, height=1, color=FRAME)))
    for sx, sy, sw, sh in [(42, 8, 3, 2), (45, 4, 3, 2), (49, 2, 2, 1)]:
        chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=sx, y=sy, width=sw, height=sh, color=SMOKE)))
    # flat stone wall
    chk(await S.pixel_draw_rect(S.DrawRectInput(
        path=OUT, x=WALL_X, y=WALL_TOP, width=WALL_W, height=WALL_BOT - WALL_TOP, color=stone[2])))
    # eaves shadow row on the wall top
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=WALL_X, y=WALL_TOP, width=WALL_W, height=1, color=stone[1])))

    # warm glow tint on the wall around each window (before bevel: tinted stone
    # stays out of the cool shading pass)
    for cx in (21, 40):
        chk(await S.pixel_draw_gradient(S.DrawGradientInput(
            path=OUT, x=cx - 7, y=36, width=15, height=12, kind="radial",
            center_x=cx, center_y=41, radius=7,
            colors=[GLOW_A, GLOW_B, "transparent"], dither="bayer4", target=stone[2])))

    # windows: dark frame, warm panes, cross mullions, hot core pixels
    for wx in (18, 37):
        chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=wx, y=37, width=8, height=9, color=FRAME)))
        chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=wx + 1, y=38, width=6, height=7, color=PANE)))
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=wx + 4, y0=38, x1=wx + 4, y1=44, color=FRAME)))
        chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=wx + 1, y0=41, x1=wx + 6, y1=41, color=FRAME)))
        chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
            S.PixelPoint(x=wx + 2, y=39), S.PixelPoint(x=wx + 3, y=39),
            S.PixelPoint(x=wx + 5, y=43)], color=PANE_HOT)))
        chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
            S.PixelPoint(x=wx + 1, y=44), S.PixelPoint(x=wx + 6, y=44)], color=PANE_DIM)))
    # door with a small lit fanlight
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=28, y=44, width=8, height=12, color=DOOR)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=28, y=44, width=8, height=1, color=DOOR_DK)))
    chk(await S.pixel_draw_line(S.DrawLineInput(path=OUT, x0=28, y0=44, x1=28, y1=55, color=DOOR_DK)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=30, y=46, width=4, height=2, color=PANE_DIM)))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[S.PixelPoint(x=34, y=50)], color=PANE)))

    # cool ambient bevel on the remaining flat stone
    chk(await S.pixel_shade_region(S.ShadeRegionInput(
        path=OUT, mode="bevel", light="top", target=stone[2], ramp=stone, levels=1, band_px=1)))

    # sparse stone texture: single lighter/darker pixels, mortar hints
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=16, y=38), S.PixelPoint(x=25, y=40), S.PixelPoint(x=34, y=37),
        S.PixelPoint(x=45, y=39), S.PixelPoint(x=17, y=47), S.PixelPoint(x=27, y=50),
        S.PixelPoint(x=43, y=48), S.PixelPoint(x=38, y=53), S.PixelPoint(x=20, y=53)], color=stone[3])))
    chk(await S.pixel_draw_pixels(S.DrawPixelsInput(path=OUT, pixels=[
        S.PixelPoint(x=19, y=35), S.PixelPoint(x=31, y=39), S.PixelPoint(x=42, y=36),
        S.PixelPoint(x=15, y=44), S.PixelPoint(x=24, y=48), S.PixelPoint(x=36, y=49),
        S.PixelPoint(x=46, y=52), S.PixelPoint(x=30, y=42)], color=stone[1])))

    # light running down the wall just under each sill
    for wx in (18, 37):
        chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=wx + 1, y=46, width=6, height=1, color=GLOW_A)))
        chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=wx + 2, y=47, width=4, height=1, color=GLOW_B)))

    # ---------- light spill on the ground ----------
    for cx in (22, 41):
        chk(await S.pixel_draw_gradient(S.DrawGradientInput(
            path=OUT, x=cx - 7, y=WALL_BOT, width=15, height=6, kind="radial",
            center_x=cx, center_y=WALL_BOT + 1, radius=7,
            colors=[GLOW_B, "transparent"], dither="bayer4")))
    # faint door spill
    chk(await S.pixel_draw_gradient(S.DrawGradientInput(
        path=OUT, x=27, y=WALL_BOT, width=10, height=5, kind="radial",
        center_x=31, center_y=WALL_BOT, radius=5,
        colors=[GLOW_B, "transparent"], dither="bayer2")))
    # stepping stones from the door: lit inside the pool, dim beyond it
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=30, y=58, width=3, height=1, color=GLOW_B)))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=33, y=60, width=3, height=1, color=stone[2])))
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=29, y=62, width=3, height=1, color=stone[1])))

    info = json.loads(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))
    print("colors:", info["unique_colors"])
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=OUT.replace(".png", "@view.png"), scale=8)))
    print("done")

asyncio.run(main())
