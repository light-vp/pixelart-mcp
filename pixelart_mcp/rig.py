"""Rig and motion layer: turn one drawn sprite into an animation.

A rig names rectangular parts of a source canvas; a motion describes how those
parts move over a normalized cycle t in [0, 1). Frames are composited from the
source pixels, so every frame is made of art that was actually drawn — only
placement and orientation are computed, never new colors.

Limbs swing rather than slide. Each part has a pivot (its joint) and may have a
parent, so a shin hangs from its thigh and a hand from its forearm: rotating
the thigh carries the shin with it (forward kinematics). Rotation uses
RotSprite — the source is upscaled 8x with Scale2x, which keeps edges sharp,
then sampled back down at the new angle — so a rotated limb is still made of
the drawn palette and keeps a clean silhouette instead of resampled mush.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

MAX_PARTS = 32

NUMERIC_CHANNELS = ("dx", "dy", "squash", "angle")
PIXEL_CHANNELS = ("dx", "dy", "squash")  # rounded to whole pixels; angle stays fractional
STEP_CHANNELS = ("flip", "rot", "visible", "use")
CHANNELS = NUMERIC_CHANNELS + STEP_CHANNELS
EASINGS = ("linear", "ease", "step")
ANCHORS = ("bottom", "center", "top")
VALID_ROT = (0, 90, 180, 270)

# Part names the built-in motions drive. A rig may use any names it likes, but
# matching these means the presets work with no extra wiring. The lower
# segments (shin/forearm) are optional: give them parent=leg_*/arm_* and the
# presets bend the knees and elbows too.
CONVENTIONAL_PARTS = (
    "head", "torso", "arm_back", "arm_front", "leg_back", "leg_front",
    "shin_back", "shin_front", "forearm_back", "forearm_front",
)
OPTIONAL_PARTS = ("shin_back", "shin_front", "forearm_back", "forearm_front")

_DEFAULTS: Dict[str, Any] = {
    "dx": 0, "dy": 0, "squash": 0, "angle": 0.0,
    "flip": False, "rot": 0, "visible": True, "use": None,
}

# Distinct hues for part boxes in the rig preview.
_BOX_COLORS = [
    (255, 96, 96), (96, 200, 255), (255, 208, 80), (140, 230, 130),
    (220, 130, 255), (255, 150, 70), (110, 255, 220), (200, 200, 200),
]
_UNCOVERED = (255, 0, 200, 255)


# ---------------------------------------------------------------------------
# Rig files
# ---------------------------------------------------------------------------

def normalize_rig(data: Any, *, source_size: Optional[Tuple[int, int]] = None) -> dict:
    """Validate a rig dict and fill in defaults, or raise ValueError.

    Checks part names are unique, boxes sit inside the source canvas, and
    enums are legal — every message names the offending part so a fix is a
    single edit rather than a re-read of the whole rig.
    """
    if not isinstance(data, dict):
        raise ValueError("A rig must be a JSON object with a 'parts' list.")
    raw = data.get("parts")
    if not isinstance(raw, list) or not raw:
        raise ValueError("Rig needs a non-empty 'parts' list.")
    if len(raw) > MAX_PARTS:
        raise ValueError(f"Too many parts ({len(raw)}); the limit is {MAX_PARTS}.")

    parts: List[dict] = []
    seen: set[str] = set()
    for i, p in enumerate(raw):
        if not isinstance(p, dict):
            raise ValueError(f"parts[{i}] must be an object, got {type(p).__name__}.")
        name = str(p.get("name", "")).strip()
        if not name:
            raise ValueError(f"parts[{i}] is missing 'name'.")
        if name in seen:
            raise ValueError(f"Duplicate part name '{name}'. Part names must be unique.")
        seen.add(name)
        try:
            x, y = int(p["x"]), int(p["y"])
            w, h = int(p["width"]), int(p["height"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Part '{name}' needs integer x, y, width, height ({exc})."
            ) from None
        if w < 1 or h < 1:
            raise ValueError(f"Part '{name}' has a zero-or-negative size ({w}x{h}).")
        if x < 0 or y < 0:
            raise ValueError(f"Part '{name}' starts off-canvas at ({x},{y}).")
        if source_size is not None and (x + w > source_size[0] or y + h > source_size[1]):
            raise ValueError(
                f"Part '{name}' box {w}x{h} at ({x},{y}) runs past the "
                f"{source_size[0]}x{source_size[1]} source canvas."
            )
        anchor = str(p.get("anchor", "bottom")).lower()
        if anchor not in ANCHORS:
            raise ValueError(
                f"Part '{name}' has anchor '{anchor}'; use one of {', '.join(ANCHORS)}."
            )
        # Placement defaults to where the art sits, so a sprite drawn in one
        # piece needs no at_* at all. Setting them lets parts be drawn apart
        # from each other — the only way two limbs can overlap in the frame.
        try:
            at_x = int(p["at_x"]) if p.get("at_x") is not None else None
            at_y = int(p["at_y"]) if p.get("at_y") is not None else None
        except (TypeError, ValueError):
            raise ValueError(f"Part '{name}' has non-integer at_x/at_y.") from None
        # The pivot is the joint the part rotates about, in box-local pixels.
        # Top-center is where a limb hangs from, which is the common case.
        try:
            pivot_x = int(p["pivot_x"]) if p.get("pivot_x") is not None else w // 2
            pivot_y = int(p["pivot_y"]) if p.get("pivot_y") is not None else 0
        except (TypeError, ValueError):
            raise ValueError(f"Part '{name}' has non-integer pivot_x/pivot_y.") from None
        if not (0 <= pivot_x < w and 0 <= pivot_y < h):
            raise ValueError(
                f"Part '{name}' pivot ({pivot_x},{pivot_y}) is outside its {w}x{h} box; "
                "pivots are box-local, (0,0) is the box's top-left pixel."
            )
        parent = p.get("parent")
        parent = str(parent).strip() if parent else None
        entry = {
            "name": name, "x": x, "y": y, "width": w, "height": h,
            "at_x": at_x, "at_y": at_y,
            "z": int(p.get("z", i)), "anchor": anchor,
            "pivot_x": pivot_x, "pivot_y": pivot_y,
        }
        if parent:
            entry["parent"] = parent
        parts.append(entry)

    names = {p["name"] for p in parts}
    for p in parts:
        if "parent" in p and p["parent"] not in names:
            raise ValueError(
                f"Part '{p['name']}' has parent '{p['parent']}', which is not a part. "
                f"Parts: {', '.join(sorted(names))}."
            )
    # Parents first, so an unplaced child can snap to its parent's placement.
    by_name = {p["name"]: p for p in parts}
    for p in _parent_order(parts):  # also raises on cycles
        parent = by_name.get(p.get("parent", ""))
        if parent is not None and p["at_x"] is None and p["at_y"] is None:
            # Joint snapping: the child's pivot lands on the parent's bottom
            # row under the parent's pivot — knee under hip, hand under elbow.
            p["at_x"] = parent["at_x"] + parent["pivot_x"] - p["pivot_x"]
            p["at_y"] = parent["at_y"] + parent["height"] - 1 - p["pivot_y"]
        else:
            p["at_x"] = p["x"] if p["at_x"] is None else p["at_x"]
            p["at_y"] = p["y"] if p["at_y"] is None else p["at_y"]

    out: Dict[str, Any] = {"parts": parts}
    for key in ("source", "width", "height", "frame_width", "frame_height", "notes"):
        if key in data and data[key] is not None:
            out[key] = data[key]
    return out


def _parent_order(parts: List[dict]) -> List[dict]:
    """Parents before children, so a child's joint can follow its parent."""
    by_name = {p["name"]: p for p in parts}
    order: List[dict] = []
    state: Dict[str, int] = {}  # 1 = visiting, 2 = done

    def visit(p: dict, chain: List[str]) -> None:
        st = state.get(p["name"])
        if st == 2:
            return
        if st == 1:
            raise ValueError(f"Parent loop: {' -> '.join(chain + [p['name']])}.")
        state[p["name"]] = 1
        if "parent" in p:
            visit(by_name[p["parent"]], chain + [p["name"]])
        state[p["name"]] = 2
        order.append(p)

    for p in parts:
        visit(p, [])
    return order


