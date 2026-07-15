# Research-wait arcade key art

These decorative scene illustrations distinguish the research-wait cartridges.
They intentionally contain no Werner: the
single live mascot remains fixed outside the control surface, so the chooser
does not create a second character or spend a mascot appearance mid-content.

## Authority and generation

- Generator: built-in ChatGPT Image (`gpt-image-2`), 2026-07-15.
- Ice Fishing call: `exec-f22b0225-4ca7-4c44-80ce-217111eebe86`.
- Paperclip archive call: `exec-8f80b4cb-e607-4097-bd9f-1d5ae6e6e8ec`.
- Clam Catcher call: `exec-8e01e75a-9136-4cef-9d31-139f507630ce`.
- Clam Catcher visual-kit call: `exec-2c98cfa4-2d12-45bc-a806-cb761c85378c`.
- Paperclip Zombies visual-kit call: `exec-a6a0f5e5-1185-4670-8e20-5db4662b0068`.
- The two earlier Werner-bearing candidates from this session were rejected and
  are not present in the repository because they violated the one-live-mascot
  restraint.
- No runtime generation, provider request, remote locator, or raw source path is
  part of the product.

## Production transforms

The generated 1536×1024 PNGs were resized to 1200×800 with macOS `sips`, then
encoded using `cwebp -q 90 -m 6`. This keeps the complete 3:2 compositions while
reducing the shipped trio from multi-megabyte PNGs to under 700 KiB combined.

| Asset                                  | SHA-256                                                            |      Size |
| -------------------------------------- | ------------------------------------------------------------------ | --------: |
| `ice-fishing-station-key-art-v1.webp`  | `cc7d090d707d6716102a1056f84d5d754d10fb091a1fa0ee6615a112ce01b1d3` |  1200×800 |
| `paperclip-archive-key-art-v1.webp`    | `d11dab01968e32846dd3a7e3b08bb25975838af461041e24078a1f0e59474b3c` |  1200×800 |
| `clam-catcher-station-key-art-v1.webp` | `0551006bcf4775c8317c2bf7a967028c3c4da7a69c4dd78ff130d119d80f29b8` |  1200×800 |
| `clam-catcher-visual-kit-v1.webp`      | `6ee8dd9c9614b8ad89ca5446c226852aae3bd0ef6410b9818af1d7413386963e` | 1254×1254 |
| `paperclip-zombies-visual-kit-v1.webp` | `43670cf9a4738f7eae319446ec1ff2f572ddec10972622eeef8e95e1e68987c3` | 1254×1254 |

The visual kit uses one built-in ChatGPT Image PNG on a removable green field.
The installed imagegen helper sampled border key `#03f805`, applied a soft
matte and despill, and encoded the result directly as alpha WebP. Validation:
all four corners have alpha 0; 1,176,888 pixels are fully transparent; 10,247
are partially transparent; nonzero coverage is 25.16%. Runtime crops use the
padded validated bounds inside each 627×627 atlas quadrant. The two-pixel
transparent margin prevents alpha-edge clipping without admitting generated
padding or a neighboring sprite into a draw call.

The Paperclip Zombies kit uses the same local, runtime-independent chroma
workflow. The generated border sampled as `#05f80a`; soft matte and despill
produced 1,260,140 fully transparent pixels and 8,008 partially transparent
pixels in the 131,870-byte WebP. All four corners and every two-pixel quadrant
edge are alpha 0. Runtime crops retain transparent padding, aspect-fit inside
the unchanged authoritative rectangles, and never enlarge hitboxes.

## Final prompts

### Ice Fishing

> A quiet polar ice-fishing station with a circular ice hole, a short
> brass-and-wood fishing rod on a stand, its line in the water, one fish
> silhouette beneath translucent ice, and a distant scientific observatory.
> No character. Refined flat editorial illustration with subtle screen-print
> texture; glacier blue, paper white, ink black, brass yellow, and muted coral.
> Horizontal 3:2, subject on the right with calm left-side negative space. No
> text, logo, watermark, UI, cursor, gradient, or stock-game styling.

### Paperclip archive

