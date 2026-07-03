# AFA-S4 — the escrow double-credit surface + payable ad-attribution path

**Date:** 2026-07-03
**Sprint:** antiek-frame-attribution SPR-04 (ledger reconciliation), M1+M3
**Status:** FINDING recorded + one **operator/architecture decision** escalated
(the agent cannot decide which ad-attribution mechanism is canonical).
**Author:** /infinite ads lane (Opus 4.8), grounded in `origin/main@f4503b0b`.

## The verified topology (corrects the sprint's "three payable ledgers" premise)

The sprint page framed three payable ledgers with a "no cent in two" invariant.
Read against the machine, that framing is wrong in a way that matters — and a
first draft of THIS doc miscounted the writers (said "two"); a fresh adversarial
review (verifier-critic, 2026-07-03) corrected it to five. The verified picture:

- **Escrow — the single payable balance — has FIVE application-level writers**,
  all routing through the one low-level writer
  `substrate/ip_holders/__init__.py::accrue_escrow:158` (seam #3, enforced by
  `tests/test_seam_single_escrow_writer.py::_SANCTIONED_ESCROW_CALLERS` and grep
  of live `accrue_escrow(` call sites):
  1. **`substrate/ad_inventory/frame_attention_accrual.py:421`** — AD revenue,
     **per-frame, attention-weighted** (SPR-05/07 + AFA-S1/S2): a window's ad
     value apportioned across in-frame assets by measured attention, written to
     the `frame_attention_accruals` **table**, then `accrue_escrow`.
  2. **`substrate/marketplace_metrics/book_escrow.py:259`** — AD revenue,
     **per-reading-session** (SPR-09): `accrue_reading_session` distributes a
     session's ad revenue to the book's `ip_holder_id`, `accrue_escrow`, and
     emits a typed **event** carrying `amount_usd_cents` (no per-accrual table).
  3. `substrate/speak/contributor.py:310` — Speak **contributor split** revenue
     (interview contribution), NOT ad revenue.
  4. `substrate/ip_holders/gated_accrual.py:51` — **gated corpus-ingest** accrual
     (an in-copyright work gated at ingest seeds its pre_onboarded holder), NOT
     ad revenue.
  5. `substrate/ip_holders/opt_in_accrual.py:45` — **publisher opt-in seed**
     accrual (§9.10 intake), NOT ad revenue.
- **Only writers 1 & 2 are AD revenue** — they are the double-credit pair (below).
  Writers 3–5 are distinct revenue sources (contribution / ingest / opt-in seed);
  they legitimately add to the same balance for the same holder and are NOT a
  double-count of the ad paths. But the reconciliation MUST sum all five, or a
  holder that received a Speak/gated/opt-in accrual is falsely flagged.
- **`paper_author_accruals` (`substrate/payouts/ledger.py`) is NOT an escrow
  writer** — its own docstring (`:19`) states it "NEVER calls
  `ip_holders.accrue_escrow`." Attribution-only audit ledger (per-author arXiv
  shares + `UNATTRIBUTED_RIGHTS_BUCKET`); a red herring for the payable-double-
  count question, reconciles only for attribution completeness.
- `book_escrow.py` has **no table of its own** (`0` `CREATE TABLE`); it is a
  module that accrues escrow and additively feeds the attribution ledger
  (`_accrue_payouts_ledger` → `accrue_paper_read`, which writes no escrow).

## The real risk: two ad-attribution mechanisms, one escrow balance

The double-credit risk is narrowly between the **two AD-revenue writers** (1 & 2
above) — the other three writers are distinct revenue and do not double-count
the ad paths. The two ad writers attribute the same category (ad revenue) by two
different models:

| | Frame path (newer) | Reading-session path (older, SPR-09) |
|---|---|---|
| Unit | per-second, per-in-frame-asset | per reading session, per book |
| Weighting | measured attention (area × prominence × dwell) | session ad-revenue distribution |
| Audit trail | `frame_attention_accruals` **table** (queryable) | a **typed event** (`amount_usd_cents`) — no per-accrual table |
| Trigger | `POST /api/ad/frame-telemetry` | `books.py:606` → `accrue_reading_session` |

If both fire for the **same ad revenue on the same reading surface** — a book
read that both (a) drives per-second frame attention and (b) closes a reading
session that distributes that session's ad revenue — the same underlying dollars
credit escrow **twice** for the same `ip_holder`. This is safe today only because
nothing disburses (accrual-only, `disbursable=False`, gated on G2/G3); it becomes
a real overpayment the moment disbursement opens.

## The decision the operator must make (agent cannot)

**Which ad-attribution mechanism is canonical — and is the other superseded?**
This is an architecture/product call, not an agent's:

- **Option A — frame supersedes reading-session.** The per-frame pipeline (AFA)
  is the go-forward ad-attribution model; `book_escrow.accrue_reading_session`'s
  escrow write is retired (or demoted to reporting), so only the frame path
  credits escrow. Cleanest "one payable truth"; requires confirming no surface
  depends on the session distribution.
- **Option B — they are complementary (different revenue events).** If the
  session distribution and the frame attention represent **distinct** ad-revenue
  events (e.g. a sponsorship vs. per-impression), both legitimately accrue and
  there is no double-count — but that must be **proven**, not assumed, and the
  reconciliation (below) must then verify they never share a revenue event.
- **Option C — both stay, guarded by reconciliation.** Keep both, and gate
  disbursement on the reconciliation proving no shared-revenue double-credit.

The recommendation, on hard-to-vary grounds: **Option A** unless Option B is
proven — two mechanisms crediting one balance from overlapping surfaces is
exactly the kind of swappable-without-loss duplication that should be cut, and
the frame pipeline is the auditable, per-driver model the operator asked for.

## What the reconciliation (S4-M4) must do once the path is decided

A read-only checker, per `ip_holder` over a period, must sum **all five**
sanctioned writers (not just the two ad paths — omitting writers 3–5 would
FALSELY flag any holder with a Speak/gated/opt-in accrual):

    escrow_balance(holder) ==  Σ frame_attention_accruals            (writer 1)
                             + Σ reading-session ad-revenue events   (writer 2)
                             + Σ Speak contributor accruals          (writer 3)
                             + Σ gated-ingest accruals               (writer 4)
                             + Σ opt-in seed accruals                (writer 5)

Equality is CONSISTENT. A balance **exceeding** the tracked sum is a double-credit
or orphan signature. The specific **ad double-credit check** is narrower: does a
single ad-revenue event credit BOTH writer 1 and writer 2 for the same holder?
**Reconciliation-readiness gaps** to fix first: (a) the reading-session path has
no queryable per-accrual **table** (only a typed event), so summing writer 2
means reading the event log — writer 1's table is directly summable; (b) writers
3–5 each need their per-accrual sum to be queryable too (verify each leaves a
table or event before relying on the reconciliation). If Option A is chosen
(frame supersedes reading-session), writer 2 leaves the ad-double-credit picture,
but the five-writer balance reconciliation still stands.

## Reconsider-if

- A surface is found that genuinely depends on `book_escrow`'s session escrow
  distribution as a distinct revenue event (→ Option B, with proof).
- Disbursement gates (G2/G3) approach opening — at which point the reconciliation
  becomes a hard pre-disbursement gate, not a guard.