def frame_size(rig: dict, source: PILImage.Image) -> Tuple[int, int]:
    """Frames match the source canvas unless the rig sets its own bounds —
    which it should when the sprite is drawn as a parts sheet with empty space."""
    return (
        int(rig.get("frame_width") or source.width),
        int(rig.get("frame_height") or source.height),
    )


def load_rig(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Rig file '{path}' is not valid JSON: {exc}") from None
    return normalize_rig(data)


def parts_by_name(rig: dict) -> Dict[str, dict]:
    return {p["name"]: p for p in rig["parts"]}


# ---------------------------------------------------------------------------
# Channel evaluation
# ---------------------------------------------------------------------------

def _smoothstep(u: float) -> float:
    return u * u * (3.0 - 2.0 * u)


def _channel_keys(spec: Any, channel: str, part: str) -> Tuple[List[Tuple[float, Any]], str]:
    """Accept either the shorthand [[t, v], ...] or {"keys": [...], "easing": ...}."""
    easing = "ease" if channel in NUMERIC_CHANNELS else "step"
    if isinstance(spec, dict):
        raw = spec.get("keys")
        if "easing" in spec:
            easing = str(spec["easing"]).lower()
            if easing not in EASINGS:
                raise ValueError(
                    f"Part '{part}' channel '{channel}' has easing '{easing}'; "
                    f"use one of {', '.join(EASINGS)}."
                )
    else:
        raw = spec
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            f"Part '{part}' channel '{channel}' needs a non-empty list of [time, value] keys."
        )

    keys: List[Tuple[float, Any]] = []
    for entry in raw:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError(
                f"Part '{part}' channel '{channel}': each key must be [time, value], got {entry!r}."
            )
        t, v = entry
        try:
            t = float(t)
        except (TypeError, ValueError):
            raise ValueError(
                f"Part '{part}' channel '{channel}': key time {t!r} is not a number."
            ) from None
        if not 0.0 <= t < 1.0:
            raise ValueError(
                f"Part '{part}' channel '{channel}': key time {t} is outside [0, 1). "
                "Cycles wrap automatically, so the frame at t=1 is the frame at t=0 — "
                "do not add a closing key."
            )
        if channel in NUMERIC_CHANNELS and not isinstance(v, (int, float)):
            raise ValueError(
                f"Part '{part}' channel '{channel}': value {v!r} must be a number."
            )
        if channel == "rot" and v not in VALID_ROT:
            raise ValueError(
                f"Part '{part}' channel 'rot': {v!r} is not allowed. Pixel art only "
                f"survives 90-degree steps — use one of {VALID_ROT}, or draw the "
                "in-between angle as its own part and swap to it with 'use'."
            )
        keys.append((t, v))
    keys.sort(key=lambda k: k[0])
    return keys, easing


