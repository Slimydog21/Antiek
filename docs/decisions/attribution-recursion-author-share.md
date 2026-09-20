# Attribution recursion — the author share, the depth cap, and the version contract

**Date:** 2026-09-20
**Sprint:** ads-settlement-and-attribution-recursion SPR-2
**Status:** BUILT (telemetry only). Three decisions recorded; one OPERATOR gate still open.
**Code:** `substrate/attribution/recursion.py`, `tests/test_attribution_recursion.py`
**Sibling:** `docs/decisions/afa-synthesis-attribution-canonical.md` (the §9.3 divergence
this lane had to build around)

## What changed

Before this, a synthesis was attributed as a single asset. A second spent reading it
landed wholly on the synthesis, and the writers whose documents grounded it saw none of
it. The operator's thesis is the opposite: attention is metered per second and
distributed "to the core data owners of who created the asset being viewed, that is
mostly the writers whose data was sourced, combined with the contributions of the writer
themselves who added new ideas."

`split_attention()` now walks the provenance chain that already existed — claim cites
chunks, chunk cites a document, document carries an `ip_holder_id` — and splits one
metered attention-second across every sourced holder, the author, and an explicit
unattributed remainder. No new store. The share vector comes from the existing §9.3
producer (`compute_attribution_for_synthesis`); this lane adds only the recursion on top
of it.

Nothing moves money. §9.0 is open, accrual is not disbursement, and this is not even
accrual — `tests/test_attribution_recursion.py` asserts the boundary two ways rather than
trusting the convention: the module contains no money-path vocabulary in executable code,
and computing a split against a real DuckDB leaves every escrow balance untouched with no
accrual row written.

## Decision 1 — the author share is a fixed versioned constant, at 0.30

**Live:** `AUTHOR_SHARE_FIXED = 0.30`, stamped on every split as
`AUTHOR_SHARE_POLICY = "author-share-fixed-30-v1"`.

**Rejected for now: a share proportional to non-quoted-span length.** The spec prefers it
and so do I; it is the more principled measure, because what a writer added is exactly
what is not quoted. It needs the five-way epistemic typing — quotation / paraphrase /
measurement / inference / synthesis — on each claim.

That typing is not merely unpopulated. `ThesisComponent` (`substrate/schemas/events.py`)
declares `model_config = ConfigDict(extra="forbid")` and carries no field for it, so no
synthesis in the tree can hold the data even if a synthesizer emitted it. Building a
share on a field that cannot exist would have produced a function that always returns the
same answer, which is worse than a constant because it looks like a measurement.
`test_fixed_author_share_is_live_because_epistemic_typing_cannot_exist_yet` is the
tripwire: it fails the day someone adds the typing and points here.

**Why 0.30 rather than some other number.** It is a convention, not a measurement, and it
is the most contestable number in the lane — which is why it is one named constant behind
one version rather than an expression scattered through the walk. It is bounded above by
the operator's own word: a second goes to the data owners *mostly*, so the author's leg is
a minority, under 0.5. It is bounded below by the fact that a synthesis whose author earns
a rounding error is not a product anyone writes for. 0.30 sits where those two bounds
leave room. It coincides in shape with the 70/30 platform split in
`ad_inventory/payout.py`; that is a coincidence noted because it makes the number easier
to argue about, not a derivation of it.

**Measured, not priced.** Each provenance snapshot records `claim_count` and
`path_only_claim_count` — claims grounded in `supporting_path_indices` with no cited
chunk, which is the substrate's closest structural evidence today of a contribution that
is not sourced material. Those counts price nothing. They exist so the operator can see,
on real syntheses, whether a principled author share is viable *before* anyone rewrites
the constant. Measurement before mechanism.

**Rejected outright: deriving the author share from the path-only ratio right now.** It
would collapse to zero for any synthesis whose claims all cite chunks, which is most of
them, and zeroing the author leg directly contradicts the thesis this lane exists to
serve.

## Decision 2 — depth is capped at 3, and the remainder is a line, not a silence

`MAX_RECURSION_DEPTH = 3`. A synthesis citing a synthesis recurses; past the cap, the
units that would have gone deeper become an `unattributed` line with reason `depth_cap`.
A cycle (`syn-a → syn-b → syn-a`, or a self-citation) terminates the same way with reason
`cycle_detected`. Neither case can loop and neither can lose units.

