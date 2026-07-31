"""Showcase: 'Dusk Wanderer' — a 128x96, 24-frame seamless loop from ONE sheet.

Exercises the whole server: ramps, dithered gradients, polygons, curves,
auto-shading, text-grid drawing, mirroring, selective outlines, sub-pixel AA
and batching to draw the sheet; then the rig layer to animate it, driving all
seven motion channels —

  dx       parallax scroll (ground, grass, mist), leg/arm swing, birds, leaf
  dy       body bob, bird flight, lantern sway, leaf fall
  squash   lantern flame guttering
  flip     leaf tumbling
  rot      leaf tumbling (90-degree steps only — pixel art survives nothing else)
  visible  stars twinkling, and hiding the pose-library parts
  use      bird wing-flap and flame shapes, by part-swap

Seamlessness comes from two rules: layers that tile scroll exactly one tile
period per loop, and sprites that do not tile start and end off-frame, so the
wrap lands where nobody can see it.
"""
import asyncio, json, random, sys
import os as _os
_REPO = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.exists(_os.path.join(_REPO, "pyproject.toml")):
    _REPO = _os.path.dirname(_REPO)
sys.path.insert(0, f"{_REPO}")
from pixelart_mcp import server as S

HERE = f"{_REPO}/benchmarks/examples"
SHEET = f"{HERE}/dusk.png"
RIG = f"{HERE}/dusk.rig.json"

FW, FH = 128, 96          # frame
FRAMES = 24
HORIZON = 58

# sweetie16, used as a dusk key: dark blue zenith down to gold at the horizon
NIGHT, DEEP = "#1a1c2c", "#29366f"
SLATE, HAZE = "#333c57", "#566c86"
MIST_C, PALE = "#94b0c2", "#f4f4f4"
PLUM, EMBER = "#b13e53", "#ef7d57"
GOLD, MOSS = "#ffcd75", "#38b764"

# --- source sheet layout -----------------------------------------------------
GROUND_Y, GROUND_W, GROUND_H, GROUND_P = 96, 152, 38, 24    # period 24 -> 1px/frame
GRASS_Y, GRASS_W, GRASS_H, GRASS_P = 136, 176, 18, 48       # period 48 -> 2px/frame
MIST_Y, MIST_W, MIST_H, MIST_P = 156, 176, 10, 48
BIN_Y = 170
SHEET_W, SHEET_H = 224, 200


def chk(res):
    txt = res if isinstance(res, str) else res[0]
    assert not txt.startswith("Error"), txt
    return txt


async def batch(ops, preview=False):
    return chk(await S.pixel_batch(S.BatchInput(
        path=SHEET, operations=[S.BatchOperation(op=o, params=p) for o, p in ops],
        preview=preview)))


async def ramp(color, steps=5, hue=22.0):
    return json.loads(chk(await S.pixel_build_ramp(
        S.BuildRampInput(color=color, steps=steps, hue_shift_deg=hue))))["ramp"]


# ---------------------------------------------------------------------------
# Stage 1 — backdrop: sky, sun, mountains, clouds, treeline (all static)
# ---------------------------------------------------------------------------