def eval_channel(spec: Any, t: float, channel: str, part: str) -> Any:
    """Sample one channel at cycle position t, wrapping from the last key to the first."""
    keys, easing = _channel_keys(spec, channel, part)
    if len(keys) == 1:
        return keys[0][1]

    idx = -1
    for i, (kt, _) in enumerate(keys):
        if kt <= t:
            idx = i
        else:
            break
    if idx == -1:
        # t sits before the first key: bracket wraps from the last key of the
        # previous cycle, which is what makes a loop seamless.
        t0, v0 = keys[-1][0] - 1.0, keys[-1][1]
        t1, v1 = keys[0]
    else:
        t0, v0 = keys[idx]
        t1, v1 = keys[idx + 1] if idx + 1 < len(keys) else (keys[0][0] + 1.0, keys[0][1])

    if channel in STEP_CHANNELS or easing == "step":
        return v0
    span = t1 - t0
    if span <= 0:
        return v0
    u = (t - t0) / span
    if easing == "ease":
        u = _smoothstep(u)
    return v0 + (v1 - v0) * u


def evaluate_part(motion_parts: dict, name: str, t: float) -> Dict[str, Any]:
    """Resolve every channel for one part at time t, falling back to defaults.

    A motion may address parts by name, or use '*' as a catch-all for parts it
    does not name individually (whole-body bobs, scroll offsets).
    """
    spec = motion_parts.get(name)
    if spec is None:
        spec = motion_parts.get("*")
    values = dict(_DEFAULTS)
    if not spec:
        return values
    if not isinstance(spec, dict):
        raise ValueError(f"Motion entry for '{name}' must be an object of channels.")
    unknown = sorted(set(spec) - set(CHANNELS))
    if unknown:
        raise ValueError(
            f"Part '{name}' has unknown channel(s) {', '.join(unknown)}. "
            f"Available: {', '.join(CHANNELS)}."
        )
    for channel, cspec in spec.items():
        v = eval_channel(cspec, t, channel, name)
        if channel in PIXEL_CHANNELS:
            v = int(round(v))  # whole pixels only — this is the whole point
        elif channel == "angle":
            v = float(v)
        elif channel in ("flip", "visible"):
            v = bool(v)
        elif channel == "rot":
            v = int(v) % 360
        values[channel] = v
    return values


# ---------------------------------------------------------------------------
# RotSprite: rotate pixel art without inventing colors
# ---------------------------------------------------------------------------

ROT_UPSCALE = 8  # three Scale2x passes


