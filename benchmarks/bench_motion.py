"""Motion benchmark: objective checks on a rendered animation.

Usage:  python benchmarks/bench_motion.py SHEET.png FRAME_WIDTH [SOURCE.png]

Reads a horizontal spritesheet and reports, per loop:

  components    8-connected opaque blobs per frame. A character should be 1;
                more means a joint tore open or a limb detached.
  palette_leak  colors in the frames that the source drawing never had.
                Must be 0 — generated frames may only reuse drawn pixels.
  floor_jitter  spread of the lowest opaque row across frames. 0 means the
                planted foot never sinks or floats.
  limb_motion   mean share of opaque pixels that change between consecutive
                frames, and its spread (min..max). Sliding rigid blocks give a
                low, spiky profile; swinging limbs a higher, even one.
"""
from __future__ import annotations

import json
import sys

from PIL import Image


def pixels(img: Image.Image) -> list:
    getter = getattr(img, "get_flattened_data", None)  # getdata() is deprecated in Pillow 12
    return list(getter() if getter is not None else img.getdata())


def frames_of(sheet: Image.Image, fw: int) -> list[Image.Image]:
    return [sheet.crop((x, 0, x + fw, sheet.height)) for x in range(0, sheet.width, fw)]


def components(img: Image.Image) -> int:
    px = img.load()
    w, h = img.size
    seen = set()
    n = 0
    for y in range(h):
        for x in range(w):
            if px[x, y][3] <= 8 or (x, y) in seen:
                continue
            n += 1
            stack = [(x, y)]
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = cx + dx, cy + dy
                        if (0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen
                                and px[nx, ny][3] > 8):
                            seen.add((nx, ny))
                            stack.append((nx, ny))
    return n


def colors(img: Image.Image) -> set:
    return {c for c in pixels(img) if c[3] > 8}


def lowest_row(img: Image.Image) -> int:
    bbox = img.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    return bbox[3] if bbox else -1


def change(a: Image.Image, b: Image.Image) -> float:
    pa, pb = pixels(a), pixels(b)
    opaque = sum(1 for p, q in zip(pa, pb) if p[3] > 8 or q[3] > 8)
    diff = sum(1 for p, q in zip(pa, pb) if (p[3] > 8 or q[3] > 8) and p != q)
    return diff / opaque if opaque else 0.0


def report(sheet_path: str, fw: int, source_path: str | None = None) -> dict:
    sheet = Image.open(sheet_path).convert("RGBA")
    frames = frames_of(sheet, fw)
    comps = [components(f) for f in frames]
    floors = [lowest_row(f) for f in frames]
    changes = [change(frames[i], frames[(i + 1) % len(frames)]) for i in range(len(frames))]
    out = {
        "frames": len(frames),
        "components": comps,
        "floor_jitter": max(floors) - min(floors),
        "limb_motion": f"{sum(changes) / len(changes):.2f} "
                       f"({min(changes):.2f}..{max(changes):.2f})",
    }
    if source_path:
        drawn = colors(Image.open(source_path).convert("RGBA"))
        out["palette_leak"] = len(set().union(*map(colors, frames)) - drawn)
    return out


if __name__ == "__main__":
    print(json.dumps(report(sys.argv[1], int(sys.argv[2]), *sys.argv[3:4]), indent=2))
