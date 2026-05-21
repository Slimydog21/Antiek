# `src/components/lemon/` — PostHog-Lemon-style primitives

Custom-built primitive components in the visual language of PostHog's Lemon UI
(chunky offset shadows, hard sun-yellow outlines, stamp-printed feel) — but
built in our own Tailwind + strict-TS world, **not** the
`@posthog/lemon-ui` npm dependency.

S0 leaves this directory empty. S1 lands the primitives:

- `LemonButton.tsx`   variants: primary / secondary / tertiary / danger
- `LemonCard.tsx`     elevation 1 / 2 / 3 + colour variants
- `LemonModal.tsx`    layered modal with backdrop; used by workspace popouts
- `LemonInput.tsx`    text + search, with `kbdHint` slot
- `LemonTextarea.tsx` autogrow textarea (used by ChatInputArea later)
- `LemonTag.tsx`      pill chip
- `LemonSelect.tsx`   custom select with options popover
- `LemonDropdown.tsx` renderless trigger + popover
- `LemonTable.tsx`    list/table component, generic over row type
- `LemonToast.tsx`    top-right toast queue
- `index.ts`          barrel export

## Rules

1. Every component consumes colours/shadows from `src/design/tokens.ts` —
   **never** inline hex.
2. Every component has a paired `*.stories.tsx` in this directory.
3. Every component is strict-TS clean. No `any`. No `@ts-ignore`.
4. Every component ships in both day **and** night mode from the first commit.
5. The brand outline colour (`sun`, `#F5DF24`) is the default border on every
   primitive. Borders that need higher contrast on white use `sun-deep`.

## Full spec

`docs/ui_redesign_posthog/sprint_01_design_system.html`