def _scale2x(px: List[List[tuple]], w: int, h: int) -> List[List[tuple]]:
    """EPX/Scale2x: double the size, rounding diagonal edges instead of
    blocking them. Only ever copies an existing neighbour, so no new colors."""
    out = [[None] * (w * 2) for _ in range(h * 2)]
    for y in range(h):
        row = px[y]
        up = px[y - 1] if y > 0 else None
        dn = px[y + 1] if y + 1 < h else None
        for x in range(w):
            p = row[x]
            a = up[x] if up is not None else p
            d = dn[x] if dn is not None else p
            c = row[x - 1] if x > 0 else p
            b = row[x + 1] if x + 1 < w else p
            e0 = e1 = e2 = e3 = p
            if c == a and c != d and a != b:
                e0 = a
            if a == b and a != c and b != d:
                e1 = b
            if d == c and d != b and c != a:
                e2 = c
            if b == d and b != a and d != c:
                e3 = d
            out[2 * y][2 * x] = e0
            out[2 * y][2 * x + 1] = e1
            out[2 * y + 1][2 * x] = e2
            out[2 * y + 1][2 * x + 1] = e3
    return out


def _upscale_for_rotation(region: PILImage.Image) -> Tuple[List[List[tuple]], int, int]:
    """Region padded by one transparent pixel (so the silhouette edge rounds
    too) and upscaled 8x. Returns (rows, width, height) of the big image."""
    w, h = region.width + 2, region.height + 2
    padded = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
    padded.paste(region, (1, 1))
    getter = getattr(padded, "get_flattened_data", None)  # getdata() is deprecated in Pillow 12
    data = list(getter() if getter is not None else padded.getdata())
    rows = [[data[y * w + x] if data[y * w + x][3] else (0, 0, 0, 0) for x in range(w)]
            for y in range(h)]
    for _ in range(3):
        rows = _scale2x(rows, w, h)
        w, h = w * 2, h * 2
    return rows, w, h


