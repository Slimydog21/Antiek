# Unified integration health — the conformance contract

**antiek-unified SPR-08 M6.** The durable record a future agent reads to
understand what keeps "four products are one product" true, and how to extend
the guard when the product grows. This is the integration contract.

> **What this guards, in one sentence:** a single graph entity flows
> Research → Read → Write → Speak → Read through the real typed seams as ONE
> node id with unbroken provenance, and no product may silently fork a shared
> contract or renumber a cited DRW sprint without a loud CI failure.

---

## The two artifacts

| Artifact | File | What it proves |
|---|---|---|
| **End-to-end flywheel test** | `tests/e2e/test_flywheel.py` | One entity traverses the committed flywheel hops via the **real SPR-03 seams**; the SAME node id at every hop; provenance unbroken; the seam-#4 publish gate fires. An injected entity copy FAILS the same-node-id assertion. |
| **Contract-conformance gate** | `tools/codegen/check_conformance.py` (+ `tests/test_conformance_gate.py`) | Every SPR-01 contract conforms (real impl or documented stub); the frozen DRW sprint-lock resolves every downstream citation. An injected contract fork OR a DRW renumber FAILS the gate. |
| **Eight-invariant suite** | `tests/test_integration_invariants.py` | Composes the load-bearing guards from SPR-02..07 + SPR-08 into one named manifest; one command runs every cross-cutting invariant. |

The e2e is the higher-value add; the **conformance gate is the non-negotiable
minimum** (see "Steelman" below). An e2e is a snapshot — it proves the
integration works *today*. The conformance gate is the thing that stops the
eight resolved seams from quietly re-breaking *tomorrow*.

---

## What fails CI, and why

CI (`.github/workflows/ci.yml`, the `pytest` job) fails the PR when:

1. **A product forks a contract** — a real impl (or a stub) drops/renames a
   field `verify_conformance` checks. Example caught: the note-taker output
   losing `source_event_ids` (the attribution field — an unattributed note is
   a hallucination). The CI log names the dropped field with a diff.
   *Owner of the fix: the product's own sprint. The gate just makes it loud.*
2. **The frozen DRW sprint-lock drifts** — a DRW sprint cited by Read/Write/
   Speak no longer resolves in `substrate/contracts/drw_sprint_lock.py`
   (`verify_citations_resolve()` non-empty). This is the **seam-#6 silent-
   renumber risk**: three downstream specs cite DRW sprints by number; a
   renumber without updating the lock would point them at the wrong
   deliverable. The lock turns that into a CI failure.
3. **Any of the eight cross-cutting invariants breaks** — the invariant suite
   re-runs each owning guard; a regression in any one fails the suite.
4. **The TS codegen goes stale** (`tools/codegen/emit_types.py`) or the
   **inline-rubric latency regresses >10%** (`benchmarks.rubric_latency
   --check-regression`) — both run in the same job (pre-existing craft
   signature + schema-drift guards).

**Proven to reject (rigor #3):** both conformance-gate negatives are exercised
in `tests/test_conformance_gate.py` — an injected fork and an injected DRW
renumber each make `run_gate()` return exit 1. A documented dry-run of the
standalone script confirms CI would fail on each. A gate nobody has seen reject
a real violation guards nothing.

---

## The eight seam resolutions — running status

The four product specs left eight integration seams assumed-but-not-pinned
(master spec, "the eight seam resolutions"). Each is resolved and now guarded:

| # | Seam | Resolution | Guard that proves it |
|---|---|---|---|
| 1 | Shared reading surface ownership | One `<Reader>` + `openDocument`; lying seam test **deleted** SPR-09 | `substrate/contracts/__tests__/test_reader_conformance.py`; `oneReader.conformance.test.ts` |
| 2 | Voice pipeline two owners | `acquisition/voice/` is the single owner; Read+Speak call it | `tests/test_seam_voice_single_owner.py` |
| 3 | Two `attribution.py` files | Distinct concerns, **one escrow-balance writer** = `ip_holders.accrue_escrow` (corrected post-SPR-03: NOT `publisher_escrow.py`, which is read-only reporting) | `tests/test_seam_single_escrow_writer.py`; invariant suite #3 |
| 4 | `platform_authored`-from-Speak gating | `provenance_class ∈ {operator_authored, speak_derived}`; speak_derived serves only after the publish gate | `tests/test_seam_platform_authored_gate.py`; invariant suite #4; **e2e M1** |
| 5 | Editor library | Commit TipTap (notebook editor already ships it); Write SPR-04 inherits | (frontend; `g4-lemon-ui-verdict.md`) — out of conformance-gate scope |
| 6 | DRW sprint-number stability | Freeze the DRW sprint→deliverable map; CI asserts cited sprints resolve | `substrate/contracts/drw_sprint_lock.py`; **conformance gate**; `tests/test_contracts_drw_lock.py` |
| 7 | §16 / research fan-out | Amend §16 to exempt research fan-out only; single-writer untouched | `tests/test_remote_exec_isolation.py`; invariant suite #1 |
| 8 | Gate coupling | Shared gates presented once with a per-product impact column; no per-product gate fork | `tests/test_coordination_no_fork.py`; invariant suite #5 |

Seam 5 is frontend/editor-stack and not a Python contract, so it is guarded by
the Lemon-UI verdict + TipTap commitment, not the conformance gate. Every other
seam is mechanically guarded by a test this suite composes.

---

## Honest scope — which legs are real vs contract-level (intellectual honesty)

The e2e runs against the **real SPR-03 seam machinery + SPR-01 contracts**, but
most product *internals* are unbuilt on this base. State of play:

- **REAL:** the typed seam contracts; the SPR-06 thread reconstruction +
  no-duplicate assertion; the seam-#4 `servability_gate` (decoupled from
  `substrate.books`); the note-taker output + Write OutlineBlock shapes
  (checked against live in-tree classes by the conformance gate).
