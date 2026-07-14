# Werner station body v1 — provenance and rejection record

Date: 2026-07-14

Canonical input SHA-256: `30c0d3f8bdf3baa243e624811174b28ec9205aadfc24181e775036c835a34f57`

Runtime asset SHA-256: `e261695e6d7ccdd469c4e401be03f9430eab4f09af67e0c8d3882fef4d1a3fdc`

## Adopted source

`werner_station_fishing_v1_transparent.png` is a deterministic crop of the
canonical `anchor/werner_default_v5_transparent.png`. No subject pixel was
generated, repainted, recolored, or resampled before the final 1024×1024
runtime normalization. The source crop is 844×844 at offset `(127,110)`.

Measured alpha bounds in the normalized asset are `(145,47)–(792,926)`. At the
native 64 px station this is 40.5 px wide × 55 px tall, with 2.94 px head
clearance and the feet ending at 57.94 px. The full border remains transparent.

## ChatGPT Image candidate — rejected

The built-in ChatGPT Image model was asked for an identity-preserving canonical
Werner edit with one raised gripping flipper and no rod or scenery. The output
was rejected before repository adoption because it changed face geometry,
beak construction, body proportions, and foot shapes. The experiment proved
that literal canonical pixels plus corrected framing/compositing were safer
than a redraw. No generated candidate is shipped or treated as Werner.

## Composition decision

The unchanged code-native rod renders behind the body at butt `(45,34)` and
tip `(66,5)`, so the canonical right flipper occludes the butt. The body is the
only semantic silhouette; the previous vector feet and flippers are removed.
Code continues to own the rod, line, fish, timing, and motion.
