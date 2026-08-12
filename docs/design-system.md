# Antiek frontend-craft design system

This document is the working design system for Antiek’s reading/research surfaces.
It is the house chrome that every HTML artifact wears, and the rules the style wheel
obeys when it re-skins an artifact without abandoning Antiek identity.

Companion thesis: [`html-first-design-thesis.md`](./html-first-design-thesis.md).
Implementation primitives: `apps/reading/src/components/lemon/`.
Tokens: `apps/reading/src/design/tokens.ts` + `tokens.css`.
Motion: `apps/reading/src/design/motion.ts`.

---

## 1. Core principles

### 1.1 Island pages

Research surfaces are **islands**, not infinite scrolls of chrome.

- A view is a clone of a document record; closing a view destroys geometry, never the record.
- Islands open, close, float, and compare. Two compare views of one document must both carry a full body.
- Every island is URL-addressable. The empty workspace serializes explicitly — never to `''` — so Back after a close restores state.
- Inside an island, prefer **container queries** over media queries. Viewport width is meaningless inside a resizable panel.

### 1.2 Tactile Lemon-style chrome

Controls should feel stamped, not sketched.

- **Offset shadow + hard sun-yellow outline** is the brand constant (`--sun` / `#F5DF24`).
- Hover lifts (−2px diagonal) and press sinks into the shadow. Shared primitive: `press` in `design/motion.ts`.
- Day mode: layered off-whites + glacials. Night mode: ten-layer off-black “majestic night sky”.
- Every Lemon primitive ships day **and** night from the first commit.
- No layout thrash: animate only transform, box-shadow, opacity. Honour `prefers-reduced-motion` by restoring state through **color**, never by leaving text invisible.

### 1.3 Honest state chips

Never launder uncertainty into smooth prose.

| State | Render as |
| --- | --- |
| Loading | Explicit “Loading…” role=status, not a skeleton that pretends content exists |
| Unavailable | Error colour **and** text: `Styles unavailable · <reason>` |
| Empty | Named empty (“Empty wheel”) with a next action, not a blank rail |
| Preview vs durable | Preview is temporary; Apply creates a versioned receipt (SHA-256 + version) |
| Builtin vs fork | Chip: `builtin` / `fork` |
| Source treatment | Chip: `source-first` / `house chrome` |
| Missing provenance | Local chip `origin untracked` — never a global disclaimer |

Honesty states that appear elsewhere in the product (`DANGLING`, `FLAKY (3/5)`, `NOT RUN`, `stale`, `superseded`, `conflicting`) follow the same rule: colour **and** text.

### 1.4 Provenance-first rendering

Every claim, style, and artifact version carries its origin close to the claim.

- Artifact receipts expose `X-Artifact-ID`, `X-Artifact-Style`, `X-Artifact-Version`, `X-Content-SHA256`. The client refuses mismatched receipts.
- Style wheel options show **Built in** vs **Your fork**, and when known, **from &lt;parent&gt;**.
- A missing source is a **local badge**, never a banner that washes the whole page.
- Corpus strings enter the DOM via `textContent` only — ledger lines and agent names are untrusted data.
- Embedded JSON must not contain a literal `<` byte: serialize then `.replaceAll('<', '\\u003c')`.

### 1.5 Brand-cast mascot discipline

- Werner (bill + feet match `sun.base`) is the cast when a mascot is warranted.
- Decline the mascot when the surface is utilitarian chrome (settings, style editor, status rails) — say so rather than paste a sticker.
- Never import PostHog trade dress, RoundHog/Squeak fonts, or mascot art. Transfer **mechanics**, not identity.

### 1.6 Density dictum

Research pages read like a research paper, not a landing page with copious whitespace.
Boldness is spent in **exactly one** place per surface; a second signature competes with the first and both lose.

---

## 2. Artifact styles: source philosophy + Antiek chrome

An artifact style is **not** a wholesale stylesheet swap.

```
[ Antiek structural base ]   tokens.TOKENS_CSS
        +
[ Theme override block ]     ProjectionStyle.theme_css
        =
[ Inlined artifact CSS ]
```

What the base always keeps:

- Block structure and reading measure primitives
- Provenance footer
- Hidden projection data island (enables deterministic restyle)
- Zero-script contract (no `<script>`, no external assets)

What a theme may re-skin:

- Typography face / size / rhythm
- Colour accents and paper tone
- Measure and indentation feel (paper / book / blog)

`source_fidelity=true` marks styles that deliberately lean into a source medium
(academic paper, book, blog). The Antiek base underneath still guarantees the
artifact is an Antiek artifact — “retain the source’s design philosophy **and**
retain core Antiek design philosophy,” made literal in CSS cascade order.

Every style, builtin or forked, is validated through the same zero-script +
external-asset gate the renderer’s output must pass. A user fork cannot smuggle
script into the reader.

---

