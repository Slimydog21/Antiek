# Tech-stack ledger — cross-cutting commitments (antiek-unified SPR-01)

**Decision date:** 2026-05-25
**Status:** ✅ Committed
**Owner:** operator + antiek-unified SPR-01

The four product specs (DRW, Read, Write, Speak) each left one or two
cross-cutting tech-stack questions open — the editor library, the voice
pipeline's owner, the escrow writer. A half-mapped stack leaves orphan
ownership that becomes a future divergence bug. This ledger commits each
cross-cutting layer to **exactly one canonical owner**, with the rationale,
the open question it closes, and the condition under which we'd reconsider.
The machine-readable form is `substrate/contracts/` (this sprint); the
master spec's "full tech-stack ledger" table is the human-readable index.

The rule that governs the whole ledger: **one owner per layer, every workflow
a consumer, never a fork.**

---

## Editor — TipTap (@tiptap/react 3, ProseMirror)

**Decision.** TipTap is the committed editor across notebooks *and* Write
authoring. Write SPR-04 inherits it; its deferral of the
ProseMirror/TipTap/Lexical choice is hereby closed.

**Rationale.** TipTap already ships for the notebook surface. Verified
against `docs/decisions/g4-lemon-ui-verdict.md`:

> The TipTap notebook editor + the Login surface + the PanelLayout shell all
> consume these primitives directly. No PostHog component is imported anywhere
> in the codebase.

Committing the editor already in the tree is the hard-to-vary choice —
consistency across notebooks and authoring beats a fresh evaluation that
re-litigates a decision the codebase has already made. One editor means one
block-citation model carrying provenance inline, shared by both surfaces.

**Closes.** Write SPR-04's editor-library open question.

**Reconsider if.** TipTap's block model proves unworkable for Write's inline
provenance citations — in which case the alternative is Lexical, but the
notebook surface would have to be re-spec'd too (the cost of divergence is
exactly what this commitment avoids).

---

## Voice pipeline owner — `acquisition/voice/` (seam #2)

**Decision.** `acquisition/voice/` is the single owner of capture → ASR →
distill (WhisperTranscriber, `webrtc.py`, `ingest_voice_note()`, TTS). Read
SPR-06 and Speak SPR-02 both *call* it; neither builds a parallel pipeline.
Read's "reusable service" framing is demoted to "call the existing service."

**Rationale.** Two capture→ASR→distill pipelines would drift and double the
maintenance surface for no benefit — the service already exists. The fix is
to forbid a second one, not to build a third. This resolves **seam #2** in the
master spec.

**Closes.** The Read-vs-Speak voice-ownership ambiguity (both specs assumed a
voice pipeline; neither named the owner).

**Reconsider if.** A workflow needs a capture mode the shared service
genuinely cannot express (then extend the owner, still not fork it).

---

## Single escrow-balance writer — `substrate/ip_holders/accrue_escrow` (seam #3)

**Decision.** Attribution modules that *compute* shares are fine to have more
than one (`ad_inventory/attribution.py` = contribution weighting; a future
`marketplace_metrics/attribution.py` = impression → ip_holder — note: only
`ad_inventory/attribution.py` exists in the tree today). But exactly **one**
function *writes* the escrow balance: `substrate/ip_holders/accrue_escrow`
(the only `SET escrow_balance_usd = …`), reached only from
`speak/contributor.py`. Both attribution concerns emit the single
`AccrualContract` shape (`substrate/contracts/accrual.py`); the balance writer
consumes it. `marketplace_metrics/publisher_escrow.py` is the read-only
*reporting* view (`compute_publisher_escrow → PublisherEscrowReport`), not a
writer.

> **Correction (post-SPR-03 verification, 2026-05-25):** the master spec and
> this ledger's first draft named `marketplace_metrics/publisher_escrow.py`
> "the single escrow writer." That was wrong — it is reporting-only. SPR-03's
> single-escrow-writer guard verified the live writer is
> `ip_holders.accrue_escrow`; the *invariant* (exactly one balance writer) is
> unchanged, only the named owner is corrected.

**Rationale.** Renaming an attribution module away is churn; the real risk is
two writers to the escrow ledger. Naming the single escrow writer is the
load-bearing fix — single-writer discipline applied to the ledger, mirroring
the DuckDB single-writer invariant. Accrual ≠ disbursement: the contract fixes
`disbursable=False`; money leaves escrow only via a path hard-gated on **G2**
(lawyer review) + **G3** (publisher opt-in). This resolves **seam #3**.

**Closes.** The "two `attribution.py` files" collision flagged across Read and
Speak.

**Reconsider if.** Escrow needs sharding by IP-holder (post-Series-A scale;
not now).

---

## Frontend stack — as-is

**Decision.** React 18 + TypeScript (strict) + Vite 5 + Tailwind 3 + the
custom Lemon-flavored design system (`apps/reading/src/components/lemon/`,
Werner skin) + Storybook + Playwright. No new framework; no PostHog package
import (per G4). SPR-04 reorganizes the *navigation* to four workflows; it does
not change the stack.

**Rationale.** The stack is live and shipping on prod. The four-workflow IA is
an information-architecture change, not a platform change. PostHog's 2025
*content-first pattern* transfers; its tone and its package do not (master-spec
§5.6).

**Closes.** Any implicit assumption in the product specs that the shell needed
a different frontend platform.

**Reconsider if.** Never for the framework within this product cycle; the
design system evolves continuously within the Werner brand bible.

---

## Codegen — `tools/codegen/` (the polyglot seam)

**Decision.** The Python Pydantic models are the single source of truth for
the TS types the frontend consumes. `tools/codegen/emit_types.py` emits event
types; `tools/codegen/emit_contracts.py` (added this sprint) emits the
`substrate.contracts` types to `apps/reading/src/generated/contracts.ts`;
`tools/codegen/check_staleness.py` fails CI on drift. Generated TS is never
hand-edited.

**Rationale.** Contracts that cross the Python↔TS boundary must not drift.
A `CONTRACT_SCHEMA_VERSION` (mirroring `EVENT_SCHEMA_VERSION`) ties the
generated TS to the contract package; the staleness gate makes a hand-edit or
a missed regen a loud CI failure rather than a silent divergence. Reuses the
existing event-codegen type-mapper rather than duplicating it (a sibling
emitter, not a fork of `emit_types.py`).

**Closes.** "How do the frontend types stay in sync with the contracts?"

**Reconsider if.** The TS side ever needs a richer type than the mapper
supports — then extend the mapper (it fails loudly on an unhandled type, by
design), never fall back to `any`.
