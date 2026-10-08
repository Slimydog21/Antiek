# SPR-08 Revision — Highlight to pane, corrected (Kimi design lane, 2026-10-08)

Status: PROPOSED revision of `specs/antiek-keyboard-panes-agents-20261007/sprint-08-highlight-to-pane.html`. Published as an additive document; the sprint page owner adopts, adapts, or counters. Evidence for every correction: `.infinite/KIMI-SPEC-REVIEW-SYNTHESIS-2026-10-08.md` (SPR-08 grade 53/100).

The operator's core interaction — highlight a passage, an agent opens beside it holding that context — must be specced against the code as it is. The current page fails that in seven places. This revision replaces the defective decisions; milestones, rigor cards, and verifier lenses not contradicted below stand.

## R1 — Retract the Shift+Arrow premise; one selection, one floating affordance

The page's motivating claim ("Shift+Arrow produces no FloatMenu today") is false: `useFloatMenuSelection.ts` opens the FloatMenu on any `selectionchange` ≥3 chars with no pointer gate (`Reading/index.tsx:556`, `Write/Outline.tsx:214` both consume it).

Revised model: **selection origin decides the affordance, per selection epoch.**

- Pointer-originated selection → FloatMenu (unchanged, including its Ask action).
- Keyboard-originated selection (Shift+Arrows, Select-All-narrowed, vim-style) → the pill.
- The two never render for the same selection. The selection hook gains an origin tag (`"pointer" | "keyboard"`), derived from whether a pointer event participated in the current selection epoch (pointerdown since last empty selection). Acceptance: property test over mixed input sequences asserts exactly one floating affordance per epoch.

This makes the pill *necessary* (keyboard users currently get a mouse-shaped menu) rather than duplicative.

## R2 — The opener is `openAgentPane`; the kind is decided

The Goal's "call SPR-07's `openAgentFromDocument(anchor, scope)`" is wrong on three axes: the contract is SPR-06's (`contracts/openers.ts:77`), its signature is a single request object, and it *refuses* `kind:"dialogue" + scope:"project"` (`openers.ts:84`, `scope_kind_mismatch`). SPR-07's real path is `openAgentPane(input)` (`workspace/agent/openAgentPane.ts`), whose header documents exactly this.

Revised: highlight→Ask calls `openAgentPane({ scope: "project", anchor, draft: seededQuestion })` — the one open path, idempotent, already inset/fullscreen-aware. The `kind` is `"dialogue"` (the thought-partner run). When handoff F1(c) widens the frozen opener vocabulary, the call may move behind `openAgentFromDocument` with zero behavioral change — recorded, not required.

## R3 — The "Ask" key exists

A keyboard-first product cannot spec a pill with no keyboard path (J4b was unexecutable). Proposed rows, subject to the keymap census guard at implementation time:

