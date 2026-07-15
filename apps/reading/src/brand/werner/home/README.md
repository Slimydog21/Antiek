# antiek-knowledge-home-v1.webp

Authored atmosphere asset for the Antiek `/home` environment (Cycle 7).

## Provenance

| Field         | Value                                                              |
| ------------- | ------------------------------------------------------------------ |
| Generator     | Built-in ChatGPT Image                                             |
| Generation ID | `exec-91d91dd6-b527-40cd-a7a4-5b4ed0c93ba0`                        |
| Source format | 1536×1024 PNG                                                      |
| Final format  | WebP (VP8, lossy, 276,450 bytes)                                   |
| SHA-256       | `b01ec8603b432f44847e22444e083f0a3e1f0916b2016b7968eb942beb5f4947` |
| Date          | 2026-07-15                                                         |

## Prompt constraints

The image was generated under these constraints:

- Knowledge and research atmosphere — books, manuscripts, instruments of inquiry
- Warm, grounded palette consistent with the Antiek brand (ice, ink, sun tokens)
- No readable text, logos, people, animals, silhouettes, or mascot
- Functional research objects at the perimeter and a calm center for interface content
- A left-side workbench focal point that survives the mobile crop (`object-[24%_center]`), with symmetric observatory framing restored at `sm:`
- Suitable as a decorative background behind translucent glass (the GlassSurface scrim composites over it)

## Usage

Imported statically in `modes/Home/Home.tsx`:

```tsx
import homeEnvironment from "../../brand/werner/home/antiek-knowledge-home-v1.webp";
```

Rendered as a decorative pointer-inert sibling (`aria-hidden`, `pointer-events-none`) beneath the GlassSurface. The glass scrim (`SCRIM_MIN_OPACITY = 0.2`) therefore composites over the image and retains its WCAG-AA authority. No animation, rAF, interaction, network request, or runtime generation is introduced.

## Immutability

This asset is final. Do not regenerate or alter it.
