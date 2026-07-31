# Pixel-art drawing benchmarks

15 standard subjects for measuring how well a model draws with this server.
Each stresses a different mix of the hard skills: form shading, material
rendering, color-ramp discipline, light consistency, and composition. Run the
same subjects across models or across server versions to see what a change to
the tools actually buys.

## Protocol

Run each subject as a fresh conversation with only this MCP server connected,
using the standard prompt:

> Draw **{subject}** as pixel art on a **{W}x{H}** canvas at
> `benchmarks/runs/{run-id}/{id}.png`. Start with `pixel_guide` and follow its
> workflow. When finished, export at 8x to `{id}@8x.png`.

Two configurations worth comparing:

- **baseline** — the model is told not to use `pixel_guide`, `pixel_build_ramp`,
  `pixel_shade_region`, `pixel_draw_gradient`, `pixel_paint_grid`,
  `pixel_ascii_view`, `pixel_mirror_canvas`, or `pixel_palettes` (v0.2.0
  feature set: shapes, fills, single pixels).
- **craft** — full toolset, prompt as above.

Record per run: model, configuration, tool-call count, and the exported PNG.
Score with the rubric below; a subject *passes* when all its must-haves are
visibly present.

## Subjects

| # | id | Subject | Canvas | Primarily tests |
|---|----|---------|--------|-----------------|
| 1 | `apple` | Highly detailed apple with stem and leaf | 48x48 | Sphere form, specular, occlusion |
| 2 | `glass-bottle` | Clear glass bottle, water inside, light reflections | 40x64 | Transparency, rim light, liquid |
| 3 | `knight` | Medieval knight with sword and shield | 48x64 | Character workflow, armor bevel, symmetry |
| 4 | `spiderman` | Spider-Man, standing | 48x64 | Iconic character, pattern following form |
| 5 | `ironman-sunny` | Iron Man in a sunny environment | 96x96 | Scene + character, sun-warmed metal |
| 6 | `campfire` | Campfire at night | 48x48 | Emissive light, glow falloff, no-outline fire |
| 7 | `chest` | Open treasure chest spilling gold | 48x48 | Wood grain + gold glint materials |
| 8 | `sword` | Steel longsword, diagonal | 48x48 | Metal ramp, clean diagonals, edge specular |
| 9 | `oak` | Large oak tree in summer | 64x64 | Foliage clustering, trunk cylinder |
| 10 | `skull` | Human skull, 3/4 view | 32x32 | Value control at small scale |
| 11 | `sunset-ocean` | Sunset over the ocean | 96x64 | Gradients, dithering, reflections |
| 12 | `potion` | Glowing green potion bottle in a dark cellar | 32x40 | Emissive vs ambient, glass, mood |
| 13 | `barrel` | Wooden barrel with iron hoops | 40x48 | Upright cylinder, wood + metal mix |
| 14 | `dragon` | Red dragon, wings spread | 96x96 | Complex creature, membranes, scales |
| 15 | `astronaut` | Astronaut standing on the moon | 64x64 | White-material shading, minimal scene |

## Per-subject must-haves

1. **apple** — visible sphere shading with one light source; hue-shifted
   shadows (not just darker red); stem well darkened; 1-3px specular.
2. **glass-bottle** — background/wall color visible *through* the glass; darker
   1px rims; at least one long vertical specular streak; water has its own
   colors, a surface line, and reads below a fill level.
3. **knight** — silhouette readable at 1x; armor shaded with consistent light;
   ≤4 material groups; face shadow under helmet or visor slit.
4. **spiderman** — red/blue split correct; mask eyes large and white with dark
   border; web lines follow the body's curvature (not a flat overlay grid).
5. **ironman-sunny** — warm highlights (sunny key light) on red/gold armor;
   cast shadow anchoring him to the ground; background desaturated vs subject;
   arc reactor / eye glow.
6. **campfire** — flames have no dark outline; white-hot core → orange → deep
   red; radial glow tints the surrounding ground/logs; logs read as cylinders.
7. **chest** — wood grain lines follow plank direction; gold pile has glint
   pixels (brightest step, sparse); interior darker than exterior (occlusion).
