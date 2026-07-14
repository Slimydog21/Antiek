# `substrate/seams/` — where the four products intersect

antiek-unified **SPR-03**. The four workflows — Research (DRW), Read, Write,
Speak — are one product only if the handoffs between them are explicit, typed,
one-direction events that move **the same graph entity by reference**, never a
copy. This package owns those handoff contracts (the *seams*) and the
collision-fix enforcement that makes the boundaries the seams cross
unambiguous. It builds no product's internals — each product spec implements
its own side of a seam against the contract here.

## The flywheel

```
                     ┌──────────────────────────────────────────────┐
                     │                                                │
   research ──research→read──▶ read ──read→write──▶ write ──write→read──▶ read
      ▲                         │                      │                  (serve)
      │                         │                      │                    ▲
      └──── read→research ──────┘                      │                    │
            (Read SPR-08)                              │              speak→read
                                            speak→write│             (Speak SPR-09)
                                            (Speak SPR-08)                  │
                                                       ▼                    │
                                                     speak ─────────────────┘

         write→speak  (commission interviews from a node-backed outline question)
```

The flywheel is a **cycle of handoffs, not an auto-loop.** Each seam is an
explicit, terminating event a human or an explicit trigger fires.
`research→read→research` must never auto-recurse — a seam that fired its
successor automatically would be a runaway-cost bug. The invariant lives in the
*absence* of any successor field on a seam (and is documented by the fixed
`terminates: Literal[True]` marker every seam carries).

## The seven seams

| Seam | Direction | Carries (by reference) | Implements (from / to) | Status |
|---|---|---|---|---|
| `ResearchToReadSeam` | research → read | `insight_node` id | DRW SPR-01 / Read corpus | committed |
| `ReadToResearchSeam` | read → research | `document_region` ref | Read SPR-08 / DRW SPR-05 | committed |
| `ReadToWriteSeam` | read → write | `insight_node` id → node-backed block | Read / Write SPR-03 | committed |
| `WriteToReadSeam` | write → read | `outline_block` ref → source span | Write SPR-07 / shared reader (DRW SPR-10) | committed |
| `SpeakToWriteSeam` | speak → write | `speak_claim` id → synthesized block | Speak SPR-08 / Write SPR-01 | committed |
| `SpeakToReadSeam` | speak → read | `servable_entry` ref | Speak SPR-09 / Read corpus (seam #4 gate) | committed |
| `WriteToSpeakSeam` | write → speak | `question_node` id | Write outline / Speak interview guide | committed |

Each seam contract (`contracts.py`) carries four load-bearing fields:
**direction** (pinned, one-way), an **entity reference** (`entity_id` +
`entity_kind` — an id of a row the substrate already owns), a **provenance ref**
(the originating event/region/source), and the **terminating marker**. There is
no field that inlines the entity's content (a copy) or names a successor (an
auto-loop). Each seam emits a typed `seam.*` event
(`substrate/schemas/events.py`) through `substrate/event_log` →
`runtime/db_lock`, so a handoff is reconstructable from the trajectory and no
seam writes the graph directly off the critical path.

### The no-copy guard

`tests/test_seam_no_copy.py` is the load-bearing test. It exercises each
committed handoff with a fake implementing the SPR-01 contract and asserts the
entity on the receiving side references the **same node id** the sending side
held. A deliberate-copy fixture (`read_to_write_handoff_COPY`) **fails** the
guard — proving the guard distinguishes a real handoff from a fork. SPR-06's
thread navigation depends on this guard; SPR-08's e2e flywheel test composes it.

## The four collision resolutions

The same cross-read surfaced four substrate collisions the seams carry data
through. Each is pinned to **one greppable / named invariant** (rigor #5).

### #1 — Shared reading-surface ownership

**One owner: DRW SPR-10** (`substrate.contracts.reading_surface.ReaderSurfaceContract`,
currently **provisional** — DRW SPR-10 unbuilt). Read SPR-03 specializes by
composition; Write SPR-07 traces into it via the same contract; neither forks a
second reader. Until DRW SPR-10 lands, Read/Write compose against the
conformance-tested stub.
**Guard:** `tests/test_seam_reader_surface_contract.py` — "Read composes the
reader contract, never forks" (a fork dropping an extension point fails the
structural check).

