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


def outline_color(rgb: Tuple[int, int, int], palette: Iterable[Tuple[int, int, int]]) -> Tuple[int, int, int]:
    """Selective-outline color for art of color `rgb`, reusing a color already
    in `palette` when one is close enough to pass for it. Without this, every
    shade the outline touches mints its own near-identical dark, and a sprite
    ends with a dozen outline colors nobody can tell apart."""
    want = darken_for_outline(rgb)
    best, best_d = None, 22.0
    for c in palette:
        d = color_distance(c, want)
        if d < best_d and _luma(c) <= _luma(rgb) - 20:
            best, best_d = c, d
    return best if best is not None else want


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


def _resolve_form_ramp(color: RGBA, ramp_colors: Optional[List[RGBA]]) -> Tuple[List[RGBA], int]:
    """Ramp for the form modes. An explicit ramp is used whole; an auto ramp is
    5 steps around the region's own color, which then stays the base."""
    if ramp_colors:
        return ramp_colors, len(ramp_colors) // 2
    return build_ramp(color, 5, 18.0)


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


def _light_vector(light: str) -> Tuple[float, float, float]:
    """Unit vector pointing TOWARD the light (screen y down, z out of screen)."""
    ox, oy = LIGHT_OFFSETS[light]
    lx, ly, lz = ox * 0.8, oy * 0.8, 1.0
    m = math.sqrt(lx * lx + ly * ly + lz * lz)
    return lx / m, ly / m, lz / m


def _band_shares(n: int, base_idx: int) -> List[float]:
    """How much of a region each ramp step covers, dark -> light.

    Encodes the 60/25/15 rule: the base step dominates, coverage falls off
    with distance from it, and the light side is kept smaller than the dark
    side so highlights stay accents. Every region shaded with the same ramp
    length gets the same proportions — that is what keeps a piece's shading
    consistent from one object to the next.
    """
    sigma = max(0.9, n / 3.2)
    w = []
    for i in range(n):
        d = (i - base_idx) / sigma
        share = math.exp(-d * d)
        if i > base_idx:
            share *= 0.45
        w.append(share)
    total = sum(w)
    return [x / total for x in w]


def _rank_quantize(
    img: PILImage.Image,
    mask: set,
    value: Dict[Tuple[int, int], float],
    ramp: List[RGBA],
    base_idx: Optional[int] = None,
) -> int:
    """Paint the mask with ramp steps by brightness RANK, not by threshold.

    The light model only decides the ORDER of pixels from darkest to lightest;
    _band_shares decides how many land on each step. So bands always follow
    the form's contours, and the base color always covers most of the region,
    whatever the shape or size.
    """
    n = len(ramp)
    if base_idx is None:
        base_idx = n // 2
    shares = _band_shares(n, base_idx)
    order = sorted(mask, key=lambda p: (value[p], -p[1], p[0]))
    total = len(order)
    band: Dict[Tuple[int, int], int] = {}
    cum = 0.0
    idx = 0
    bound = shares[0] * total
    for rank, p in enumerate(order):
        while rank >= bound and idx < n - 1:
            idx += 1
            cum += shares[idx - 1]
            bound = (cum + shares[idx]) * total
        band[p] = idx
    _absorb_orphans(band)
    px = img.load()
    for (x, y), i in band.items():
        px[x, y] = ramp[i][:3] + (px[x, y][3],)
    return total


def _absorb_orphans(band: Dict[Tuple[int, int], int]) -> None:
    """A pixel sharing its band with none of its 4 neighbours reads as noise,
    not form: fold it into the band most of its neighbours are in."""
    for _ in range(2):
        changes = {}
        for (x, y), i in band.items():
            nbs = [band[q] for q in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)) if q in band]
            if len(nbs) < 2 or i in nbs:
                continue
            best = max(set(nbs), key=lambda v: (nbs.count(v), -abs(v - i)))
            changes[(x, y)] = best
        if not changes:
            return
        band.update(changes)


def _lambert(nx: float, ny: float, nz: float, l: Tuple[float, float, float]) -> float:
    return nx * l[0] + ny * l[1] + nz * l[2]


