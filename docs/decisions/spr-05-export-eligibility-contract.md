# SPR-05 M1 — Synthesis-artifact export-eligibility contract

**Status: CONTRACT (M1 done) — M2–M5 implement against it.** This is the
document the operator's lawyer reads. It defines, per rights state, what may be
embedded (full text) in an exported synthesis artifact, what falls back to
cite-only, and what refuses the whole export. The rule it encodes is **reused,
not reimplemented**: the adapter calls the existing allowlist symbol, never a
private copy of the rights vocabulary.

## The reused allowlist (cite by path + symbol)

- **`substrate/constants.py:535` `SERVABLE_CONTENT_CLASSES`** — the embed
  allowlist: `{public_domain, user_owned, user_public_contribution,
  opt_in_licensed, source_declared_open}`. A claim's source document may have
  its **full chunk text embedded** in an artifact **iff**
  `document.content_class in SERVABLE_CONTENT_CLASSES`.
- **`substrate/constants.py:572` `PERSONAL_READING_CONTENT_CLASS`** =
  `"personal_reading"`, with the **import-time assertion** (`:605`) that it is
  NOT in `SERVABLE_CONTENT_CLASSES`. This is the §9.0 (Hachette / Bartz) fourth
  rights state: owner-readable, **never publicly servable**.
- **`substrate/graph/search.py:139`** — the read-side public chunk-search gate
  (`policy_tag="attribution_eligible"`) already excludes `personal_reading` and
  `restricted_pending_opt_in` from non-privileged reads. The adapter's filter is
  the **same allowlist** applied at export time.

**Why an export must filter even for the operator:** an exported artifact IS
serving — a file full of quoted third-party text travels beyond the operator
and out of the rights boundary. There is no operator-convenience bypass; that
bypass is exactly the §9.0 hole the Personal-Reading Lane closed.

## The contract table

| `content_class` | In an exported artifact | Basis |
|---|---|---|
| `public_domain` | **EMBED** (full chunk text) | ∈ `SERVABLE_CONTENT_CLASSES` |
| `user_owned` | **EMBED** | ∈ `SERVABLE_CONTENT_CLASSES` |
| `user_public_contribution` | **EMBED** | ∈ `SERVABLE_CONTENT_CLASSES` |
| `opt_in_licensed` | **EMBED** | ∈ `SERVABLE_CONTENT_CLASSES` |
| `source_declared_open` | **EMBED** | ∈ `SERVABLE_CONTENT_CLASSES` |
| `restricted_pending_opt_in` | **CITE-ONLY** (title + locator + `ip_holder_id`; body absent) | ∉ `SERVABLE_CONTENT_CLASSES` |
| `personal_reading` | **CITE-ONLY — never embed** | ∉ `SERVABLE` + the §9.0 fourth-state discipline (`:601-611`) |
| `NULL` / unrecognised | **CITE-ONLY** (deny-by-default) | ∉ `SERVABLE_CONTENT_CLASSES` |

"CITE-ONLY" = the SPR-03 `cite_block` widget renders a structured pointer
(document title, locator, resolved `ip_holder_id`) and the **chunk body text is
absent from the serialized doc-model entirely** — not merely hidden in the
rendered HTML. (The island would otherwise carry leaked text; the rights test
asserts on the doc-model, per the sprint's rigor #3.)

## Mixed-rights syntheses

A synthesis whose claims resolve to a mix of servable and non-servable
documents is the common case. The rule:

- **Per-claim fallback, NOT whole-artifact refusal.** Embed the servable claims'
  text; render the non-servable claims cite-only. The artifact ships (200) with
  the cite-only blocks **visibly marked** as cite-only.
- **Whole-export refusal (403 with a structured reason) only when the
  synthesis-level metadata itself is restricted** — i.e. the synthesis row's own
  visibility/rights flag denies export. The synthesis's own output (title,
  attribution manifest, skill/param versions) is operator-authored research
  (`user_owned`-equivalent) and is servable by default, so this is the rare
  case, not the common one.

## Ambiguity rule (rigor #2)

When a rights state's eligibility is ambiguous, **cite-only is the default** and
the ambiguity is surfaced to the operator — never embed-on-doubt. The absent
stakeholder is the IP holder; a beautiful artifact full of quoted third-party
text is a §9.0 leak with nice typography.

## What M2–M5 build against this

- **M2 adapter** (`services/html_projection/adapters/synthesis.py`): filtering
  happens IN the adapter (consumes this contract via `SERVABLE_CONTENT_CLASSES`)
  so no caller can bypass it by calling the renderer directly. Rights test
  asserts the restricted chunk text is absent from the **serialized doc-model**.
- **M3 route** (`GET /api/syntheses/{id}/artifact.html`): adapt → render →
  zero-script gate (`services/html_projection/gate.assert_script_free`, wired in
  the route path, not decorative) → download, or 403-with-reason on a
  synthesis-level restriction.
- **M4 provenance gate**: walk every claim's claim→chunk→document chain; render
  a "provenance incomplete — N of M claims fully sourced" banner rather than
  fabricated citation density.
- **M5 UI**: one "Export artifact" affordance in `apps/reading`, surfacing the
  403 reason honestly.

## Open question for the operator

Does any `syntheses`-row-level restriction flag exist today, or is
synthesis-level refusal (vs. per-claim cite-only) purely theoretical until such
a flag is added? M2 reads the live `syntheses` schema to answer this; if no
row-level restriction exists, whole-export refusal is wired but never triggered
until the flag lands, and that is recorded honestly rather than faked.
