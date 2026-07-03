# AFA-S3 — the canonical share vector for per-frame ad attribution on a synthesis surface

**Date:** 2026-07-03
**Sprint:** antiek-frame-attribution SPR-03 (synthesis composition), M2
**Status:** FINDING recorded + one **architecture decision** escalated
(the agent recommends, the operator ratifies which attribution math is canonical).
**Author:** /infinite ads lane (Opus 4.8), grounded in the `afa/spr03-synthesis-composition`
worktree over `origin/main`. Every claim below was traced against the code, not recalled.
**Verification:** adversarial verifier-critic pass (2026-07-03) confirmed Defect 1 and the
topology against file:line, and **corrected** the Defect-2 narrative — the
`restricted_pending_opt_in` gating asymmetry is intentional per §9.10, not a defect (folded
in below). That correction prevented an M4 design that would have zeroed escrow for
pre-onboarded rights holders.

## Why this doc exists

AFA-S3 composes the per-frame ad pipeline with the synthesis surface. The prior
sprint framing assumed M2 was a "reuse `record_attribution` as a clean drop-in."
Reading the machine, that is **wrong in a way that matters** — there are TWO
attribution systems with divergent math, and the durable audit store is wired to
the one that does *not* do §9.0 gating. This doc records the verified topology and
escalates the one call the agent cannot make: which math is canonical.

## The verified topology

There are **two independent attribution subsystems**, each implementing "master-spec
§9.3 options A/B/C," that are **not connected** (grep found no module bridging them):

### System 1 — the synthesis producer (`substrate/attribution/`)

- `compute_attribution_for_synthesis(synthesis_id)` (`compute.py:94`) reads a
  synthesis + its `thesis_components` from DuckDB, resolves
  `chunk→document→source_tier→ip_holder`, runs the three algorithms
  (`algorithms.py`), and returns a `SynthesisAttributionResult` of **per-document
  share maps**. Optionally emits a `PAGE_ATTRIBUTION_COMPUTED` event.
- **It is provenance- and gating-aware.** It applies the §9.0 retrieval-time
  exclusion (`compute.py:160-195`): `restricted_pending_opt_in` **and**
  `personal_reading` documents receive zero share and zero title, using the *same*
  `_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES` union the public chunk-search gate
  uses, so the two surfaces cannot drift. It also resolves each owner's
  `ip_holder` **status** (`pre_onboarded` … `claimed`) to drive opt-in-only escrow
  framing (§9.10).
- **It computes on read; it does not persist a durable, replayable record.** The
  emitted event is an investigation-scoped JSONL snapshot, not a queryable,
  version-stamped, byte-reproducible audit row.
- **Live callers:** exactly one — `interfaces/research/api/app.py:3279` (read-only
  API surface).
- Its math (`algorithms.py`) iterates **claims**: for each claim, for each cited
  chunk, add a unit (A) or `confidence_weight × (6−tier)` (B), where
  `confidence_weight` comes from a **string→float table** (`CONFIDENCE_WEIGHTS`,
  `very_high=1.0 … very_low=0.2`) keyed off the claim's confidence *word*.

### System 2 — the durable audit store (`substrate/ad_inventory/`)

- `attribution.py` implements the *same three options* but with a **different input
  shape and a different reduction**: it iterates **distinct chunks** over
  pre-resolved dicts (`chunk_to_document`, `chunk_to_claim_confidence` as a
  per-chunk **float**, `document_to_source_tier`).
- `attribution_audit.py::record_attribution` is the **append-only, idempotent,
  version-stamped, replayable** store — keyed by `impression_set_ref` (the AD unit,
  not `synthesis_id`). `_ALGO_INPUT_KEYS` validates the exact kwargs so `replay()`
  reproduces the split byte-for-byte. This is the counsel-defensible trust layer
  the operator named as the #1 waste mode this project prevents.
- **It does NOT apply §9.0 gating.** It has an orthogonal EARN gate
  (`monetization_eligible`, drops `user_owned` private uploads) but nothing that
  excludes `restricted_pending_opt_in` / `personal_reading` from a synthesis split.
- `record_attribution` has **no live production call site** today (referenced only
  in `__all__` + docstrings/comments in `frame_attention.py` and `arxiv_audit.py`)
  — a built-but-not-yet-reached durable store.

### System 3 (context) — the per-frame accrual (`frame_attention_accrual.py`)

- The actual per-frame money path apportions a second's cents across the assets
  **in the frame** by **measured attention** (`aw.weight` = area × prominence ×
  dwell), via `apportion_cents` (`:316`). The asset key is the frame's
  `data-akb-asset-id`.