def shade_sphere(
    img: PILImage.Image,
    mask: set,
    ramp: List[RGBA],
    light: str,
    base_idx: Optional[int] = None,
) -> int:
    """Light the region as an ellipsoid fitted to its bounding box: a lit cap
    toward the light, a terminator, and a core shadow on the far side. Good
    for fruit, heads, orbs."""
    xs = [p[0] for p in mask]
    ys = [p[1] for p in mask]
    cx, cy = (min(xs) + max(xs) + 1) / 2.0, (min(ys) + max(ys) + 1) / 2.0
    rx, ry = max(0.5, (max(xs) - min(xs) + 1) / 2.0), max(0.5, (max(ys) - min(ys) + 1) / 2.0)
    lv = _light_vector(light)
    value = {}
    for (x, y) in mask:
        nx, ny = (x + 0.5 - cx) / rx, (y + 0.5 - cy) / ry
        r2 = nx * nx + ny * ny
        if r2 >= 1.0:
            r = math.sqrt(r2)
            nx, ny, nz = nx / r, ny / r, 0.0
        else:
            nz = math.sqrt(1.0 - r2)
        value[(x, y)] = _lambert(nx, ny, nz, lv)
    return _rank_quantize(img, mask, value, ramp, base_idx)


def shade_cylinder(
    img: PILImage.Image,
    mask: set,
    ramp: List[RGBA],
    light: str,
    upright: bool,
    base_idx: Optional[int] = None,
) -> int:
    """Cylinder shading per row (upright: bottles, trunks, standing limbs) or
    per column (on its side: barrels, logs). The lit band sits off-center
    toward the light and the far edge falls into core shadow, following the
    silhouette's own width at every row."""
    spans: Dict[int, Tuple[int, int]] = {}
    for (x, y) in mask:
        key, val = (y, x) if upright else (x, y)
        lo, hi = spans.get(key, (val, val))
        spans[key] = (min(lo, val), max(hi, val))
    lv = _light_vector(light)
    value = {}
    for (x, y) in mask:
        key, val = (y, x) if upright else (x, y)
        lo, hi = spans[key]
        half = (hi - lo + 1) / 2.0
        u = (val + 0.5 - (lo + half)) / half  # -1..1 across the cylinder
        u = max(-1.0, min(1.0, u))
        across, along = u, 0.0
        nz = math.sqrt(max(0.0, 1.0 - u * u))
        nx, ny = (across, along) if upright else (along, across)
        value[(x, y)] = _lambert(nx, ny, nz, lv)
    return _rank_quantize(img, mask, value, ramp, base_idx)


def shade_form(
    img: PILImage.Image,
    mask: set,
    ramp: List[RGBA],
    light: str,
    base_idx: Optional[int] = None,
) -> int:
    """Shade ANY silhouette as a rounded volume.

    Builds a height field from each pixel's distance to the region's edge,
    domed so the rim falls off steeply, takes surface normals from its slope,
    and lights them. Lobes, waists, and limbs each round off on their own —
    a dragon's body, a cloud, a foliage clump or a pillow-free cloth fold
    without fitting a primitive first.
    """
    dist = _edge_distance(mask)
    peak = max(dist.values()) or 1.0
    height = {p: math.sqrt(max(0.0, d * (2.0 * peak - d))) for p, d in dist.items()}
    # The distance field has creases along the shape's medial axis; a couple
    # of blur passes inside the mask round them off so normals don't flip.
    for _ in range(2):
        height = {
            (x, y): sum(height.get((x + dx, y + dy), 0.0)
                        for dx in (-1, 0, 1) for dy in (-1, 0, 1)) / 9.0
            for (x, y) in height
        }
    lv = _light_vector(light)
    value = {}
    for (x, y) in mask:
        h = height[(x, y)]
        hl = height.get((x - 1, y), 0.0)
        hr = height.get((x + 1, y), 0.0)
        hu = height.get((x, y - 1), 0.0)
        hd = height.get((x, y + 1), 0.0)
        gx, gy = (hr - hl) / 2.0, (hd - hu) / 2.0
        m = math.sqrt(gx * gx + gy * gy + 1.0)
        value[(x, y)] = _lambert(-gx / m, -gy / m, 1.0 / m, lv) + 0.01 * h / peak
    return _rank_quantize(img, mask, value, ramp, base_idx)


