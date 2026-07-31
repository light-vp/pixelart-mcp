"""Rig and motion layer: turn one drawn sprite into an animation.

A rig names rectangular parts of a source canvas; a motion describes how those
parts translate, mirror, and squash over a normalized cycle t in [0, 1). Frames
are composited from the source pixels, so every frame is made of art that was
actually drawn — nothing interpolates pixel *content*, only placement, and
placements round to whole pixels. That is what keeps a generated frame looking
hand-made instead of resampled.

Deliberately absent: arbitrary rotation. Rotating pixel art by anything other
than a multiple of 90 degrees resamples it into mush, so the only orientation
channels are `flip` (mirror) and `rot` (90-degree steps). Where a limb really
needs an in-between angle, draw that angle as its own part and swap to it with
the `use` channel.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

MAX_PARTS = 32

NUMERIC_CHANNELS = ("dx", "dy", "squash")
STEP_CHANNELS = ("flip", "rot", "visible", "use")
CHANNELS = NUMERIC_CHANNELS + STEP_CHANNELS
EASINGS = ("linear", "ease", "step")
ANCHORS = ("bottom", "center", "top")
VALID_ROT = (0, 90, 180, 270)

# Part names the built-in motions drive. A rig may use any names it likes, but
# matching these means the presets work with no extra wiring.
CONVENTIONAL_PARTS = (
    "head", "torso", "arm_back", "arm_front", "leg_back", "leg_front",
)

_DEFAULTS: Dict[str, Any] = {
    "dx": 0, "dy": 0, "squash": 0,
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
            at_x = int(p["at_x"]) if p.get("at_x") is not None else x
            at_y = int(p["at_y"]) if p.get("at_y") is not None else y
        except (TypeError, ValueError):
            raise ValueError(f"Part '{name}' has non-integer at_x/at_y.") from None
        parts.append({
            "name": name, "x": x, "y": y, "width": w, "height": h,
            "at_x": at_x, "at_y": at_y,
            "z": int(p.get("z", i)), "anchor": anchor,
        })

    out: Dict[str, Any] = {"parts": parts}
    for key in ("source", "width", "height", "frame_width", "frame_height", "notes"):
        if key in data and data[key] is not None:
            out[key] = data[key]
    return out


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
        if channel in NUMERIC_CHANNELS:
            v = int(round(v))  # whole pixels only — this is the whole point
        elif channel in ("flip", "visible"):
            v = bool(v)
        elif channel == "rot":
            v = int(v) % 360
        values[channel] = v
    return values


# ---------------------------------------------------------------------------
# Frame composition
# ---------------------------------------------------------------------------

_ROT_TRANSPOSE = {
    90: PILImage.Transpose.ROTATE_270,  # PIL rotates counter-clockwise
    180: PILImage.Transpose.ROTATE_180,
    270: PILImage.Transpose.ROTATE_90,
}


def compose_frame(
    source: PILImage.Image,
    rig: dict,
    motion_parts: dict,
    t: float,
) -> PILImage.Image:
    """Build one frame by stamping each rigged part at its position at time t."""
    frame = PILImage.new("RGBA", frame_size(rig, source), (0, 0, 0, 0))
    lookup = parts_by_name(rig)
    for part in sorted(rig["parts"], key=lambda p: p["z"]):
        ch = evaluate_part(motion_parts, part["name"], t)
        if not ch["visible"]:
            continue

        src = part
        if ch["use"] is not None:
            src = lookup.get(str(ch["use"]))
            if src is None:
                raise ValueError(
                    f"Part '{part['name']}' swaps to unknown part '{ch['use']}'. "
                    f"Known parts: {', '.join(sorted(lookup))}."
                )
        region = source.crop((src["x"], src["y"], src["x"] + src["width"], src["y"] + src["height"]))

        if ch["flip"]:
            region = region.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)
        if ch["rot"]:
            transpose = _ROT_TRANSPOSE.get(ch["rot"])
            if transpose is None:
                raise ValueError(
                    f"Part '{part['name']}' has rot={ch['rot']}; only {VALID_ROT} are allowed."
                )
            region = region.transpose(transpose)
        if ch["squash"]:
            # Positive squash compresses vertically and spreads horizontally by
            # the same count, so volume reads as conserved the way squash-and-
            # stretch expects. Negative values stretch.
            nw = max(1, region.width + ch["squash"])
            nh = max(1, region.height - ch["squash"])
            region = region.resize((nw, nh), PILImage.Resampling.NEAREST)

        # Place against the part's own box, not the swapped source's, so a
        # part-swap changes the pixels without teleporting the limb.
        box_w, box_h = part["width"], part["height"]
        px = part["at_x"] + ch["dx"] + (box_w - region.width) // 2
        if part["anchor"] == "bottom":
            py = part["at_y"] + ch["dy"] + (box_h - region.height)
        elif part["anchor"] == "center":
            py = part["at_y"] + ch["dy"] + (box_h - region.height) // 2
        else:
            py = part["at_y"] + ch["dy"]

        # Clip rather than fail: a limb may legitimately swing past the edge.
        left, top = max(0, -px), max(0, -py)
        right = min(region.width, frame.width - px)
        bottom = min(region.height, frame.height - py)
        if left >= right or top >= bottom:
            continue
        frame.alpha_composite(region.crop((left, top, right, bottom)), (px + left, py + top))
    return frame


def render_cycle(
    source: PILImage.Image,
    rig: dict,
    motion_parts: dict,
    frames: int,
) -> List[PILImage.Image]:
    """Render a full loop as `frames` images sampled evenly across t in [0, 1)."""
    return [compose_frame(source, rig, motion_parts, i / frames) for i in range(frames)]


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
        "notes": "Side-view walk cycle: contact, down, pass, up, twice per loop. "
                 "Arms swing opposite the legs; the body dips twice per stride.",
        "parts": {
            "leg_front": {
                "dx": {"keys": [[0.0, 3], [0.25, 0], [0.5, -3], [0.75, 0]], "easing": "linear"},
                "dy": {"keys": [[0.0, 0], [0.5, 0], [0.75, -2]]},
            },
            "leg_back": {
                "dx": {"keys": [[0.0, -3], [0.25, 0], [0.5, 3], [0.75, 0]], "easing": "linear"},
                "dy": {"keys": [[0.0, 0], [0.25, -2], [0.5, 0]]},
            },
            "arm_front": {
                "dx": {"keys": [[0.0, -2], [0.25, 0], [0.5, 2], [0.75, 0]], "easing": "linear"},
            },
            "arm_back": {
                "dx": {"keys": [[0.0, 2], [0.25, 0], [0.5, -2], [0.75, 0]], "easing": "linear"},
            },
            "torso": {"dy": {"keys": [[0.0, 0], [0.25, -1], [0.5, 0], [0.75, -1]]}},
            "head": {"dy": {"keys": [[0.0, 0], [0.25, -1], [0.5, 0], [0.75, -1]]}},
        },
    },
    "run": {
        "frames": 8,
        "notes": "Wider stride and a real airborne lift. Legs reach further than walk "
                 "and the torso rises off the ground between contacts.",
        "parts": {
            "leg_front": {
                "dx": {"keys": [[0.0, 5], [0.25, 0], [0.5, -5], [0.75, 0]], "easing": "linear"},
                "dy": {"keys": [[0.0, 0], [0.5, 0], [0.75, -4]]},
            },
            "leg_back": {
                "dx": {"keys": [[0.0, -5], [0.25, 0], [0.5, 5], [0.75, 0]], "easing": "linear"},
                "dy": {"keys": [[0.0, 0], [0.25, -4], [0.5, 0]]},
            },
            "arm_front": {
                "dx": {"keys": [[0.0, -4], [0.25, 0], [0.5, 4], [0.75, 0]], "easing": "linear"},
                "dy": {"keys": [[0.0, -1], [0.5, 0]]},
            },
            "arm_back": {
                "dx": {"keys": [[0.0, 4], [0.25, 0], [0.5, -4], [0.75, 0]], "easing": "linear"},
                "dy": {"keys": [[0.0, 0], [0.5, -1]]},
            },
            "torso": {"dy": {"keys": [[0.0, 0], [0.125, -2], [0.5, 0], [0.625, -2]]}},
            "head": {"dy": {"keys": [[0.0, 0], [0.125, -2], [0.5, 0], [0.625, -2]]}},
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


def resolve_motion(
    name: Optional[str],
    custom: Optional[dict],
) -> Tuple[dict, Optional[int], str]:
    """Merge a preset with any inline overrides.

    Returns (parts, suggested_frames, label). Overrides replace a preset entry
    per part, so tweaking one limb does not mean restating the whole cycle.
    """
    if name is None and not custom:
        raise ValueError(
            f"Give a motion preset ({', '.join(MOTION_NAMES)}) or a custom parts object."
        )
    parts: dict = {}
    frames: Optional[int] = None
    label = "custom"
    if name is not None:
        preset = MOTIONS.get(name.lower())
        if preset is None:
            raise ValueError(
                f"Unknown motion '{name}'. Available: {', '.join(MOTION_NAMES)}."
            )
        parts = {k: dict(v) for k, v in preset["parts"].items()}
        frames = int(preset["frames"])
        label = name.lower()
    if custom:
        if not isinstance(custom, dict):
            raise ValueError("Custom motion must be an object mapping part names to channels.")
        parts.update(custom)
        label = f"{label}+custom" if name else "custom"
    return parts, frames, label
