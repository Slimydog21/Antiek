# Werner dawn waking beat — Cycle 574

## Decision

The sole derived scene mood authority emits one typed cue only for a committed
`night → dawn` transition. AppShell transports that cue without reading time or
theme. The existing PenguinMascot consumes it at most once and renders the
existing authored waking pose for the existing 900 ms waking duration.

## Foreground authority

The dawn beat is subordinate to product emotes, direct manipulation, directed
travel and return, product-surface station suspension, and true long-rest
waking. It outranks sleeping and ambient station behavior. Reduced-motion users
receive the same bounded semantic pose without animation.

Cue completion is sequence-qualified, so a stale callback cannot clear a newer
cue. Unmount clears the timer without firing a post-unmount callback.

## Rejected drift

- No second mascot, scene clock, media listener, event bus, or rest state.
- No new bitmap. The validated waking asset already has the required authored
  meaning; a variant would split Werner's visual authority.
- No change to station position, cursor behavior, Krea, palette, network, or
  spend paths.

## Evidence

- Production reading build: green.
- Focused Vitest: 5 files, 48 tests, green.
- TypeScript and diff checks: green.
- HTML sprint/index structure checks: green.
- hardenx 1.4.0 strict: LOW, 0 real findings; corpus certification unavailable.
- PR #2102 implementation commit `efc7b6d4f7415029c50c14ac5233478969261193`
  is locally qualified; its documentation tip awaits four remote checks.

## Honest gaps

The repository-wide suite remains non-green from pre-existing localStorage,
motion-guard, notebook-hydration, and hotkey harness failures. Two independent
Codex read-only review attempts inspected the diff but failed to emit a terminal
verdict after their sandbox spent the rollout on macOS git/Xcode cache errors.
Neither is counted as approval.