def _edge_distance(mask: set) -> Dict[Tuple[int, int], float]:
    """Chamfer distance (3-4 weights) from each mask pixel to the outside."""
    inf = float("inf")
    d = {p: inf for p in mask}
    for (x, y) in mask:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (nx, ny) not in mask:
                d[(x, y)] = 1.0
                break
    order = sorted(mask, key=lambda p: (p[1], p[0]))
    fwd = ((-1, 0, 1.0), (0, -1, 1.0), (-1, -1, 1.4), (1, -1, 1.4))
    bwd = ((1, 0, 1.0), (0, 1, 1.0), (1, 1, 1.4), (-1, 1, 1.4))
    for seq, nb in ((order, fwd), (order[::-1], bwd)):
        for (x, y) in seq:
            best = d[(x, y)]
            for dx, dy, w in nb:
                q = d.get((x + dx, y + dy))
                if q is not None and q + w < best:
                    best = q + w
            d[(x, y)] = best
    return d


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
# Lint: the consistency problems that make pixel art look amateur
# ---------------------------------------------------------------------------

NEAR_DUPLICATE = 14.0  # redmean distance under which two colors read as one
STRAY_CONTRAST = 40.0  # an orphan pixel closer than this to its surroundings is noise


def color_distance(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> float:
    """'Redmean' perceptual RGB distance — cheap and good enough for palettes."""
    rm = (a[0] + b[0]) / 2.0
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return math.sqrt((2 + rm / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rm) / 256) * db * db) / 3.0


def _luma(c: Tuple[int, int, int]) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


# Within 2px, plus the 4px lattice where the sparsest Bayer-4 level repeats.
_PARTNER_OFFSETS = [(dx, dy) for dy in range(-2, 3) for dx in range(-2, 3) if dx or dy] + [
    (4, 0), (-4, 0), (0, 4), (0, -4), (4, 4), (-4, -4), (4, -4), (-4, 4)]


def _has_partner(px, x: int, y: int, w: int, h: int, c) -> bool:
    """Dither and texture always have a same-colored pixel close by on their
    pattern; a speck of noise does not."""
    for dx, dy in _PARTNER_OFFSETS:
        if 0 <= x + dx < w and 0 <= y + dy < h:
            q = px[x + dx, y + dy]
            if q[3] and q[:3] == c[:3]:
                return True
    return False