8. **sword** — blade uses a high-contrast gray ramp with a hard specular line
   down its length; diagonal edges are clean pixel stairs (no jaggy wobble);
   guard/grip distinct materials.
9. **oak** — foliage is 4+ shaded clusters, not one blob and not per-leaf
   noise; darkest green fills the gaps between clusters; trunk cylinder-shaded
   with light matching the canopy.
10. **skull** — eye sockets and nasal cavity darkest; cranium reads as a
    sphere; teeth suggested with ≤2 colors; works with ≤6 colors total.
11. **sunset-ocean** — sky gradient dithered (no hard wide bands); sun's
    reflection on water as broken vertical streaks; horizon line level;
    warm sky vs cooler dark water.
12. **potion** — the liquid is the brightest thing in frame; its glow tints
    nearby surfaces; the cellar stays dark and desaturated; glass rim catches
    1px of the glow.
13. **barrel** — stave lines curve with the barrel's bulge; upright-cylinder
    shading (bright band off-center toward the light); hoops darker with their
    own 1px highlight.
14. **dragon** — silhouette readable at 1x (wings/head/tail distinct); wing
    membranes lighter/thinner-looking than the body; scale texture only in
    midtone areas, not everywhere; consistent light.
15. **astronaut** — white suit shaded with tinted grays (never pure gray
    ramps only — cool shadows); visor reflection; harsh single-source light
    (no soft ambient); dark sky, bright ground.

## Stress extras (16-20)

Additional subjects for large stress runs:

| # | id | Subject | Canvas | Primarily tests |
|---|----|---------|--------|-----------------|
| 16 | `cottage` | Cozy stone cottage at dusk, lit windows | 64x64 | Emissive windows vs dusk ambient |
| 17 | `phoenix` | Phoenix rising, wings spread | 64x64 | Fire as a body, glow, motion |
| 18 | `koi` | Koi pond seen from above, lily pads | 64x64 | Seeing through water, ripples |
| 19 | `pirate-ship` | Pirate ship on rough seas | 96x64 | Cloth sails, hull wood, sea foam |
| 20 | `ice-cave` | Glowing crystal in an ice cave | 48x48 | Ice translucency, emissive core |

Must-haves:

16. **cottage** — dithered dusk-sky gradient; windows are the brightest thing
    in frame and spill warm light onto ground/walls; roofline silhouette
    readable; warm emissive against cool ambient.
17. **phoenix** — flame body/wings with no dark outline (white-hot core →
    orange → deep red); rising pose readable from silhouette; a few detached
    ember pixels.
18. **koi** — fish visible *through* the water (blue-shifted and subdued vs
    surface elements); ripple rings; lily pads two-tone shaded; water surface
    is not one flat blue.
19. **pirate-ship** — sails shaded as curved cloth (soft bands, low contrast);
    hull planks with grain; wave bands with foam highlights; masts and 1px
    rigging read cleanly.
20. **ice-cave** — crystal is the brightest element, cyan-white core; its glow
    tints nearby ice; ice reads glassy (rim edges, streak highlights); cool
    palette with deep blue shadows.

## Rubric (score each 0-5)

| Dimension | 5 looks like |
|---|---|
| Silhouette | Subject instantly recognizable from shape alone at 1x |
| Palette | ≤16 colors, ramps hue-shift, no near-duplicate strays |
| Light | One consistent direction; shadows and highlights agree everywhere |
| Form | Volumes read as 3D: spheres, cylinders, bevels — no pillow-shading |
| Materials | Metal/glass/wood/etc. each identifiable by rendering alone |
| Detail | Density matches canvas size; focal point most detailed |
| Finish | Deliberate outline style; no stray pixels; clean edges |

Report: total /35 per subject, plus pass/fail on must-haves. Compare runs in a
filmstrip with `pixel_view_frames`.

## Reference examples

`examples/` holds pieces drawn with the full craft toolset (see the scripts
alongside them) — the current quality ceiling of the tools, useful as a visual
anchor when scoring: `apple` (subject 1) and `glass-bottle` (subject 2).
