# pixelart-mcp

A local MCP server for creating pixel art — no paid software, no external apps.
Canvases are ordinary PNG files on disk, edited with Pillow. One canvas pixel is
one image pixel; exports upscale with nearest-neighbor so pixels stay crisp.

The server encodes pixel-art *craft* in its tools, so models — including small
ones — don't have to be artists to produce good sprites: hue-shifted shading
ramps, one-call auto-shading (sphere / cylinder / bevel), dithered gradients,
symmetry mirroring, text-grid drawing and reading, curated palettes, and an
on-demand technique guide (`pixel_guide`) with a staged workflow
(size → palette → silhouette → flats → shading → details → finish).

## Tools

### Craft (color, shading, knowledge)

| Tool | Purpose |
|---|---|
| `pixel_guide` | Technique playbook: workflow, sizing, color, shading, dithering, materials, characters, scenes |
| `pixel_build_ramp` | One base color → professional dark→light ramp (hue-shifted shadows/highlights) |
| `pixel_shade_region` | Flat regions → shaded 3D form in one call: `sphere`, `cylinder_upright`, `cylinder_side`, `bevel` |
| `pixel_draw_gradient` | Linear/radial gradients with ordered dithering (`bayer4`, `checker`); can target one flat color or fade out via `transparent` |
| `pixel_paint_grid` | Draw from a text grid + character→color legend — the reliable way to place shapes |
| `pixel_ascii_view` | Read the canvas back as a labeled character grid with exact coordinates |
| `pixel_mirror_canvas` | Draw half a symmetric subject, mirror it across an axis |
| `pixel_palettes` | Curated, pre-harmonized palettes (sweetie16, pico8, dawnbringer16, slso8, nes) |
| `pixel_draw_polygon` | Angular silhouettes from a handful of vertices (hulls, roofs, blades, mountains) |
| `pixel_draw_curve` | Quadratic/cubic Bézier strokes for organic contours (necks, tails, hair, flames) |
| `pixel_apply_spaa` | Sub-pixel anti-aliasing: softens diagonal staircases; uses partial alpha on transparent backgrounds |

### Drawing

| Tool | Purpose |
|---|---|
| `pixel_create_canvas` | New PNG canvas (up to 1024x1024), any background or transparent |
| `pixel_draw_pixels` | Batch-set individual pixels, per-point colors supported |
| `pixel_draw_line` / `pixel_draw_rect` / `pixel_draw_ellipse` | Shape primitives, filled or outlined |
| `pixel_flood_fill` | Paint-bucket fill of a contiguous region |
| `pixel_replace_color` | Exact-match palette swap across the canvas |
| `pixel_apply_palette` | Snap all colors to the nearest entry of a given palette |
| `pixel_outline_sprite` | Auto 1px outline: `solid` color or `selective` (darkened neighbor colors) |

### Canvas surgery

| Tool | Purpose |
|---|---|
| `pixel_copy_region` | Copy/composite a rect within or between canvases (`over` / `replace`) |
| `pixel_shift_canvas` | Shift art by (dx, dy), optionally wrapping at edges |
| `pixel_resize_canvas` | Grow/crop canvas bounds with a 9-way anchor, art unscaled |
| `pixel_scale_canvas` | Nearest-neighbor rescale (squash-and-stretch friendly) |
| `pixel_transform_canvas` | Flip / rotate the whole canvas |

### Animation

| Tool | Purpose |
|---|---|
| `pixel_duplicate_canvas` | Start the next frame from the current one |
| `pixel_onion_view` | Current frame over faded ghosts of up to 3 earlier frames |
| `pixel_view_frames` | Filmstrip contact sheet of many frames in one image |
| `pixel_export_gif` | Looping GIF with per-frame durations and ping-pong mode |
| `pixel_export_spritesheet` | Pack frames into a grid PNG for game engines |
| `pixel_slice_spritesheet` | Split an existing sheet back into frame canvases |

### Inspection & export

| Tool | Purpose |
|---|---|
| `pixel_view_canvas` | Render the canvas as an image; `grid: true` adds labeled 8px coordinate gridlines |
| `pixel_canvas_info` | Dimensions + palette report without rendering |
| `pixel_export_png` | Nearest-neighbor upscaled PNG export |

Mutating tools accept `preview: true` to return a rendered image of the result
in the same call, and `preview_diff: true` to return only the region that
changed (roughly 90% fewer image tokens while iterating on a detail; falls back
to the full canvas when the change is large). Colors are hex (`#1a1c2c`,
`#1a1c2cff`), CSS names (`crimson`), or `transparent` (which erases).

## Design principle

Describe shapes, don't enumerate pixels. Every tool exists so a model can
express an artistic intent in one call rather than hundreds of coordinates: a
mountain is 5 polygon vertices, a dragon's neck is one Bézier, a sky is one
dithered gradient, a shaded sphere is one `pixel_shade_region` call. The staged
workflow in `pixel_guide` (silhouette → flats → shading → details → finish)
mirrors how pixel artists actually construct a piece, and `pixel_apply_spaa` is
the hand-finishing pass at the end.

## Benchmarks

[benchmarks/BENCHMARKS.md](benchmarks/BENCHMARKS.md) defines 15 standard
subjects (detailed apple, glass bottle with water, medieval knight, Spider-Man,
Iron Man in sunlight, campfire, dragon, ...) with per-subject must-haves and a
7-dimension rubric — run them across models or server versions to measure
whether a tooling change actually improves the art. `benchmarks/examples/`
holds reference pieces drawn with the craft toolset, with the scripts that
produced them.

## Setup

Requires [uv](https://docs.astral.sh/uv/). Register with Claude Code:

```bash
claude mcp add pixelart -s user -- uv --directory /path/to/pixelart-mcp run -m pixelart_mcp
```

Or in any MCP client config:

```json
{
  "mcpServers": {
    "pixelart": {
      "command": "uv",
      "args": ["--directory", "/path/to/pixelart-mcp", "run", "-m", "pixelart_mcp"]
    }
  }
}
```
