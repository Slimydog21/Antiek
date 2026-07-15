# Scene bounded dayparts — Cycle 572 decision

The Mountain Shell has four daypart scene keys and deterministic seeded compositions, but production reads `prefers-color-scheme` only during render and emits only day/night. The new authority repairs reactivity and activates dawn/dusk semantics without claiming solar knowledge. Procedural dawn/day and dusk/night still share their OS band's colour ramp; distinct transitional ramps require a separate reviewed art-direction change.

- OS color scheme remains sovereign: light can produce dawn/day; dark can produce dusk/night.
- Dawn is the branded ambience window `[05:30, 08:00)` local civil time; dusk is `[17:00, 20:00)`. Outside those bounded windows the current OS band resolves to day or night.
- These are art-direction values, not sunrise/sunset. A manually pinned theme may intentionally disagree with wall time.
- One semantic hook subscribes theme changes and owns at most one boundary timeout. Every signal recomputes from a fresh `Date`; hidden tabs cancel, return recomputes, and unmount tears down.
- Animation time remains in `useSceneClock`. Reduced motion never freezes semantic time.
- A mount-time explicit `Scene mood` is fully deterministic and creates no derived subscription. Switching authority at runtime is unsupported because the component split remounts the scene substrate.
- Within a mounted production authority, a real derived mood-key change invokes the existing Krea effect once. React development StrictMode may probe that pre-existing effect twice. This can add bounded automatic requests, but no endpoint, retry, cap, kill switch, or budget policy changes.

Rejected: a single upper threshold (02:00 becomes dusk), wall-clock light/dark authority, geolocation/astronomical sunrise, intervals/rAF polling, and running unused subscriptions under explicit overrides.