### #2 — Single voice-pipeline owner

**One owner: `acquisition/voice/`** (`ingest_voice_note()` etc.). Read SPR-06 and
Speak SPR-02 both *call* it; neither builds a parallel capture→ASR→distill
pipeline. Read SPR-06's spec-page "reusable service" framing is **demoted to
"calls the existing service."** Contract: `substrate/contracts/voice_pipeline.py`.
**Guard:** `tests/test_seam_voice_single_owner.py` — exactly one `def
ingest_voice_note` (in the owner), and the owner is the only producer of
`document_type='voice_note'` documents.

### #3 — Single escrow writer

Two `attribution.py` concerns are fine (`ad_inventory/attribution.py` =
contribution weighting A/B/C; `marketplace_metrics` = impression→ip_holder);
two writers to the escrow ledger are not. The load-bearing fix is single-writer
discipline on the escrow **balance**. The single escrow-balance writer is
`substrate/ip_holders/__init__.py::accrue_escrow` (the only `SET
escrow_balance_usd = …` in the tree), reached today only from
`substrate/speak/contributor.py`. Both attribution concerns emit the single
`AccrualContract` shape; neither writes escrow. Accrual ≠ disbursement
(`disbursable` fixed `False`; G2+G3 gate disbursement).
**Naming nuance (honesty):** the ledger + master spec name
`marketplace_metrics/publisher_escrow.py` the "single escrow writer," but in the
live code that file *reports* escrow, it does not write it. The invariant the
ledger means — exactly one escrow-balance writer — holds and is what the guard
enforces; both files' docstrings now say so.
**Guard:** `tests/test_seam_single_escrow_writer.py`.

### #4 — `platform_authored`-from-Speak gating

`platform_authored` carries `provenance_class ∈ {operator_authored,
speak_derived}` (SPR-01 `ServableEntryContract`). A `speak_derived` document is
served full text only after Speak's publish gate passes; `operator_authored`
stays auto-servable (no Write-output regression). The seam-level adapter
`substrate/seams/servability_gate.py` translates Speak's publish outcome into
the single boolean Read consults — so Read stays uncoupled from Speak's models
(it calls a boolean / a `ConsentContract`, not `substrate/speak/` internals).
*Read's `serve.py` is unbuilt (Read SPR-01); this sprint owns the seam adapter,
Read SPR-01 owns serve.py and will call it.*
**Guard:** `tests/test_seam_platform_authored_gate.py` — "speak_derived docs hit
the publish gate" (a non-gate-passing speak_derived doc is NOT served).

## The committed `write→speak` seam

`WriteToSpeakSeam` commissions a private Speak interview project from a
node-backed open question in a Write outline. The command stores the original
question node id and outline reference. Speak resolves the question text from
that node when loading the interview guide, so the seam never copies the
question into a second record. The operator still chooses invitees and sends
links explicitly; the handoff never auto-fires an interview or widens publish
intent.

## Rejected alternative (fairness) — "each workflow owns its own seams"

The rejected design: no shell-owned seam contracts; each workflow defines its
own handoff shapes. It buys *less central coordination*. It loses because two
workflows then define the same handoff differently and the entity gets
copied/reshaped at the boundary — exactly the bug the no-copy guard catches. If
the operator wants minimal coordination, the seam contracts could shrink to
*just the no-copy guard + the four collision fixes* — but the typed contracts are
cheap and they are what make the SPR-08 conformance gate mechanical.

## What this package is NOT

Seam contracts + the two collision-fix adapters (`servability_gate`, and the
voice/reader/escrow guards' contracts). No product internals. The real
implementations — Read's `serve.py`, Write's editor, Speak's interviewer, DRW's
reading surface — live in the product sprints. Implementing a product's side
here would be the duplication the master spec's "integration, not duplication"
rule forbids.