Three levels covers a synthesis built on syntheses built on sources. Past that the
provenance is too diluted for a per-second credit to mean anything, and an uncapped walk
over a graph that can contain a cycle is an outage rather than a feature.

Every early exit in the walk emits a line for its whole budget, so conservation holds by
construction rather than by a reconciliation step afterwards. Shares are integer units
(`UNITS_PER_ATTENTION_SECOND = 1_000_000`), apportioned by largest remainder, so a split
sums to exactly one second — "sums to 1.0 modulo float rounding" is not a property anyone
can defend in a payout dispute.

**Honest scope on depth.** Nothing in the tree deposits a synthesis back into `documents`
today, so the live depth is 1 and `DisplayGatedProvenanceResolver` finds no nested
syntheses in production. The cap and the cycle guard are exercised against an injected
resolver, and arm themselves the moment a depositor exists. They were built now rather
than deferred because the cap has to be inside the versioned contract before the first
priced row, not bolted on after rows exist.

## Decision 3 — a new version constant, NOT a bump of `ATTRIBUTION_ALGORITHM_VERSION`

The spec says to bump `ATTRIBUTION_ALGORITHM_VERSION`. I did not, deliberately.

That constant versions the §9.3 A/B/C *share math* and stamps the durable audit rows
`attribution_audit.record_attribution` writes. This lane does not touch that math. Worse,
`docs/decisions/afa-synthesis-attribution-canonical.md` reserves its next bump for the
Option-C unification of the two divergent §9.3 implementations — a math-identity change
the operator has still to ratify. Spending the bump here would consume exactly the signal
that decision needs, and would mark future audit rows as a new math generation when the
math had not moved. Rows already recorded stay on their own version; nothing is
recomputed.

So a split stamps three independently-movable versions, because three independently
changeable decisions price it:

| stamp | versions | constant |
| --- | --- | --- |
| `recursion_version` | the walk: author/source split, depth cap, remainder rules, tie-break | `ATTRIBUTION_RECURSION_VERSION = "attr-recursion-v1"` |
| `author_share_policy` | how much of a second is new ideas | `AUTHOR_SHARE_POLICY = "author-share-fixed-30-v1"` |
| `share_algorithm` + `share_algorithm_version` | which §9.3 vector it apportioned across | `ATTRIBUTION_SHARE_MATH_VERSION = "attr-math-v1-substrate"` |

`ATTRIBUTION_SHARE_MATH_VERSION` is new on `substrate/attribution/algorithms.py`. It is
not a second version of one contract; it is the missing label on a second *implementation*
that already existed. `ad_inventory/attribution.py` stamped its output and this module
stamped nothing, so a share vector produced here was unidentifiable after the fact, which
is the part of a payout dispute you cannot argue your way out of. When the operator
ratifies the unification the two constants collapse along with the two implementations.

The event carries the full canonical inputs, so `replay(inputs_json)` reproduces the lines
with no database and no network. A replay that re-read the substrate would reproduce
today's graph, not the graph that priced the row.

## The operator gate this lane could not close

`docs/decisions/afa-synthesis-attribution-canonical.md` records two live, divergent
implementations of §9.3 and escalates *which is canonical* as an operator decision. It is
still open. Building the recursion on the wrong base was the named risk.

**I built against System 1 (`substrate/attribution/compute.py` + `algorithms.py`), and
here is why that is safe whichever way the operator rules.**

1. It is the only one that can do this job at all. It resolves a `synthesis_id` through
   chunk → document → `ip_holder`; System 2 consumes pre-resolved dicts keyed to an
   impression set and has no concept of a claim, which the author leg needs.
2. It is the gating-aware one. System 2 applies no §9.0 exclusion.
3. The recursion consumes a *share vector* through a named algorithm and records which
   one priced it. If the operator ratifies Option C, the unified math supplies the same
   vector and the recursion layer is unchanged — the delegation direction does not reach
   this code.
4. This lane writes no durable audit row and touches `ATTRIBUTION_ALGORITHM_VERSION` not
   at all, so it prejudges nothing the operator has to decide.

## The gate this lane deliberately did not import

Every split records `gate`. Today the only value is `display`.

