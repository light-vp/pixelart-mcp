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
from PIL import ImageColor, ImageDraw
from pydantic import BaseModel, ConfigDict, Field

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

def _parse_color(value: str) -> tuple[int, int, int, int]:
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


def _color_hex(rgba: tuple[int, int, int, int]) -> str:
    r, g, b, a = rgba
    return f"#{r:02x}{g:02x}{b:02x}" + (f"{a:02x}" if a != 255 else "")


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
    return p, PILImage.open(p).convert("RGBA")


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


def _result(payload: dict, img: Optional[PILImage.Image] = None, preview: bool = False) -> Any:
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


class InfoInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    path: str = Field(..., description="Canvas file path ending in .png")


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
        return _result(payload, img, params.preview)
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
        return _result(payload, img, params.preview)
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
        return _result(payload, img, params.preview)
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
        return _result(payload, img, params.preview)
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
        return _result(payload, img, params.preview)
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
        return _result(payload, img, params.preview)
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
        return _result(payload, img, params.preview)
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
        return _result(payload, img, params.preview)
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
            for count, rgba in colors[:PALETTE_TOP_N]
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

    Frames play in the order given at duration_ms per frame. Transparency is
    preserved as GIF binary transparency (alpha <= 128 becomes transparent).
    Source canvases are untouched. Returns JSON {"exported", "frames",
    "duration_ms", "scale", "width", "height"}. On failure returns "Error: ...".
    """
    try:
        out = _resolve(params.out_path, suffix=".gif", must_exist=False)
        frames = [_upscaled(f, params.scale) for f in _load_frames(params.frame_paths)]
        gif_frames = [_to_gif_frame(f) for f in frames]
        out.parent.mkdir(parents=True, exist_ok=True)
        gif_frames[0].save(
            out,
            save_all=True,
            append_images=gif_frames[1:],
            duration=params.duration_ms,
            loop=0,
            disposal=2,
            transparency=255,
        )
        return json.dumps({
            "exported": str(out),
            "frames": len(frames),
            "duration_ms": params.duration_ms,
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