async def draw_backdrop():
    ops = [
        # dithered dusk sky; bayer4 is what stops the bands reading as stripes
        ("draw_gradient", {"x": 0, "y": 0, "width": FW, "height": HORIZON + 2,
                           "colors": [NIGHT, DEEP, HAZE, PLUM, EMBER, GOLD],
                           "angle_deg": 90, "dither": "bayer4"}),
    ]
    # sun sitting on the horizon, with a soft radial bloom around it
    ops += [
        ("draw_gradient", {"x": 62, "y": 28, "width": 44, "height": 44,
                           "colors": [GOLD, EMBER, "transparent"], "kind": "radial",
                           "center_x": 84, "center_y": 50, "radius": 22, "dither": "bayer4"}),
        ("draw_ellipse", {"x": 76, "y": 42, "width": 17, "height": 17, "color": GOLD}),
        ("draw_ellipse", {"x": 79, "y": 45, "width": 11, "height": 11, "color": "#ffe9a8"}),
    ]
    # far range: lighter and lower contrast — aerial perspective does the depth
    ops.append(("draw_polygon", {"points": [
        {"x": -4, "y": 60}, {"x": 6, "y": 46}, {"x": 16, "y": 52}, {"x": 27, "y": 38},
        {"x": 38, "y": 50}, {"x": 48, "y": 44}, {"x": 60, "y": 55}, {"x": 72, "y": 41},
        {"x": 86, "y": 53}, {"x": 98, "y": 45}, {"x": 112, "y": 55}, {"x": 132, "y": 47},
        {"x": 132, "y": 62}, {"x": -4, "y": 62}], "color": HAZE}))
    # snow catching the last light on the two tallest peaks
    ops += [
        ("draw_polygon", {"points": [{"x": 27, "y": 38}, {"x": 32, "y": 44}, {"x": 22, "y": 44}],
                          "color": MIST_C}),
        ("draw_polygon", {"points": [{"x": 72, "y": 41}, {"x": 77, "y": 47}, {"x": 67, "y": 47}],
                          "color": MIST_C}),
    ]
    # nearer ridge: darker, so the ranges separate by value not by outline
    ops.append(("draw_polygon", {"points": [
        {"x": -4, "y": 62}, {"x": 10, "y": 54}, {"x": 24, "y": 58}, {"x": 40, "y": 51},
        {"x": 55, "y": 57}, {"x": 70, "y": 52}, {"x": 88, "y": 58}, {"x": 104, "y": 53},
        {"x": 120, "y": 58}, {"x": 132, "y": 55}, {"x": 132, "y": 64}, {"x": -4, "y": 64}],
        "color": SLATE}))
    await batch(ops)

    # static clouds, drawn as soft stacked bars rather than sprites: a cloud that
    # had to cross the frame inside 24 frames would have to move ~6px/frame.
    rnd = random.Random(7)
    cl = []
    for cx, cy, w, tone in ((14, 12, 30, PLUM), (58, 8, 24, "#6b4a70"),
                            (92, 16, 28, PLUM), (36, 22, 18, "#6b4a70")):
        for i in range(3):
            iw = w - i * rnd.randint(4, 7)
            if iw < 4:
                break
            cl.append(("draw_rect", {"x": cx + (w - iw) // 2 + rnd.randint(-2, 2),
                                     "y": cy + i * 2, "width": iw, "height": 2,
                                     "color": tone if i else "#7d5580"}))
    await batch(cl)

    # treeline: darkest value in the scene, so it reads as the nearest static mass
    trees = []
    rnd = random.Random(3)
    x = -3
    while x < FW + 4:
        h = rnd.randint(7, 14)
        w = rnd.randint(5, 8)
        base = HORIZON + 3
        trees.append(("draw_polygon", {"points": [
            {"x": x + w // 2, "y": base - h}, {"x": x + w, "y": base}, {"x": x, "y": base}],
            "color": NIGHT}))
        x += rnd.randint(3, 6)
    await batch(trees)


# ---------------------------------------------------------------------------
# Stage 2 — scrolling strips. Content repeats every P px so one loop = one tile.
# ---------------------------------------------------------------------------

async def draw_strips():
    g = await ramp(SLATE, 5)
    # Flat shadow with one lit band at the horizon. The sky is already a big
    # dithered gradient; dithering the ground too leaves the eye nowhere to
    # rest and the whole frame reads as texture. And it deliberately does NOT
    # fade to black — the foreground grass is a NIGHT silhouette, so the
    # darkest value in frame has to belong to the nearest thing.
    ops = [("draw_rect", {"x": 0, "y": GROUND_Y, "width": GROUND_W, "height": GROUND_H,
                          "color": DEEP}),
           ("draw_gradient", {"x": 0, "y": GROUND_Y, "width": GROUND_W, "height": 13,
                              "colors": [g[2], g[1], DEEP], "angle_deg": 90, "dither": "bayer4"})]
    # one tile of speckle, repeated — fine noise hides the 24px period entirely
    rnd = random.Random(11)
    tile = [(rnd.randrange(GROUND_P), rnd.randrange(2, GROUND_H), rnd.choice([g[0], g[2], DEEP]))
            for _ in range(26)]
    px = []
    for tx, ty, c in tile:
        for rep in range(GROUND_W // GROUND_P + 2):
            x = tx + rep * GROUND_P
            if x < GROUND_W:
                px.append({"x": x, "y": GROUND_Y + ty, "color": c})
    ops.append(("draw_pixels", {"pixels": px}))
    await batch(ops)

    # foreground grass: silhouette tufts on a longer period, so the two scrolling
    # layers never visibly line up
    rnd = random.Random(5)
    tufts = []
    for rep in range(GRASS_W // GRASS_P + 2):
        r2 = random.Random(5)
        x = 0
        while x < GRASS_P:
            h = r2.randint(3, 9)
            bx = rep * GRASS_P + x
            if bx < GRASS_W:
                tufts.append(("draw_polygon", {"points": [
                    {"x": bx, "y": GRASS_Y + GRASS_H - 1}, {"x": bx + 2, "y": GRASS_Y + GRASS_H - 1 - h},
                    {"x": bx + 4, "y": GRASS_Y + GRASS_H - 1}], "color": NIGHT}))
            x += r2.randint(2, 5)
    tufts.append(("draw_rect", {"x": 0, "y": GRASS_Y + GRASS_H - 3, "width": GRASS_W,
                                "height": 3, "color": NIGHT}))
    await batch(tufts)

    # low mist band, translucent so the treeline reads through it
    rnd = random.Random(13)
    mist = []
    for rep in range(MIST_W // MIST_P + 2):
        r2 = random.Random(13)
        for _ in range(7):
            bx = rep * MIST_P + r2.randrange(MIST_P)
            w = r2.randint(9, 20)
            y = MIST_Y + r2.randint(2, MIST_H - 3)
            if bx < MIST_W:
                mist.append(("draw_rect", {"x": bx, "y": y, "width": w, "height": 2,
                                           "color": f"{MIST_C}55"}))
    await batch(mist)


# ---------------------------------------------------------------------------
# Stage 3 — the parts bin: character, lantern, birds, leaf, star
# ---------------------------------------------------------------------------
# Bin coordinates. Limbs are drawn APART here and placed together on the body,
# which is the only way a side view's front and back limbs can overlap.
P = {
    "head":      (0, BIN_Y, 12, 12),
    "torso":     (14, BIN_Y, 10, 18),
    "arm_back":  (26, BIN_Y, 4, 14),
    "arm_front": (32, BIN_Y, 4, 14),
    "leg_back":  (38, BIN_Y, 6, 16),
    "leg_front": (46, BIN_Y, 6, 16),
    "lantern":   (54, BIN_Y, 13, 15),
    "flame_a":   (69, BIN_Y, 3, 5),
    "flame_b":   (74, BIN_Y, 3, 5),
    "flame_c":   (79, BIN_Y, 3, 5),
    "bird_up":   (84, BIN_Y, 5, 3),
    "bird_mid":  (91, BIN_Y, 5, 3),
    "bird_dn":   (98, BIN_Y, 5, 3),
    "leaf":      (105, BIN_Y, 5, 5),
    "star":      (112, BIN_Y, 3, 3),
    "shadow":    (117, BIN_Y, 12, 4),
}


async def _part(name, w, h, ops, spaa=True):
    """Build one part on its own canvas, then stamp it into the bin.

    Per-part canvases are not fussiness: pixel_shade_region groups by COLOR
    across the whole canvas, so six cloak-colored limbs drawn side by side
    would shade as one blob spanning the bin. Isolating each part is what
    makes auto-shading — and apply_spaa, which is also whole-canvas — correct.
    """
    tmp = f"{HERE}/_tmp.png"
    chk(await S.pixel_create_canvas(S.CreateCanvasInput(
        path=tmp, width=w, height=h, background="transparent", overwrite=True)))
    chk(await S.pixel_batch(S.BatchInput(
        path=tmp, operations=[S.BatchOperation(op=o, params=q) for o, q in ops])))
    if spaa:
        # A part with no diagonals (a plain rect limb) has nothing to soften, and
        # apply_spaa reports that as an error. Here it just means "no-op".
        r = await S.pixel_apply_spaa(S.SpaaInput(path=tmp, strength=0.45, interior=False))
        txt = r if isinstance(r, str) else r[0]
        assert not txt.startswith("Error") or "no staircase" in txt, txt
    bx, by, _, _ = P[name]
    chk(await S.pixel_copy_region(S.CopyRegionInput(
        path=tmp, x=0, y=0, width=w, height=h,
        dest_path=SHEET, dest_x=bx, dest_y=by, mode="replace")))
    _os.remove(tmp)


async def draw_parts():
    cloak = await ramp(SLATE, 5)
    skin = await ramp("#c07a55", 5)
    LIGHT = "right"          # the lantern and the sunset are both stage-right

    # A 12px head has no room for auto-shading to model a hood AND leave the
    # face readable — the sphere highlight and the skin patch fight, and it
    # reads as a lit rectangle. At this size the grid is the right tool: place
    # the hood shadow, the face notch and the lantern rim by hand.
    await _part("head", 12, 12, [
        ("paint_grid", {"x": 0, "y": 0, "rows": [
            "....DDdd....", "..DDDdddd...", ".DDDddddddL.", ".DDDddddddL.",
            ".DDdsssSddL.", ".DDdsseSddL.", ".DDdsssSddL.", ".DDddssSddL.",
            ".DDDddddddL.", "..DDDdddddL.", "...DDdddd...", "............"],
            "legend": {"D": cloak[0], "d": cloak[1], "L": cloak[2],
                       "s": skin[1], "S": skin[3], "e": NIGHT}}),
    ])
    await _part("torso", 10, 18, [
        ("draw_rect", {"x": 0, "y": 0, "width": 10, "height": 18, "color": cloak[1]}),
        ("draw_rect", {"x": 0, "y": 0, "width": 2, "height": 18, "color": cloak[0]}),
        ("draw_rect", {"x": 9, "y": 1, "width": 1, "height": 16, "color": cloak[2]}),
        ("draw_rect", {"x": 3, "y": 0, "width": 5, "height": 1, "color": cloak[0]}),
        ("draw_rect", {"x": 0, "y": 10, "width": 10, "height": 2, "color": NIGHT}),
    ])
    # Limbs are 4-6px wide. Auto-shading needs room to put a ramp across a form,
    # and at this width it spends the whole ramp in four columns — which reads as
    # rainbow stripes, not roundness. Two hand-placed columns is what the width
    # can actually carry: shadow away from the lantern, rim light toward it.
    for nm, base, dark, lit, hand in (
            ("arm_back", cloak[0], cloak[0], cloak[1], skin[0]),
            ("arm_front", cloak[1], cloak[0], cloak[3], skin[2])):
        await _part(nm, 4, 14, [
            ("draw_rect", {"x": 0, "y": 0, "width": 4, "height": 11, "color": base}),
            ("draw_rect", {"x": 0, "y": 0, "width": 1, "height": 11, "color": dark}),
            ("draw_rect", {"x": 3, "y": 1, "width": 1, "height": 9, "color": lit}),
            ("draw_rect", {"x": 0, "y": 11, "width": 4, "height": 3, "color": hand}),
        ])
    for nm, base, dark, lit, boot in (
            ("leg_back", cloak[0], NIGHT, cloak[1], NIGHT),
            ("leg_front", cloak[1], cloak[0], cloak[2], DEEP)):
        await _part(nm, 6, 16, [
            ("draw_rect", {"x": 1, "y": 0, "width": 4, "height": 12, "color": base}),
            ("draw_rect", {"x": 1, "y": 0, "width": 1, "height": 12, "color": dark}),
            ("draw_rect", {"x": 4, "y": 1, "width": 1, "height": 10, "color": lit}),
            ("draw_rect", {"x": 0, "y": 12, "width": 6, "height": 4, "color": boot}),
            ("draw_rect", {"x": 5, "y": 13, "width": 1, "height": 2, "color": cloak[1]}),
        ])

    # lantern: translucent bloom, then the cage over it. The flame is a separate
    # part drawn UNDER the cage, so the bars read in front of the light.
    lx, ly, lw, lh = P["lantern"]
    fy = P["flame_a"][1]
    await batch([
        ("draw_gradient", {"x": lx, "y": ly, "width": lw, "height": lh,
                           "colors": [f"{GOLD}70", f"{EMBER}26", "transparent"], "kind": "radial",
                           "center_x": lx + 6, "center_y": ly + 8, "radius": 7, "dither": "bayer4"}),
        ("paint_grid", {"x": lx + 4, "y": ly + 2, "rows": [
            "..#..", ".###.", "#...#", "#...#", "#...#", "#...#", "#####", "..#.."],
            "legend": {"#": NIGHT}}),
        ("paint_grid", {"x": P["flame_a"][0], "y": fy, "rows": [".g.", ".g.", "geg", "geg", ".e."],
                        "legend": {"g": GOLD, "e": EMBER}}),
        ("paint_grid", {"x": P["flame_b"][0], "y": fy, "rows": [".g.", "geg", "geg", ".e.", ".e."],
                        "legend": {"g": GOLD, "e": EMBER}}),
        ("paint_grid", {"x": P["flame_c"][0], "y": fy, "rows": ["..g", ".gg", "geg", ".eg", ".e."],
                        "legend": {"g": GOLD, "e": EMBER}}),
        # three wing poses; the `use` channel swaps between them for the flap.
        # 5x3 — at this distance a bird is a chevron, and anything larger reads
        # as a smudge rather than a silhouette.
        ("paint_grid", {"x": P["bird_up"][0], "y": fy,
                        "rows": ["#...#", ".#.#.", "..#.."], "legend": {"#": NIGHT}}),
        ("paint_grid", {"x": P["bird_mid"][0], "y": fy,
                        "rows": [".....", "#...#", ".###."], "legend": {"#": NIGHT}}),
        ("paint_grid", {"x": P["bird_dn"][0], "y": fy,
                        "rows": [".....", ".###.", "#...#"], "legend": {"#": NIGHT}}),
        ("paint_grid", {"x": P["leaf"][0], "y": fy, "rows": [
            ".ee..", "eEEe.", ".eEEe", "..ee.", "....."], "legend": {"e": PLUM, "E": EMBER}}),
        ("paint_grid", {"x": P["star"][0], "y": fy, "rows": [".#.", "#o#", ".#."],
                        "legend": {"#": f"{PALE}99", "o": PALE}}),
        # contact shadow — without one the wanderer reads as hovering
        ("draw_ellipse", {"x": P["shadow"][0], "y": fy, "width": 12, "height": 4,
                          "color": f"{NIGHT}88"}),
    ])


# ---------------------------------------------------------------------------
# Stage 4 — the rig: where each part lands, and in what order
# ---------------------------------------------------------------------------
# Frame layout: horizon at 58, the wanderer walking at x~40 with feet at y~80.
CX, FEET = 39, 78
PLACE = {                       # name -> (source part, at_x, at_y, z, anchor)
    "backdrop":   ("backdrop", 0, 0, 0, "top"),
    "star_a":     ("star", 18, 9, 1, "center"),
    "star_b":     ("star", 47, 5, 1, "center"),
    "star_c":     ("star", 108, 12, 1, "center"),
    "mist":       ("mist", 0, 52, 2, "top"),
    "bird_a":     ("bird_up", 0, 17, 3, "center"),
    "bird_b":     ("bird_up", 0, 26, 3, "center"),
    "bird_pose_mid": ("bird_mid", 0, 17, 3, "center"),   # pose library, kept hidden
    "bird_pose_dn":  ("bird_dn", 0, 17, 3, "center"),
    "ground":     ("ground", 0, 58, 4, "top"),
    # Vertical spacing is chosen so the masses OVERLAP: the torso runs 3px over
    # the hips and 2px over the jaw, so a swinging limb never tears a gap open.
    "shadow":     ("shadow", CX, FEET - 3, 5, "center"),
    "arm_back":   ("arm_back", CX - 1, FEET - 28, 6, "center"),
    "leg_back":   ("leg_back", CX + 1, FEET - 15, 7, "bottom"),
    "leg_front":  ("leg_front", CX + 4, FEET - 15, 8, "bottom"),
    "torso":      ("torso", CX + 1, FEET - 30, 9, "bottom"),
    "head":       ("head", CX, FEET - 40, 10, "center"),
    "arm_front":  ("arm_front", CX + 8, FEET - 28, 11, "center"),
    "flame":      ("flame_a", CX + 14, FEET - 16, 12, "center"),
    "flame_pose_b": ("flame_b", CX + 14, FEET - 16, 12, "center"),
    "flame_pose_c": ("flame_c", CX + 14, FEET - 16, 12, "center"),
    "lantern":    ("lantern", CX + 9, FEET - 20, 13, "center"),
    "leaf":       ("leaf", 0, 0, 14, "center"),
    "grass":      ("grass", 0, 78, 15, "top"),
}
STRIP = {"backdrop": (0, 0, FW, FH),
         "ground": (0, GROUND_Y, GROUND_W, GROUND_H),
         "grass": (0, GRASS_Y, GRASS_W, GRASS_H),
         "mist": (0, MIST_Y, MIST_W, MIST_H)}


def parts_spec():
    out = []
    for name, (src, ax, ay, z, anchor) in PLACE.items():
        x, y, w, h = STRIP[src] if src in STRIP else P[src]
        out.append({"name": name, "x": x, "y": y, "width": w, "height": h,
                    "at_x": ax, "at_y": ay, "z": z, "anchor": anchor})
    return out


# ---------------------------------------------------------------------------
# Stage 5 — motion. One key per frame with step easing gives exact control;
# the preset shapes are for when you want the cycle chosen for you.
# ---------------------------------------------------------------------------
import math

STRIDES = 3          # 3 strides over 24 frames = the classic 8-frame walk
HIDE = {"visible": [[0.0, 0]]}


def step_keys(vals):
    return {"keys": [[round(i / FRAMES, 6), v] for i, v in enumerate(vals)], "easing": "step"}


def scroll(period):
    """Exactly one tile period per loop — that is what makes the seam vanish."""
    return step_keys([-round(i * period / FRAMES) for i in range(FRAMES)])


def cross(a, b):
    """Straight traverse; start and end off-frame so the wrap is unseen."""
    return step_keys([round(a + (b - a) * i / (FRAMES - 1)) for i in range(FRAMES)])


def stride(vals, amp, easing="linear"):
    return {"keys": [[round(s / STRIDES + q / (4 * STRIDES), 6), v * amp]
                     for s in range(STRIDES) for q, v in enumerate(vals)], "easing": easing}


def bob(amp=1, phase=0.0):
    return {"keys": [[round((i / 12 + phase) % 1.0, 6), (-amp if i % 2 else 0)]
                     for i in range(12)], "easing": "ease"}


FLAP = ["bird_a", "bird_pose_mid", "bird_pose_dn", "bird_pose_mid"]
FLICK = ["flame", "flame_pose_b", "flame_pose_c", "flame_pose_b", "flame", "flame_pose_c"]

MOTION = {
    # --- parallax: near layers move faster, and each returns to its own start
    "ground": {"dx": scroll(GROUND_P)},                 # 1px/frame
    "grass":  {"dx": scroll(GRASS_P)},                  # 2px/frame
    "mist":   {"dx": scroll(MIST_P), "dy": bob(1, 0.3)},

    # --- the walk: legs oppose arms, body dips twice per stride
    "leg_front": {"dx": stride([1, 0, -1, 0], 4), "dy": stride([0, 0, 0, -3], 1, "ease")},
    "leg_back":  {"dx": stride([-1, 0, 1, 0], 4), "dy": stride([0, -3, 0, 0], 1, "ease")},
    "arm_front": {"dx": stride([-1, 0, 1, 0], 3), "dy": bob()},
    "arm_back":  {"dx": stride([1, 0, -1, 0], 3), "dy": bob()},
    "torso":     {"dy": bob()},
    "shadow":    {"squash": bob(1)},
    "head":      {"dy": bob()},

    # --- the lantern lags the body by a beat and its flame gutters
    "lantern": {"dy": bob(1, 0.04), "dx": stride([-1, 0, 1, 0], 1)},
    "flame": {
        "dy": bob(1, 0.04),
        "dx": stride([-1, 0, 1, 0], 1),
        "squash": step_keys([(0, 1, 0, -1, 1, 0, -1, 0)[i % 8] for i in range(FRAMES)]),
        "use": step_keys([FLICK[i % 6] for i in range(FRAMES)]),
    },
    "flame_pose_b": HIDE, "flame_pose_c": HIDE,

    # --- birds cross the sky, wings flapping by part-swap
    "bird_a": {"dx": cross(134, -12), "dy": bob(2, 0.1), "use": step_keys(
        [FLAP[(i // 2) % 4] for i in range(FRAMES)])},
    # both birds must END off-frame: a traverse that stops at a visible x pops
    # out of existence at the loop point
    "bird_b": {"dx": cross(160, -14), "dy": bob(2, 0.55), "use": step_keys(
        [FLAP[(i // 2 + 1) % 4] for i in range(FRAMES)])},
    "bird_pose_mid": HIDE, "bird_pose_dn": HIDE,

    # --- one leaf, tumbling: rot and flip are the only orientation tools pixel
    #     art tolerates, and together they read as a full tumble
    "leaf": {
        "dy": cross(-8, 104),
        "dx": step_keys([round(96 - 34 * i / (FRAMES - 1) + 3 * math.sin(i * 0.9))
                         for i in range(FRAMES)]),
        "rot": step_keys([(0, 90, 180, 270)[(i // 2) % 4] for i in range(FRAMES)]),
        "flip": step_keys([bool((i // 4) % 2) for i in range(FRAMES)]),
    },

    # --- stars, each blinking on its own phase
    "star_a": {"visible": [[0.0, 1], [0.30, 0], [0.38, 1]]},
    "star_b": {"visible": [[0.0, 1], [0.62, 0], [0.72, 1]]},
    "star_c": {"visible": [[0.0, 0], [0.16, 1], [0.84, 0]]},
}


async def main():
    chk(await S.pixel_create_canvas(S.CreateCanvasInput(
        path=SHEET, width=SHEET_W, height=SHEET_H, background="transparent", overwrite=True)))
    await draw_backdrop()
    await draw_strips()
    await draw_parts()

    chk(await S.pixel_define_rig(S.DefineRigInput(
        rig_path=RIG, source=SHEET, parts=[S.RigPart(**p) for p in parts_spec()],
        frame_width=FW, frame_height=FH, notes="Dusk Wanderer showcase",
        overwrite=True, preview=False)))

    out = chk(await S.pixel_render_motion(S.RenderMotionInput(
        rig_path=RIG, out_dir=f"{HERE}/dusk", custom=MOTION, frames=FRAMES,
        prefix="dusk", overwrite=True, preview=False)))
    frames = json.loads(out)["frame_paths"]

    chk(await S.pixel_export_gif(S.ExportGifInput(
        frame_paths=frames, out_path=f"{HERE}/dusk@4x.gif", duration_ms=90, scale=4)))
    chk(await S.pixel_export_spritesheet(S.ExportSpritesheetInput(
        frame_paths=frames, out_path=f"{HERE}/dusk_sheet.png", columns=6)))
    print(f"dusk.png ({SHEET_W}x{SHEET_H} sheet) -> {FRAMES} frames -> dusk@4x.gif")
    return frames


if __name__ == "__main__":
    asyncio.run(main())