def lint(img: PILImage.Image, max_colors: int = 16, fix: bool = False) -> Dict[str, object]:
    """Find (and optionally fix) what makes a piece look inconsistent.

    * near-duplicate colors — two colors no viewer can tell apart split one
      material into noise and waste the palette; fix merges the rarer into the
      commoner.
    * stray pixels — a pixel with no same-colored pixel within 2px that
      barely contrasts with its surroundings: noise, not detail. High-contrast
      lone pixels (eyes, sparkles, glints) are deliberate and left alone;
      dither and texture always have a partner within 2px and are left alone
      too. Fix paints them with the
      surrounding color.
    * color budget, partial alpha, and outline coverage are reported.
    """
    w, h = img.size
    px = img.load()
    counts: Dict[Tuple[int, int, int], int] = {}
    partial = 0
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            if c[3] == 0:
                continue
            if c[3] < 255:
                partial += 1
            counts[c[:3]] = counts.get(c[:3], 0) + 1

    issues: List[str] = []
    fixed = {"merged_colors": 0, "strays_cleaned": 0}

    colors = sorted(counts, key=lambda c: -counts[c])
    dupes = []
    merge: Dict[Tuple[int, int, int], Tuple[int, int, int]] = {}
    for i, a in enumerate(colors):
        for b in colors[i + 1:]:
            if b in merge or a in merge:
                continue
            d = color_distance(a, b)
            if d < NEAR_DUPLICATE:
                dupes.append((a, b, d))
                merge[b] = a  # b is rarer (colors sorted by count)
    if dupes:
        issues.append(
            f"{len(dupes)} near-duplicate color pair(s) — merge them so each material "
            "reads as one ramp: " + ", ".join(
                f"{color_hex(b + (255,))}({counts[b]}px)->{color_hex(a + (255,))}"
                for a, b, _ in dupes[:8])
        )
        if fix:
            for y in range(h):
                for x in range(w):
                    c = px[x, y]
                    if c[3] and c[:3] in merge:
                        px[x, y] = merge[c[:3]] + (c[3],)
            fixed["merged_colors"] = len(merge)

    strays = []
    snap = img.copy().load() if fix else px
    for y in range(h):
        for x in range(w):
            c = snap[x, y]
            if c[3] == 0:
                continue
            nbs = [snap[x + dx, y + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                   if (dx or dy) and 0 <= x + dx < w and 0 <= y + dy < h]
            if len(nbs) < 8:
                continue
            opaque = [n[:3] for n in nbs if n[3]]
            if len(opaque) < 6:
                continue  # an edge pixel; the silhouette is the outline's business
            if _has_partner(snap, x, y, w, h, c):
                continue
            major = max(set(opaque), key=opaque.count)
            if opaque.count(major) >= 5 and color_distance(c[:3], major) < STRAY_CONTRAST:
                strays.append((x, y, major))
    if strays:
        issues.append(
            f"{len(strays)} stray pixel(s) — lone, low-contrast specks that read as "
            "noise, e.g. at " + ", ".join(f"({x},{y})" for x, y, _ in strays[:10])
        )
        if fix:
            for x, y, major in strays:
                px[x, y] = major + (px[x, y][3],)
            fixed["strays_cleaned"] = len(strays)

    n_colors = len({px[x, y][:3] for y in range(h) for x in range(w) if px[x, y][3]})
    if n_colors > max_colors:
        issues.append(
            f"{n_colors} colors, over the {max_colors} budget — snap with "
            "pixel_apply_palette or merge ramps."
        )
    if partial:
        issues.append(
            f"{partial} semi-transparent pixel(s). Fine if they are SPAA edge softening; "
            "anywhere else they blend unpredictably over backgrounds."
        )

    # Outline coverage: how much of the silhouette edge is darker than the
    # pixel just inside it. Near 0 = no outline, near 1 = full; in between is a
    # half-finished outline, the most common inconsistency.
    edge = dark = 0
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            if c[3] == 0:
                continue
            outward = [(dx, dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                       if not (0 <= x + dx < w and 0 <= y + dy < h) or px[x + dx, y + dy][3] == 0]
            if not outward:
                continue
            dx, dy = outward[0]
            ix, iy = x - dx, y - dy
            if not (0 <= ix < w and 0 <= iy < h) or px[ix, iy][3] == 0:
                continue
            edge += 1
            if _luma(c[:3]) < _luma(px[ix, iy][:3]) - 8:
                dark += 1
    coverage = round(dark / edge, 2) if edge else None
    if coverage is not None and edge >= 24 and 0.35 <= coverage <= 0.8:
        issues.append(
            f"outline covers {int(coverage * 100)}% of the silhouette — commit: run "
            "pixel_outline_sprite for a full outline, or leave none."
        )

    score = 100
    score -= min(30, 3 * len(dupes))
    score -= min(30, 2 * len(strays))
    score -= min(20, 2 * max(0, n_colors - max_colors))
    if coverage is not None and edge >= 24 and 0.35 <= coverage <= 0.8:
        score -= 10
    report: Dict[str, object] = {
        "score": max(0, score),
        "colors": n_colors,
        "near_duplicates": len(dupes),
        "strays": len(strays),
        "outline_coverage": coverage,
        "issues": issues or ["none — palette is tight and edges are clean"],
    }
    if fix:
        report["fixed"] = fixed
    return report


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
  form = organic shapes (bodies, foliage, clouds, cloth), sphere = round things,
  cylinder = limbs/bottles/trunks, bevel = flat-faced things (armor, crates).
  Large smooth areas (sky, glow): pixel_draw_gradient with dither='bayer4'.
  GATE: light reads from ONE direction; base color still covers ~60%.

STAGE 5 — DETAILS.
  Now (not earlier) add: face, patterns, texture, seams — with pixel_paint_grid
  or pixel_draw_pixels. Darkest ramp step in crevices/contacts (ambient
  occlusion). 1-2px brightest-step specular ONLY on shiny materials.

STAGE 6 — FINISH.
  pixel_outline_sprite (mode='selective' for soft look, 'solid' #1a1c2c-style
  for game sprites). Then pixel_apply_spaa — it softens diagonal staircases
  and is what makes edges read as drawn rather than blocky (leave
  interior=false under ~32px). Then pixel_lint fix=true: it merges colors
  nobody can tell apart and cleans stray specks. Aim for score >= 90; if it
  reports colors over budget, pixel_apply_palette with your ramps. Final
  pixel_view_canvas at high scale.

TOKEN DISCIPLINE — two rules, both worth more than they look.
  1. BATCH EACH STAGE. Send a whole stage as ONE pixel_batch call rather than
     one call per operation: every separate call re-sends the conversation so
     far, so 25 calls cost far more than 25 operations inside 4 calls. Plan the
     stage, batch it, then view once.
  2. DESCRIBE SHAPES, DON'T ENUMERATE PIXELS. polygon/curve/gradient/shade/
     paint_grid each replace tens to hundreds of single-pixel placements.
  While iterating on one detail, pass preview_diff=true to get back just the
  changed region instead of the whole canvas.

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
    form      ANY organic silhouette — creature bodies, foliage clumps, clouds,
              cloth, rocks. Each lobe rounds on its own; the default choice.
    sphere    fruit, heads, orbs — one round mass
    cylinder  limbs, bottles, trunks, towers, barrels(on side)
    bevel     flat-faced things: armor plates, crates, stone blocks, UI
  form/sphere/cylinder keep the 60/25/15 proportions for you, so every object
  in a piece shades in the same style. Ramp is auto-built from the region
  color (which stays the base); pass your own for a custom look.

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

    "animation": """ANIMATION — do NOT draw frame by frame. Draw ONE sprite, rig it,
and let the server pose the frames. An 8-frame walk should cost one drawing.

THE LOOP:
  1. Draw the character once, side-on, facing RIGHT, in a neutral pose with
     arms and legs hanging straight. Finish it properly (topic='workflow') —
     every frame is made of these exact pixels, so flaws repeat 8 times.
  2. DRAW THE LIMBS IN A PARTS BIN, not on the body. Make the canvas wider
     than the sprite and draw each limb segment out to the side, clear of the
     others: upper arm, forearm (+hand), thigh, shin (+foot), for the back
     and front side. Keep head and torso where they belong.
     Why: a part is a RECTANGLE of source pixels, so limbs drawn on top of
     each other can never be boxed apart — but a side view needs them to
     overlap once placed.
  3. pixel_define_rig. Name parts head, torso, arm_back, arm_front, leg_back,
     leg_front (the upper segments, given at_x/at_y on the body) and
     forearm_back, forearm_front, shin_back, shin_front with
     parent=<the upper segment> and NO at_x/at_y — their joint snaps onto
     the parent's bottom row. Set frame_width/frame_height to the sprite so
     the bin never shows. Single-segment limbs work too: skip the lower parts.
  4. Check the preview. Magenta = drawn pixels no box covers (they vanish).
     Dots = joints: each must sit on the hip/shoulder/knee/elbow.
  5. pixel_render_motion motion='walk' (or 'run') -> frames.
  6. pixel_export_gif on the returned frame_paths. 100-125ms per frame reads
     as walking; 60-80ms as running.

HOW LIMBS MOVE:
  - Parts SWING about their pivot with the 'angle' channel (degrees; positive
    swings a hanging limb's end toward +x, i.e. forward). The pivot defaults
    to the top-center of the box — where a limb hangs from.
  - Children ride their parent: rotate the thigh and the shin goes with it,
    then bends at the knee by its own angle. That is what makes a stride
    flow instead of sliding blocks.
  - Rotation is RotSprite: the part is upscaled 8x with Scale2x and sampled
    back at the new angle, so it only ever reuses your drawn colors and edges
    stay clean. Thin (1px) features can still nick at odd angles — draw limbs
    at least 3px wide.
  - GROUND LOCK (on for walk/run): every frame is shifted so the lowest pixel
    sits on the rest pose's floor. Planted feet never sink or float, and the
    body's up-and-down bob falls out of the leg angles for free.

RIGGING RULES:
  - Z-ORDER: back limbs lowest, then torso, then front limbs, head highest.
    Shade the back limbs one ramp step darker — depth reads from value.
  - OVERLAP THE JOINTS. The torso box should run 2-3px over the hips and
    shoulders, so a swinging limb never opens a hole at its root.
  - ANCHOR 'bottom' for legs and body, 'center' for heads and floating props.

MOTION RULES:
  - Keys are [t, value] with t in [0, 1). The cycle wraps on its own; a key at
    t=1 is an error, not a closing frame.
  - dx/dy/squash round to whole pixels; amplitudes under ~2px on a 32px
    sprite quantize away. Angles do not round.
  - CONTRAST BEATS SMOOTHNESS. 8 punchy frames read better than 24 soft ones.
  - Opposition sells weight: arms swing against legs.
  - Start from a preset (pixel_motions) and override one part with `custom`
    rather than authoring a cycle from scratch.
  - flip/rot (90-degree steps) and the 'use' part-swap still exist for poses
    no rotation can reach — a hand opening, a face turning.

MOVING A WHOLE SCENE: rig the scrolling layers as parts and drive them with
'*' or per-layer dx at different rates — parallax for free (ground_lock off).
For a background that repeats, pixel_shift_canvas with wrap=true is cheaper.""",
}

GUIDE_TOPICS = list(GUIDES.keys())