- **CONTRACT-LEVEL ONLY (pending a product merge):** the **served-back-in-Read
  leg**. Read's serving layer (`substrate/books/`) is on an unmerged branch —
  `import substrate.books` raises `ModuleNotFoundError` on this base, and
  `substrate/speak/publish.py` carries a dangling `substrate.books` import that
  breaks ~47 test files' collection. So that leg is proven via
  `ServableEntryContract` + `servability_gate` (both decoupled from
  `substrate.books`). **The full live Read-serving leg lands when Read's
  `substrate/books/` merges** — the e2e is structured so the real serve drops
  in by swapping the contract assertion for a live serve call, no other change.
- **STUB (live module not present):** Research `promote_insight`, Write block
  repository, Speak interview/publish paths — represented by the contracts the
  seams carry. The conformance gate's registry records, per contract, whether a
  real impl or a documented stub stands in.

The honest claim this suite warrants: *the integration substrate is sound and
conformance-gated; one entity traverses the committed flywheel hops as one node
with unbroken provenance.* NOT "the full product flywheel works end to end."

---

## How to add a guarded contract or seam (the recipe — defensibility #5)

When a future agent adds a ninth seam or a new shared contract, follow this so
the new thing is guarded too (and the gate does not rot):

### Adding a new shared contract

1. Add the Pydantic contract to `substrate/contracts/` and export it; add it to
   `CODEGEN_CONTRACTS` in `substrate/contracts/__init__.py`.
2. Add **one row** to `_CONFORMANCE_REGISTRY` in
   `tools/codegen/check_conformance.py`:
   - if the owning product ships a live module, set
     `conformer=<callable returning the live class>` (it will be checked
     directly — give it teeth);
   - if the product is unbuilt, set `stub_status="<why a stub stands in>"`
     (an honest record, never a fabricated entity).
   The coverage check (`test_every_contract_is_in_the_registry`) FAILS CI if you
   add a contract to `CODEGEN_CONTRACTS` and forget the registry row.
3. If the contract is owned by a DRW sprint cited downstream, add it to
   `DRW_SPRINTS` / `_DOWNSTREAM_CITATIONS` in `drw_sprint_lock.py` and **bump
   `LOCK_VERSION`** (a deliberate, reviewable act).

### Adding a new seam

1. Add the typed seam to `substrate/seams/contracts.py` (subclass `_SeamBase`;
   pin `from_workflow`/`to_workflow` with `Literal`s; carry `entity_id` +
   `entity_kind` + `provenance_ref` BY REFERENCE — never a content field).
2. Register it in `COMMITTED_SEAMS` or `PROVISIONAL_SEAMS`, and add its
   `seam.*` action type to `_SEAM_ACTION_DIRECTION` in
   `substrate/seams/thread.py` so the thread walk reconstructs trajectories that
   touch it.
3. Add a no-copy guard for it to `tests/test_seam_no_copy.py` (same-id passes, a
   forked id fails), and a hop to the e2e flywheel in `tests/e2e/test_flywheel.py`
   if it is on the flywheel's critical path.
4. If it carries a new cross-cutting invariant, add a row to
   `INVARIANT_MANIFEST` + a `test_invariant_N_*` in
   `tests/test_integration_invariants.py`.

### Verifying you did it right

```
# one command — the conformance gate (CI runs this on every PR):
python tools/codegen/check_conformance.py

# the three SPR-08 test artifacts:
python -m pytest tests/e2e/test_flywheel.py tests/test_conformance_gate.py \
                 tests/test_integration_invariants.py -q
```

If the gate is green and the negatives still fail (try deleting a contract field
locally and watch CI go red), the new thing is guarded.

---

## Superseded: `specs/shell/`

The shell spec's integration role now lives here, in `specs/antiek-unified/`.
The shell's 6 sprints do not carry the §16 amendment, the seam-collision fixes,
the 37-mode taxonomy, or the e2e conformance gate; editing it in place would
understate the new scope. Per the master spec's decision ("Never — superseding
is cleaner"), `specs/shell/` stays in the tree marked superseded with a pointer
to `specs/antiek-unified/`.

> **NOTE (intellectual honesty):** the `specs/shell/README.md` superseded-by
> banner could not be added by this SPR-08 worktree — `specs/shell/` is not
> tracked on the `unified/spr-08` branch (it lives only in the main tree, which
> this worktree's absolute rules forbid touching). The banner is a one-line
> edit the integration owner applies on the main tree:
> *"⚠️ SUPERSEDED by `specs/antiek-unified/` — the shell's integration role now
> lives in the unified spec; see `docs/decisions/unified-integration-health.md`."*

---

*Generated for antiek-unified SPR-08 — the integration capstone. If you are
extending the product, read the recipe above before adding a contract or a
seam, so the new thing is guarded the day it lands.*
