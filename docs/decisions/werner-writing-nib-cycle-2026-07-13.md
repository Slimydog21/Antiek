# Werner writing nib cycle — 2026-07-13

## Decision

Write and Create routes use a brass fountain-pen cursor instrument selected
from the canonical workflow taxonomy. Werner remains fixed at his station. The
working document remains ordinary HTML; the generated alpine scriptorium is
versioned design evidence only.

`/brainstorm` remains Research and therefore retains the research lens. Unknown,
shared, and Speak paths retain ice fishing. No new route catalog, settings
state, product authority, network call, navigation, content inspection, or
spend seam was introduced.

## Product translation

- `writingNibActivity` is the third ordered station activity; ice fishing stays
  the default.
- `activityIdForPathname` maps taxonomy workflow `write` to `writing-nib` before
  the existing Research/Read and default branches.
- `WritingNibCursor` reads only live pointer, idle, and hidden-tab state through
  `useMouseFollow`; it captures no events and is absent under reduced motion.
- The nib point is bottom-center anchored to the true interaction hotspot.
- While the writing activity is mounted, one scoped root marker suppresses
  explicit descendant and mascot cursors. Its cleanup restores the existing
  fishing-specific Werner grab exception on route change or unmount.
- The Storybook scriptorium uses real selectable HTML. The generated PNG is not
  imported by runtime code.

## Generated evidence

- Asset: `docs/design-evidence/werner-writing-scriptorium-v1.png`
- Dimensions: 1672 × 941 px
- SHA-256: `c0a127f4df719c5abc90e5daa56e5368374cfb7f948622fd70d41063849a8ad4`
- Generator: ChatGPT Image, with the canonical transparent Werner anchor as the
  character-identity reference.
- Authority: mood/composition evidence only; no behavior, content, provenance,
  accessibility, or product-data claim.

## Verification

- Focused and coupled behavior: 5 files, 86 tests, 0 failed.
- Writing nib sharpen regression: 3 files, 12 tests, 0 failed.
- TypeScript project typecheck: passed.
- Token lint: passed; no new hardcoded hex.
- Type-scale lint: passed; no new oversized chrome type.
- Motion guard: 1 file, 1 test, passed.
- Storybook production build: passed and emitted the writing-nib story/CSS.
- Reading production build: passed.
- `git diff --check`: passed.
- Hardenx strict: LOW, 0 REAL findings. Existing unrelated advisory findings
  remain advisory; no dependency or secret-bearing file changed.

Build output retained pre-existing Storybook dependency `eval` and bundle-size /
static-plus-dynamic import warnings. They are not introduced by this slice.

## Independent criticism and repairs

Codex merge-bar review found and caused two repairs:

1. The original visual nib point was displaced from the native click hotspot.
   The point is now bottom-center anchored before rotation.
2. Explicit descendant cursors and Werner's fishing grab exception could render
   a second native cursor. Suppression is now scoped to a cleaned-up
   `werner-writing-nib-active` marker and mechanically pinned in tests.

The final Codex reread reported no functional regression. GLM-CC acknowledged
the requested `/ultracode` mode but twice exited without repository evidence;
GLM-Codex later hung and was terminated. Neither is counted as a verdict.

## Unproven acceptance

Live appearance remains **NOT PROVEN**. The in-app browser had no available tab
or target during this cycle, so compilation and DOM tests are not promoted into
visual screenshot evidence. A follow-up visual pass must inspect Write/Create,
text selection, draggable blocks, Werner hover, Research/brainstorm, route
transitions, dark mode, and reduced motion in the in-app browser.

## Collision record

The shared dirty checkout and its reaction bus, shell signals, arcade, hotspots,
session assets, generated runtime poses, workflow taxonomy, navigation, content,
network, and spend surfaces were left untouched. This slice is stacked from PR
#2049 and does not authorize merge or deployment.
