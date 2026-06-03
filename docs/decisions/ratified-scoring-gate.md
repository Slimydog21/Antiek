# Ratified-scoring gate — blocking, pre-merge, structural pre-registration

**Decision date:** 2026-06-04
**Status:** ✅ Active (blocking on `pull_request:[main]` + `push:[main]` via the
`Ratified-scoring gate` step in the `pytest` job of `.github/workflows/ci.yml`)
**Owner:** Antiek — Convergence SPR-06 (reuse-consuming loop / compounding made measurable)
**Scope:** a new `tools/ratified_gate.py` scanner + a blocking CI step + a
`--ratified` / `--ratification-ref` flag on `compounding.benchmark.run`. Does
**not** run the decision-0.2 prod measurement (operator-gated); it installs the
gate that makes ratification a precondition of any scored run.

## The decision

A benchmark result artifact is **SCORED** iff `mock_run == false`. A scored
artifact **must** carry `parameters_ratified == true` **and** a non-empty
`ratification_ref` (the pilot-report id / decision reference it ratified
against). The CI gate `tools/ratified_gate.py` scans every `*.json` under
`compounding/benchmark/results/` and **fails the build** for any scored artifact
that is not ratified-with-a-ref. A **mock** run (`mock_run == true`) is **exempt**.

## What is gated, and what "scored" means

"Scored" is defined **once**, in the gate's docstring and here: `mock_run ==
false`. A mock run is the autonomous demo-loop (or a reuse-consuming dev run that
still sets `mock_run=true`) — the keystone null, which makes no scored
compounding *claim*. A scored run is the operator-window `mock_run=false` run
whose verdict would be **reported as the flywheel finding**. Only the latter can
do damage by being un-ratified (a post-hoc re-roll of `n`/floor/tolerance changes
the verdict), so only the latter is gated. The mock-run exemption is what keeps
the autonomous CI mock artifact (`results/spr09_run.json`) green without an
operator in the loop — at the cost that the gate says nothing about the dev mock,
which is correct because the dev mock asserts nothing.

## Why blocking (not informational)

The cardinal sin this whole spec exists to prevent is a **faked or
goalpost-moved compounding number**. Decision-0.2 pre-registers the
question-set + metrics + thresholds + verdict logic *before* any scored run so
the result is falsifiable and goalpost-proof. But pre-registration is merely
**procedural** unless something **structurally** enforces that the scored
artifact was actually ratified — otherwise a scored run could be silently
re-rolled with a different `n`/floor/tolerance after seeing the numbers, and the
pre-registration would buy nothing. An un-ratified scored artifact **is** the
post-hoc-re-roll vector. So the gate is blocking: its exit code is the build's —
no `|| echo` swallow, no `continue-on-error`, no `::warning::`-only (the same
contract as the reachability/keystone gates, *not* the informational latency
step). The self-test `tests/test_ratified_gate.py::test_ci_step_is_blocking`
asserts the workflow does not swallow the gate's exit code, so a future edit that
demotes it to informational reds.

## What the mock-run exemption costs (and why it is acceptable)

The exemption means a `mock_run=true` artifact never needs ratification. The cost
is that an actor could set `mock_run=true` on a run that *did* make real provider
calls, dodging the gate. That is mitigated structurally, not by this gate:
`run.py` REFUSES a `mock_run=false` live run from the build environment (no creds,
no box), and the prod profile's live run is operator-window-only. The exemption's
benefit (the autonomous mock CI artifact stays green with no operator) is
load-bearing; the residual risk (a mislabelled mock) is owned by the operator who
runs the scored window, where `--ratified` is the deliberate, recorded act.

## Auditability — `--ratified` records WHAT was ratified

`--ratified` alone is not enough: it must be accompanied by `--ratification-ref
<pilot_report_id | decision-ref>`, which is recorded as `ratification_ref` on the
artifact. `run.py` REFUSES `--ratified` without a non-empty ref. The pilot
(`run --pilot`) persists a `pilot_report.json` carrying the observed CV, the
derived `n`/floor/tolerance, the derivation string, and a content-addressed
`pilot_report_id`. So a reader of a scored artifact can resolve its
`ratification_ref` back to the exact pilot report and reconstruct the ratified
parameters — ratification is a reconstructable provenance chain, not a bare
boolean.

## The end-to-end flow (decision-0.2 Part C, made runnable)

1. `python -m compounding.benchmark.run --pilot` → runs a small pilot, observes
   the per-metric CV, calls `propose_parameters` (n ≈ (z·CV/target)², z=1.96,
   target=0.10, bounds 5..200; floor = 2·CV·|cold_mean|; tolerance = floor/2),
   and **persists** `results/pilot_report.json` with a `pilot_report_id`.
2. **(HUMAN step — NOT performed by this sprint)** the operator reads the report
   and ratifies the derived `n`/floor/tolerance into decision-0.2 §A.6.
3. `python -m compounding.benchmark.run --loop consuming --n <n> --material-floor
   <floor> --control-tolerance <tolerance> --ratified --ratification-ref
   <pilot_report_id>` (on the box, with prod creds) → the scored artifact, which
   the gate then passes.

## Reconsider-if

* the artifact location changes (the gate scans `compounding/benchmark/results/`
  — re-point it if the benchmark writes elsewhere);
* a second legitimate artifact shape gains a `mock_run` key for a different
  purpose (the gate would then gate it too — narrow `_looks_like_benchmark_artifact`);
* the definition of "scored" changes (today it is exactly `mock_run == false`).

## Out of scope

The actual decision-0.2 prod measurement (operator-gated: needs operator
ratification + a measurement window). This sprint builds and wires the procedure;
the operator runs it. The flywheel WIRE (SPR-02) and the reuse assembly (SPR-06's
sibling foundation work) are unchanged.
