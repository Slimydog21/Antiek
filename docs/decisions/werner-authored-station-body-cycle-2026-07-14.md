# Werner authored station body — cycle decision

Date: 2026-07-14
Sprint: WERNER-ACT SPR-24

## Decision

Ship an exact canonical-derived station crop inside the existing private
`WernerAuthoredPose` vocabulary. Keep the 64 px hitbox and the rod contract at
butt `(45,34)` and tip `(66,5)`. Paint the rod behind the body, paint the
line/fish marks in front, and remove the redundant vector feet and flippers.

The generated ChatGPT Image candidate was rejected because it changed Werner's
face, beak, body proportions, and feet. This cycle uses ChatGPT Image as an
evaluated design instrument, not as authority to overwrite canonical identity.

## Proof

- Runtime alpha bounds resolve to 40.5 × 55 px at the native 64 px station,
  with transparent borders and attached feet ending at 57.94 px.
- The rig has exactly three paint layers and one accessible wrapper.
- Eighteen rig tests plus the wider five-file, 57-test mascot suite pass.
- TypeScript, production build, Storybook build, scoped Lost Pixel at
  768/1024/1280, and diff checks pass.
- HardenX strict reports LOW with 0 REAL findings.

## Review honesty

The OpenAI CLI reviewer inspected the diff, assets, motion wiring, and reran the
18-test rig suite, but its rollout produced no terminal verdict. GLM-CC
`/ultracode` at maximum effort failed with HTTP 429. These are recorded as
review and engine gaps; neither is represented as an approval.

## Withheld authority

No fifth mood, new mascot, hitbox increase, behavior change, provider runtime,
network spend, merge, or deployment is authorized by this decision.