## 3. The style-wheel model

Backend: `interfaces/research/api/style_routes.py` + `substrate/styles/store.py`.
Frontend: `apps/reading/src/modes/ResearchWorkstation/StyleWheel.tsx` +
`apps/reading/src/api/styles.ts`.

| Verb | Route | UX |
| --- | --- | --- |
| Browse wheel | `GET /styles` | Horizontal rail of builtins (fixed order) + caller’s forks |
| Preview | `GET /artifacts/{id}/render?style=` | Side-effect-free blob preview in a sandboxed iframe |
| Apply | `POST /artifacts/{id}/render?style=` | Durable version + receipt (version, style, SHA-256) |
| Create / replace fork | `POST /styles` | Fork form seeded from selected style; builtins 409 if name collides |
| Delete fork | `DELETE /styles/{name}` | Two-step confirm; builtins 409; unknown 404 |

Rules the UI must honour:

1. **Builtins are anchors.** They cannot be deleted or overwritten. Fork under a new slug.
2. **Forks are untrusted input.** Theme CSS is gated; failures surface the server `detail` string, not a generic toast.
3. **Preview ≠ apply.** Preview is temporary (`X-Artifact-Version: preview`). Apply creates a versioned HTML under the artifact store.
4. **Determinism.** Restyle is pure presentation: `render(extract_island(artifact), style=X)` — no model call.
5. **Provenance of forks.** The API does not yet persist `parent_style`. The wheel tracks seed parent **session-locally** when the operator forks from a selected style, and labels reloaded forks as `origin untracked` rather than inventing a parent.

### 3.1 Wheel interaction craft

- Rail is a horizontal `listbox` with arrow / Home / End parity and vertical-wheel → horizontal scroll when focused.
- Option cards use the Lemon ledge (offset shadow, selected edge in ocean).
- Provenance chips sit under the active description, not inside the preview iframe.
- Empty and unavailable are distinct states with distinct copy.

---

## 4. Lemon primitive inventory

| Primitive | Job |
| --- | --- |
| `LemonButton` | primary / secondary / tertiary / danger · sm/md/lg · shared `press` |
| `LemonCard` | elevation 1–3 surfaces |
| `LemonModal` | portal dialog, ESC + outside-click, hand-rolled focus trap |
| `LemonInput` | single-line, optional kbd hint chip |
| `LemonTextarea` | auto-grow, Cmd+Enter submit |
| `LemonTag` | status / provenance chips |
| `LemonSelect` / `LemonDropdown` | option popovers |
| `LemonTable` | generic list/table |
| `LemonToast` | top-right queue |

Rules for new primitives:

1. Colours/shadows only from design tokens — never inline hex.
2. Paired `*.stories.tsx`.
3. Strict-TS clean. No `any`. No `@ts-ignore`.
4. Day + night from day one.
5. Default border is brand sun.

---

## 5. Do’s and don’ts

### Do

- Spend the aesthetic risk once; keep the rest quiet hierarchy.
- Name empty, loading, error, and partial states in the UI copy.
- Keep artifact previews script-free (`sandbox=""`) and revoke blob URLs on replace/unmount.
- Abort in-flight preview/apply when the selected style or artifact changes; ignore stale responses.
- Prefer exact file:line and exact error text in operator-facing receipts.
- Match surrounding Lemon idiom when extending ResearchWorkstation surfaces.

### Don’t

- Don’t replace the Antiek structural base with a theme — append, don’t overwrite.
- Don’t promote a weaker honesty state into smooth success copy.
- Don’t invent parent-style provenance the backend did not store.
- Don’t put theme CSS on the render query string; CSS stays in the `POST /styles` body.
- Don’t ship a second mascot, a second accent system, or a second shadow language on the same surface.
- Don’t use media-query breakpoints inside resizable islands when container queries will do.
- Don’t commit, push, or deploy as a “finishing touch” of a design pass — distribution is an operator act.

---

## 6. Verification discipline

A structural pass and a rendered pass are different proofs.

For the style wheel specifically:

1. `npx vitest run src/modes/ResearchWorkstation/StyleWheel.test.tsx src/api/styles.test.ts`
2. `npx tsc --noEmit` in `apps/reading`
3. Manual: keyboard rail, fork → apply → receipt hash, delete confirm, reduced motion

Report what was not proved (geometry in a real browser, print, theme toggle under night tokens) rather than claiming “production ready.”

---

## 7. Related docs

- [`html-first-design-thesis.md`](./html-first-design-thesis.md) — why every artifact is HTML
- [`craft_signature.md`](./craft_signature.md) — the performance craft signature (rubric p95)
- [`design/physics-of-reading.md`](./design/physics-of-reading.md) — reading geometry
- `apps/reading/src/components/lemon/README.md` — primitive catalogue
- `services/html_projection/styles.py` — ProjectionStyle + builtin wheel