- **It stops at the in-frame `asset_id`.** It does **not** recurse a *synthesis*
  asset down to the source documents / ip_holders that drove its content. So a
  synthesis asset today would pay "the synthesis," not the underlying drivers —
  which is exactly the S3 gap this sprint closes.

## The two verified defects this surfaces

**Defect 1 — divergent §9.3 math (a LIVE payout-dispute time bomb, not merely latent).**
The two subsystems can produce **different share vectors for the same synthesis**,
and *both are live-reachable today*: System 1's math answers the synthesis-attribution
API (`app.py:3279`) while System 2's math answers `POST /attribution/compute`
(`app.py:4702`) and the Speak contributor split (`speak/contributor.py:198`). They can
disagree on the same page **right now**. Traced divergences:
- **Iteration multiplicity (A, B, C):** if chunk *X* (→ document *D*) is cited by 3
  claims, `substrate/attribution/algorithms.py::attribution_option_a` credits *D* **+3**
  (one per claim-citation, `algorithms.py:74-79`), while
  `substrate/ad_inventory/attribution.py::compute_attribution_option_a` credits *D*
  **+1** (one per distinct chunk, `attribution.py:225-228`). System 2 has no concept of
  a claim — one chunk carries one confidence — so a chunk shared by two claims of
  different confidence cannot even be represented the same way.
- **Confidence axis (B):** claim-level string weight (`CONFIDENCE_WEIGHTS`,
  `algorithms.py:95`) vs per-chunk float (`chunk_to_claim_confidence`,
  `attribution.py:256`).
- **Tier clamp (B) — LATENT, not live:** `algorithms.py:101` clamps
  `tier_factor = max(1, 6−int(tier))`; `attribution.py:259` uses an unclamped `(6 − tier)`
  that reaches 0 at tier 6 and goes negative beyond. Because source tiers are documented
  1..5, this axis only *bites* if a tier ≥6 ever appears — so it is a latent divergence,
  distinct from the two axes above. The doc's urgency rests on the **live** axes (Option-A
  per-citation multiplicity + the Option-B confidence type), not this one; it is listed for
  completeness and as a reason the unified math should clamp defensively. (Independent
  AFA-lane verification, 2026-07-03, made this latent/live distinction explicit.)

The two live axes alone mean two implementations of one labeled spec section are
live-reachable and divergent — which is
exactly the swappable-without-loss duplication that produces a dispute where two Antiek
surfaces disagree on the same page's split. This is the opposite of the auditability the
operator asked for.

**Defect 2 — `personal_reading` can leak into the durable earn path (corrected scope).**
The first draft of this doc claimed the durable store must carry System 1's *entire*
§9.0 exclusion. The verifier-critic corrected that, and the correction is load-bearing:
the two excluded classes have **opposite** monetization semantics (`retrieval_gate.py:62-64`),
so they must be handled separately, not as one exclusion:
- **`restricted_pending_opt_in` — the asymmetry is INTENTIONAL (§9.10), not a defect.**
  System 1 zeroes its *display* share and title (`compute.py:170-173`) because a withheld
  body must not surface; but the earn/escrow path **must keep it accruing** to the
  pre-onboarded holder — that pre-onboarded-escrow mechanism is the whole point of §9.10
  (`attribution.py:90-97` explicitly warns future maintainers not to collapse the gates).
  Importing System 1's §9.0 exclusion wholesale into the money path would zero-out escrow
  for exactly the rights holders §9.10 exists to serve. **Do NOT propagate compute.py's
  display-zeroing of this class into M4.**
- **`personal_reading` — a GENUINE latent leak the money path must close.** It must never
  earn. System 2 only drops it via deny-by-default *if* a caller applies `eligible_shares`
  (`attribution.py:173-193`) — and `record_attribution` applies **neither** that gate nor
  the §9.0 exclusion. So a synthesis split persisted through the durable store today could
  durably record earn-share for a `personal_reading` document. **M4 must exclude
  `personal_reading` from the earn path everywhere**, while leaving
  `restricted_pending_opt_in` accruing.

Net: the durable recorder does not need System 1's *display* gate; it needs a *narrower*
earn gate — `personal_reading` excluded, `restricted_pending_opt_in` retained.

## The decision the operator must ratify (agent recommends)

**Which §9.3 math is canonical, and how does the durable audit record persist the
gated synthesis split?**

- **Option A — `compute.py` canonical; extend the audit store to accept its output.**
  System 1 is the go-forward share-vector source (it is the only one that gates).
  Add a durable, version-stamped, replayable record path that persists System 1's
  result. Leaves System 2's divergent algorithm copy alive unless separately
  retired — so in practice it must also be made to delegate, collapsing into C.
