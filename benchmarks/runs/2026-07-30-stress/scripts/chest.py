"""Stress test: 'Open treasure chest spilling gold', 48x48, 3/4 view.
Pipeline: ramps -> flats -> bevel/sphere auto-shade (top_left) -> paint_grid
details (plank grain, metal brackets/lock, glow, glints) -> selective outline
-> palette snap. Gold is the hero material (7-step ramp)."""
import asyncio, json, sys

import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
REPO = f"{_REPO}"
sys.path.insert(0, REPO)
from pixelart_mcp import server as S

RUN = REPO + "/benchmarks/runs/2026-07-30-stress"
OUT = RUN + "/chest.png"
VIEW = RUN + "/chest@view.png"

W = H = 48
CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"


def chk(res):
    txt = res if isinstance(res, str) else res[0]
    assert not txt.startswith("Error"), txt
    return txt


def grid_call(pixmap):
    legend, rows, color_char = {}, [], {}
    for y in range(H):
        row = []
        for x in range(W):
            c = pixmap.get((x, y))
            if c is None:
                row.append(".")
            else:
                ch = color_char.get(c)
                if ch is None:
                    ch = CHARS[len(color_char)]
                    color_char[c] = ch
                    legend[ch] = c
                row.append(ch)
        rows.append("".join(row))
    return rows, legend


# --- geometry -------------------------------------------------------------
def side_o(x):
    """Vertical rise of the receding right side face at column x (34..42)."""
    return (x - 33 + 1) // 2


def in_ellipse(x, y, cx, cy, rx, ry):
    dx, dy = x + 0.5 - cx, y + 0.5 - cy
    return (dx / rx) ** 2 + (dy / ry) ** 2 <= 1.0


def in_pile(x, y):
    return (in_ellipse(x, y, 21.0, 27.0, 13.0, 5.5)      # main mound
            or in_ellipse(x, y, 21.0, 24.5, 7.0, 4.2))   # crest


def in_front(x, y):
    return 5 <= x <= 33 and 28 <= y <= 44


def in_side(x, y):
    return 34 <= x <= 42 and 28 - side_o(x) <= y <= 44 - side_o(x)


def in_lid(x, y):
    if not (11 <= x <= 42 and 6 <= y <= 23):
        return False
    if (x, y) in ((11, 6), (12, 6), (11, 7), (42, 6), (41, 6), (42, 7)):
        return False  # rounded top corners
    return True


def in_lid_panel(x, y):
    return 13 <= x <= 40 and 8 <= y <= 21


def in_opening(x, y):
    if not 24 <= y <= 27:
        return False
    s = 27 - y
    return 6 + 2 * s <= x <= 34 + 2 * s


