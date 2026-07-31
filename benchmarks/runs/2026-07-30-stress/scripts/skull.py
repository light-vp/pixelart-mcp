"""Stress test: human skull, 3/4 view, 32x32, transparent bg, <=6 colors.
Facing viewer's left: far (left) eye socket narrower, jaw offset left.
Pipeline: bone ramp -> silhouette -> sphere shade (top_left) -> hand details.
Colors (6): SOCK #2a1a10 (cavities, darkest) + 5-step warm bone ramp."""
import asyncio, json, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

OUT = f"{_REPO}/benchmarks/runs/2026-07-30-stress/skull.png"
VIEW = OUT.replace(".png", "@view.png")


async def main():
    def chk(res):
        txt = res if isinstance(res, str) else res[0]
        assert not txt.startswith("Error"), txt
        return txt

    # Stage 1 — palette: warm bone ramp (5) + one cavity near-black = 6 total
    bone = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(
        color="#c9bda0", steps=5, hue_shift_deg=10))))["ramp"]
    K, D, B, L, W = bone  # #532e18 #a67944 #c9bda0 #d6d3c1 #e6e5de
    SOCK = "#2a1a10"      # eye sockets / nasal cavity — darkest value on canvas
    print("bone ramp:", bone)

    chk(await S.pixel_create_canvas(S.CreateCanvasInput(
        path=OUT, width=32, height=32, overwrite=True)))

    # Stage 2/3 — silhouette in flat base color (asymmetric, NOT mirrored)
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=5, y=2, width=23, height=20, color=B)))   # cranium
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=7, y=13, width=16, height=11, color=B)))  # maxilla/face
    chk(await S.pixel_draw_ellipse(S.DrawEllipseInput(path=OUT, x=9, y=22, width=12, height=8, color=B)))   # mandible (offset left)
    chk(await S.pixel_draw_rect(S.DrawRectInput(path=OUT, x=20, y=16, width=5, height=3, color=B)))         # zygomatic arch (near)

    # Stage 4 — gentle sphere shade, 4 upper ramp steps only (60/25/15), top_left
    chk(await S.pixel_shade_region(S.ShadeRegionInput(
        path=OUT, mode="sphere", light="top_left", target=B, ramp=[D, B, L, W])))

    # Stage 5 — details (grid columns are canvas x-4)
    chk(await S.pixel_paint_grid(S.PaintGridInput(
        path=OUT, x=4, y=12,
        rows=[
            "....LLL...WWWWWW........",  # y12 brow: far lit, near bright
            "....SSS...SSSSSS........",  # y13 sockets: far narrow / near wide
            "....SSS...SSSSSS........",  # y14
            "....SSS...SSSSSS........",  # y15
            "....SS.....SSSSS........",  # y16 socket floors
            "............SSS.LLL.....",  # y17 near socket tail + cheekbone light
            "........SS......ddd.....",  # y18 nasal top + under-cheek shadow
            ".......SSS.......dd.....",  # y19 nasal + jaw hinge shadow (soft)
            ".......SSSS......d......",  # y20
            "........SSS.............",  # y21
            "........SS..............",  # y22 nasal tip
            ".....LLkLLkLLkLL........",  # y23 upper teeth, 1px dark seams
            ".....LLkLLkLLkLL........",  # y24
            ".....kkkkkkkkkkk........",  # y25 bite line
            ".....BLLkLLkLLdd........",  # y26 lower teeth (jaw offset left)
            "......BBBBBBBBdd........",  # y27 chin: base bone, shadow right
            "......BBBBBBBdd.........",  # y28
            ".......ddddddd..........",  # y29 mandible bottom rim
        ],
        legend={"S": SOCK, "k": K, "d": D, "L": L, "W": W, "B": B})))

    # Stage 6 — finish: solid outline in the ramp's darkest brown (in budget)
    chk(await S.pixel_outline_sprite(S.OutlineInput(path=OUT, mode="solid", color=K, corners=False)))

    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=VIEW, scale=12)))
    print(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))
    print(chk(await S.pixel_ascii_view(S.AsciiViewInput(path=OUT))))

asyncio.run(main())
