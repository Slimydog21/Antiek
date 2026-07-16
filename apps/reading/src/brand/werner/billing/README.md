# Billing Usage Observatory — Werner environment asset

## File

`billing_usage_observatory_environment_v1.webp`

## Purpose

Decorative background image for the Billing Usage Observatory page. Rendered
as a fixed-position `<img>` behind the glass-panel content via a gradient
veil, following the same pattern as the Pricing and PayoutsAudit pages.

## Provenance

Krea-generated Antarctic landscape — the same visual language as the other
Werner environment assets (Pricing, PayoutsAudit, Research). The veil
gradient overlays the image to ensure text readability at all viewport sizes.

## Accessibility

The image is marked `aria-hidden="true"` and carries an empty `alt=""` — it
is purely decorative and contributes no semantic content. The `pointer-events:
none` CSS rule prevents accidental interaction. Under
`prefers-reduced-motion`, the image is already static (no animation to
collapse).

## Usage

```tsx
import environment from "../../brand/werner/billing/billing_usage_observatory_environment_v1.webp";

// In the component:
<img className="buo-environment" src={environment} alt="" aria-hidden="true" />
<div className="buo-veil" aria-hidden="true" />
```

The `data-visual-fixture` attribute on the shell hides the environment for
visual regression testing (Storybook).

## Colour profile

The asset renders behind a gradient veil (`buo-veil`) that transitions from
near-transparent at the top to the page background colour at the bottom. The
night-mode variant swaps the veil gradient to the dark page colour.