`DisplayGatedProvenanceResolver` inherits `compute.py`'s §9.0 retrieval-time gate, which
withholds **both** `restricted_pending_opt_in` and `personal_reading`. That is correct for
a surface and wrong for an earn path: on the money side `restricted_pending_opt_in` must
keep accruing to its pre-onboarded holder, and that escrow mechanism is the entire point
of §9.10. The AFA doc's verifier caught this exact mistake once already, in a draft that
would have zeroed escrow for the rights holders §9.10 exists to serve.

So the gate is in the class name and on every row. A settlement path needs an
`EarnGatedProvenanceResolver` that excludes only `personal_reading`; reaching for this one
would be the silent-zeroing bug. A row stamped `display` is telemetry and must never be
settled as money.

## Findings this lane surfaced, for whoever picks up SPR-3

1. **A `syntheses` row carries no owner, and neither does the event envelope.** The author
   leg of the operator's thesis has no subject to pay for most syntheses. The resolver
   falls back to the single owner of the documents ingested under the same
   `investigation_id`, and returns `None` when they disagree or when no document carries
   it — those units become an explicit `author_unresolved` line rather than a guess.
   Making the author leg real means writing `owner_user_id` on `syntheses` at deposit
   time. Historical rows cannot be backfilled; inventing ownership is not an option.
   That is a schema-plus-writer change and was out of this lane's boundary.

2. **`ad_inventory/attribution_explain._largest_remainder_cents` breaks ties in
   dict-insertion order.** Its `sorted(weights.keys(), key=remainder)` is stable, so two
   callers assembling the same logical weights in different orders can assign a tie cent
   differently. Inside `attribution_audit.replay()` this is harmless (the dict is rebuilt
   from canonical JSON), but `aggregate_window` builds weights in batch order. It is a
   narrow latent nondeterminism on the money path. `apportion_units` in this lane sorts
   keys and breaks ties on the key, and the two should be unified the day the cents twin
   gets the same property — a money-path change, not this lane's.

3. **A raw read-only DuckDB handle is green under pytest and raises in production.**
   Found by adversarial verification, fixed in this lane. DuckDB refuses a true
   read-only connection whenever the same process already holds the file read-write,
   and the API process does exactly that: uvicorn runs `--workers 1`, and `connect_write`
   parks a warm writer for `ANTIEK_WRITE_KEEPALIVE_S` (20 seconds by default) after every
   write. That keepalive is disabled under pytest, so a raw
   `duckdb.connect(path, read_only=True)` passes every test and then raises
   `ConnectionException` for twenty seconds after each write in the live process.
   `runtime.db_lock.connect_read` is the seam that absorbs it, and 65 of the 75 read
   sites under `substrate/` already used it. Both the new resolver and
   `compute_attribution_for_synthesis` — which `GET /attribution/{synthesis_id}` has
   been calling all along — now go through it.
   `test_resolver_reads_while_the_single_writer_holds_the_db` reproduces the failure
   behaviourally and `test_read_path_goes_through_the_sanctioned_read_connection` keeps
   the seam from drifting back.

4. **Adding an `ActionType` breaks the reading app's narration map.**
   `apps/reading/src/modes/ResearchWorkstation/narrateEvent.ts` declares
   `Record<ActionTypeValue, NarrationRule>` and `narrateEvent.test.ts` asserts every
   catalogue entry has a row. A new event type without a row is a red frontend test and a
   TypeScript error, in a file nothing about the substrate change points at. Row added
   (suppressed — the reader is watching research progress, not the ledger).

## Reconsider-if

- The epistemic typing lands on `ThesisComponent`. Then bump `AUTHOR_SHARE_POLICY` to a
  span-proportional policy; do not edit `AUTHOR_SHARE_FIXED` in place, or rows priced
  under the old constant become unreadable.
- Real syntheses turn out to carry a meaningful `path_only_claim_count`. That is the
  cheap evidence that a structural author share is viable before the full typing exists.
- A depositor writes syntheses into `documents`. Then `test_live_walk_has_no_nested_
  syntheses_today` fails — good news, and the cap is already in the contract.
- The operator ratifies a canonical §9.3 math. The recursion layer does not change; only
  what fills `share_algorithm_version` does.
- §9.0 closes and settlement is built. Do not reuse `DisplayGatedProvenanceResolver`.
