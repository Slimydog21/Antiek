# Research-wait arcade key art

These two decorative scene illustrations distinguish the existing Ice Fishing
and Paperclip Zombies cartridges. They intentionally contain no Werner: the
single live mascot remains fixed outside the control surface, so the chooser
does not create a second character or spend a mascot appearance mid-content.

## Authority and generation

- Generator: built-in ChatGPT Image (`gpt-image-2`), 2026-07-15.
- Ice Fishing call: `exec-f22b0225-4ca7-4c44-80ce-217111eebe86`.
- Paperclip archive call: `exec-8f80b4cb-e607-4097-bd9f-1d5ae6e6e8ec`.
- The two earlier Werner-bearing candidates from this session were rejected and
  are not present in the repository because they violated the one-live-mascot
  restraint.
- No runtime generation, provider request, remote locator, or raw source path is
  part of the product.

## Production transforms

The generated 1536×1024 PNGs were resized to 1200×800 with macOS `sips`, then
encoded using `cwebp -q 90 -m 6`. This keeps the complete 3:2 compositions while
reducing the shipped pair from multi-megabyte PNGs to under 500 KiB combined.

| Asset                                 | SHA-256                                                            |     Size |
| ------------------------------------- | ------------------------------------------------------------------ | -------: |
| `ice-fishing-station-key-art-v1.webp` | `cc7d090d707d6716102a1056f84d5d754d10fb091a1fa0ee6615a112ce01b1d3` | 1200×800 |
| `paperclip-archive-key-art-v1.webp`   | `d11dab01968e32846dd3a7e3b08bb25975838af461041e24078a1f0e59474b3c` | 1200×800 |

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
