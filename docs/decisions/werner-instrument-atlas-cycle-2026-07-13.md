# Werner instrument atlas cycle — 2026-07-13

## Decision

The complete fixed-station cursor grammar has one Storybook-only review desk.
It renders the four registered instruments through their real activity
components, mounts the real Werner station required by fishing geometry, and
states each instrument's job and deliberately withheld authority in selectable
HTML.

No production activity, component, CSS, registry, route selection, taxonomy,
shell, mascot, reaction, audio, game, generated runtime asset, network, or spend
surface changed.

## Lifecycle contract

- The atlas mounts exactly one enabled instrument at a time.
- Research/Read uses the lens, Write uses the nib, Speak uses resonance, and
  shared/unknown uses ice fishing when its production feature flag permits it.
- Reduced motion mounts no custom instrument and preserves the native cursor.
- A disabled fishing flag mounts neither bait nor line and preserves the native
  cursor.
- Writing and speaking activity markers are removed when selection or route
  ownership changes.
- Fishing renders beside the real `PenguinMascot`; its line reads the mascot's
  actual rectangle rather than a shadow station model.

## Adversarial sharpening

Independent Codex review found and drove fixes for four proof and policy gaps:

1. The first atlas bypassed reduced-motion and fishing-flag policy.
2. The fishing instrument lacked the real mascot geometry needed by its line.
3. The first fallback assertion changed behavior with the ambient environment
   instead of testing deterministic flag-on and flag-off cases.
4. The first geometry assertion could match a Werner rig path; the final test
   uniquely targets the fishing-layer path, asserts `getBoundingClientRect` was
   consumed, advances a live pointer frame, and requires non-empty line data.

The final independent verdict is **ACCEPT**.

## Verification

- Focused/coupled behavior: 10 files, 111 tests, 0 failed.
- Atlas/transition contract: 5 deterministic cases, including flag on/off,
  reduced motion, four selections, marker cleanup, and real fishing geometry.
- TypeScript typecheck: passed.
- Token lint: passed; no new hardcoded hex.
- Type-scale lint: passed; no oversized chrome type.
- Storybook production build: passed; atlas emitted as a distinct story asset.
- Reading production build: passed; no production runtime source changed.
- `git diff --check`: passed.
- Hardenx strict: LOW, 0 REAL findings; unrelated repository advisories only.

The builds retain pre-existing dependency `eval`, bundle-size, and mixed
static/dynamic import warnings. No dependency or lockfile changed.

## Unproven acceptance

Live appearance remains **NOT PROVEN** because the in-app browser runtime was
unavailable. A later live pass must inspect all four atlas selections, native
cursor restoration, dark mode, reduced motion, fishing flag off, real Werner
placement, and the cursor hotspot at multiple viewport sizes.

## Transport boundary

This slice stacks from PR #2060. It is not merged or deployed by this cycle.
