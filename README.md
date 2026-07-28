# pixelart-mcp

A local MCP server for creating pixel art — no paid software, no external apps.
Canvases are ordinary PNG files on disk, edited with Pillow. One canvas pixel is
one image pixel; exports upscale with nearest-neighbor so pixels stay crisp.

## Tools

### Drawing

| Tool | Purpose |
|---|---|
| `pixel_create_canvas` | New PNG canvas (up to 1024x1024), any background or transparent |
| `pixel_draw_pixels` | Batch-set individual pixels, per-point colors supported |
| `pixel_draw_line` / `pixel_draw_rect` / `pixel_draw_ellipse` | Shape primitives, filled or outlined |
| `pixel_flood_fill` | Paint-bucket fill of a contiguous region |
| `pixel_replace_color` | Exact-match palette swap across the canvas |
| `pixel_apply_palette` | Snap all colors to the nearest entry of a given palette |
| `pixel_outline_sprite` | Auto 1px outline around opaque art |

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
| `pixel_view_canvas` | Render the canvas as an image the model can see |
| `pixel_canvas_info` | Dimensions + palette report without rendering |
| `pixel_export_png` | Nearest-neighbor upscaled PNG export |

Mutating tools accept `preview: true` to return a rendered image of the result
in the same call. Colors are hex (`#1a1c2c`, `#1a1c2cff`), CSS names
(`crimson`), or `transparent` (which erases).

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