- `prefix+shift+a` / `ctrl+alt+shift+a` — "Ask about the current selection": opens the agent pane with the anchor and focuses the composer. With no selection, falls back to `openAgentPaneFromKey()` behavior (plain project agent).
- The pill itself is focusable via the same key when a keyboard selection exists (it is the selection's affordance, not a mouse-only ornament), exposes `aria-keyshortcuts` from `ariaKeyshortcutsFor` (bindings.ts convention), and appears in the KeySheet via the keymap row — never as a parallel listing.

`prefix+a` / `ctrl+alt+a` are taken by #3756 (SPR-07 pane open); `prefix+w` by #3757; `prefix+shift+j/g` by #3758. The proposed keys were free on every in-flight head at review time; the census test proves it at implementation time.

## R4 — Escape goes through the arbitration, and does not eat the selection

The pill registers via `registerKeyboardOwner` (the merged one-Esc-one-handler discipline that FloatMenu.tsx:172-175 and ThreadIsland.tsx:139-146 already use). Rules:

- Esc with the pill open closes *only* the pill; the DOM selection survives (the pill must not call `removeAllRanges` — that is FloatMenu's behavior and it would destroy the passage the user is about to ask about).
- A second Esc falls through the existing chain (FloatMenu, then selection clear) unchanged.
- Acceptance: one-Esc-one-handler e2e over pill-above-FloatMenu-above-island stacks — the exact conflict class #3757 fixed for the switcher.

## R5 — Writer-inset placement: the agent joins the right pane as a tab; the outline stays

INBOX F7 recorded the blocker: `RightPaneForMode.tsx:40-56` renders the WriteOutlinePane whenever the mothership is writing, so the agent pane was unreachable in the writer. Decision, composing with C5 rather than replacing it:

- In Write mode the right pane is a *tabbed* surface: the outline is one tab (one tab per building block stays as specced in C5), and an agent opens as an adjacent tab in the same right pane — exactly how C5 already keeps agents "one keystroke away via the AI sidecar (mod+/)".
- Highlight→Ask in the writer opens/focuses that agent tab with the block anchor (`anchorFromWriterBlock`); the outline tab is untouched. No third surface, no overlay, no replacement.

## R6 — Unversioned is lawful; refusal needs identity, not version

Resolve the three-way contradiction in favor of the shipped contract: `anchor.ts` types `{kind:"unversioned", reason}` as a lawful `DocumentVersion` (`anchorFromWriterBlock` produces it for unpersisted prose). Revised rule:

- A pane may open with an unversioned anchor; the pane shows "unversioned — prose not yet saved" copy and the provenance label carries it.
- Refusal (with plain copy) happens only when *identity* is absent: no `nodeId`, or a range that no longer resolves against the mounted text. Version absence is a label; identity absence is a refusal.

## R7 — `data-quote-source-id` gets an owner: this sprint, milestone M0

The same-source check depends on `data-quote-source-id` attributes that nothing sets (zero hits on main and every in-flight head). Added as M0 of the revised sprint: mark quotable regions — reader page blocks in `Reading/index.tsx` and writer blocks via `Write/Editor/locator.ts` identity (`sectionId/outlineBlockId/paragraphIndex`). Without M0 the same-source adversarial lenses have no mechanism; with it they are executable.

## R8 — The visual link survives focus

The operator ties the pane to the highlight; the DOM selection visually clears the moment the composer takes focus. Revised: on Ask, the range gains a persistent, token-styled anchor mark (subtle underline-emphasis, day/night parity, reduced-motion still), visually keyed to the pane's chip (same accent index). Cleared when: the tab closes, the user clears it (`esc` chain endpoint), or the run is dismissed. Acceptance: after focusing the composer and typing a full turn, the mark persists and axe finds no contrast regression.

## R9 — Multi-span: refuse, don't guess

`AnchorRange` is single-range. A selection spanning blocks/chunks (either affordance) is refused with plain copy ("Ask about one passage at a time — its anchor stays exact") rather than silently anchoring the first chunk. The provenance rule prefers an honest refusal over a blurred anchor. Cross-chunk deep dives remain available by asking the pane without an anchor.

## R10 — The armed context fences continuously

The quote chip's admission fence (accountWorkspaceOwner epoch) is checked at open *and* subscribed for the armed lifetime: an epoch bump (account/workspace replacement) drops the armed context with a one-line notice. Once-at-open would let a stale quote ride a replaced identity; the subscription is three lines against the existing epoch source.

## Revised acceptance set (replaces M1–M5 acceptance where contradicted)

- [ ] One floating affordance per selection epoch, property-tested over mixed pointer/keyboard sequences (R1).
- [ ] `prefix+shift+a` with a selection opens the agent pane anchored and composer-focused; without a selection it degrades to the plain pane open; census-guarded keymap rows; KeySheet derives from the same row (R3).
- [ ] One-Esc-one-handler e2e across pill/FloatMenu/island stacks; Esc on the pill never clears the DOM selection (R4).
- [ ] Writer: Ask opens the agent as a right-pane tab beside the outline; the outline's tab and DnD state are byte-identical before and after (R5).
- [ ] Unversioned anchor → pane opens with "unversioned" copy; identity-less anchor → refusal copy; both pinned by test (R6).
- [ ] M0: `data-quote-source-id` present on reader blocks and writer blocks; same-source lens tests executable (R7).
- [ ] Anchor mark persists through a full composed turn; contrast parity gate passes day/night (R8).
- [ ] Cross-block selection → refusal copy on both affordances (R9).
- [ ] Epoch bump mid-arm drops the chip with notice (R10).

## What stands from the original page

The 2,000-char grapheme-safe quote cap with the emoji-boundary test, client-side quote verification against the servable text (honestly labelled interim for SPR-B), the same-source adversarial lenses, the admission-fence concept, and the rigor cards not contradicted above. The bones were good; this revision puts them on the code that actually exists.