> A midnight polar research archive under playful siege from animated
> paperclips. Curving paperclip paths move through archive aisles toward a brass
> data terminal and one red archival stamp; a telescope and ice ridge connect
> the scene to serious research. No character. Refined flat editorial
> illustration with subtle screen-print texture; ink navy, glacier blue, paper
> white, brass yellow, and muted coral. Horizontal 3:2, terminal on the right
> with calm upper-left negative space. No text, logo, watermark, UI, weapon,
> gore, horror imagery, or copied franchise imagery.

### Clam Catcher

> Create one production key-art illustration for Antiek's “Clam Catcher”
> research-wait mini-game. Scene only: an empty polar archive sorting station
> viewed slightly from above, with a brass-rimmed catch bucket centered near the
> bottom, two small pearl clams falling through clear glacier water, and one
> softly glowing jellyfish hazard offset to the upper right. Include subtle
> archive architecture and an underwater observation window so it belongs to a
> serious research workstation, not a generic mobile game. No character, no
> penguin, no Werner, no person, no hands. Refined flat editorial illustration
> with restrained screen-print texture and crisp geometric silhouettes; Antiek
> palette of ink navy, glacier blue, paper white, brass yellow, muted coral, and
> a very small aurora accent. Horizontal 3:2 composition, action concentrated on
> the right and lower center with calm negative space at upper left. No text,
> letters, numbers, logo, watermark, UI chrome, cursor, gradient, photorealism,
> gore, weapons, franchise imagery, or stock-game styling.

### Clam Catcher visual kit

> Use case: stylized-concept. Asset type: production 2x2 game sprite atlas for
> Antiek's Clam Catcher canvas mini-game. Create exactly four isolated, readable
> underwater archive-game objects arranged as a strict 2x2 atlas: top-left one
> small closed common clam, top-right one small open pearl clam with a single
> pearl, bottom-left one softly glowing jellyfish hazard, bottom-right one
> brass-rimmed archive catch bucket viewed slightly from above. Each object must
> be fully contained and centered within its own equal quadrant with generous
> padding; no overlap between quadrants. Use a perfectly flat solid #00ff00
> chroma-key background across the entire image, with no grid lines or dividers.
> Refined flat editorial game illustration with restrained screen-print texture,
> crisp geometric silhouettes, consistent three-quarter perspective, and calm
> polar underwater light. Palette: ink navy, glacier blue, paper white, brass
> yellow, muted coral, and a very small aurora accent; never use #00ff00 inside
> an object. Exactly four objects and nothing else. No shadows, gradients,
> texture, reflections, floor plane, or lighting variation in the background.
> No text, letters, numbers, logo, watermark, UI, cursor, character, penguin,
> Werner, person, hands, fake research evidence, weapon, gore, photorealism,
> franchise imagery, or stock-game styling.

### Paperclip Zombies visual kit

> Use case: stylized-concept. Asset type: production 2x2 game sprite atlas for
> Antiek's Paperclip Zombies research-wait canvas mini-game. Create exactly four
> isolated, readable archive-game objects arranged as a strict 2x2 atlas:
> top-left one small single-loop animated paperclip threat for 1 HP; top-right
> one reinforced double-loop paperclip threat for 2 HP; bottom-left one compact
> many-loop paperclip swarm-knot for 3-or-more HP; bottom-right one small brass
> archive-fort sigil shaped like a filing-tab shield with a centered diamond
> aperture. These are whimsical haunted office artifacts, not people or bodies.
> Use a perfectly flat solid #00ff00 chroma-key background across the entire
> image with no grid lines or dividers. Refined flat editorial game illustration
> with restrained screen-print texture and crisp geometric silhouettes;
> unmistakably a serious polar research archive transformed into a playful
> midnight arcade. Each object must be fully contained and centered within its
> equal quadrant with generous padding, no overlap, consistent three-quarter
> perspective, and a strong silhouette distinct around 18x18 pixels. Palette:
> ink navy, glacier blue, paper white, brass yellow, muted coral, and a tiny
> aurora accent; never use #00ff00 inside an object. Exactly four objects and
> nothing else. HP progression must read through silhouette complexity without
> numbers. No background shadows, gradients, texture, reflections, floor plane,
> glow spill, or lighting variation. No text, letters, numbers, logo, watermark,
> UI, cursor, character, penguin, Werner, person, hands, fake research evidence,
> weapon, gore, body horror, skulls, blood, copied franchise imagery,
> photorealism, or stock-game styling.
