"""Pixel-art craft algorithms: color ramps, dithering, auto-shading, ASCII
grid codec, curated palettes, and technique guides.

This module holds the "art knowledge" so the MCP tools in server.py stay thin.
Everything here is deterministic — same inputs, same pixels.
"""

from __future__ import annotations

import colorsys
import math
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image as PILImage
from PIL import ImageColor

RGBA = Tuple[int, int, int, int]

# ---------------------------------------------------------------------------
# Color parsing and conversion
# ---------------------------------------------------------------------------

def parse_color(value: str) -> RGBA:
    v = value.strip().lower()
    if v in ("transparent", "none"):
        return (0, 0, 0, 0)
    try:
        return ImageColor.getcolor(value, "RGBA")  # type: ignore[return-value]
    except ValueError as exc:
        raise ValueError(
            f"Unrecognized color '{value}'. Use hex like '#1a1c2c' or '#1a1c2cff', "
            "a CSS name like 'crimson', or 'transparent'."
        ) from exc


def color_hex(rgba: RGBA) -> str:
    r, g, b, a = rgba
    return f"#{r:02x}{g:02x}{b:02x}" + (f"{a:02x}" if a != 255 else "")


def _rgb_to_hsl(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
    """Returns (hue_degrees 0-360, saturation 0-1, lightness 0-1)."""
    h, l, s = colorsys.rgb_to_hls(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    return (h * 360.0, s, l)


def _hsl_to_rgb(h: float, s: float, l: float) -> Tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb((h % 360.0) / 360.0, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return (round(r * 255), round(g * 255), round(b * 255))


def _shift_hue(h: float, target: float, amount: float) -> float:
    """Rotate hue h toward target by up to `amount` degrees (shortest path)."""
    delta = ((target - h + 180.0) % 360.0) - 180.0
    if abs(delta) <= amount:
        return target
    return (h + math.copysign(amount, delta)) % 360.0


# ---------------------------------------------------------------------------
# Color ramps (hue-shifted shading ladders)
# ---------------------------------------------------------------------------

SHADOW_HUE = 250.0    # shadows bend toward blue/violet
HIGHLIGHT_HUE = 55.0  # highlights bend toward warm yellow


def build_ramp(base: RGBA, steps: int, hue_shift_deg: float) -> Tuple[List[RGBA], int]:
    """Build a dark->light shading ramp around a base color.

    Uses the standard pixel-art recipe: shadows get darker, more saturated,
    and hue-shift toward blue/violet; highlights get lighter, less saturated,
    and hue-shift toward warm yellow. Returns (ramp, index_of_base_in_ramp).
    Near-gray bases (saturation < 0.02) stay gray so grayscale art is possible.
    """
    h0, s0, l0 = _rgb_to_hsl(base[:3])
    base_idx = steps // 2
    n_dark = base_idx
    n_light = steps - 1 - base_idx
    gray = s0 < 0.02

    ramp: List[RGBA] = [base[:3] + (255,)]

    h, s, l = h0, s0, l0
    for d in range(1, n_dark + 1):
        l = l0 - (l0 - 0.06) * (d / (n_dark + 0.6))
        if not gray:
            h = _shift_hue(h, SHADOW_HUE, hue_shift_deg)
            s = min(1.0, s0 + 0.10 * d + s0 * 0.15 * d)
        ramp.insert(0, _hsl_to_rgb(h, s, l) + (255,))

    h, s = h0, s0
    for u in range(1, n_light + 1):
        l = l0 + (0.95 - l0) * (u / (n_light + 0.7))
        if not gray:
            h = _shift_hue(h, HIGHLIGHT_HUE, hue_shift_deg * 0.8)
            s = max(0.0, s0 * (1 - 0.26 * u))
        ramp.append(_hsl_to_rgb(h, s, l) + (255,))

    return ramp, base_idx


def darken_for_outline(rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Selective-outline color: a darker, cooler, slightly richer neighbor."""
    h, s, l = _rgb_to_hsl(rgb)
    if s >= 0.02:
        h = _shift_hue(h, SHADOW_HUE, 12.0)
        s = min(1.0, s + 0.08)
    return _hsl_to_rgb(h, s, l * 0.45)


# ---------------------------------------------------------------------------
# Ordered dithering
# ---------------------------------------------------------------------------

_BAYER2 = [[0, 2], [3, 1]]
_BAYER4 = [
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
]
_CHECKER = [[0.25, 0.75], [0.75, 0.25]]


def _dither_threshold(pattern: str, x: int, y: int) -> Optional[float]:
    """Threshold in (0,1) for canvas position (x,y), or None for no dithering."""
    if pattern == "none":
        return None
    if pattern == "checker":
        return _CHECKER[y % 2][x % 2]
    if pattern == "bayer2":
        return (_BAYER2[y % 2][x % 2] + 0.5) / 4.0
    if pattern == "bayer4":
        return (_BAYER4[y % 4][x % 4] + 0.5) / 16.0
    raise ValueError(f"Unknown dither pattern '{pattern}'.")


def paint_gradient(
    img: PILImage.Image,
    rect: Tuple[int, int, int, int],
    colors: List[RGBA],
    kind: str,
    angle_deg: float,
    center: Optional[Tuple[float, float]],
    radius: Optional[float],
    dither: str,
    paint_over: str,
    target: Optional[RGBA] = None,
) -> int:
    """Paint a quantized, optionally dithered gradient into rect. Returns pixel count."""
    x0, y0, w, h = rect
    n = len(colors)
    px = img.load()

    if kind == "linear":
        dx = math.cos(math.radians(angle_deg))
        dy = math.sin(math.radians(angle_deg))
        corners = [(cx, cy) for cx in (x0, x0 + w - 1) for cy in (y0, y0 + h - 1)]
        projs = [cx * dx + cy * dy for cx, cy in corners]
        lo, hi = min(projs), max(projs)
        span = (hi - lo) or 1.0
    else:  # radial
        ccx, ccy = center if center else (x0 + (w - 1) / 2.0, y0 + (h - 1) / 2.0)
        if radius is None:
            radius = max(
                math.hypot(cx - ccx, cy - ccy)
                for cx in (x0, x0 + w - 1)
                for cy in (y0, y0 + h - 1)
            ) or 1.0

    painted = 0
    for y in range(y0, min(y0 + h, img.height)):
        for x in range(x0, min(x0 + w, img.width)):
            if x < 0 or y < 0:
                continue
            cur = px[x, y]
            if paint_over == "opaque" and cur[3] == 0:
                continue
            if paint_over == "transparent" and cur[3] != 0:
                continue
            if target is not None and (cur[3] == 0 or cur[:3] != target[:3]):
                continue
            if kind == "linear":
                t = (x * dx + y * dy - lo) / span
            else:
                t = min(1.0, math.hypot(x - ccx, y - ccy) / radius)
            v = t * (n - 1)
            i = min(int(v), n - 1)
            frac = v - i
            thr = _dither_threshold(dither, x, y)
            if thr is None:
                idx = min(n - 1, i + (1 if frac >= 0.5 else 0))
            else:
                idx = min(n - 1, i + (1 if frac > thr else 0))
            if colors[idx][3] == 0:
                continue  # 'transparent' in a gradient means fade out: leave the pixel as-is
            px[x, y] = colors[idx]
            painted += 1
    return painted


# ---------------------------------------------------------------------------
# Auto-shading
# ---------------------------------------------------------------------------

LIGHT_OFFSETS = {
    "top_left": (-1, -1), "top": (0, -1), "top_right": (1, -1),
    "left": (-1, 0), "right": (1, 0),
    "bottom_left": (-1, 1), "bottom": (0, 1), "bottom_right": (1, 1),
}


def _color_masks(img: PILImage.Image, target: Optional[RGBA]) -> List[Tuple[RGBA, set]]:
    """Group opaque pixels into (color, {(x,y)}) regions to shade."""
    px = img.load()
    groups: Dict[Tuple[int, int, int], set] = {}
    for y in range(img.height):
        for x in range(img.width):
            p = px[x, y]
            if p[3] == 0:
                continue
            if target is not None and p[:3] != target[:3]:
                continue
            groups.setdefault(p[:3], set()).add((x, y))
    return [(rgb + (255,), pts) for rgb, pts in groups.items()]


def _resolve_ramp(color: RGBA, ramp_colors: Optional[List[RGBA]], levels: int) -> Tuple[List[RGBA], int]:
    if ramp_colors:
        return ramp_colors, len(ramp_colors) // 2
    return build_ramp(color, 2 * levels + 1, 18.0)


def shade_bevel(
    img: PILImage.Image,
    mask: set,
    ramp: List[RGBA],
    base_idx: int,
    light: str,
    levels: int,
    band_px: int,
) -> int:
    """Edge-band shading: pixels near the lit edge lighten, near the far edge
    darken, interior stays base. Thin features cancel to base naturally."""
    ox, oy = LIGHT_OFFSETS[light]
    px = img.load()
    changed = 0
    max_march = levels * band_px
    for (x, y) in mask:
        hi = lo = 0
        for k in range(1, max_march + 1):
            if hi == 0 and (x + k * ox, y + k * oy) not in mask:
                hi = levels - math.ceil(k / band_px) + 1
            if lo == 0 and (x - k * ox, y - k * oy) not in mask:
                lo = levels - math.ceil(k / band_px) + 1
            if hi and lo:
                break
        net = hi - lo
        if net:
            idx = max(0, min(len(ramp) - 1, base_idx + net))
            a = px[x, y][3]
            px[x, y] = ramp[idx][:3] + (a,)
            changed += 1
    return changed


def shade_sphere(
    img: PILImage.Image,
    mask: set,
    ramp: List[RGBA],
    light: str,
) -> int:
    """Radial form shading: brightest near a highlight point offset toward the
    light, darkening toward the far rim. Good for fruit, heads, orbs."""
    ox, oy = LIGHT_OFFSETS[light]
    mag = math.hypot(ox, oy) or 1.0
    cx = sum(p[0] for p in mask) / len(mask)
    cy = sum(p[1] for p in mask) / len(mask)
    r = max(math.hypot(x - cx, y - cy) for x, y in mask) or 1.0
    hx = cx + (ox / mag) * r * 0.35
    hy = cy + (oy / mag) * r * 0.35
    n = len(ramp)
    px = img.load()
    for (x, y) in mask:
        t = min(1.0, math.hypot(x - hx, y - hy) / (r * 1.35))
        brightness = (1.0 - t) ** 1.5  # tighten the bright core; midtones dominate
        idx = round(brightness * (n - 1))
        a = px[x, y][3]
        px[x, y] = ramp[idx][:3] + (a,)
    return len(mask)


def shade_cylinder(
    img: PILImage.Image,
    mask: set,
    ramp: List[RGBA],
    light: str,
    upright: bool,
) -> int:
    """Cylinder shading: a bright band ~30% in from the lit side, darkening
    toward the far side. Upright = bottle/trunk (varies across x); on-side =
    barrel/limb (varies across y)."""
    ox, oy = LIGHT_OFFSETS[light]
    lit_from_start = (ox < 0) if upright else (oy < 0)
    if (upright and ox == 0) or (not upright and oy == 0):
        lit_from_start = True
    spans: Dict[int, Tuple[int, int]] = {}
    for (x, y) in mask:
        key, val = (y, x) if upright else (x, y)
        lo, hi = spans.get(key, (val, val))
        spans[key] = (min(lo, val), max(hi, val))
    n = len(ramp)
    px = img.load()
    for (x, y) in mask:
        key, val = (y, x) if upright else (x, y)
        lo, hi = spans[key]
        t = 0.5 if hi == lo else (val - lo) / (hi - lo)
        if not lit_from_start:
            t = 1.0 - t
        brightness = max(0.0, min(1.0, 1.0 - abs(t - 0.28) / 0.75))
        idx = round(brightness * (n - 1))
        a = px[x, y][3]
        px[x, y] = ramp[idx][:3] + (a,)
    return len(mask)


# ---------------------------------------------------------------------------
# Bezier curves
# ---------------------------------------------------------------------------

def bezier_points(
    p0: Tuple[int, int],
    c1: Tuple[int, int],
    p1: Tuple[int, int],
    c2: Optional[Tuple[int, int]] = None,
    steps: Optional[int] = None,
) -> List[Tuple[int, int]]:
    """Sample a quadratic (c2=None) or cubic Bezier into integer pixel points.

    Step count defaults to the control-polygon length so long curves stay
    smooth and short ones stay cheap. Consecutive duplicates are dropped;
    callers should connect the returned points with straight segments so the
    stroke has no gaps.
    """
    pts_in = [p0, c1] + ([c2] if c2 else []) + [p1]
    if steps is None:
        length = sum(
            math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts_in, pts_in[1:])
        )
        steps = max(8, min(512, int(length * 1.5)))

    out: List[Tuple[int, int]] = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        if c2 is None:
            x = u * u * p0[0] + 2 * u * t * c1[0] + t * t * p1[0]
            y = u * u * p0[1] + 2 * u * t * c1[1] + t * t * p1[1]
        else:
            x = (u ** 3 * p0[0] + 3 * u * u * t * c1[0]
                 + 3 * u * t * t * c2[0] + t ** 3 * p1[0])
            y = (u ** 3 * p0[1] + 3 * u * u * t * c1[1]
                 + 3 * u * t * t * c2[1] + t ** 3 * p1[1])
        pt = (round(x), round(y))
        if not out or pt != out[-1]:
            out.append(pt)
    return out


# ---------------------------------------------------------------------------
# Sub-pixel anti-aliasing (SPAA)
# ---------------------------------------------------------------------------

def _lerp(a: Tuple[int, int, int], b: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def apply_spaa(
    img: PILImage.Image,
    strength: float,
    background: Optional[RGBA],
    edges: bool,
    interior: bool,
) -> Tuple[int, int]:
    """Soften diagonal staircase corners by placing intermediate pixels.

    Two independent passes, both reading from a pristine snapshot so results
    don't cascade:

    * edges — a background pixel wedged in the elbow of a step (exactly two
      art neighbours, one horizontal and one vertical) is filled with a
      partial-strength version of that art. With `background=None` the fill
      uses partial ALPHA rather than a baked-in background color, so the
      sprite still anti-aliases correctly over any backdrop.
    * interior — an art pixel that juts one step into a neighbouring flat
      color region is blended toward that region, smoothing color boundaries
      inside the sprite.

    Returns (edge_pixels, interior_pixels).
    """
    src = img.copy()
    sp = src.load()
    dp = img.load()
    w, h = img.size

    def is_bg(px: RGBA) -> bool:
        return px[3] == 0 if background is None else px[:3] == background[:3]

    def neighbors4(x: int, y: int):
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                yield nx, ny, sp[nx, ny]

    edge_n = interior_n = 0

    if edges:
        for y in range(h):
            for x in range(w):
                if not is_bg(sp[x, y]):
                    continue
                horiz = [p for nx, ny, p in neighbors4(x, y) if ny == y and not is_bg(p)]
                vert = [p for nx, ny, p in neighbors4(x, y) if nx == x and not is_bg(p)]
                # exactly one horizontal + one vertical art neighbour = step elbow
                if len(horiz) != 1 or len(vert) != 1:
                    continue
                a, b = horiz[0], vert[0]
                art = _lerp(a[:3], b[:3], 0.5)
                if background is None:
                    dp[x, y] = art + (round(255 * strength),)
                else:
                    dp[x, y] = _lerp(background[:3], art, strength) + (255,)
                edge_n += 1

    if interior:
        for y in range(h):
            for x in range(w):
                cur = sp[x, y]
                if is_bg(cur):
                    continue
                others = [
                    p for _, _, p in neighbors4(x, y)
                    if not is_bg(p) and p[:3] != cur[:3]
                ]
                if len(others) != 2:
                    continue
                if others[0][:3] != others[1][:3]:
                    continue
                dp[x, y] = _lerp(cur[:3], others[0][:3], strength) + (cur[3],)
                interior_n += 1

    return edge_n, interior_n


# ---------------------------------------------------------------------------
# ASCII grid codec
# ---------------------------------------------------------------------------

# Distinct, unambiguous glyphs; '.' is reserved for transparent.
ASCII_GLYPHS = "#@XOx%&*+=o^~ABCDEFGHJKLMNPQRSTUVWYZabcdefghjkmnpqrstuvwyz23456789?!/\\|<>()[]{}"

MAX_ASCII_PIXELS = 16384  # 128x128


def ascii_view(img: PILImage.Image, region: Tuple[int, int, int, int]) -> str:
    """Render a region as a labeled character grid with a color legend."""
    x0, y0, w, h = region
    if w * h > MAX_ASCII_PIXELS:
        raise ValueError(
            f"Region {w}x{h} has {w * h} pixels; ascii view is capped at "
            f"{MAX_ASCII_PIXELS} (e.g. 128x128). Pass a smaller region."
        )
    px = img.load()
    counts: Dict[Tuple[int, int, int, int], int] = {}
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            p = px[x, y]
            key = (0, 0, 0, 0) if p[3] == 0 else p
            counts[key] = counts.get(key, 0) + 1
    opaque = sorted(
        (c for c in counts if c[3] != 0), key=lambda c: counts[c], reverse=True
    )
    if len(opaque) > len(ASCII_GLYPHS):
        raise ValueError(
            f"Region has {len(opaque)} distinct colors; ascii view supports up to "
            f"{len(ASCII_GLYPHS)}. Run pixel_apply_palette first, or view a smaller region."
        )
    charmap = {c: ASCII_GLYPHS[i] for i, c in enumerate(opaque)}
    charmap[(0, 0, 0, 0)] = "."

    tens = "     " + "".join(str(((x0 + i) // 10) % 10) if (x0 + i) % 10 == 0 else " " for i in range(w))
    ones = "     " + "".join(str((x0 + i) % 10) for i in range(w))
    lines = [tens, ones]
    for y in range(y0, y0 + h):
        row = "".join(
            charmap[(0, 0, 0, 0) if px[x, y][3] == 0 else px[x, y]]
            for x in range(x0, x0 + w)
        )
        lines.append(f"{y:>4} {row}")
    legend = ["", "legend:", "  . = transparent"]
    legend += [f"  {charmap[c]} = {color_hex(c)}  ({counts[c]} px)" for c in opaque]
    return "\n".join(lines + legend)


def paint_grid(
    img: PILImage.Image,
    x0: int,
    y0: int,
    rows: List[str],
    legend: Dict[str, RGBA],
) -> Tuple[int, int]:
    """Paint an ASCII grid at (x0, y0). '.' and ' ' skip (unless remapped in
    legend). Returns (painted, skipped_out_of_bounds)."""
    px = img.load()
    painted = skipped = 0
    for ry, row in enumerate(rows):
        for rx, ch in enumerate(row):
            if ch not in legend:
                if ch in (".", " "):
                    continue
                raise ValueError(
                    f"Character '{ch}' (row {ry}, column {rx}) is not in the legend. "
                    "Every non-'.'/non-space character must be mapped to a color."
                )
            x, y = x0 + rx, y0 + ry
            if x < 0 or y < 0 or x >= img.width or y >= img.height:
                skipped += 1
                continue
            px[x, y] = legend[ch]
            painted += 1
    return painted, skipped


# ---------------------------------------------------------------------------
# Curated palettes
# ---------------------------------------------------------------------------

PALETTES: Dict[str, Dict[str, object]] = {
    "sweetie16": {
        "colors": [
            "#1a1c2c", "#5d275d", "#b13e53", "#ef7d57", "#ffcd75", "#a7f070",
            "#38b764", "#257179", "#29366f", "#3b5dc9", "#41a6f6", "#73eff7",
            "#f4f4f4", "#94b0c2", "#566c86", "#333c57",
        ],
        "notes": "Balanced modern 16 — good default for characters and scenes; "
                 "#1a1c2c is a great universal outline/shadow color.",
    },
    "pico8": {
        "colors": [
            "#000000", "#1d2b53", "#7e2553", "#008751", "#ab5236", "#5f574f",
            "#c2c3c7", "#fff1e8", "#ff004d", "#ffa300", "#ffec27", "#00e436",
            "#29adff", "#83769c", "#ff77a8", "#ffcaaa",
        ],
        "notes": "Punchy arcade 16 — bold saturated sprites, retro game feel; "
                 "weak at subtle gradients.",
    },
    "dawnbringer16": {
        "colors": [
            "#140c1c", "#442434", "#30346d", "#4e4a4e", "#854c30", "#346524",
            "#d04648", "#757161", "#597dce", "#d27d2c", "#8595a1", "#6daa2c",
            "#d2aa99", "#6dc2ca", "#dad45e", "#deeed6",
        ],
        "notes": "Muted, painterly 16 — earthy fantasy scenes, medieval subjects; "
                 "colors are pre-harmonized to mix well.",
    },
    "slso8": {
        "colors": [
            "#0d2b45", "#203c56", "#544e68", "#8d697a", "#d08159", "#ffaa5e",
            "#ffd4a3", "#ffecd6",
        ],
        "notes": "A single 8-step warm-light/cool-shadow ramp — sunsets, "
                 "atmospheric scenes, monochromatic studies. Use as-is for "
                 "dramatic lighting.",
    },
    "nes": {
        "colors": [
            "#000000", "#fcfcfc", "#f8f8f8", "#bcbcbc", "#7c7c7c", "#a40000",
            "#f83800", "#e45c10", "#ac7c00", "#00b800", "#00a800", "#008888",
            "#0078f8", "#0000fc", "#6844fc", "#d800cc", "#f878f8",
        ],
        "notes": "NES-flavored subset — authentic 8-bit look; pair max 3 colors "
                 "+ transparent per sprite for true hardware feel.",
    },
}


# ---------------------------------------------------------------------------
# Craft guides — the systematic method, served on demand
# ---------------------------------------------------------------------------

GUIDES: Dict[str, str] = {
    "workflow": """PIXEL ART WORKFLOW — follow these stages IN ORDER. Do not skip ahead.
After every stage call pixel_view_canvas and check the listed gate before continuing.

STAGE 0 — SIZE & PLAN.
  Pick canvas size from the sizing guide (pixel_guide topic='sizing').
  Decide ONE light direction now (default 'top_left') and write it in your plan.
  List the 2-4 materials in the subject (skin, metal, cloth, glass...).

STAGE 1 — PALETTE FIRST.
  One pixel_build_ramp call per material (5 steps; 7 for the hero material).
  Or pick a curated set: pixel_palettes. Never invent colors ad hoc mid-drawing.

STAGE 2 — SILHOUETTE.
  Draw the whole subject as ONE flat dark shape. Pick the cheapest tool for
  each part — describing a shape beats enumerating its pixels:
    angular masses (roofs, hulls, blades, mountains, wings)  pixel_draw_polygon
    organic contours (necks, torsos, tails, hair, flames)    pixel_draw_curve
    round masses                                             pixel_draw_ellipse
    irregular detail you can sketch as text                  pixel_paint_grid
  Carve concavities back out with the same tools in 'transparent'.
  GATE: view the canvas — is the subject readable from shape alone? If not,
  fix NOW; nothing later can rescue a bad silhouette.

STAGE 3 — FLAT COLORS.
  Fill each material region with its ramp's base color (pixel_flood_fill on
  the silhouette, or pixel_paint_grid regions). No shading yet.
  GATE: every region is a flat base color, ~16 colors max on canvas.

STAGE 4 — SHADING.
  One pixel_shade_region call per material (same light every call!):
  sphere = round things, cylinder = limbs/bottles/trunks, bevel = everything else.
  Large smooth areas (sky, glow): pixel_draw_gradient with dither='bayer4'.
  GATE: light reads from ONE direction; base color still covers ~60%.

STAGE 5 — DETAILS.
  Now (not earlier) add: face, patterns, texture, seams — with pixel_paint_grid
  or pixel_draw_pixels. Darkest ramp step in crevices/contacts (ambient
  occlusion). 1-2px brightest-step specular ONLY on shiny materials.

STAGE 6 — FINISH.
  pixel_outline_sprite (mode='selective' for soft look, 'solid' #1a1c2c-style
  for game sprites). Then pixel_apply_spaa LAST — it softens diagonal
  staircases and is what makes edges read as drawn rather than blocky (leave
  interior=false under ~32px). pixel_canvas_info: too many stray colors ->
  pixel_apply_palette with your ramps. Final pixel_view_canvas at high scale.

TOKEN DISCIPLINE. Every stage: describe the shape, don't enumerate pixels.
  polygon/curve/gradient/shade/paint_grid each replace tens to hundreds of
  single-pixel calls. While iterating on a detail, pass preview_diff=true so
  you get back just the changed region instead of the whole canvas.

Symmetric subject? Draw the left half through stage 5, pixel_mirror_canvas,
then break symmetry (weapon, pose, lighting on one side).""",

    "sizing": """CANVAS SIZE — pick from what the subject needs, then double it if the
request says 'detailed'. Pixel art fails when the canvas is too big (empty,
noisy) OR too small (no room for shading). Sweet spots:

  16x16   icons, tiles, bullets            1 ramp, 3-4 colors, no dithering
  24x24   small items (fruit, coin, gem)   1-2 ramps of 3-5
  32x32   props (chest, potion, skull)     2-3 ramps of 5
  48x48   detailed single object 'portrait' ramps of 5-7 + dither accents
  48x64   full character, heroic 1:3.5 head:body
  64x64   character + effects / mount
  96x96   character IN an environment
  128x96  full scene with background layers

Rules of thumb:
  - Head of a 64px-tall character: 14-18px. Eyes: 2x2 or 2x3 each.
  - Leave 1-2px transparent margin all around for the outline pass.
  - 'Highly detailed X' => 48x48 minimum + 7-step ramp + selective outline.
  - When in doubt go SMALLER; crisp beats mushy.""",

    "color": """COLOR — palette discipline is what makes art look professional.

  1. RAMPS, NOT COLORS. Materials get a 5-step ramp (pixel_build_ramp), not one
     color. The tool hue-shifts for you: shadows toward blue, highlights toward
     warm — never shade by adding black/white; that makes mud.
  2. BUDGET: <=4 ramps per sprite. Merge: leather+wood+hair can share one brown
     ramp. Whole sprite <=16 colors (32 for big scenes). Check pixel_canvas_info.
  3. SHARED SHADOWS: reuse ONE very dark color (e.g. #1a1c2c) as the darkest
     step of every ramp — instantly unifies the piece. Replace each ramp's
     darkest with it via pixel_replace_color at the end if needed.
  4. SATURATION peaks in midtones; highlights are pale, shadows are deep but
     never pure black (except a deliberate outline style).
  5. HERO CONTRAST: the focal point gets the most saturated color and the
     biggest value jump; background colors are desaturated and lighter.
  6. Curated 16-color sets in pixel_palettes when speed matters more than a
     custom look; pixel_apply_palette snaps stray colors afterward.""",

    "shading": """SHADING — form comes from VALUE placed with intent.

  ONE LIGHT SOURCE. Decide direction before shading anything; every
  pixel_shade_region call uses the same 'light'. Mixed lights = broken form.

  60/25/15 RULE: base color ~60% of a region, shadow ~25%, highlight ~15%.
  If shading covers most of a region, undo — you have pillow-shading.

  WHICH MODE (pixel_shade_region):
    sphere    fruit, heads, orbs, clouds, muscle masses
    cylinder  limbs, bottles, trunks, towers, barrels(on side)
    bevel     armor plates, rocks, cloth folds, UI, anything angular
  Ramp is auto-built from the region color; pass your own for a custom look.

  BY HAND ON TOP (pixel_paint_grid / pixel_draw_pixels):
    - Ambient occlusion: darkest step where things touch (under chin, arm
      against torso, object on ground). 1px lines, biggest impact per pixel.
    - Cast shadow: flat 1-2 step-darker shape on the surface BELOW, offset
      away from the light. Ground shadow = dark ellipse under feet.
    - Specular: 1-2px of the ramp's brightest step, only on wet/metal/glass.
    - Bounce light: 1px of a slightly lighter cool step on the shadow-side
      rim makes objects feel 3D (skip on matte cloth).

  BIG SMOOTH AREAS: pixel_draw_gradient with your ramp + dither='bayer4'
  (sky, glow falloff, underwater). Never leave hard bands on areas > ~20px.""",

    "dithering": """DITHERING — blending two ramp steps with a pattern. Powerful, easy to overdo.

  USE for: skies and large gradients (bayer4), soft round shading on areas
  >20px (checker at the band boundary), glow falloff, water, fog, worn texture.
  DON'T on: sprites under 32px, faces, focal details, clean armor — noise
  destroys readability at small sizes.

  Via pixel_draw_gradient dither param: 'checker' = coarse retro 50% mix;
  'bayer2' fine; 'bayer4' = smoothest, best for skies.
  By hand (pixel_paint_grid): alternate two adjacent ramp steps in a 1px
  checker along the boundary between their bands, 2-4px wide zone.
  Only ever dither ADJACENT ramp steps — never distant colors.""",

    "materials": """MATERIALS — what sells each surface (apply after flat colors):

  METAL   High contrast: use 7-step ramp, skip steps between bands (hard
          transitions). Vertical/diagonal specular STREAKS of the brightest
          step, 1-2px wide. Shadows go cool. Edges/rivets: 1px bright top-left,
          1px dark bottom-right (bevel does this). Gold: warm browns + a near-
          white glint; silver: blue-grays.
  GLASS   The background must SHOW THROUGH: fill with a pale tint of what's
          behind (or leave part transparent). 1px darker rim at the edges.
          One long bright vertical streak near the lit edge + a short parallel
          one. Contents (liquid) get their own mini-ramp + an ellipse surface
          line 1 step lighter. A few isolated pure-white sparkle pixels.
  WOOD    Medium contrast brown ramp; grain = 1px wavy lines of adjacent
          steps ALONG the form (cylinder shade first, grain follows shading).
          Knots: 2-3px darker ellipses. Planks: 1px darkest seams.
  STONE   Gray-brown ramp, bevel shading, cracks = 1px dark zigzags; a few
          single lighter pixels for grit; moss = desaturated green clusters.
  CLOTH   Low contrast, soft: shade folds with bevel light bands following
          drape direction; no specular.
  FOLIAGE Draw leaf CLUSTERS (blobby masses), never single leaves. Sphere-
          shade each cluster; darkest color fills gaps between clusters;
          scatter a few single bright pixels on lit clusters only.
  FIRE    Ramp white->yellow->orange->deep red, radial gradient, NO outline,
          NO black; flame tips flick with 1px teardrops. Glow: radial gradient
          of the light's color into the surroundings, dithered at its edge.
  WATER   Horizontal bands of a blue ramp, 1px white sparkle line where light
          hits; reflections = vertical 1px streaks of the object's colors,
          broken every 2-3px.
  SKIN    3-4 step ramp, warm; shadows toward red/purple never green; blush =
          midtone+1 on cheeks; keep faces LOW detail at small sizes.""",

    "characters": """CHARACTERS — order of operations matters more than talent.

  1. PROPORTIONS by canvas height (heroic): head 1/3.5, shoulders 2 heads
     wide, hands at mid-thigh. Chibi/cute: head 1/2. Pick one, stay with it.
  2. SILHOUETTE FIRST as one dark shape. The pose must read with zero interior
     detail: gaps between arm and body, asymmetric stance, oversized signature
     props (sword, shield) — exaggerate; timid poses vanish at pixel scale.
  3. SYMMETRY: front-facing? Draw the LEFT half, pixel_mirror_canvas
     ('left_to_right'), then break symmetry with the weapon/props/lighting.
  4. FLATS: 3-4 material groups max (skin / armor / cloth / leather). Big
     readable shapes beat costume accuracy.
  5. SHADE: cylinder for limbs/torso, sphere for head, bevel for armor.
     Same light everywhere. Then AO: darkest step where limbs meet body,
     under the chin, under the belt.
  6. FACE at <=64px: eyes = 2px dark + 1px white catch-light, brow line,
     NO mouth or a 1px shadow. Do not model the nose.
  7. FINISH: selective outline; ground shadow ellipse so they don't float.
  Named characters: get the 2-3 iconic features right (mask eyes, chest
  emblem, color split) and simplify everything else aggressively.""",

    "scenes": """SCENES — a scene is 3 flat layers plus consistent light, not a photo.

  1. LAYERS: background (sky/far), midground (subject), foreground (frame
     elements). Draw back to front. Background: lighter, desaturated, LESS
     contrast (aerial perspective); foreground: darkest, most saturated.
  2. SKY: pixel_draw_gradient, 3-5 ramp colors, vertical, dither='bayer4'.
     Sunset: use pixel_palettes 'slso8' as-is.
  3. SUN/KEY LIGHT: declare position; it tints EVERYTHING's highlight ramp
     warm (raise hue_shift_deg to ~25 when building ramps for a sunny scene);
     shadows share one cool color. Cast shadows all point the same way,
     opposite the sun, hugging the ground plane.
  4. The subject gets the scene's strongest value contrast + sharpest outline;
     background objects get NO outline and 2-3 colors each.
  5. GROUND: horizontal texture bands getting sparser with distance; anchor
     every standing object with a contact shadow.
  6. Readability check: pixel_view_canvas — squint; if the subject doesn't pop
     instantly, darken the background or brighten the subject's rim.""",
}

GUIDE_TOPICS = list(GUIDES.keys())