async def main():
    # Stage 1 -- ramps (dark -> light); gold is the hero: 7 steps.
    wood = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#8a5f38", steps=5, hue_shift_deg=15))))["ramp"]
    gold = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#c8922e", steps=7, hue_shift_deg=8))))["ramp"]
    gray = json.loads(chk(await S.pixel_build_ramp(S.BuildRampInput(color="#6a707a", steps=5, hue_shift_deg=10))))["ramp"]
    print("wood:", wood, "\ngold:", gold, "\ngray:", gray)

    chk(await S.pixel_create_canvas(S.CreateCanvasInput(path=OUT, width=W, height=H, overwrite=True)))

    # Stage 2+3 -- flats, back to front: lid, interior, box, pile.
    flats = {}
    for y in range(H):
        for x in range(W):
            if in_lid(x, y):
                flats[(x, y)] = wood[1] if in_lid_panel(x, y) else wood[2]
            if in_opening(x, y):
                flats[(x, y)] = wood[0]           # chest interior: darkest (AO)
            if in_front(x, y):
                flats[(x, y)] = wood[2]
            if in_side(x, y):
                flats[(x, y)] = wood[1]           # receding side face, darker
            if in_pile(x, y):
                flats[(x, y)] = gold[3]
    rows, legend = grid_call(flats)
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=0, y=0, rows=rows, legend=legend)))

    # Stage 4 -- auto-shade, ONE light: top_left.
    chk(await S.pixel_shade_region(S.ShadeRegionInput(path=OUT, mode="bevel", light="top_left", target=wood[2], ramp=wood, levels=1)))
    chk(await S.pixel_shade_region(S.ShadeRegionInput(path=OUT, mode="bevel", light="top_left", target=wood[1], ramp=wood, levels=1)))
    chk(await S.pixel_shade_region(S.ShadeRegionInput(path=OUT, mode="sphere", light="top_left", target=gold[3], ramp=gold[1:6])))

    # Stage 5 -- details, one z-ordered overlay grid.
    det = {}

    # Wood grain: 1px wavy lines following each plank's direction.
    wave = (0, 0, 1, 1, 1, 0, 0, 0, -1, -1, 0, 0)
    def grain_row(base_y, x0, x1, color, face_test, breaks=(5, 11), phase=0):
        for x in range(x0, x1 + 1):
            i = (x + phase) % 12
            if i in breaks:
                continue
            y = base_y + wave[i]
            if face_test(x, y) and not in_pile(x, y):
                det[(x, y)] = color
    # front face planks (horizontal): seams + grain
    for sy in (33, 39):
        for x in range(5, 34):
            if not in_pile(x, sy):
                det[(x, sy)] = wood[0]
    grain_row(30, 6, 32, wood[1], in_front)
    grain_row(36, 6, 32, wood[1], in_front, phase=5)
    grain_row(42, 6, 32, wood[1], in_front, phase=9)
    # side face planks (following the slope): seams + short grain dashes
    for x in range(34, 43):
        o = side_o(x)
        det[(x, 33 - o)] = wood[0]
        det[(x, 39 - o)] = wood[0]
        if x % 3 != 0:
            det[(x, 30 - o)] = wood[0]
            det[(x, 36 - o)] = wood[0]
    # lid panel grain (horizontal, broken)
    grain_row(11, 14, 39, wood[0], in_lid_panel, breaks=(3, 8))
    grain_row(15, 14, 39, wood[0], in_lid_panel, breaks=(3, 8), phase=6)
    # knot on the front face
    det[(11, 41)] = wood[1]
    det[(12, 41)] = wood[0]
    det[(12, 40)] = wood[1]

    # Front wall top edge (lit rim) painted over the pile line.
    for x in range(5, 34):
        det[(x, 28)] = wood[3]

    # Gold glow lighting the lid's underside: lighten the panel's lowest rows,
    # sparse warm checker only at the very bottom, lit lower rim edge.
    for x in range(13, 40):
        if in_lid_panel(x, 20) and not in_pile(x, 20):
            det[(x, 20)] = wood[2]
    for x in range(13, 40):
        if in_lid_panel(x, 21) and not in_pile(x, 21):
            det[(x, 21)] = gold[2] if x % 2 == 0 else wood[2]
    for x in range(12, 41):
        if in_lid(x, 23) and not in_pile(x, 23):
            det[(x, 23)] = wood[3]

    # Metal: corner brackets + lock plate (own gray ramp, 1px bright edges).
    def bracket(x0, y0, w_, h_):
        for yy in range(y0, y0 + h_):
            for xx in range(x0, x0 + w_):
                if yy == y0 or xx == x0:
                    det[(xx, yy)] = gray[4]      # bright top/left edge
                elif yy == y0 + h_ - 1 or xx == x0 + w_ - 1:
                    det[(xx, yy)] = gray[0]      # dark bottom/right edge
                else:
                    det[(xx, yy)] = gray[2]
    bracket(5, 28, 2, 5); bracket(5, 28, 4, 2)      # top-left L
    bracket(32, 28, 2, 6)                           # top-right
    bracket(5, 40, 2, 5); bracket(5, 43, 6, 2)      # bottom-left L
    bracket(32, 40, 2, 5); bracket(28, 43, 6, 2)    # bottom-right L
    bracket(17, 32, 7, 7)                           # lock plate
    det[(20, 34)] = gray[0]                          # keyhole
    det[(20, 35)] = gray[0]
    det[(20, 36)] = gray[0]

    # Gold: overflow over the rim, spill trickles, coin texture, sparse glints.
    for x, y in ((14, 28), (15, 28), (16, 28), (15, 29), (22, 28), (23, 28),
                 (24, 28), (23, 29), (30, 28), (31, 28)):
        det[(x, y)] = gold[2]
    # left trickle: tumbling coin dashes with gaps, small puddle at the bottom
    for y in (29, 30, 32, 33, 35):
        det[(10, y)] = gold[4] if y == 29 else gold[3]
        det[(11, y)] = gold[2]
    det[(9, 37)] = gold[3]; det[(10, 37)] = gold[4]; det[(11, 37)] = gold[4]; det[(12, 37)] = gold[3]
    det[(9, 38)] = gold[2]; det[(10, 38)] = gold[3]; det[(11, 38)] = gold[3]; det[(12, 38)] = gold[2]
    # right trickle
    for y in (29, 30, 32):
        det[(27, y)] = gold[4] if y == 29 else gold[3]
        det[(28, y)] = gold[2]
    det[(26, 34)] = gold[3]; det[(27, 34)] = gold[4]; det[(28, 34)] = gold[3]; det[(29, 34)] = gold[2]
    det[(26, 35)] = gold[2]; det[(27, 35)] = gold[3]; det[(28, 35)] = gold[3]; det[(29, 35)] = gold[2]
    # coin edges (short light dashes) + gaps (dark pixels) on the pile
    for x, y in ((14, 23), (15, 23), (22, 22), (23, 22), (18, 26), (19, 26),
                 (26, 25), (27, 25), (11, 28), (30, 26), (16, 21), (17, 21)):
        det[(x, y)] = gold[4]
    for x, y in ((17, 24), (25, 23), (13, 27), (28, 27), (19, 22)):
        det[(x, y)] = gold[2]
    # fallen coins on the ground
    for xx in range(1, 5):
        det[(xx, 43)] = gold[4] if xx in (2, 3) else gold[3]
        det[(xx, 44)] = gold[3]
        det[(xx, 45)] = gold[1]
    for xx in range(36, 41):
        det[(xx, 42)] = gold[4] if xx in (37, 38) else gold[3]
        det[(xx, 43)] = gold[3]
        det[(xx, 44)] = gold[1]
    # sparse isolated glints: brightest gold step
    for x, y in ((16, 22), (21, 21), (26, 24), (12, 26), (30, 27), (2, 43), (37, 42)):
        det[(x, y)] = gold[6]

    rows, legend = grid_call(det)
    chk(await S.pixel_paint_grid(S.PaintGridInput(path=OUT, x=0, y=0, rows=rows, legend=legend)))

    # Stage 6 -- finish.
    chk(await S.pixel_outline_sprite(S.OutlineInput(path=OUT, mode="selective", corners=False)))
    chk(await S.pixel_apply_palette(S.ApplyPaletteInput(path=OUT, palette=wood + gold + gray)))

    print(chk(await S.pixel_canvas_info(S.InfoInput(path=OUT))))
    chk(await S.pixel_export_png(S.ExportPngInput(path=OUT, out_path=VIEW, scale=10)))
    print("done")


asyncio.run(main())
