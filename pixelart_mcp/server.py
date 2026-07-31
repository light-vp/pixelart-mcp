"""Pixel art MCP server.

Creates, edits, inspects, and exports pixel art canvases stored as ordinary
PNG files on disk, using Pillow. Canvases are true-size (1 canvas pixel ==
1 image pixel); exports can upscale with nearest-neighbor so pixels stay crisp.
"""

from __future__ import annotations

import io
import json
import math
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional

from mcp.server.fastmcp import FastMCP, Image
from PIL import Image as PILImage
from PIL import ImageChops, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field

from pixelart_mcp import craft

mcp = FastMCP("pixelart_mcp")

MAX_DIM = 1024
MAX_SCALE = 32
MAX_BATCH_PIXELS = 4096
MAX_FRAMES = 256
VIEW_TARGET = 512  # previews auto-upscale to roughly this size on the long edge
PALETTE_TOP_N = 16


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_parse_color = craft.parse_color
_color_hex = craft.color_hex


def _resolve(path: str, *, suffix: str = ".png", must_exist: bool) -> Path:
    p = Path(path).expanduser()
    if p.suffix.lower() != suffix:
        raise ValueError(f"Path must end with '{suffix}', got '{path}'.")
    if must_exist and not p.exists():
        raise FileNotFoundError(
            f"No canvas at '{p}'. Create one with pixel_create_canvas, or check the path."
        )
    return p


def _load(path: str) -> tuple[Path, PILImage.Image]:
    p = _resolve(path, must_exist=True)
    img = PILImage.open(p).convert("RGBA")
    # Stash a pristine copy so preview_diff can crop to what actually changed.
    # Tools that rebind `img` to a new object (transform/resize/scale) lose it
    # and fall back to a full preview — correct, since those change everything.
    img._pixelart_before = img.copy()  # type: ignore[attr-defined]
    return p, img


