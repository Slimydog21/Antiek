# §9.0 retrieval gate — unknown content_class is FAIL-OPEN (both paths)

**Date:** 2026-06-03
**Status:** FINDING recorded (no policy change — see "Scope" below)
**Owner:** Antiek — Convergence SPR-03 (M3, the retrieval-gate reachability probe)
**Surfaces:** `substrate/graph/retrieval_gate.py`
(`non_privileged_chunk_sql_clause`, `is_chunk_body_withheld`);
`interfaces/research/api/app.py:2221-2230` (the `GET /chunks/{id}` withhold);
`substrate/graph/search.py` (the chunk-search gate)

## The finding (VERIFIED, not assumed)

A `content_class` that is in **neither** gate set — i.e. a new/future class added
without updating the gate's frozensets — is **SERVED** on **both** the HTTP chunk
path and the SQL chunk-search path. Both fail **OPEN** on an unknown class.

Verified by booting the production `create_app()` factory and seeding a chunk
with `content_class="some_future_class_v2"` (an explicit value in no gate set):

| path | unknown class | NULL/legacy | restricted | personal_reading |
|---|---|---|---|---|
| HTTP `GET /chunks/{id}` (`is_chunk_body_withheld`) | **served** (fail-open) | served (grandfathered) | withheld `restricted` | withheld `personal_readable` |
| SQL chunk search (`non_privileged_chunk_sql_clause`) | **served** (passes `NOT IN`) | served (`IS NULL`) | excluded | excluded |

Why each path fail-opens:

* **HTTP** — `is_chunk_body_withheld` (`retrieval_gate.py:119`) withholds only if
  `taken_down`, or `content_class in PERSONAL_ONLY_CONTENT_CLASSES`, or
  `content_class in RESTRICTED_CONTENT_CLASSES`; **everything else returns
  `(False, None)` → served.** An unknown class hits none of those branches.
* **SQL** — the clause is
  `content_class IS NULL OR content_class NOT IN (<personal, restricted>)`
  (`retrieval_gate.py:112-115`). An unknown class is not in the excluded list, so
  `NOT IN` is TRUE → the row survives the gate.

## This CORRECTS the SPR-03 brief's premise

The SPR-03 sprint brief hypothesized an **asymmetry**: that the SQL gate
"fail-CLOSES on an unknown content_class (`NOT IN` → excluded)" while the HTTP
path fail-opens. **That is inverted.** `NOT IN (<known-withheld>)` is TRUE for an
unknown class, so the SQL gate fail-OPENS too. There is **no SQL-vs-HTTP
asymmetry on unknown classes** — both serve them. (There IS a real, intended
asymmetry elsewhere: the *public book serve* path in `substrate/books/serve.py`
uses an **allowlist** `SERVABLE_CONTENT_CLASSES` — deny-by-default — which is the
opposite polarity from these chunk-gate denylists. That allowlist is unaffected
by this finding and correctly fail-CLOSES an unknown class.)

A separate, smaller honesty note: the inline comment at `app.py:2225` reads
"NULL/unknown fails closed (SR-07), consistent with the search path." That
comment is **factually wrong on both counts** — NULL is grandfathered (served,
deliberately, per the `retrieval_gate` docstring), and unknown is served
(fail-open, this finding). SR-07's NULL-fail-closed proposal was *rejected* for
#65 (it would hide legacy content with no backfill). The comment is stale; left
in place this session only because correcting prose in a §9 hot path without an
operator review felt out of scope, but it should be fixed (the docstring on
`is_chunk_body_withheld` is the correct reference).

## Why this matters (the leak it would become)

The deny-list polarity means the chunk gate is only as complete as its enumerated
set. If a future rights state is introduced (the way `personal_reading` was added
in the Personal-Reading Lane) and is added to `register_source_document`'s write
side **without** also being added to `RESTRICTED_CONTENT_CLASSES` /
`PERSONAL_ONLY_CONTENT_CLASSES` (and therefore `_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES`),
then chunks of that class would **leak via both chunk search AND `GET /chunks`**
the moment they are ingested — silently, because both paths fail-open. The union
set is the single chokepoint, so a one-line omission there is the whole exposure.

## Scope — what SPR-03 does and does NOT do

* **DOES:** record this verified behaviour; add the `retrieval_gate` reachability
  probe (`tools/reachability/probes/retrieval_gate.py`) that asserts the unknown
  class is **served today** and reds if that polarity FLIPS without a deliberate
  decision (so a future deny-by-default change must land *with* an update to this
  note, not as a probe surprise).
* **Does NOT:** change the gate's withhold policy. Flipping the chunk gate to
  deny-by-default (withhold any class not on an explicit allowlist) is a **§9
  design decision for the operator** — it would change which content is
  searchable/servable and interacts with the NULL-grandfather contract and the
  legacy migration question. SPR-03 exposes the behaviour honestly; it does not
  redesign it.

## Reconsider-if (what would make a deny-by-default flip the right call)

* A new gated rights state is added → the enumerate-or-leak risk becomes concrete;
  consider switching the chunk gate to an **allowlist** mirroring
  `substrate/books/serve.py` (one polarity across the codebase), paired with the
  legacy-NULL migration SR-07 needs.
* OR: add a unit/contract test that asserts every `content_class` written by
  `register_source_document` is classified by the gate (servable, restricted, or
  personal) — so an un-enumerated class fails CI at the write side rather than
  leaking at the read side. (Cheaper than flipping the polarity; closes the same
  hole.)