- **Option B — route the synthesis surface through System 2 (`ad_inventory`).**
  Keep `record_attribution` as-is; have the frame surface resolve the dicts and
  call System 2's algorithms. **Rejected on hard-to-vary grounds:** this surface
  would then not get §9.0 gating for free — re-implementing the exclusion is the
  drift System 1's comment explicitly warns against.
- **Option C — unify the algorithm math into ONE module; both entry points consume it.**
  Make `substrate/attribution/algorithms.py` the single implementation of the §9.3
  A/B/C math; make `ad_inventory/attribution.py` **delegate** to it (adapting input
  shapes) so the durable store and the synthesis producer compute **byte-identical**
  splits. `compute.py` stays the §9.0-gating-aware synthesis producer;
  `record_attribution` stays the durable, impression-set-keyed store; both call one
  math. Then S3 composition is: frame-attention cents on a synthesis `asset_id` →
  §9.3 **unified** split (gated) → per-source-document accrual → durable audit row.

**Recommendation, on hard-to-vary grounds: Option C.** The element that is
swappable-without-loss — and therefore must be cut — is the *second copy of the
§9.3 algorithm math*. One spec section, one implementation. Everything else
(the gating in `compute.py`, the replay/version-stamp in `attribution_audit.py`,
the attention apportionment in `frame_attention_accrual.py`) is load-bearing and
stays. Option C removes the divergence (Defect 1) and lets the durable record carry
the gated split (Defect 2) without forcing a single entry point. Deciding this is
the operator's call because it retires a live code path's public math contract
(`ATTRIBUTION_ALGORITHM_VERSION` must bump, and any already-recorded audit rows
must be checked against the unified math before disbursement).

## What S3-M2..M6 must do once the path is decided (if Option C)

1. **Deduplicate the math (M2, the real unblock):** make `algorithms.py` canonical;
   `ad_inventory/attribution.py` delegates. Bump `ATTRIBUTION_ALGORITHM_VERSION`
   (a math-identity change). Add a golden test proving System-1 and System-2 entry
   points return identical splits for a shared fixture — this is what proves the
   divergence is closed and stays closed. **This step is buildable and verifiable
   now; it does not depend on the reading-app change.**
2. **Recurse synthesis assets in the frame accrual (M3):** when an in-frame
   `asset_id` resolves to a synthesis, split its accrued cents across source
   documents via the unified §9.3 (gated) producer before accruing to ip_holders.
3. **Persist durably (M4):** record the synthesis split through `record_attribution`
   (now consuming the unified math), keyed to the window's impression-set, so it replays
   byte-identically. Apply the **narrow earn gate** (Defect 2): exclude
   `personal_reading` from the earn path; **retain** `restricted_pending_opt_in`
   accruing to escrow per §9.10. Do NOT reuse `compute.py`'s display exclusion here — it
   is a display gate, not an earn gate, and would zero pre-onboarded holders' escrow.
4. **Conservation invariant (M5):** the sum of per-source-document accruals for a
   synthesis asset equals that asset's attention-apportioned cents (no cent minted
   or lost in the synthesis→source recursion). Assert it, red-prove it.

## Dormancy note (honest scope)

Steps 2–4 stay **dormant** until a synthesis surface in the reading app carries
`data-akb-asset-id` on its composed page (a one-line frontend change, not in this
worktree's scope). **Step 1 (the math deduplication) is NOT dormant** — it is a
live latent divergence (Defect 1) that matters independent of frames, and is the
correct first build once the operator ratifies Option C.

## Reconsider-if

- The operator ratifies a different canonical math (A or B) — this doc's Step-1
  deduplication still applies; only the *direction* of delegation flips.
- A surface is found that legitimately needs System 2's chunk-iteration reduction
  as a *distinct* measure (not a duplicate) — then Defect 1 is not a defect and
  Option C is wrong; but that must be **proven**, not assumed (the two are labeled
  as the same §9.3 options today, which is the evidence they are meant to agree).
- The **gating** divergence, by contrast, is NOT a candidate for unification: the
  display gate (`compute.py`) and the earn gate (the money path) are genuinely
  different measures, and §9.10 requires them to give opposite answers for
  `restricted_pending_opt_in`. Unify the *math*; keep the two *gates* distinct.
- Disbursement gates (G2/G3) approach — at which point closing Defect 1 becomes a
  hard pre-disbursement gate, since a payout computed against the divergent copy
  cannot be reconciled against the audit store's replay.