def _png_bytes(img: PILImage.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _upscaled(img: PILImage.Image, scale: int) -> PILImage.Image:
    if scale <= 1:
        return img
    return img.resize((img.width * scale, img.height * scale), PILImage.Resampling.NEAREST)


def _auto_scale(img: PILImage.Image) -> int:
    return max(1, VIEW_TARGET // max(img.width, img.height))


def _preview_image(img: PILImage.Image, scale: Optional[int] = None) -> Image:
    return Image(data=_png_bytes(_upscaled(img, scale or _auto_scale(img))), format="png")


def _gridded(img: PILImage.Image, scale: int) -> PILImage.Image:
    """Upscale and overlay gridlines + coordinate labels every 8 canvas pixels."""
    margin = 22
    scaled = _upscaled(img, scale).convert("RGBA")
    out = PILImage.new("RGBA", (scaled.width + margin, scaled.height + margin), (24, 24, 30, 255))
    # checkerboard backdrop so transparency is visible under the art
    backdrop = PILImage.new("RGBA", scaled.size, (90, 90, 96, 255))
    bd = ImageDraw.Draw(backdrop)
    cell = max(4, scale // 2)
    for by in range(0, scaled.height, cell):
        for bx in range(0, scaled.width, cell):
            if (bx // cell + by // cell) % 2 == 0:
                bd.rectangle([bx, by, bx + cell - 1, by + cell - 1], fill=(112, 112, 118, 255))
    backdrop.alpha_composite(scaled)
    out.paste(backdrop, (margin, margin))
    overlay = PILImage.new("RGBA", out.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()
    if scale >= 4:
        for cx in range(img.width + 1):
            x = margin + cx * scale
            major = cx % 8 == 0
            draw.line([(x, margin), (x, out.height - 1)],
                      fill=(255, 255, 255, 90 if major else 36), width=1)
        for cy in range(img.height + 1):
            y = margin + cy * scale
            major = cy % 8 == 0
            draw.line([(margin, y), (out.width - 1, y)],
                      fill=(255, 255, 255, 90 if major else 36), width=1)
    for cx in range(0, img.width, 8):
        draw.text((margin + cx * scale + 2, 4), str(cx), fill=(220, 220, 230, 255), font=font)
    for cy in range(0, img.height, 8):
        draw.text((3, margin + cy * scale + 1), str(cy), fill=(220, 220, 230, 255), font=font)
    return PILImage.alpha_composite(out, overlay)


DIFF_PAD = 2
DIFF_FULL_FRACTION = 0.7  # a diff this large is not worth cropping
DIFF_VIEW_TARGET = 160  # diffs render small on purpose — that is the token saving


def _diff_view(img: PILImage.Image) -> Optional[tuple[PILImage.Image, str]]:
    """Crop to the region this operation changed, for a cheap preview.

    Returns (cropped_image, label), or None to fall back to a full preview.
    """
    before = getattr(img, "_pixelart_before", None)
    if before is None or before.size != img.size:
        return None
    # getbbox() on RGBA looks only at alpha, so a color-only edit would read as
    # empty; flatten the per-channel differences into one L mask first.
    bands = ImageChops.difference(before, img).split()
    mask = bands[0]
    for band in bands[1:]:
        mask = ImageChops.lighter(mask, band)
    bbox = mask.getbbox()
    if bbox is None:
        return img.crop((0, 0, min(8, img.width), min(8, img.height))), "no pixels changed"
    x0 = max(0, bbox[0] - DIFF_PAD)
    y0 = max(0, bbox[1] - DIFF_PAD)
    x1 = min(img.width, bbox[2] + DIFF_PAD)
    y1 = min(img.height, bbox[3] + DIFF_PAD)
    if (x1 - x0) * (y1 - y0) > img.width * img.height * DIFF_FULL_FRACTION:
        return None
    return img.crop((x0, y0, x1, y1)), f"changed region ({x0},{y0})-({x1 - 1},{y1 - 1})"


def _result(
    payload: dict,
    img: Optional[PILImage.Image] = None,
    preview: bool = False,
    preview_diff: bool = False,
) -> Any:
    if preview and img is not None and preview_diff:
        diff = _diff_view(img)
        if diff is not None:
            cropped, label = diff
            payload = {**payload, "preview": label}
            scale = max(1, min(16, DIFF_VIEW_TARGET // max(cropped.width, cropped.height)))
            return [json.dumps(payload, indent=2), _preview_image(cropped, scale)]
    text = json.dumps(payload, indent=2)
    if preview and img is not None:
        return [text, _preview_image(img)]
    return text


def _error(exc: Exception) -> str:
    if isinstance(exc, (ValueError, FileNotFoundError)):
        return f"Error: {exc}"
    return f"Error: unexpected {type(exc).__name__}: {exc}"


def _load_frames(frame_paths: List[str]) -> List[PILImage.Image]:
    frames = [_load(fp)[1] for fp in frame_paths]
    sizes = {f.size for f in frames}
    if len(sizes) > 1:
        raise ValueError(
            f"All frames must be the same size; got {sorted(sizes)}. "
            "Resize or recreate the mismatched frames first."
        )
    return frames


def _to_gif_frame(img: PILImage.Image) -> PILImage.Image:
    """Convert RGBA -> P-mode GIF frame, reserving palette index 255 for transparency."""
    p = img.convert("RGB").quantize(colors=255, method=PILImage.Quantize.MEDIANCUT)
    mask = img.getchannel("A").point(lambda a: 255 if a <= 128 else 0)
    p.paste(255, mask=mask)
    return p


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class CanvasOp(BaseModel):
    """Base input for operations that modify an existing canvas."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    path: str = Field(..., description="Canvas file path ending in .png. Prefer absolute paths.")
    preview: bool = Field(
        default=False,
        description="If true, also return a rendered image of the canvas after this operation.",
    )
    preview_diff: bool = Field(
        default=False,
        description="With preview=true, show only the region this call changed instead of the "
                    "whole canvas — far cheaper for small edits on a big canvas. Falls back to "
                    "the full canvas when the change is large.",
    )


class CreateCanvasInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    path: str = Field(..., description="Where to save the new canvas; must end in .png. Prefer absolute paths.")
    width: int = Field(..., ge=1, le=MAX_DIM, description=f"Canvas width in pixels (1-{MAX_DIM})")
    height: int = Field(..., ge=1, le=MAX_DIM, description=f"Canvas height in pixels (1-{MAX_DIM})")
    background: str = Field(
        default="transparent",
        description="Background color: hex ('#1a1c2c'), CSS name ('white'), or 'transparent'",
    )
    overwrite: bool = Field(default=False, description="Replace the file if it already exists")
    preview: bool = Field(default=False, description="If true, also return a rendered image of the new canvas")


class PixelPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(..., ge=0, description="X coordinate (0 = left edge)")
    y: int = Field(..., ge=0, description="Y coordinate (0 = top edge)")
    color: Optional[str] = Field(
        default=None, description="Color for this point; omit to use the batch default color"
    )


class DrawPixelsInput(CanvasOp):
    pixels: List[PixelPoint] = Field(
        ..., min_length=1, max_length=MAX_BATCH_PIXELS,
        description=f"Points to set (1-{MAX_BATCH_PIXELS} per call)",
    )
    color: str = Field(
        default="#000000",
        description="Default color for points that don't specify their own. 'transparent' erases.",
    )


class DrawLineInput(CanvasOp):
    x0: int = Field(..., description="Start X")
    y0: int = Field(..., description="Start Y")
    x1: int = Field(..., description="End X")
    y1: int = Field(..., description="End Y")
    color: str = Field(default="#000000", description="Line color; 'transparent' erases")
    thickness: int = Field(default=1, ge=1, le=64, description="Line thickness in pixels")


class DrawRectInput(CanvasOp):
    x: int = Field(..., description="Left edge X")
    y: int = Field(..., description="Top edge Y")
    width: int = Field(..., ge=1, description="Rectangle width in pixels")
    height: int = Field(..., ge=1, description="Rectangle height in pixels")
    color: str = Field(default="#000000", description="Color; 'transparent' erases")
    filled: bool = Field(default=True, description="Fill the rectangle; false draws a 1px outline")


class DrawEllipseInput(CanvasOp):
    x: int = Field(..., description="Bounding-box left edge X")
    y: int = Field(..., description="Bounding-box top edge Y")
    width: int = Field(..., ge=1, description="Bounding-box width in pixels")
    height: int = Field(..., ge=1, description="Bounding-box height in pixels")
    color: str = Field(default="#000000", description="Color; 'transparent' erases")
    filled: bool = Field(default=True, description="Fill the ellipse; false draws a 1px outline")


class FloodFillInput(CanvasOp):
    x: int = Field(..., ge=0, description="Seed point X")
    y: int = Field(..., ge=0, description="Seed point Y")
    color: str = Field(..., description="Fill color; 'transparent' erases the region")


class ReplaceColorInput(CanvasOp):
    find: str = Field(..., description="Exact color to replace (hex, CSS name, or 'transparent')")
    replace: str = Field(..., description="New color (hex, CSS name, or 'transparent')")


class TransformOp(str, Enum):
    FLIP_HORIZONTAL = "flip_horizontal"
    FLIP_VERTICAL = "flip_vertical"
    ROTATE_90_CW = "rotate_90_cw"
    ROTATE_90_CCW = "rotate_90_ccw"
    ROTATE_180 = "rotate_180"


_TRANSPOSE = {
    TransformOp.FLIP_HORIZONTAL: PILImage.Transpose.FLIP_LEFT_RIGHT,
    TransformOp.FLIP_VERTICAL: PILImage.Transpose.FLIP_TOP_BOTTOM,
    TransformOp.ROTATE_90_CW: PILImage.Transpose.ROTATE_270,  # PIL rotates counter-clockwise
    TransformOp.ROTATE_90_CCW: PILImage.Transpose.ROTATE_90,
    TransformOp.ROTATE_180: PILImage.Transpose.ROTATE_180,
}


class TransformInput(CanvasOp):
    operation: TransformOp = Field(..., description="Whole-canvas transform to apply")


class ViewInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    path: str = Field(..., description="Canvas file path ending in .png")
    scale: Optional[int] = Field(
        default=None, ge=1, le=64,
        description="Nearest-neighbor display scale; omit to auto-fit to ~512px",
    )
    grid: bool = Field(
        default=False,
        description="Overlay pixel gridlines with coordinate labels every 8px — "
                    "use when planning precise pixel placement",
    )


class InfoInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    path: str = Field(..., description="Canvas file path ending in .png")
    top_n: int = Field(
        default=8, ge=1, le=PALETTE_TOP_N,
        description=f"How many of the most-used colors to list (1-{PALETTE_TOP_N})",
    )


class ExportPngInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    path: str = Field(..., description="Source canvas path ending in .png")
    out_path: str = Field(..., description="Destination path ending in .png")
    scale: int = Field(default=8, ge=1, le=MAX_SCALE, description="Nearest-neighbor upscale factor")


class ExportGifInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    frame_paths: List[str] = Field(
        ..., min_length=2, max_length=MAX_FRAMES,
        description="Canvas PNGs to use as animation frames, in order. All must be the same size.",
    )
    out_path: str = Field(..., description="Destination path ending in .gif")
    duration_ms: int = Field(default=100, ge=20, le=5000, description="Time per frame in milliseconds")
    durations_ms: Optional[List[int]] = Field(
        default=None,
        description="Per-frame durations in ms, one per entry in frame_paths; overrides duration_ms",
    )
    ping_pong: bool = Field(
        default=False,
        description="Play frames forward then backward (1,2,3,2 loop) — good for idle/bounce cycles",
    )
    scale: int = Field(default=1, ge=1, le=MAX_SCALE, description="Nearest-neighbor upscale factor")


class ExportSpritesheetInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    frame_paths: List[str] = Field(
        ..., min_length=1, max_length=MAX_FRAMES,
        description="Canvas PNGs to pack, in order. All must be the same size.",
    )
    out_path: str = Field(..., description="Destination path ending in .png")
    columns: Optional[int] = Field(
        default=None, ge=1,
        description="Frames per row; omit to lay out all frames in a single row",
    )


# ---------------------------------------------------------------------------
# Tools: canvas lifecycle and drawing
# ---------------------------------------------------------------------------

@mcp.tool(
    name="pixel_create_canvas",
    annotations={
        "title": "Create Pixel Canvas",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def pixel_create_canvas(params: CreateCanvasInput) -> Any:
    """Create a new pixel art canvas saved as a PNG file.

    The canvas is true-size (one canvas pixel = one image pixel); keep sprites
    small (e.g. 16x16, 32x32, 64x64) and upscale later with pixel_export_png.
    Parent directories are created automatically. Refuses to replace an
    existing file unless overwrite=true.

    Returns: JSON {"canvas", "width", "height", "background"}; plus a rendered
    image of the canvas when preview=true. On failure returns "Error: ...".
    """
    try:
        p = _resolve(params.path, must_exist=False)
        if p.exists() and not params.overwrite:
            return (
                f"Error: '{p}' already exists. Pass overwrite=true to replace it, "
                "or choose a different path."
            )
        bg = _parse_color(params.background)
        img = PILImage.new("RGBA", (params.width, params.height), bg)
        p.parent.mkdir(parents=True, exist_ok=True)
        img.save(p)
        payload = {
            "canvas": str(p),
            "width": params.width,
            "height": params.height,
            "background": _color_hex(bg) if bg[3] else "transparent",
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_draw_pixels",
    annotations={
        "title": "Draw Pixels",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_draw_pixels(params: DrawPixelsInput) -> Any:
    """Set individual pixels on a canvas in one batch.

    Each point may carry its own color; points without one use the batch
    default `color`. Drawing 'transparent' erases pixels. Out-of-bounds points
    are skipped and counted, not fatal. Batch as many points per call as
    possible — one call per sprite region, not one call per pixel.

    Returns: JSON {"canvas", "pixels_drawn", "skipped_out_of_bounds"?}; plus a
    rendered image when preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        default = _parse_color(params.color)
        cache: dict[str, tuple[int, int, int, int]] = {}
        px = img.load()
        drawn = skipped = 0
        for point in params.pixels:
            if point.x >= img.width or point.y >= img.height:
                skipped += 1
                continue
            if point.color is None:
                value = default
            else:
                value = cache.get(point.color)
                if value is None:
                    value = _parse_color(point.color)
                    cache[point.color] = value
            px[point.x, point.y] = value
            drawn += 1
        if drawn == 0:
            return (
                f"Error: all {skipped} points fell outside the "
                f"{img.width}x{img.height} canvas. Coordinates are 0-indexed "
                f"from the top-left; the largest valid point is "
                f"({img.width - 1}, {img.height - 1})."
            )
        img.save(p)
        payload: dict[str, Any] = {"canvas": str(p), "pixels_drawn": drawn}
        if skipped:
            payload["skipped_out_of_bounds"] = skipped
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_draw_line",
    annotations={
        "title": "Draw Line",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_draw_line(params: DrawLineInput) -> Any:
    """Draw a straight line between two points on a canvas.

    Endpoints may lie outside the canvas; the visible segment is drawn.
    Drawing 'transparent' erases. Returns JSON {"canvas", "line", "color"};
    plus a rendered image when preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        color = _parse_color(params.color)
        draw = ImageDraw.Draw(img)
        draw.line(
            [(params.x0, params.y0), (params.x1, params.y1)],
            fill=color, width=params.thickness,
        )
        img.save(p)
        payload = {
            "canvas": str(p),
            "line": f"({params.x0},{params.y0}) -> ({params.x1},{params.y1})",
            "color": _color_hex(color),
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_draw_rect",
    annotations={
        "title": "Draw Rectangle",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_draw_rect(params: DrawRectInput) -> Any:
    """Draw a filled or outlined rectangle on a canvas.

    (x, y) is the top-left corner; width/height are in pixels. Drawing
    'transparent' erases the region. Returns JSON {"canvas", "rect", "color",
    "filled"}; plus a rendered image when preview=true. On failure returns
    "Error: ...".
    """
    try:
        p, img = _load(params.path)
        color = _parse_color(params.color)
        draw = ImageDraw.Draw(img)
        box = [params.x, params.y, params.x + params.width - 1, params.y + params.height - 1]
        if params.filled:
            draw.rectangle(box, fill=color)
        else:
            draw.rectangle(box, outline=color, width=1)
        img.save(p)
        payload = {
            "canvas": str(p),
            "rect": f"{params.width}x{params.height} at ({params.x},{params.y})",
            "color": _color_hex(color),
            "filled": params.filled,
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_draw_ellipse",
    annotations={
        "title": "Draw Ellipse",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_draw_ellipse(params: DrawEllipseInput) -> Any:
    """Draw a filled or outlined ellipse inside a bounding box on a canvas.

    (x, y) is the bounding box's top-left corner; equal width and height give
    a circle. Drawing 'transparent' erases. Returns JSON {"canvas", "ellipse",
    "color", "filled"}; plus a rendered image when preview=true. On failure
    returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        color = _parse_color(params.color)
        draw = ImageDraw.Draw(img)
        box = [params.x, params.y, params.x + params.width - 1, params.y + params.height - 1]
        if params.filled:
            draw.ellipse(box, fill=color)
        else:
            draw.ellipse(box, outline=color, width=1)
        img.save(p)
        payload = {
            "canvas": str(p),
            "ellipse": f"{params.width}x{params.height} at ({params.x},{params.y})",
            "color": _color_hex(color),
            "filled": params.filled,
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_flood_fill",
    annotations={
        "title": "Flood Fill",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_flood_fill(params: FloodFillInput) -> Any:
    """Flood-fill the contiguous region containing (x, y), like a paint bucket.

    Fills all connected pixels that exactly match the seed pixel's color.
    Returns JSON {"canvas", "seed", "color"}; plus a rendered image when
    preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        if params.x >= img.width or params.y >= img.height:
            return (
                f"Error: seed point ({params.x},{params.y}) is outside the "
                f"{img.width}x{img.height} canvas."
            )
        color = _parse_color(params.color)
        ImageDraw.floodfill(img, (params.x, params.y), color)
        img.save(p)
        payload = {
            "canvas": str(p),
            "seed": f"({params.x},{params.y})",
            "color": _color_hex(color),
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_replace_color",
    annotations={
        "title": "Replace Color",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_replace_color(params: ReplaceColorInput) -> Any:
    """Replace every pixel of one exact color with another across the canvas.

    Useful for palette swaps and recoloring sprites. Matching is exact RGBA.
    Returns JSON {"canvas", "find", "replace", "pixels_changed"}; plus a
    rendered image when preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        find = _parse_color(params.find)
        replace = _parse_color(params.replace)
        data = list(img.getdata())
        changed = data.count(find)
        if changed == 0:
            return (
                f"Error: no pixels of color {_color_hex(find)} found on '{p.name}'. "
                "Use pixel_canvas_info to list the colors actually present."
            )
        img.putdata([replace if px == find else px for px in data])
        img.save(p)
        payload = {
            "canvas": str(p),
            "find": _color_hex(find),
            "replace": _color_hex(replace),
            "pixels_changed": changed,
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_transform_canvas",
    annotations={
        "title": "Transform Canvas",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def pixel_transform_canvas(params: TransformInput) -> Any:
    """Flip or rotate the entire canvas in place.

    Operations: flip_horizontal, flip_vertical, rotate_90_cw, rotate_90_ccw,
    rotate_180. 90-degree rotations swap the canvas dimensions. Returns JSON
    {"canvas", "operation", "width", "height"}; plus a rendered image when
    preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        img = img.transpose(_TRANSPOSE[params.operation])
        img.save(p)
        payload = {
            "canvas": str(p),
            "operation": params.operation.value,
            "width": img.width,
            "height": img.height,
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Tools: inspection
# ---------------------------------------------------------------------------

@mcp.tool(
    name="pixel_view_canvas",
    annotations={
        "title": "View Canvas",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_view_canvas(params: ViewInput) -> Any:
    """Render a canvas as an image so you can see its current state.

    Small canvases are upscaled with nearest-neighbor (crisp pixels) to about
    512px on the long edge unless an explicit scale is given. Use this after a
    series of edits to check your work. Returns a text summary plus the
    rendered image. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        scale = params.scale or _auto_scale(img)
        summary = f"{p.name}: {img.width}x{img.height} canvas, shown at {scale}x"
        if params.grid:
            summary += " with an 8px coordinate grid"
            return [summary, Image(data=_png_bytes(_gridded(img, scale)), format="png")]
        return [summary, _preview_image(img, scale)]
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_canvas_info",
    annotations={
        "title": "Canvas Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_canvas_info(params: InfoInput) -> str:
    """Report a canvas's dimensions and color palette without rendering it.

    Returns JSON: {"canvas", "width", "height", "unique_colors",
    "has_transparency", "top_colors": [{"color", "count"}, ...]} with the up
    to 16 most-used colors (fully transparent pixels reported as
    'transparent'). On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        colors = img.getcolors(maxcolors=img.width * img.height) or []
        colors.sort(key=lambda item: item[0], reverse=True)
        top = [
            {
                "color": "transparent" if rgba[3] == 0 else _color_hex(rgba),
                "count": count,
            }
            for count, rgba in colors[:params.top_n]
        ]
        payload = {
            "canvas": str(p),
            "width": img.width,
            "height": img.height,
            "unique_colors": len(colors),
            "has_transparency": any(rgba[3] < 255 for _, rgba in colors),
            "top_colors": top,
        }
        return json.dumps(payload, indent=2)
    except Exception as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Tools: export
# ---------------------------------------------------------------------------

@mcp.tool(
    name="pixel_export_png",
    annotations={
        "title": "Export Scaled PNG",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_export_png(params: ExportPngInput) -> str:
    """Export a canvas as an upscaled PNG with crisp nearest-neighbor pixels.

    The source canvas is untouched; the export is written to out_path (parent
    directories are created). Use scale 1 for game-ready true-size assets and
    larger scales for display or sharing. Returns JSON {"source", "exported",
    "scale", "width", "height"}. On failure returns "Error: ...".
    """
    try:
        _, img = _load(params.path)
        out = _resolve(params.out_path, must_exist=False)
        out.parent.mkdir(parents=True, exist_ok=True)
        scaled = _upscaled(img, params.scale)
        scaled.save(out)
        return json.dumps({
            "source": params.path,
            "exported": str(out),
            "scale": params.scale,
            "width": scaled.width,
            "height": scaled.height,
        }, indent=2)
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_export_gif",
    annotations={
        "title": "Export Animated GIF",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_export_gif(params: ExportGifInput) -> str:
    """Combine same-size canvas PNGs into a looping animated GIF.

    Frames play in the order given at duration_ms per frame (or per-frame
    durations_ms). ping_pong=true plays forward then backward for seamless
    bounce/idle loops. Transparency is preserved as GIF binary transparency
    (alpha <= 128 becomes transparent). Source canvases are untouched.
    Returns JSON {"exported", "frames", "frames_played", "scale", "width",
    "height"}. On failure returns "Error: ...".
    """
    try:
        out = _resolve(params.out_path, suffix=".gif", must_exist=False)
        if params.durations_ms is not None:
            if len(params.durations_ms) != len(params.frame_paths):
                return (
                    f"Error: durations_ms has {len(params.durations_ms)} entries but there are "
                    f"{len(params.frame_paths)} frames; provide exactly one duration per frame."
                )
            if any(d < 20 or d > 5000 for d in params.durations_ms):
                return "Error: each entry in durations_ms must be between 20 and 5000 milliseconds."
        frames = [_upscaled(f, params.scale) for f in _load_frames(params.frame_paths)]
        order = list(range(len(frames)))
        if params.ping_pong and len(frames) > 2:
            order += list(range(len(frames) - 2, 0, -1))
        per_frame = params.durations_ms or [params.duration_ms] * len(frames)
        gif_frames = [_to_gif_frame(frames[i]) for i in order]
        out.parent.mkdir(parents=True, exist_ok=True)
        gif_frames[0].save(
            out,
            save_all=True,
            append_images=gif_frames[1:],
            duration=[per_frame[i] for i in order],
            loop=0,
            disposal=2,
            transparency=255,
        )
        return json.dumps({
            "exported": str(out),
            "frames": len(frames),
            "frames_played": len(order),
            "scale": params.scale,
            "width": frames[0].width,
            "height": frames[0].height,
        }, indent=2)
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_export_spritesheet",
    annotations={
        "title": "Export Spritesheet",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_export_spritesheet(params: ExportSpritesheetInput) -> str:
    """Pack same-size canvas PNGs into a single spritesheet PNG grid.

    Frames are placed left-to-right, top-to-bottom, `columns` per row (all in
    one row if omitted), with no padding — ideal for game engines. Source
    canvases are untouched. Returns JSON {"exported", "frames", "columns",
    "rows", "frame_width", "frame_height", "width", "height"}. On failure
    returns "Error: ...".
    """
    try:
        out = _resolve(params.out_path, must_exist=False)
        frames = _load_frames(params.frame_paths)
        fw, fh = frames[0].size
        cols = min(params.columns or len(frames), len(frames))
        rows = math.ceil(len(frames) / cols)
        sheet = PILImage.new("RGBA", (fw * cols, fh * rows), (0, 0, 0, 0))
        for i, frame in enumerate(frames):
            sheet.paste(frame, ((i % cols) * fw, (i // cols) * fh))
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out)
        return json.dumps({
            "exported": str(out),
            "frames": len(frames),
            "columns": cols,
            "rows": rows,
            "frame_width": fw,
            "frame_height": fh,
            "width": sheet.width,
            "height": sheet.height,
        }, indent=2)
    except Exception as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Helpers for animation and sprite tools
# ---------------------------------------------------------------------------

def _shift_l(mask: PILImage.Image, dx: int, dy: int) -> PILImage.Image:
    """Shift an L-mode mask without wrapping (edges clip to black)."""
    out = PILImage.new("L", mask.size, 0)
    out.paste(mask, (dx, dy))
    return out


def _dilate(mask: PILImage.Image, corners: bool) -> PILImage.Image:
    shifts = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if corners:
        shifts += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    out = mask.copy()
    for dx, dy in shifts:
        out = ImageChops.lighter(out, _shift_l(mask, dx, dy))
    return out


def _ghost(img: PILImage.Image, factor: float, tint: Optional[tuple[int, int, int, int]]) -> PILImage.Image:
    faded = img.getchannel("A").point(lambda a: int(a * factor))
    if tint is not None:
        out = PILImage.new("RGBA", img.size, (tint[0], tint[1], tint[2], 255))
    else:
        out = img.copy()
    out.putalpha(faded)
    return out


# ---------------------------------------------------------------------------
# Input models for animation and sprite tools
# ---------------------------------------------------------------------------

class DuplicateCanvasInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    path: str = Field(..., description="Source canvas path ending in .png")
    dest_path: str = Field(..., description="Destination path ending in .png")
    overwrite: bool = Field(default=False, description="Replace the destination if it already exists")


class PasteMode(str, Enum):
    REPLACE = "replace"
    OVER = "over"


class CopyRegionInput(CanvasOp):
    x: int = Field(..., ge=0, description="Source region left edge X")
    y: int = Field(..., ge=0, description="Source region top edge Y")
    width: int = Field(..., ge=1, description="Region width in pixels")
    height: int = Field(..., ge=1, description="Region height in pixels")
    dest_path: Optional[str] = Field(
        default=None, description="Destination canvas; omit to copy within the source canvas"
    )
    dest_x: int = Field(..., description="Destination X for the region's top-left (may be negative; clips)")
    dest_y: int = Field(..., description="Destination Y for the region's top-left (may be negative; clips)")
    mode: PasteMode = Field(
        default=PasteMode.OVER,
        description="'over' composites respecting transparency; 'replace' overwrites the rect including alpha",
    )


class ShiftCanvasInput(CanvasOp):
    dx: int = Field(..., ge=-MAX_DIM, le=MAX_DIM, description="Horizontal shift in pixels (positive = right)")
    dy: int = Field(..., ge=-MAX_DIM, le=MAX_DIM, description="Vertical shift in pixels (positive = down)")
    wrap: bool = Field(default=False, description="Wrap pixels around edges instead of shifting them off-canvas")


class Anchor(str, Enum):
    TOP_LEFT = "top_left"
    TOP = "top"
    TOP_RIGHT = "top_right"
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM = "bottom"
    BOTTOM_RIGHT = "bottom_right"


_ANCHOR_FRACTIONS = {
    Anchor.TOP_LEFT: (0.0, 0.0), Anchor.TOP: (0.5, 0.0), Anchor.TOP_RIGHT: (1.0, 0.0),
    Anchor.LEFT: (0.0, 0.5), Anchor.CENTER: (0.5, 0.5), Anchor.RIGHT: (1.0, 0.5),
    Anchor.BOTTOM_LEFT: (0.0, 1.0), Anchor.BOTTOM: (0.5, 1.0), Anchor.BOTTOM_RIGHT: (1.0, 1.0),
}


class ResizeCanvasInput(CanvasOp):
    width: int = Field(..., ge=1, le=MAX_DIM, description=f"New canvas width (1-{MAX_DIM})")
    height: int = Field(..., ge=1, le=MAX_DIM, description=f"New canvas height (1-{MAX_DIM})")
    anchor: Anchor = Field(
        default=Anchor.CENTER,
        description="Where the existing art sits in the new bounds (e.g. 'bottom' keeps feet planted)",
    )


class ScaleCanvasInput(CanvasOp):
    width: int = Field(..., ge=1, le=MAX_DIM, description=f"New width (1-{MAX_DIM})")
    height: int = Field(..., ge=1, le=MAX_DIM, description=f"New height (1-{MAX_DIM})")


class ApplyPaletteInput(CanvasOp):
    palette: List[str] = Field(
        ..., min_length=1, max_length=64,
        description="Allowed colors (hex or CSS names); every opaque pixel snaps to the nearest one",
    )


class OutlineMode(str, Enum):
    SOLID = "solid"
    SELECTIVE = "selective"


class OutlineInput(CanvasOp):
    color: str = Field(default="#000000", description="Outline color (used by mode='solid')")
    corners: bool = Field(
        default=False,
        description="Also outline diagonal (8-neighbor) contact — thicker, rounder result",
    )
    mode: OutlineMode = Field(
        default=OutlineMode.SOLID,
        description="'solid' uses one color; 'selective' colors each outline pixel a "
                    "darkened, cooled version of the art it touches (softer, pro look)",
    )


class OnionViewInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    path: str = Field(..., description="Current frame canvas path ending in .png")
    previous_paths: List[str] = Field(
        ..., min_length=1, max_length=3,
        description="Earlier frames, most recent first; drawn as fading ghosts under the current frame",
    )
    tint: Optional[str] = Field(
        default=None,
        description="Optional color for ghost silhouettes (e.g. '#ff00ff'); omit to show dimmed originals",
    )
    scale: Optional[int] = Field(
        default=None, ge=1, le=64,
        description="Display scale; omit to auto-fit to ~512px",
    )


class ViewFramesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    frame_paths: List[str] = Field(
        ..., min_length=1, max_length=64,
        description="Same-size canvas PNGs to lay out as a filmstrip, in order",
    )
    columns: Optional[int] = Field(default=None, ge=1, description="Frames per row; omit for a single row")
    scale: Optional[int] = Field(
        default=None, ge=1, le=MAX_SCALE,
        description="Display scale; omit to auto-fit the strip to ~1024px wide",
    )


class SliceSpritesheetInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    path: str = Field(..., description="Spritesheet PNG to slice")
    frame_width: int = Field(..., ge=1, le=MAX_DIM, description="Width of each frame in pixels")
    frame_height: int = Field(..., ge=1, le=MAX_DIM, description="Height of each frame in pixels")
    out_dir: str = Field(..., description="Directory to write frame PNGs into (created if missing)")
    prefix: str = Field(
        default="frame", pattern=r"^[A-Za-z0-9_-]+$",
        description="Output filename prefix; frames are written as '<prefix>_f00.png', '<prefix>_f01.png', ...",
    )
    skip_empty: bool = Field(default=True, description="Skip fully transparent tiles")
    overwrite: bool = Field(default=False, description="Replace existing frame files")


# ---------------------------------------------------------------------------
# Tools: animation workflow
# ---------------------------------------------------------------------------

@mcp.tool(
    name="pixel_duplicate_canvas",
    annotations={
        "title": "Duplicate Canvas",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def pixel_duplicate_canvas(params: DuplicateCanvasInput) -> str:
    """Copy a canvas to a new file — the standard way to start the next
    animation frame from the current one, then edit only what moves.

    Refuses to replace an existing file unless overwrite=true. Returns JSON
    {"source", "canvas", "width", "height"}. On failure returns "Error: ...".
    """
    try:
        _, img = _load(params.path)
        dest = _resolve(params.dest_path, must_exist=False)
        if dest.exists() and not params.overwrite:
            return f"Error: '{dest}' already exists. Pass overwrite=true to replace it."
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest)
        return json.dumps({
            "source": params.path,
            "canvas": str(dest),
            "width": img.width,
            "height": img.height,
        }, indent=2)
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_copy_region",
    annotations={
        "title": "Copy Region",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_copy_region(params: CopyRegionInput) -> Any:
    """Copy a rectangular region from one canvas onto another (or within the
    same canvas) — for moving limbs between frames, stamping repeated parts,
    or compositing a sprite onto a background.

    mode='over' (default) respects transparency like layering; mode='replace'
    overwrites the destination rect including alpha. Destination coordinates
    may be negative or overhang; the region clips to the destination canvas.
    Returns JSON {"source", "canvas", "region", "pasted_at", "mode"}; plus a
    rendered image of the destination when preview=true. On failure returns
    "Error: ...".
    """
    try:
        src_p, src = _load(params.path)
        if params.x + params.width > src.width or params.y + params.height > src.height:
            return (
                f"Error: region {params.width}x{params.height} at ({params.x},{params.y}) "
                f"exceeds the {src.width}x{src.height} source canvas."
            )
        region = src.crop((params.x, params.y, params.x + params.width, params.y + params.height))

        if params.dest_path is None or _resolve(params.dest_path, must_exist=False) == src_p:
            dest_p, dest = src_p, src
        else:
            dest_p, dest = _load(params.dest_path)

        dx, dy = params.dest_x, params.dest_y
        left_clip = max(0, -dx)
        top_clip = max(0, -dy)
        right = min(region.width, dest.width - dx)
        bottom = min(region.height, dest.height - dy)
        if left_clip >= right or top_clip >= bottom:
            return (
                f"Error: the region lands entirely outside the {dest.width}x{dest.height} "
                "destination canvas."
            )
        region = region.crop((left_clip, top_clip, right, bottom))
        at = (dx + left_clip, dy + top_clip)
        if params.mode == PasteMode.OVER:
            dest.alpha_composite(region, at)
        else:
            dest.paste(region, at)
        dest.save(dest_p)
        payload = {
            "source": str(src_p),
            "canvas": str(dest_p),
            "region": f"{params.width}x{params.height} from ({params.x},{params.y})",
            "pasted_at": f"({at[0]},{at[1]})",
            "mode": params.mode.value,
        }
        return _result(payload, dest, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_shift_canvas",
    annotations={
        "title": "Shift Canvas",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def pixel_shift_canvas(params: ShiftCanvasInput) -> Any:
    """Shift the whole canvas by (dx, dy) pixels — quick motion between
    animation frames (bobbing, jumping, sliding).

    Without wrap, pixels shifted past the edge are lost and vacated space is
    transparent; with wrap=true they re-enter from the opposite edge (good for
    scrolling backgrounds). Returns JSON {"canvas", "shift", "wrap"}; plus a
    rendered image when preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        if params.wrap:
            img = ImageChops.offset(img, params.dx, params.dy)
        else:
            shifted = PILImage.new("RGBA", img.size, (0, 0, 0, 0))
            shifted.paste(img, (params.dx, params.dy))
            img = shifted
        img.save(p)
        payload = {"canvas": str(p), "shift": f"({params.dx},{params.dy})", "wrap": params.wrap}
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_resize_canvas",
    annotations={
        "title": "Resize Canvas Bounds",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def pixel_resize_canvas(params: ResizeCanvasInput) -> Any:
    """Change the canvas bounds without scaling the art — grow the canvas
    (new space is transparent) or crop it, with the existing art held at the
    chosen anchor.

    Pixel sizes are unchanged; use pixel_scale_canvas to actually rescale art.
    Example: after squashing a sprite, resize back to the original height with
    anchor='bottom' to keep it grounded. Returns JSON {"canvas", "width",
    "height", "anchor"}; plus a rendered image when preview=true. On failure
    returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        fx, fy = _ANCHOR_FRACTIONS[params.anchor]
        offset = (round((params.width - img.width) * fx), round((params.height - img.height) * fy))
        resized = PILImage.new("RGBA", (params.width, params.height), (0, 0, 0, 0))
        resized.paste(img, offset)
        resized.save(p)
        payload = {
            "canvas": str(p),
            "width": params.width,
            "height": params.height,
            "anchor": params.anchor.value,
        }
        return _result(payload, resized, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_scale_canvas",
    annotations={
        "title": "Scale Canvas Art",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def pixel_scale_canvas(params: ScaleCanvasInput) -> Any:
    """Rescale the canvas and its art to new dimensions with nearest-neighbor
    sampling (no blurring).

    Integer multiples or divisors keep pixels perfectly crisp; other ratios
    will distort — useful deliberately for squash-and-stretch animation
    frames. Returns JSON {"canvas", "width", "height"}; plus a rendered image
    when preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        scaled = img.resize((params.width, params.height), PILImage.Resampling.NEAREST)
        scaled.save(p)
        payload = {"canvas": str(p), "width": scaled.width, "height": scaled.height}
        return _result(payload, scaled, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_apply_palette",
    annotations={
        "title": "Apply Palette",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_apply_palette(params: ApplyPaletteInput) -> Any:
    """Snap every opaque pixel to the nearest color in a given palette —
    enforce a consistent game palette across sprites or clean up stray colors.

    Nearest match is by RGB distance; each pixel's alpha is preserved and
    fully transparent pixels are untouched. Returns JSON {"canvas",
    "palette_size", "pixels_changed"}; plus a rendered image when
    preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        palette = [_parse_color(c)[:3] for c in params.palette]

        def nearest(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
            return min(palette, key=lambda c: (c[0] - rgb[0]) ** 2 + (c[1] - rgb[1]) ** 2 + (c[2] - rgb[2]) ** 2)

        mapping: dict[tuple[int, int, int], tuple[int, int, int]] = {}
        data = list(img.getdata())
        out = []
        changed = 0
        for px in data:
            if px[3] == 0:
                out.append(px)
                continue
            rgb = px[:3]
            new = mapping.get(rgb)
            if new is None:
                new = nearest(rgb)
                mapping[rgb] = new
            if new != rgb:
                changed += 1
            out.append((new[0], new[1], new[2], px[3]))
        img.putdata(out)
        img.save(p)
        payload = {"canvas": str(p), "palette_size": len(palette), "pixels_changed": changed}
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_outline_sprite",
    annotations={
        "title": "Outline Sprite",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_outline_sprite(params: OutlineInput) -> Any:
    """Draw a 1px outline around all opaque art on the canvas — the classic
    finishing pass that makes sprites pop against any background.

    The outline occupies transparent pixels adjacent to the art; the art
    itself is untouched. mode='solid' uses `color`; mode='selective' derives
    each outline pixel from the art it touches (darker, cooler — the "sel-out"
    style). If the sprite touches the canvas edge, grow the canvas first with
    pixel_resize_canvas so the outline has room. Returns JSON {"canvas",
    "mode", "pixels_outlined"}; plus a rendered image when preview=true.
    On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        color = _parse_color(params.color)
        mask = img.getchannel("A").point(lambda a: 255 if a > 0 else 0)
        ring = ImageChops.subtract(_dilate(mask, params.corners), mask)
        outlined = sum(1 for v in ring.getdata() if v)
        if outlined == 0:
            return (
                "Error: nothing to outline — the canvas is either empty or fully opaque. "
                "Outlines are drawn on transparent pixels next to opaque art."
            )
        if params.mode == OutlineMode.SELECTIVE:
            px = img.load()
            ring_px = ring.load()
            cache: dict[tuple[int, int, int], tuple[int, int, int]] = {}
            for y in range(img.height):
                for x in range(img.width):
                    if not ring_px[x, y]:
                        continue
                    neighbors = [
                        px[nx, ny][:3]
                        for nx, ny in (
                            (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1),
                            (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1), (x + 1, y + 1),
                        )
                        if 0 <= nx < img.width and 0 <= ny < img.height and px[nx, ny][3] > 0
                    ]
                    if not neighbors:
                        continue
                    src = max(set(neighbors), key=neighbors.count)
                    dark = cache.get(src)
                    if dark is None:
                        dark = craft.darken_for_outline(src)
                        cache[src] = dark
                    px[x, y] = dark + (255,)
        else:
            img.paste(color, mask=ring)
        img.save(p)
        payload = {
            "canvas": str(p),
            "mode": params.mode.value,
            "pixels_outlined": outlined,
        }
        if params.mode == OutlineMode.SOLID:
            payload["color"] = _color_hex(color)
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_onion_view",
    annotations={
        "title": "Onion-Skin View",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_onion_view(params: OnionViewInput) -> Any:
    """Render the current frame over faded ghosts of up to 3 earlier frames —
    onion-skinning, the standard way to judge motion between animation frames.

    List previous_paths most-recent first; ghosts fade with distance (35%,
    20%, 12% opacity). Pass a tint color to show ghosts as silhouettes when
    frame colors overlap too much. Nothing is written to disk. Returns a text
    summary plus the rendered image. On failure returns "Error: ...".
    """
    try:
        frames = _load_frames([params.path] + params.previous_paths)
        current, ghosts = frames[0], frames[1:]
        tint = _parse_color(params.tint) if params.tint else None
        opacities = [0.35, 0.20, 0.12]
        composite = PILImage.new("RGBA", current.size, (0, 0, 0, 0))
        for frame, opacity in reversed(list(zip(ghosts, opacities))):
            composite.alpha_composite(_ghost(frame, opacity, tint))
        composite.alpha_composite(current)
        scale = params.scale or _auto_scale(composite)
        summary = (
            f"{Path(params.path).name} over {len(ghosts)} ghost frame(s) "
            f"({', '.join(Path(fp).name for fp in params.previous_paths)}), shown at {scale}x"
        )
        return [summary, _preview_image(composite, scale)]
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_view_frames",
    annotations={
        "title": "View Frames Filmstrip",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_view_frames(params: ViewFramesInput) -> Any:
    """Render several same-size canvases side by side as one filmstrip image —
    review a whole animation or sprite set at a glance.

    Frames are laid out left-to-right, top-to-bottom on a neutral gray
    backdrop with thin separators, in the order given. Nothing is written to
    disk. Returns a text summary naming each frame position plus the rendered
    image. On failure returns "Error: ...".
    """
    try:
        frames = _load_frames(params.frame_paths)
        fw, fh = frames[0].size
        cols = min(params.columns or len(frames), len(frames))
        rows = math.ceil(len(frames) / cols)
        scale = params.scale or max(1, min(MAX_SCALE, 1024 // (cols * fw)))
        gap = 2
        cell_w, cell_h = fw * scale, fh * scale
        sheet = PILImage.new(
            "RGBA",
            (cols * cell_w + (cols - 1) * gap, rows * cell_h + (rows - 1) * gap),
            (64, 64, 64, 255),
        )
        for i, frame in enumerate(frames):
            cx = (i % cols) * (cell_w + gap)
            cy = (i // cols) * (cell_h + gap)
            sheet.alpha_composite(_upscaled(frame, scale), (cx, cy))
        order = " | ".join(f"{i + 1}: {Path(fp).name}" for i, fp in enumerate(params.frame_paths))
        summary = f"{len(frames)} frames at {scale}x, {cols} per row — {order}"
        return [summary, Image(data=_png_bytes(sheet), format="png")]
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_slice_spritesheet",
    annotations={
        "title": "Slice Spritesheet",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_slice_spritesheet(params: SliceSpritesheetInput) -> str:
    """Split a spritesheet PNG into individual frame canvases — the way to
    bring existing game assets in for editing or re-animation.

    Tiles are read left-to-right, top-to-bottom on a strict frame_width x
    frame_height grid (partial tiles at the right/bottom edges are ignored)
    and written to out_dir as '<prefix>_f00.png', '<prefix>_f01.png', ....
    Fully transparent tiles are skipped unless skip_empty=false. Returns JSON
    {"source", "out_dir", "frames_written", "skipped_empty", "frame_paths"}.
    On failure returns "Error: ...".
    """
    try:
        _, sheet = _load(params.path)
        cols = sheet.width // params.frame_width
        rows = sheet.height // params.frame_height
        if cols == 0 or rows == 0:
            return (
                f"Error: frame size {params.frame_width}x{params.frame_height} is larger than "
                f"the {sheet.width}x{sheet.height} sheet."
            )
        if cols * rows > MAX_FRAMES:
            return (
                f"Error: {cols}x{rows} grid is {cols * rows} tiles (max {MAX_FRAMES}). "
                "Check the frame size — it is probably smaller than the sheet's real tiles."
            )
        out_dir = Path(params.out_dir).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        skipped = 0
        for row in range(rows):
            for col in range(cols):
                tile = sheet.crop((
                    col * params.frame_width,
                    row * params.frame_height,
                    (col + 1) * params.frame_width,
                    (row + 1) * params.frame_height,
                ))
                if params.skip_empty and tile.getchannel("A").getbbox() is None:
                    skipped += 1
                    continue
                dest = out_dir / f"{params.prefix}_f{len(written):02d}.png"
                if dest.exists() and not params.overwrite:
                    return (
                        f"Error: '{dest}' already exists. Pass overwrite=true to replace "
                        "existing frames, or use a different prefix/out_dir."
                    )
                tile.save(dest)
                written.append(str(dest))
        if not written:
            return "Error: every tile in the sheet was fully transparent; nothing was written."
        return json.dumps({
            "source": params.path,
            "out_dir": str(out_dir),
            "frames_written": len(written),
            "skipped_empty": skipped,
            "frame_paths": written,
        }, indent=2)
    except Exception as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Input models for craft tools (color, shading, grid painting)
# ---------------------------------------------------------------------------

class BuildRampInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    color: str = Field(..., description="Base (midtone) color of the material, hex or CSS name")
    steps: int = Field(default=5, ge=3, le=9, description="Ramp length; 5 typical, 7 for hero materials")
    hue_shift_deg: float = Field(
        default=18.0, ge=0.0, le=45.0,
        description="Hue rotation per step: shadows toward blue, highlights toward warm. "
                    "18 = natural, 25-30 = dramatic/sunny, 0 = flat tints",
    )


class GradientKind(str, Enum):
    LINEAR = "linear"
    RADIAL = "radial"


class DitherPattern(str, Enum):
    NONE = "none"
    CHECKER = "checker"
    BAYER2 = "bayer2"
    BAYER4 = "bayer4"


class PaintOver(str, Enum):
    ALL = "all"
    OPAQUE = "opaque"
    TRANSPARENT = "transparent"


class DrawGradientInput(CanvasOp):
    x: int = Field(..., description="Region left edge X")
    y: int = Field(..., description="Region top edge Y")
    width: int = Field(..., ge=1, description="Region width in pixels")
    height: int = Field(..., ge=1, description="Region height in pixels")
    colors: List[str] = Field(
        ..., min_length=2, max_length=16,
        description="Gradient colors in order (start -> end); use a ramp from pixel_build_ramp",
    )
    kind: GradientKind = Field(default=GradientKind.LINEAR, description="'linear' or 'radial'")
    angle_deg: float = Field(
        default=90.0, ge=-360.0, le=360.0,
        description="Linear only: gradient direction; 0 = left-to-right, 90 = top-to-bottom",
    )
    center_x: Optional[int] = Field(default=None, description="Radial only: center X (default region center)")
    center_y: Optional[int] = Field(default=None, description="Radial only: center Y (default region center)")
    radius: Optional[float] = Field(
        default=None, gt=0,
        description="Radial only: distance at which the last color is reached (default: to region corner)",
    )
    dither: DitherPattern = Field(
        default=DitherPattern.NONE,
        description="Blend bands with ordered dithering: 'bayer4' smoothest (skies), "
                    "'checker' coarse retro, 'none' for hard bands",
    )
    paint_over: PaintOver = Field(
        default=PaintOver.ALL,
        description="'all' paints everything; 'opaque' only over existing art (shade a sprite); "
                    "'transparent' only empty pixels (fill a background behind art)",
    )
    target: Optional[str] = Field(
        default=None,
        description="Only paint pixels currently of this exact color — gradient-shade one "
                    "flat region (e.g. the water inside a bottle) without touching neighbors",
    )


class ShadeMode(str, Enum):
    BEVEL = "bevel"
    SPHERE = "sphere"
    CYLINDER_UPRIGHT = "cylinder_upright"
    CYLINDER_SIDE = "cylinder_side"


class LightDirection(str, Enum):
    TOP_LEFT = "top_left"
    TOP = "top"
    TOP_RIGHT = "top_right"
    LEFT = "left"
    RIGHT = "right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM = "bottom"
    BOTTOM_RIGHT = "bottom_right"


class ShadeRegionInput(CanvasOp):
    mode: ShadeMode = Field(
        ...,
        description="'sphere' round things (fruit, heads); 'cylinder_upright' bottles/trunks/limbs; "
                    "'cylinder_side' barrels/logs lying down; 'bevel' angular things (armor, rocks, cloth)",
    )
    light: LightDirection = Field(
        default=LightDirection.TOP_LEFT,
        description="Where the light comes FROM. Use the same value for every region of one artwork!",
    )
    target: Optional[str] = Field(
        default=None,
        description="Only shade pixels of this exact color; omit to shade every flat color "
                    "region on the canvas independently",
    )
    ramp: Optional[List[str]] = Field(
        default=None, min_length=3, max_length=9,
        description="Explicit dark->light ramp to shade with; omit to auto-build one from "
                    "each region's color (recommended)",
    )
    levels: int = Field(
        default=2, ge=1, le=3,
        description="Bevel only: shadow/highlight bands per side (2 = base±2 -> 5-color ramp)",
    )
    band_px: int = Field(default=1, ge=1, le=8, description="Bevel only: thickness of each band in pixels")


class PaintGridInput(CanvasOp):
    x: int = Field(default=0, description="Canvas X where the grid's left column lands")
    y: int = Field(default=0, description="Canvas Y where the grid's top row lands")
    rows: List[str] = Field(
        ..., min_length=1, max_length=MAX_DIM,
        description="The art as text, one string per pixel row; row length = width in pixels",
    )
    legend: dict[str, str] = Field(
        ...,
        description="Map from single characters used in rows to colors (hex/CSS/'transparent'). "
                    "'.' and ' ' skip (leave the canvas untouched) unless remapped here.",
    )


class Point2D(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(..., description="X coordinate")
    y: int = Field(..., description="Y coordinate")


class DrawPolygonInput(CanvasOp):
    points: List[Point2D] = Field(
        ..., min_length=3, max_length=256,
        description="Vertices in order; the shape is closed automatically. May sit partly "
                    "off-canvas (clips).",
    )
    color: str = Field(default="#000000", description="Color; 'transparent' erases")
    filled: bool = Field(default=True, description="Fill the polygon; false draws a 1px outline")


class DrawCurveInput(CanvasOp):
    x0: int = Field(..., description="Start point X")
    y0: int = Field(..., description="Start point Y")
    x1: int = Field(..., description="End point X")
    y1: int = Field(..., description="End point Y")
    cx: int = Field(..., description="First control point X — the curve bends toward it")
    cy: int = Field(..., description="First control point Y")
    cx2: Optional[int] = Field(
        default=None, description="Second control point X; give both cx2/cy2 for an S-curve (cubic)"
    )
    cy2: Optional[int] = Field(default=None, description="Second control point Y")
    color: str = Field(default="#000000", description="Color; 'transparent' erases")
    thickness: int = Field(default=1, ge=1, le=32, description="Stroke thickness in pixels")


class SpaaInput(CanvasOp):
    strength: float = Field(
        default=0.5, ge=0.05, le=1.0,
        description="How strongly the intermediate pixel reads: 0.5 is the classic half-tone",
    )
    background: Optional[str] = Field(
        default=None,
        description="Treat this color as the background to blend against. Omit for sprites on "
                    "transparency — edge pixels then use partial ALPHA, which composites "
                    "correctly over any backdrop instead of baking one in.",
    )
    edges: bool = Field(
        default=True, description="Soften the outer staircase corners of the silhouette"
    )
    interior: bool = Field(
        default=False,
        description="Also smooth staircase boundaries between two flat color regions inside "
                    "the art. Skip on sprites under ~32px — it muddies small details.",
    )


class AsciiViewInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    path: str = Field(..., description="Canvas file path ending in .png")
    x: int = Field(default=0, ge=0, description="Region left edge X")
    y: int = Field(default=0, ge=0, description="Region top edge Y")
    width: Optional[int] = Field(default=None, ge=1, description="Region width; omit for full canvas")
    height: Optional[int] = Field(default=None, ge=1, description="Region height; omit for full canvas")


class MirrorDirection(str, Enum):
    LEFT_TO_RIGHT = "left_to_right"
    RIGHT_TO_LEFT = "right_to_left"
    TOP_TO_BOTTOM = "top_to_bottom"
    BOTTOM_TO_TOP = "bottom_to_top"


class MirrorInput(CanvasOp):
    direction: MirrorDirection = Field(
        ...,
        description="Which half is the source: 'left_to_right' copies the left half, "
                    "mirrored, onto the right half",
    )
    axis: Optional[int] = Field(
        default=None, ge=0,
        description="Column (or row) the mirror reflects across; that line stays fixed. "
                    "Omit for the canvas center.",
    )


MAX_BATCH_OPS = 128


class BatchOperation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    op: str = Field(
        ...,
        description="Operation name without the 'pixel_' prefix, e.g. 'draw_rect', "
                    "'paint_grid', 'shade_region'. See pixel_batch's docstring for the list.",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="That operation's arguments, minus 'path' (the batch supplies it) and "
                    "minus preview flags (ignored per-op).",
    )


class BatchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    path: str = Field(..., description="Canvas every operation applies to; must end in .png")
    operations: List[BatchOperation] = Field(
        ..., min_length=1, max_length=MAX_BATCH_OPS,
        description=f"Operations to run in order (1-{MAX_BATCH_OPS})",
    )
    stop_on_error: bool = Field(
        default=True,
        description="Stop at the first failing operation. False runs the rest and reports "
                    "every failure — useful when operations are independent.",
    )
    preview: bool = Field(
        default=False, description="Return a rendered image of the canvas after the whole batch"
    )
    preview_diff: bool = Field(
        default=False,
        description="With preview=true, show only the region the whole batch changed",
    )


class PalettesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: Optional[str] = Field(
        default=None,
        description="Palette to fetch in full; omit to list all palettes with notes",
    )


class GuideInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    topic: Optional[str] = Field(
        default=None,
        description=f"One of: {', '.join(craft.GUIDE_TOPICS)}. Omit for the core workflow "
                    "plus the topic list.",
    )


# ---------------------------------------------------------------------------
# Tools: color and shading craft
# ---------------------------------------------------------------------------

@mcp.tool(
    name="pixel_build_ramp",
    annotations={
        "title": "Build Color Ramp",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_build_ramp(params: BuildRampInput) -> str:
    """Generate a professional dark->light shading ramp from one base color.

    Applies standard pixel-art color theory automatically: shadows get darker,
    more saturated, and hue-shift toward blue/violet; highlights get lighter,
    desaturate, and shift toward warm yellow. Build one ramp per material
    BEFORE drawing, then use only these colors. The base color sits at
    base_index; colors below it are shadows, above it highlights. Returns JSON
    {"ramp", "base_index", "base"}. On failure returns "Error: ...".
    """
    try:
        base = _parse_color(params.color)
        ramp, base_idx = craft.build_ramp(base, params.steps, params.hue_shift_deg)
        return json.dumps({
            "ramp": [_color_hex(c) for c in ramp],
            "base_index": base_idx,
            "base": _color_hex(base),
        }, indent=2)
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_draw_gradient",
    annotations={
        "title": "Draw Gradient",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_draw_gradient(params: DrawGradientInput) -> Any:
    """Fill a rectangular region with a quantized, optionally dithered gradient.

    The go-to tool for skies, glows, water, and smooth shading over large
    areas. Pass a ramp from pixel_build_ramp as `colors`. 'linear' flows along
    angle_deg (90 = top-to-bottom sky); 'radial' spreads from a center point
    (glows, vignettes). dither='bayer4' gives the smoothest banding-free look.
    paint_over='opaque' shades existing art only; 'transparent' fills the
    empty background behind art. Including 'transparent' in `colors` makes
    that part of the gradient leave existing pixels untouched — end a radial
    glow with it to fade out over the background. Returns JSON {"canvas",
    "region", "kind", "pixels_painted"}; plus a rendered image when
    preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        colors = [_parse_color(c) for c in params.colors]
        center = None
        if params.center_x is not None or params.center_y is not None:
            cx = params.center_x if params.center_x is not None else params.x + params.width // 2
            cy = params.center_y if params.center_y is not None else params.y + params.height // 2
            center = (float(cx), float(cy))
        painted = craft.paint_gradient(
            img,
            (params.x, params.y, params.width, params.height),
            colors,
            params.kind.value,
            params.angle_deg,
            center,
            params.radius,
            params.dither.value,
            params.paint_over.value,
            _parse_color(params.target) if params.target else None,
        )
        if painted == 0:
            return (
                "Error: no pixels painted — the region is outside the canvas or the "
                f"paint_over='{params.paint_over.value}' filter matched nothing."
            )
        img.save(p)
        payload = {
            "canvas": str(p),
            "region": f"{params.width}x{params.height} at ({params.x},{params.y})",
            "kind": params.kind.value,
            "dither": params.dither.value,
            "pixels_painted": painted,
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_shade_region",
    annotations={
        "title": "Auto-Shade Region",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def pixel_shade_region(params: ShadeRegionInput) -> Any:
    """Turn flat color regions into shaded 3D-looking forms in one call.

    Draw flat colors first, then shade: 'sphere' for round masses (fruit,
    heads, orbs), 'cylinder_upright' for bottles/trunks/standing limbs,
    'cylinder_side' for barrels/logs lying down, 'bevel' for angular surfaces
    (armor plates, rocks, cloth) — bevel lightens bands near the lit edge and
    darkens near the far edge. A hue-shifted ramp is auto-built from each
    region's color unless you pass one. Keep `light` identical across all
    calls for one artwork. Returns JSON {"canvas", "mode", "light",
    "regions_shaded", "pixels_shaded"}; plus a rendered image when
    preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        target = _parse_color(params.target) if params.target else None
        explicit_ramp = [_parse_color(c) for c in params.ramp] if params.ramp else None
        groups = craft._color_masks(img, target)
        if not groups:
            return (
                "Error: nothing to shade — no opaque pixels"
                + (f" of color {params.target}" if params.target else "")
                + " on the canvas. Lay down flat colors first."
            )
        if target is None and len(groups) > 32:
            return (
                f"Error: {len(groups)} distinct colors on canvas — too many to shade "
                "independently. Pass `target` to shade one color, or consolidate with "
                "pixel_apply_palette first."
            )
        total = 0
        for color, mask in groups:
            ramp, base_idx = craft._resolve_ramp(color, explicit_ramp, params.levels)
            if params.mode == ShadeMode.BEVEL:
                total += craft.shade_bevel(
                    img, mask, ramp, base_idx, params.light.value, params.levels, params.band_px
                )
            elif params.mode == ShadeMode.SPHERE:
                total += craft.shade_sphere(img, mask, ramp, params.light.value)
            else:
                total += craft.shade_cylinder(
                    img, mask, ramp, params.light.value,
                    upright=params.mode == ShadeMode.CYLINDER_UPRIGHT,
                )
        img.save(p)
        payload = {
            "canvas": str(p),
            "mode": params.mode.value,
            "light": params.light.value,
            "regions_shaded": len(groups),
            "pixels_shaded": total,
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Tools: text-grid drawing and reading
# ---------------------------------------------------------------------------

@mcp.tool(
    name="pixel_draw_polygon",
    annotations={
        "title": "Draw Polygon",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_draw_polygon(params: DrawPolygonInput) -> Any:
    """Draw a filled or outlined polygon from a list of vertices.

    The cheapest way to block in an angular silhouette — mountains, a ship
    hull, a sword blade, a roof, a leaf — describing the whole shape in a
    handful of points instead of hundreds of pixels. The outline closes
    automatically. Combine with pixel_draw_curve for shapes that mix straight
    runs and organic bends. Returns JSON {"canvas", "vertices", "color",
    "filled"}; plus a rendered image when preview=true. On failure returns
    "Error: ...".
    """
    try:
        p, img = _load(params.path)
        color = _parse_color(params.color)
        draw = ImageDraw.Draw(img)
        xy = [(pt.x, pt.y) for pt in params.points]
        if params.filled:
            draw.polygon(xy, fill=color)
        else:
            draw.polygon(xy, outline=color)
        img.save(p)
        payload = {
            "canvas": str(p),
            "vertices": len(xy),
            "color": _color_hex(color),
            "filled": params.filled,
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_draw_curve",
    annotations={
        "title": "Draw Bezier Curve",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_draw_curve(params: DrawCurveInput) -> Any:
    """Draw a smooth Bezier curve between two points.

    The tool for organic contours that lines and ellipses can't make: a
    dragon's neck, a torso's waist, hair, a hull's sheer, flame tongues, a
    tail. The curve bows from (x0,y0) toward the control point and on to
    (x1,y1); supply cx2/cy2 as well for an S-curve. Sampling is automatic and
    gap-free, so one call replaces dozens of pixel placements. Returns JSON
    {"canvas", "from", "to", "kind", "pixels_drawn"}; plus a rendered image
    when preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        color = _parse_color(params.color)
        cubic = params.cx2 is not None and params.cy2 is not None
        if (params.cx2 is None) != (params.cy2 is None):
            return "Error: give both cx2 and cy2 for a cubic curve, or neither for a quadratic."
        pts = craft.bezier_points(
            (params.x0, params.y0),
            (params.cx, params.cy),
            (params.x1, params.y1),
            (params.cx2, params.cy2) if cubic else None,
        )
        draw = ImageDraw.Draw(img)
        if len(pts) == 1:
            draw.point(pts[0], fill=color)
        else:
            draw.line(pts, fill=color, width=params.thickness, joint="curve")
        img.save(p)
        payload = {
            "canvas": str(p),
            "from": f"({params.x0},{params.y0})",
            "to": f"({params.x1},{params.y1})",
            "kind": "cubic" if cubic else "quadratic",
            "pixels_drawn": len(pts),
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_apply_spaa",
    annotations={
        "title": "Sub-Pixel Anti-Alias",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def pixel_apply_spaa(params: SpaaInput) -> Any:
    """Soften diagonal staircase edges by placing intermediate pixels — the
    hand-finishing pass that separates polished pixel art from blocky art.

    Run it LAST, after outlining. It finds the elbow of each diagonal step and
    fills it at partial strength, so curves and diagonals read smooth without
    any blurring. On a transparent background it uses partial alpha rather
    than blending into an assumed backdrop, so the sprite still anti-aliases
    correctly over any background. Set interior=true to also smooth boundaries
    between flat color regions inside the art (skip on sprites under ~32px).
    Not idempotent — running it twice thickens the softening. Returns JSON
    {"canvas", "edge_pixels", "interior_pixels", "strength"}; plus a rendered
    image when preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        bg = _parse_color(params.background) if params.background else None
        edge_n, interior_n = craft.apply_spaa(
            img, params.strength, bg, params.edges, params.interior
        )
        if edge_n == 0 and interior_n == 0:
            return (
                "Error: no staircase corners found to anti-alias. The art may have no "
                "diagonal edges yet, or `background` doesn't match the actual backdrop "
                "color (omit it for transparent backgrounds)."
            )
        img.save(p)
        payload = {
            "canvas": str(p),
            "edge_pixels": edge_n,
            "interior_pixels": interior_n,
            "strength": params.strength,
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_paint_grid",
    annotations={
        "title": "Paint ASCII Grid",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_paint_grid(params: PaintGridInput) -> Any:
    """Paint pixels from a text grid — the most reliable way to draw shapes.

    Write the art as strings, one character per pixel, with a legend mapping
    characters to colors. '.' and ' ' leave pixels untouched (so grids can
    layer over existing art); map a character to 'transparent' to erase.
    Example: rows=[".XX.", "XXXX"], legend={"X": "#b13e53"}, at (x, y).
    Rows may be different lengths. Far better than pixel_draw_pixels for any
    shape you can sketch as text — silhouettes, faces, patterns, texture.
    Returns JSON {"canvas", "at", "pixels_drawn", "skipped_out_of_bounds"?};
    plus a rendered image when preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        legend: dict[str, tuple[int, int, int, int]] = {}
        for ch, color in params.legend.items():
            if len(ch) != 1:
                raise ValueError(
                    f"Legend key '{ch}' must be exactly one character."
                )
            legend[ch] = _parse_color(color)
        if max(len(r) for r in params.rows) > MAX_DIM:
            raise ValueError(f"Rows longer than {MAX_DIM} characters are not allowed.")
        painted, skipped = craft.paint_grid(img, params.x, params.y, params.rows, legend)
        if painted == 0:
            return (
                f"Error: nothing painted — all {skipped} grid cells fell outside the "
                f"{img.width}x{img.height} canvas (grid placed at ({params.x},{params.y}))."
                if skipped else
                "Error: nothing painted — the grid contains only '.'/' ' skip characters."
            )
        img.save(p)
        payload: dict[str, Any] = {
            "canvas": str(p),
            "at": f"({params.x},{params.y})",
            "pixels_drawn": painted,
        }
        if skipped:
            payload["skipped_out_of_bounds"] = skipped
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_ascii_view",
    annotations={
        "title": "ASCII View",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_ascii_view(params: AsciiViewInput) -> str:
    """Read the canvas as a character grid with exact coordinates — see every
    pixel as text instead of an image.

    Rows are labeled with y, columns with an x ruler, and each color gets a
    legend character ('.' = transparent). Use it to verify precise placement,
    find stray pixels, or inspect art when an image view is ambiguous. Capped
    at 16384 pixels (128x128) per view — pass a region for larger canvases.
    Returns the grid + legend as plain text. On failure returns "Error: ...".
    """
    try:
        _, img = _load(params.path)
        w = params.width if params.width is not None else img.width - params.x
        h = params.height if params.height is not None else img.height - params.y
        if params.x + w > img.width or params.y + h > img.height or w < 1 or h < 1:
            return (
                f"Error: region {w}x{h} at ({params.x},{params.y}) exceeds the "
                f"{img.width}x{img.height} canvas."
            )
        return craft.ascii_view(img, (params.x, params.y, w, h))
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_mirror_canvas",
    annotations={
        "title": "Mirror Half",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_mirror_canvas(params: MirrorInput) -> Any:
    """Copy one half of the canvas onto the other, mirrored — draw half a
    symmetric subject (faces, characters, vehicles), then mirror it.

    'left_to_right' reflects the left half onto the right, etc. By default the
    mirror line is the canvas center (on odd sizes the center column/row stays
    as-is); pass `axis` to reflect across a specific column/row instead. After
    mirroring, break symmetry deliberately (weapon, lighting, pose). Returns
    JSON {"canvas", "direction", "axis"}; plus a rendered image when
    preview=true. On failure returns "Error: ...".
    """
    try:
        p, img = _load(params.path)
        horizontal = params.direction in (MirrorDirection.LEFT_TO_RIGHT, MirrorDirection.RIGHT_TO_LEFT)
        extent = img.width if horizontal else img.height
        axis2 = 2 * params.axis if params.axis is not None else extent - 1
        px = img.load()
        for y in range(img.height):
            for x in range(img.width):
                m = (axis2 - x, y) if horizontal else (x, axis2 - y)
                if not (0 <= m[0] < img.width and 0 <= m[1] < img.height):
                    continue
                pos, mpos = (x, m[0]) if horizontal else (y, m[1])
                if params.direction in (MirrorDirection.LEFT_TO_RIGHT, MirrorDirection.TOP_TO_BOTTOM):
                    if pos < mpos:
                        px[m] = px[x, y]
                else:
                    if pos > mpos:
                        px[m] = px[x, y]
        img.save(p)
        payload = {
            "canvas": str(p),
            "direction": params.direction.value,
            "axis": params.axis if params.axis is not None else (extent - 1) / 2,
        }
        return _result(payload, img, params.preview, getattr(params, "preview_diff", False))
    except Exception as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Tools: reference knowledge
# ---------------------------------------------------------------------------

def _batch_registry() -> dict[str, tuple[type[BaseModel], Any]]:
    """Allow-list of operations pixel_batch may run. Explicit by design — a batch
    never dispatches to an arbitrary attribute."""
    return {
        "draw_pixels": (DrawPixelsInput, pixel_draw_pixels),
        "draw_line": (DrawLineInput, pixel_draw_line),
        "draw_rect": (DrawRectInput, pixel_draw_rect),
        "draw_ellipse": (DrawEllipseInput, pixel_draw_ellipse),
        "draw_polygon": (DrawPolygonInput, pixel_draw_polygon),
        "draw_curve": (DrawCurveInput, pixel_draw_curve),
        "draw_gradient": (DrawGradientInput, pixel_draw_gradient),
        "paint_grid": (PaintGridInput, pixel_paint_grid),
        "flood_fill": (FloodFillInput, pixel_flood_fill),
        "replace_color": (ReplaceColorInput, pixel_replace_color),
        "shade_region": (ShadeRegionInput, pixel_shade_region),
        "apply_palette": (ApplyPaletteInput, pixel_apply_palette),
        "outline_sprite": (OutlineInput, pixel_outline_sprite),
        "apply_spaa": (SpaaInput, pixel_apply_spaa),
        "mirror_canvas": (MirrorInput, pixel_mirror_canvas),
        "copy_region": (CopyRegionInput, pixel_copy_region),
        "shift_canvas": (ShiftCanvasInput, pixel_shift_canvas),
        "transform_canvas": (TransformInput, pixel_transform_canvas),
        "resize_canvas": (ResizeCanvasInput, pixel_resize_canvas),
        "scale_canvas": (ScaleCanvasInput, pixel_scale_canvas),
    }


@mcp.tool(
    name="pixel_batch",
    annotations={
        "title": "Batch Draw",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def pixel_batch(params: BatchInput) -> Any:
    """Run many drawing operations on one canvas in a single call.

    THE DEFAULT WAY TO DRAW. A finished piece is 20-30 operations; sending them
    one per call re-sends the whole conversation each time, so batching a stage
    (silhouette, flats, details) into one call is where the real token saving
    is. Operations run in order and share the batch's `path`, so you never
    repeat it.

    Each entry is {"op": "<name>", "params": {...}} where <name> is a tool name
    without the 'pixel_' prefix: draw_pixels, draw_line, draw_rect, draw_ellipse,
    draw_polygon, draw_curve, draw_gradient, paint_grid, flood_fill,
    replace_color, shade_region, apply_palette, outline_sprite, apply_spaa,
    mirror_canvas, copy_region, shift_canvas, transform_canvas, resize_canvas,
    scale_canvas. Omit 'path' and preview flags from params.

    Example: [{"op": "draw_ellipse", "params": {"x": 4, "y": 4, "width": 24,
    "height": 24, "color": "#c22e2e"}}, {"op": "shade_region", "params":
    {"mode": "sphere", "light": "top_left"}}]

    The response is deliberately terse — a count, not a report per operation —
    and names only what failed. Returns JSON {"canvas", "ok", "pixels_changed",
    "failed"?}; plus a rendered image when preview=true (preview_diff crops to
    what the whole batch changed). On failure returns "Error: ...".
    """
    try:
        p, start = _load(params.path)
        before = start.copy()
        registry = _batch_registry()

        unknown = sorted({o.op for o in params.operations} - registry.keys())
        if unknown:
            return (
                f"Error: unknown operation(s) {', '.join(unknown)}. Use a tool name without "
                f"the 'pixel_' prefix; available: {', '.join(sorted(registry))}."
            )

        ok = 0
        failures: list[str] = []
        for i, entry in enumerate(params.operations):
            model, fn = registry[entry.op]
            args = {k: v for k, v in entry.params.items()
                    if k not in ("preview", "preview_diff")}
            args["path"] = str(p)
            try:
                parsed = model(**args)
            except Exception as exc:
                failures.append(f"[{i}] {entry.op}: invalid params — {exc}")
                if params.stop_on_error:
                    break
                continue
            result = await fn(parsed)
            text = result if isinstance(result, str) else result[0]
            if text.startswith("Error"):
                failures.append(f"[{i}] {entry.op}: {text[7:]}")
                if params.stop_on_error:
                    break
            else:
                ok += 1

        _, final = _load(params.path)
        bands = ImageChops.difference(before, final).split()
        mask = bands[0]
        for band in bands[1:]:
            mask = ImageChops.lighter(mask, band)
        changed = sum(1 for v in mask.getdata() if v) if before.size == final.size else -1

        payload: dict[str, Any] = {"canvas": str(p), "ok": ok}
        if changed >= 0:
            payload["pixels_changed"] = changed
        if failures:
            payload["failed"] = failures
        final._pixelart_before = before  # type: ignore[attr-defined]
        return _result(payload, final, params.preview, params.preview_diff)
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_palettes",
    annotations={
        "title": "Curated Palettes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_palettes(params: PalettesInput) -> str:
    """Fetch battle-tested pixel-art palettes instead of inventing colors.

    Without a name: lists every palette with its character notes. With a name:
    returns the full color list, ready to draw with and to pass to
    pixel_apply_palette. These sets are pre-harmonized — any two colors in one
    palette look good together. Returns JSON. On failure returns "Error: ...".
    """
    try:
        if params.name is None:
            return json.dumps({
                "palettes": [
                    {"name": name, "size": len(data["colors"]), "notes": data["notes"]}
                    for name, data in craft.PALETTES.items()
                ],
                "tip": "Fetch one by name, or build custom ramps with pixel_build_ramp.",
            }, indent=2)
        data = craft.PALETTES.get(params.name.lower())
        if data is None:
            return (
                f"Error: unknown palette '{params.name}'. "
                f"Available: {', '.join(craft.PALETTES)}."
            )
        return json.dumps({"name": params.name.lower(), **data}, indent=2)
    except Exception as exc:
        return _error(exc)


@mcp.tool(
    name="pixel_guide",
    annotations={
        "title": "Pixel Art Guide",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pixel_guide(params: GuideInput) -> str:
    """Get the pixel-art playbook — concrete technique recipes that map
    directly onto this server's tools.

    ALWAYS read topic 'workflow' before starting a new piece; it is the
    staged process (size -> palette -> silhouette -> flats -> shading ->
    details -> finish) that separates good sprites from mush. Other topics:
    'sizing' (canvas size table), 'color' (ramp discipline), 'shading' (light
    and form), 'dithering', 'materials' (metal/glass/wood/fire/...),
    'characters', 'scenes'. On failure returns "Error: ...".
    """
    try:
        if params.topic is None:
            return (
                craft.GUIDES["workflow"]
                + "\n\nOther topics: "
                + ", ".join(t for t in craft.GUIDE_TOPICS if t != "workflow")
            )
        topic = params.topic.lower()
        if topic not in craft.GUIDES:
            return (
                f"Error: unknown topic '{params.topic}'. "
                f"Available: {', '.join(craft.GUIDE_TOPICS)}."
            )
        return craft.GUIDES[topic]
    except Exception as exc:
        return _error(exc)
