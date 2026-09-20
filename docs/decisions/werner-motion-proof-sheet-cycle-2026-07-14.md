# Decision: freeze motion evidence outside production

The semantic reaction reel runs real one-shot animations. Lost Pixel captures
stories at three widths, so a live reel can record an arbitrary instant and
miss the evidence-bearing pose entirely.

Cycle 562 adds a Storybook-only contact sheet. It uses negative animation delay
plus `animation-play-state: paused` to expose the start, semantic beat, and
settled frame for every reaction. A fourth column renders the component's real
explicit reduced-motion state. Timings are data: settle uses the exported
canonical duration table and each semantic beat points to an existing authored
keyframe.

The review stylesheet is imported only by the story. Production component
props, runtime CSS, keyframes, event semantics, and bundle authority do not
change. This gives visual regression a stable proof surface without turning a
test convenience into product API.

The host may itself prefer reduced motion. Non-reduced proof cells therefore
restore only the existing named semantic tracks before pausing them; the fourth
column remains `data-reduced=true` and still exercises the real static fallback.