def _rotate_vec(vx: float, vy: float, deg: float) -> Tuple[float, float]:
    """Rotate a screen-space offset. Positive degrees swing the end of a
    downward-hanging limb toward +x (forward, for a right-facing sprite)."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return vx * c + vy * s, -vx * s + vy * c


def _rotsprite(
    region: PILImage.Image,
    pivot: Tuple[float, float],
    deg: float,
    world_pivot: Tuple[float, float],
    cache: Dict[int, Tuple[List[List[tuple]], int, int]],
) -> Tuple[PILImage.Image, int, int]:
    """Rotate `region` by `deg` about its local `pivot`, landing that pivot at
    `world_pivot`. Returns (image, left, top) in frame coordinates."""
    key = id(region)
    if key not in cache:
        cache[key] = _upscale_for_rotation(region)
    big, bw, bh = cache[key]
    k = ROT_UPSCALE

    w, h = region.width, region.height
    corners = [_rotate_vec(cx - pivot[0], cy - pivot[1], deg)
               for cx in (-1, w + 1) for cy in (-1, h + 1)]
    left = math.floor(world_pivot[0] + min(c[0] for c in corners))
    top = math.floor(world_pivot[1] + min(c[1] for c in corners))
    right = math.ceil(world_pivot[0] + max(c[0] for c in corners))
    bottom = math.ceil(world_pivot[1] + max(c[1] for c in corners))

    out = PILImage.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
    opx = out.load()
    for oy in range(out.height):
        for ox in range(out.width):
            # Inverse-map this output pixel's center into the big image.
            vx = left + ox + 0.5 - world_pivot[0]
            vy = top + oy + 0.5 - world_pivot[1]
            lx, ly = _rotate_vec(vx, vy, -deg)
            sx = math.floor((lx + pivot[0] + 1) * k)
            sy = math.floor((ly + pivot[1] + 1) * k)
            if 0 <= sx < bw and 0 <= sy < bh:
                c = big[sy][sx]
                if c[3]:
                    opx[ox, oy] = c
    if _min_thickness_ok(region):
        _remove_spurs(out)
    return out, left, top


def _opaque_neighbors(px, x: int, y: int, w: int, h: int) -> int:
    n = 0
    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
        if 0 <= nx < w and 0 <= ny < h and px[nx, ny][3]:
            n += 1
    return n


def _min_thickness_ok(region: PILImage.Image) -> bool:
    """True when the drawn part has no 1px-wide tips of its own — then any
    tip in the rotated copy is a sampling spur, not art."""
    px = region.load()
    w, h = region.size
    return not any(
        px[x, y][3] and _opaque_neighbors(px, x, y, w, h) <= 1
        for y in range(h) for x in range(w)
    )


def _remove_spurs(img: PILImage.Image) -> None:
    """Drop lone pixels that rotation sampling leaves hanging off an edge."""
    px = img.load()
    w, h = img.size
    spurs = [(x, y) for y in range(h) for x in range(w)
             if px[x, y][3] and _opaque_neighbors(px, x, y, w, h) <= 1]
    for x, y in spurs:
        px[x, y] = (0, 0, 0, 0)


# ---------------------------------------------------------------------------
# Frame composition
# ---------------------------------------------------------------------------

_ROT_TRANSPOSE = {
    90: PILImage.Transpose.ROTATE_270,  # PIL rotates counter-clockwise
    180: PILImage.Transpose.ROTATE_180,
    270: PILImage.Transpose.ROTATE_90,
}


def _oriented_pivot(px: int, py: int, w: int, h: int, flip: bool, rot: int) -> Tuple[int, int]:
    """Where a box-local pivot pixel lands after flip and a 90-degree turn."""
    if flip:
        px = w - 1 - px
    if rot == 90:
        return h - 1 - py, px
    if rot == 180:
        return w - 1 - px, h - 1 - py
    if rot == 270:
        return py, w - 1 - px
    return px, py


def _orient(source: PILImage.Image, part: dict, src: dict, ch: Dict[str, Any]):
    """Cut a part's pixels and apply flip / 90-degree turn / squash. Returns
    (region, pivot) with the joint in region-local coordinates (pixel center)."""
    region = source.crop((src["x"], src["y"], src["x"] + src["width"], src["y"] + src["height"]))
    if ch["flip"]:
        region = region.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)
    rot = ch["rot"]
    if rot:
        transpose = _ROT_TRANSPOSE.get(rot)
        if transpose is None:
            raise ValueError(f"Part '{part['name']}' has rot={rot}; only {VALID_ROT} are allowed.")
        region = region.transpose(transpose)
    pvx, pvy = _oriented_pivot(src["pivot_x"], src["pivot_y"], src["width"], src["height"],
                               ch["flip"], rot)
    pivot = (pvx + 0.5, pvy + 0.5)
    if ch["squash"]:
        # Positive squash compresses vertically and spreads horizontally by
        # the same count, so volume reads as conserved the way squash-and-
        # stretch expects. Negative values stretch.
        nw = max(1, region.width + ch["squash"])
        nh = max(1, region.height - ch["squash"])
        pivot = (pivot[0] * nw / region.width, pivot[1] * nh / region.height)
        region = region.resize((nw, nh), PILImage.Resampling.NEAREST)
    return region, pivot


def _origin(part: dict, region: PILImage.Image, ch: Dict[str, Any]) -> Tuple[int, int]:
    """Top-left of the region in the frame before any rotation. Placed against
    the part's own box, not a swapped source's, so a part-swap changes the
    pixels without teleporting the limb."""
    box_w, box_h = part["width"], part["height"]
    px = part["at_x"] + ch["dx"] + (box_w - region.width) // 2
    if part["anchor"] == "bottom":
        py = part["at_y"] + ch["dy"] + (box_h - region.height)
    elif part["anchor"] == "center":
        py = part["at_y"] + ch["dy"] + (box_h - region.height) // 2
    else:
        py = part["at_y"] + ch["dy"]
    return px, py


def _paste_clipped(frame: PILImage.Image, region: PILImage.Image, px: int, py: int) -> None:
    # Clip rather than fail: a limb may legitimately swing past the edge.
    left, top = max(0, -px), max(0, -py)
    right = min(region.width, frame.width - px)
    bottom = min(region.height, frame.height - py)
    if left >= right or top >= bottom:
        return
    frame.alpha_composite(region.crop((left, top, right, bottom)), (px + left, py + top))


def compose_frame(
    source: PILImage.Image,
    rig: dict,
    motion_parts: dict,
    t: float,
    cache: Optional[dict] = None,
) -> PILImage.Image:
    """Build one frame: pose every part (parents first, so children follow
    their joints), then stamp them in z order."""
    frame = PILImage.new("RGBA", frame_size(rig, source), (0, 0, 0, 0))
    lookup = parts_by_name(rig)
    cache = {} if cache is None else cache
    posed: Dict[str, dict] = {}

    for part in _parent_order(rig["parts"]):
        ch = evaluate_part(motion_parts, part["name"], t)
        src = part
        if ch["use"] is not None:
            src = lookup.get(str(ch["use"]))
            if src is None:
                raise ValueError(
                    f"Part '{part['name']}' swaps to unknown part '{ch['use']}'. "
                    f"Known parts: {', '.join(sorted(lookup))}."
                )
        key = (src["name"], ch["flip"], ch["rot"], ch["squash"])
        if key not in cache:
            cache[key] = _orient(source, part, src, ch)
        region, pivot = cache[key]
        origin = _origin(part, region, ch)

        rest = (origin[0] + pivot[0], origin[1] + pivot[1])
        angle = ch["angle"]
        world = rest
        parent = posed.get(part.get("parent", ""))
        if parent is not None:
            # Carry the joint with the parent's rotation and offset, then snap
            # to a pixel center so the limb lands on the grid, not between it.
            vx, vy = _rotate_vec(rest[0] - parent["rest"][0], rest[1] - parent["rest"][1],
                                 parent["angle"])
            world = (math.floor(parent["world"][0] + vx) + 0.5,
                     math.floor(parent["world"][1] + vy) + 0.5)
            angle += parent["angle"]
        posed[part["name"]] = {
            "part": part, "ch": ch, "region": region, "pivot": pivot,
            "rest": rest, "world": world, "angle": angle,
        }

    rot_cache: dict = cache.setdefault("_rotsprite", {})
    for part in sorted(rig["parts"], key=lambda p: p["z"]):
        pose = posed[part["name"]]
        if not pose["ch"]["visible"]:
            continue
        region, angle = pose["region"], pose["angle"]
        if abs(angle) < 0.5:
            # No rotation: an exact stamp of the drawn pixels.
            px = round(pose["world"][0] - pose["pivot"][0])
            py = round(pose["world"][1] - pose["pivot"][1])
            _paste_clipped(frame, region, px, py)
        else:
            img, left, top = _rotsprite(region, pose["pivot"], angle, pose["world"], rot_cache)
            _paste_clipped(frame, img, left, top)
    return frame


def _lowest_opaque_row(img: PILImage.Image) -> Optional[int]:
    bbox = img.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    return None if bbox is None else bbox[3]


def render_cycle(
    source: PILImage.Image,
    rig: dict,
    motion_parts: dict,
    frames: int,
    ground: bool = False,
    lift: Optional[Any] = None,
) -> List[PILImage.Image]:
    """Render a full loop as `frames` images sampled evenly across t in [0, 1).

    With ground=True each frame is shifted so its lowest pixel sits where the
    rest pose's does — the planted foot stays on the floor and the body bob
    falls out of the leg angles, instead of being keyed by hand. `lift` keys
    (pixels, negative = up) then raise the whole frame, e.g. a run's airborne
    beat.
    """
    cache: dict = {}
    images = [compose_frame(source, rig, motion_parts, i / frames, cache) for i in range(frames)]
    if not ground and lift is None:
        return images
    floor = _lowest_opaque_row(compose_frame(source, rig, {}, 0.0, cache)) if ground else None
    out = []
    for i, img in enumerate(images):
        shift = 0
        if floor is not None:
            low = _lowest_opaque_row(img)
            if low is not None:
                shift = floor - low
        if lift is not None:
            shift += int(round(eval_channel(lift, i / frames, "dy", "lift")))
        if shift:
            moved = PILImage.new("RGBA", img.size, (0, 0, 0, 0))
            _paste_clipped(moved, img, 0, shift)
            img = moved
        out.append(img)
    return out


# ---------------------------------------------------------------------------
# Rig preview
# ---------------------------------------------------------------------------

def rig_preview(source: PILImage.Image, rig: dict, scale: int) -> Tuple[PILImage.Image, int]:
    """Draw the part boxes over the source, and flag art no part covers.

    Returns (image, uncovered_pixel_count). Uncovered art is the failure mode
    that matters: any drawn pixel outside every box simply vanishes from every
    rendered frame, so it is worth showing loudly rather than reporting as a
    number alone.
    """
    margin = 2
    base = source.resize(
        (source.width * scale, source.height * scale), PILImage.Resampling.NEAREST
    ).convert("RGBA")
    canvas = PILImage.new("RGBA", (base.width + margin * 2, base.height + margin * 2), (28, 28, 34, 255))

    # Checkerboard so transparent regions read as empty rather than dark.
    cell = max(4, scale)
    board = PILImage.new("RGBA", base.size, (74, 74, 80, 255))
    bd = ImageDraw.Draw(board)
    for by in range(0, base.height, cell):
        for bx in range(0, base.width, cell):
            if (bx // cell + by // cell) % 2 == 0:
                bd.rectangle([bx, by, bx + cell - 1, by + cell - 1], fill=(92, 92, 98, 255))
    board.alpha_composite(base)
    canvas.paste(board, (margin, margin))

    # Any opaque source pixel not inside some part box is dropped at render time.
    covered = PILImage.new("1", source.size, 0)
    cov = ImageDraw.Draw(covered)
    for p in rig["parts"]:
        cov.rectangle([p["x"], p["y"], p["x"] + p["width"] - 1, p["y"] + p["height"] - 1], fill=1)
    alpha = source.getchannel("A").load()
    cov_px = covered.load()
    uncovered = 0
    flag = ImageDraw.Draw(canvas)
    for y in range(source.height):
        for x in range(source.width):
            if alpha[x, y] > 8 and not cov_px[x, y]:
                uncovered += 1
                flag.rectangle(
                    [margin + x * scale, margin + y * scale,
                     margin + (x + 1) * scale - 1, margin + (y + 1) * scale - 1],
                    fill=_UNCOVERED,
                )

    overlay = PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()
    ordered = sorted(rig["parts"], key=lambda q: q["z"])

    # Boxes first, labels after — otherwise a later part's fill paints over an
    # earlier part's label and the name reads as truncated.
    for i, p in enumerate(ordered):
        color = _BOX_COLORS[i % len(_BOX_COLORS)]
        x0, y0 = margin + p["x"] * scale, margin + p["y"] * scale
        draw.rectangle(
            [x0, y0, x0 + p["width"] * scale - 1, y0 + p["height"] * scale - 1],
            fill=color + (36,), outline=color + (235,), width=1,
        )
        if (p["at_x"], p["at_y"]) != (p["x"], p["y"]):
            # Where this part actually lands in the frame, outline only.
            ax, ay = margin + p["at_x"] * scale, margin + p["at_y"] * scale
            draw.rectangle(
                [ax, ay, ax + p["width"] * scale - 1, ay + p["height"] * scale - 1],
                outline=color + (150,), width=1,
            )
            draw.line([x0 + 2, y0 + 2, ax + 2, ay + 2], fill=color + (110,), width=1)

    for i, p in enumerate(ordered):
        color = _BOX_COLORS[i % len(_BOX_COLORS)]
        x0, y0 = margin + p["x"] * scale, margin + p["y"] * scale
        label = f"{p['name']} z{p['z']}"
        tx, ty = x0 + 1, max(margin, y0 - 9)
        draw.rectangle([tx - 1, ty - 1, tx + 5.4 * len(label) + 1, ty + 8], fill=(16, 16, 20, 215))
        draw.text((tx, ty), label, fill=color + (255,), font=font)
    # Joints last, so no label hides one: a ringed dot where each part's pivot
    # lands on the body — it should sit on the hip, shoulder, knee or elbow.
    for i, p in enumerate(ordered):
        color = _BOX_COLORS[i % len(_BOX_COLORS)]
        cx = margin + (p["at_x"] + p["pivot_x"]) * scale + scale // 2
        cy = margin + (p["at_y"] + p["pivot_y"]) * scale + scale // 2
        r = max(2, scale // 3)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (255,),
                     outline=(16, 16, 20, 255), width=1)
    return PILImage.alpha_composite(canvas, overlay), uncovered


# ---------------------------------------------------------------------------
# Built-in motions
# ---------------------------------------------------------------------------
#
# Each preset drives the CONVENTIONAL_PARTS names above; a rig missing one of
# them just skips that channel set. Keys are [cycle_position, value] with
# positions in [0, 1) — the loop closes automatically.

MOTIONS: Dict[str, Dict[str, Any]] = {
    "walk": {
        "frames": 8,
        "ground": True,
        "notes": "Side-view walk, facing right. Legs swing from the hip and arms "
                 "from the shoulder in opposition; with shins/forearms rigged the "
                 "knee folds through the passing pose. Feet stay planted and the "
                 "body bob comes from the leg angles (ground lock).",
        "parts": {
            "leg_front": {"angle": [[0.0, 24], [0.5, -24]]},
            "leg_back": {"angle": [[0.0, -24], [0.5, 24]]},
            "shin_front": {"angle": [[0.0, 0], [0.1, -8], [0.3, 0], [0.55, -14],
                                     [0.7, -45], [0.88, -10]]},
            "shin_back": {"angle": [[0.05, -14], [0.2, -45], [0.38, -10], [0.5, 0],
                                    [0.6, -8], [0.8, 0]]},
            "arm_front": {"angle": [[0.0, -20], [0.5, 20]]},
            "arm_back": {"angle": [[0.0, 20], [0.5, -20]]},
            "forearm_front": {"angle": [[0.0, 6], [0.5, 30]]},
            "forearm_back": {"angle": [[0.0, 30], [0.5, 6]]},
        },
    },
    "run": {
        "frames": 8,
        "ground": True,
        "lift": [[0.0, 0], [0.25, -3], [0.5, 0], [0.75, -3]],
        "notes": "Long stride with an airborne beat between contacts. Legs swing "
                 "wider than walk, knees fold hard on the recovery, arms pump "
                 "bent at the elbow.",
        "parts": {
            "leg_front": {"angle": [[0.0, 38], [0.5, -34]]},
            "leg_back": {"angle": [[0.0, -34], [0.5, 38]]},
            "shin_front": {"angle": [[0.0, -6], [0.25, -10], [0.5, -30], [0.68, -90],
                                     [0.88, -20]]},
            "shin_back": {"angle": [[0.0, -30], [0.18, -90], [0.38, -20], [0.5, -6],
                                    [0.75, -10]]},
            "arm_front": {"angle": [[0.0, -40], [0.5, 40]]},
            "arm_back": {"angle": [[0.0, 40], [0.5, -40]]},
            "forearm_front": {"angle": [[0.0, 70], [0.5, 90]]},
            "forearm_back": {"angle": [[0.0, 90], [0.5, 70]]},
        },
    },
    "idle": {
        "frames": 4,
        "notes": "Subtle breathing loop for a standing character — one pixel of lift "
                 "in the torso and head, with the arms trailing a beat behind.",
        "parts": {
            "torso": {"dy": {"keys": [[0.0, 0], [0.5, -1]]}},
            "head": {"dy": {"keys": [[0.0, 0], [0.5, -1]]}},
            "arm_front": {"dy": {"keys": [[0.25, 0], [0.75, -1]]}},
            "arm_back": {"dy": {"keys": [[0.25, 0], [0.75, -1]]}},
        },
    },
    "bob": {
        "frames": 4,
        "notes": "Whole-sprite float, applied to every part via the '*' catch-all — "
                 "for items, pickups, hovering enemies, and UI stingers.",
        "parts": {
            "*": {"dy": {"keys": [[0.0, 0], [0.25, -1], [0.5, 0], [0.75, 1]]}},
        },
    },
    "squash_land": {
        "frames": 6,
        "notes": "Impact accent: the body compresses on contact then rebounds past "
                 "its rest height. Anchor parts 'bottom' so the feet stay planted.",
        "parts": {
            "*": {
                "squash": {"keys": [[0.0, 0], [0.17, 3], [0.5, -1], [0.83, 0]]},
                "dy": {"keys": [[0.0, 0], [0.17, 1], [0.5, -1], [0.83, 0]]},
            },
        },
    },
}

MOTION_NAMES = list(MOTIONS)


def resolve_motion(name: Optional[str], custom: Optional[dict]) -> dict:
    """Merge a preset with any inline overrides.

    Returns {"parts", "frames", "label", "ground", "lift"}. Overrides replace a
    preset entry per part, so tweaking one limb does not mean restating the
    whole cycle. `custom` is either {part: channels} or a full motion object
    {"parts": {...}, "ground": bool, "lift": keys} as pixel_motions returns it.
    """
    if name is None and not custom:
        raise ValueError(
            f"Give a motion preset ({', '.join(MOTION_NAMES)}) or a custom parts object."
        )
    out: Dict[str, Any] = {"parts": {}, "frames": None, "label": "custom",
                           "ground": False, "lift": None}
    if name is not None:
        preset = MOTIONS.get(name.lower())
        if preset is None:
            raise ValueError(
                f"Unknown motion '{name}'. Available: {', '.join(MOTION_NAMES)}."
            )
        out.update(
            parts={k: dict(v) for k, v in preset["parts"].items()},
            frames=int(preset["frames"]), label=name.lower(),
            ground=bool(preset.get("ground", False)), lift=preset.get("lift"),
        )
    if custom:
        if not isinstance(custom, dict):
            raise ValueError("Custom motion must be an object mapping part names to channels.")
        if isinstance(custom.get("parts"), dict):
            if "ground" in custom:
                out["ground"] = bool(custom["ground"])
            if "lift" in custom:
                out["lift"] = custom["lift"]
            if custom.get("frames") is not None:
                try:
                    out["frames"] = int(custom["frames"])
                except (TypeError, ValueError):
                    raise ValueError(f"Motion 'frames' must be a number, got {custom['frames']!r}.") from None
            custom = custom["parts"]
        out["parts"].update(custom)
        out["label"] = f"{out['label']}+custom" if name else "custom"
    if out["lift"] is not None:
        _channel_keys(out["lift"], "dy", "lift")  # validate early, with a clear message
    return out
