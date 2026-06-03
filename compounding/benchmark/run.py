"""AFF SPR-09 M6 — end-to-end mock run + pilot, emitting the recorded artifact.

``python -m compounding.benchmark.run`` drives all arms over the frozen question
set on the deterministic mock path (the host-local demo loop), aggregates the
signed delta + CI, runs the validity gate + 5-state verdict, and writes
``compounding/benchmark/results/spr09_run.json`` with the HONEST result.

THE HONEST EXPECTATION (intellectual honesty #1): the demo loop is reuse-blind
(it charges a fixed cost per step and makes no provider calls), so the mock run
reports delta ≈ 0 across the board — there is no dispatch.call cost to differ.
That is the keystone finding, not a defect: the instrument can measure
compounding (proven by the seed-and-catch tests in tests/test_falsifiability.py),
but the current host-local demo loop does not consume the reuse pack, so a live
``--mock-run false`` run with a reuse-consuming browse loop + provider creds is
required to measure REAL compounding. This module emits the null verbatim; it
does NOT re-roll or tune.

§16: this module drives the EXISTING host-local runner through ``harness.run_arm``
— no external process launch, no remote-exec provider, no second runtime
entrypoint. The git sha is read from ``.git`` (plain file reads, not a process
launch) and falls back to a documented placeholder; the orchestrator's commit
sets the real sha.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime

from .aggregate import DEFAULT_BOOTSTRAP_RESAMPLES, aggregate_comparison
from .harness import (
    LOOP_CONSUMING,
    LOOP_DEMO,
    ArmResult,
    ColdSeed,
    IrrelevantSeed,
    WarmSeed,
    run_arm,
)
from .measure import CostToResolve
from .pilot import propose_parameters, run_pilot
from .profiles import BenchmarkProfile, load_profile
from .question_set import QUESTION_SET_PATH, QuestionSet, load_question_set
from .result_schema import ArmComparison, BenchmarkResult
from .validity import HEADLINE_METRIC, decide

RESULTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "spr09_run.json")

# ACV SPR-06 (sharpen) — the DEFAULT --out for an interactive/dev run. The
# committed baseline (RESULTS_PATH / spr09_run.json) is a TRACKED file the gate
# scans + test_run_mock.py reads; defaulting --out to it would mean every dev
# `run --loop consuming …` overwrites a tracked file and dirties the tree. So a
# bare run writes a GITIGNORED transient twin instead (results/*.json is ignored
# except spr09_run.json — see .gitignore), leaving the committed baseline clean.
# Re-mint the baseline DELIBERATELY with `--out <RESULTS_PATH>` (then
# `git add -f`), never as a side effect of an exploratory run.
DEFAULT_RUN_OUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "results", "spr09_run.local.json"
)

# ACV SPR-06 — the persisted pilot-report artifact (decision-0.2 §C.2-C.3 + B3).
# ``--pilot`` writes the observed CV + the propose_parameters() output here so the
# operator reads a committed report, ratifies the derived n/floor/tolerance, and
# later passes ``--ratified --ratification-ref <this artifact's id>`` against it.
PILOT_REPORT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "results", "pilot_report.json"
)

# Documented placeholder. The recorded artifact's git_sha is set by the
# orchestrator's commit (the artifact is written BEFORE the commit exists), so a
# from-the-run artifact carries this sentinel until re-stamped. The README
# documents this; the verification gate notes the sha matches only post-commit.
GIT_SHA_PLACEHOLDER = "PENDING_COMMIT"

# Default mock parameters (§2): the mock artifact only. The LIVE n is operator-
# ratified after the pilot (decision 0.2) — never baked in here.
MOCK_N = 20
MOCK_RESAMPLES = DEFAULT_BOOTSTRAP_RESAMPLES


def read_git_sha(repo_root: str | None = None) -> str:
    """Read the short HEAD sha from ``.git`` via plain file reads (NOT a process
    launch — the §16 grep gate forbids process-launch tokens in this package).
    Returns the placeholder when ``.git`` is unreadable (e.g. a worktree gitdir
    pointer or a detached state we don't resolve), so the artifact is honest
    about provenance rather than crashing."""
    root = repo_root or os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    git_dir = os.path.join(root, ".git")
    try:
        # A worktree's .git is a file pointing at the real gitdir; resolving that
        # robustly is out of scope — fall back to the placeholder, which is the
        # honest "set at commit time" value anyway.
        if not os.path.isdir(git_dir):
            return GIT_SHA_PLACEHOLDER
        with open(os.path.join(git_dir, "HEAD"), encoding="utf-8") as f:
            head = f.read().strip()
        if head.startswith("ref:"):
            ref = head[4:].strip()
            with open(os.path.join(git_dir, ref), encoding="utf-8") as f:
                return f.read().strip()[:7]
        return head[:7]
    except OSError:
        return GIT_SHA_PLACEHOLDER


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def write_pilot_report(report, proposal, *, path: str, frozen_sha: str, git_sha: str) -> str:
    """Persist the pilot-report artifact (ACV SPR-06 / decision-0.2 §C.2-C.4 + B3).

    Records the observed per-metric CV, the cold means, the DERIVED proposal
    (n/floor/tolerance) AND the derivation string + inputs they came from — the
    full provenance the operator ratifies. Returns a stable ``pilot_report_id``
    (content-addressed over frozen_sha + the CV + the proposal) that a later
    ``run --ratified --ratification-ref <id>`` references, so the scored
    artifact's ratification is reconstructable. The HUMAN ratification step is NOT
    performed here — this only emits the report the operator reads."""
    import hashlib
    import json

    body = {
        "kind": "pilot_report",
        "frozen_sha": frozen_sha,
        "git_sha": git_sha,
        "captured_at": _now_iso(),
        "questions": report.questions,
        "runs_per_cell": report.runs_per_cell,
        "observed_cv": report.cv,
        "cold_means": report.cold_means,
        "cell_stats": [
            {"arm": c.arm, "metric": c.metric, "mean": c.mean, "cv": c.cv, "n_runs": c.n_runs}
            for c in report.cell_stats
        ],
        "proposed_parameters": {
            "n": proposal.n,
            "material_floor": proposal.material_floor,
            "control_tolerance": proposal.control_tolerance,
            "derivation": proposal.derivation,
        },
        "ratified": False,  # the operator flips this by RUNNING --ratified, not by editing here
        "ratification_note": (
            "OPERATOR STEP (not performed by this sprint): read this report, then run "
            "`python -m compounding.benchmark.run --loop consuming --material-floor "
            "<material_floor> --control-tolerance <control_tolerance> --n <n> --ratified "
            "--ratification-ref <pilot_report_id>` to ratify these derived parameters "
            "(decision-0.2 §A.6 / §C.4)."
        ),
    }
    digest = hashlib.sha256(
        json.dumps(
            {"frozen_sha": frozen_sha, "cv": report.cv, "proposal": body["proposed_parameters"]},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    body["pilot_report_id"] = f"pilot:{digest}"

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2)
        f.write("\n")
    return body["pilot_report_id"]


def _run_cell(
    questions: Sequence,
    arm_seed,
    *,
    events_dir: str,
    graphs_dir: str,
    n: int,
    loop_kind: str = LOOP_DEMO,
) -> dict[str, list[CostToResolve]]:
    """Run ``n`` runs of ``arm_seed`` for each question. Returns
    ``{question_id: [CostToResolve, ...]}`` (n entries per question).

    ACV SPR-06: ``loop_kind`` is threaded to ``run_arm`` so a ``--loop consuming``
    benchmark drives the reuse-CONSUMING loop on every arm (cold pays for all
    sub-questions, warm skips the covered ones → a genuinely negative delta)."""
    out: dict[str, list[CostToResolve]] = {}
    for q in questions:
        runs: list[CostToResolve] = []
        for run_index in range(n):
            res: ArmResult = run_arm(
                q, arm_seed, events_dir=events_dir, graphs_dir=graphs_dir,
                run_index=run_index, loop_kind=loop_kind,
            )
            runs.append(res.cost)
        out[q.question_id] = runs
    return out


def _pool(cell: dict[str, list[CostToResolve]], question_ids: Sequence[str]) -> list[CostToResolve]:
    """Pool the per-run CostToResolve across the given questions into one list
    (run order preserved per question, questions concatenated) so the aggregator
    pairs warm[i] vs cold[i] within the pooled stream."""
    pooled: list[CostToResolve] = []
    for qid in question_ids:
        pooled.extend(cell.get(qid, []))
    return pooled


def run_benchmark(
    qs: QuestionSet,
    *,
    events_dir: str,
    graphs_dir: str,
    n: int = MOCK_N,
    resamples: int = MOCK_RESAMPLES,
    material_floor: float = 0.0,
    control_tolerance: float = 0.0,
    mock_run: bool = True,
    git_sha: str | None = None,
    parameters_ratified: bool = False,
    ratification_ref: str | None = None,
    loop_kind: str = LOOP_DEMO,
) -> BenchmarkResult:
    """Drive every arm over the frozen set, aggregate, gate, and build the
    artifact. ``material_floor`` / ``control_tolerance`` are operator-ratified
    for a scored run; for the mock artifact they default to 0 (the demo loop's
    zero-variance null makes any positive floor trivially unmet — the verdict is
    null regardless, and the README is explicit about it).

    ACV SPR-06: ``loop_kind`` selects the browse loop on every arm. ``"demo"``
    (default) reproduces the historical reuse-blind null; ``"consuming"`` drives
    the reuse-CONSUMING loop so the warm arm genuinely does less work and the
    token_cost delta is strictly negative. ``ratification_ref`` is the
    pilot-report / decision reference the operator ratified against (recorded in
    the artifact when ``--ratified`` is passed — M3 auditability)."""
    seed = qs.seed
    headline_qids = [q.question_id for q in qs.headline_questions()]
    internal_qids = [q.question_id for q in qs.by_class("high_overlap") if not q.headline_pooled]
    partial_qids = [q.question_id for q in qs.by_class("partial_overlap")]
    control_qids = [q.question_id for q in qs.control_questions()]
    all_qs = list(qs.questions)

    cold = _run_cell(all_qs, ColdSeed(), events_dir=events_dir, graphs_dir=graphs_dir, n=n, loop_kind=loop_kind)
    warm = _run_cell(all_qs, WarmSeed(), events_dir=events_dir, graphs_dir=graphs_dir, n=n, loop_kind=loop_kind)
    irrelevant = _run_cell(all_qs, IrrelevantSeed(), events_dir=events_dir, graphs_dir=graphs_dir, n=n, loop_kind=loop_kind)

    def compare(label, exp_qids, base_cell, exp_cell) -> ArmComparison:
        return aggregate_comparison(
            label,
            _pool(exp_cell, exp_qids),
            _pool(base_cell, exp_qids),
            method="bootstrap",
            resamples=resamples,
            seed=seed,
        )

    headline = compare("warm_vs_cold_high_overlap", headline_qids, cold, warm)
    internal_probe = compare("warm_vs_cold_internal_probe", internal_qids, cold, warm)
    partial = compare("warm_vs_cold_partial", partial_qids, cold, warm)
    control = compare("irrelevant_vs_cold_control", control_qids, cold, irrelevant)

    # Per-domain control points (one control question = one domain) for the §2
    # "single domain spikes" invalidation.
    per_domain_points: list[float] = []
    for qid in control_qids:
        c = aggregate_comparison(
            f"control_{qid}",
            irrelevant.get(qid, []),
            cold.get(qid, []),
            method="bootstrap", resamples=resamples, seed=seed,
        )
        m = c.metric(HEADLINE_METRIC)
        if m is not None:
            per_domain_points.append(m.delta)

    verdict = decide(
        headline=headline,
        control=control,
        control_tolerance=control_tolerance,
        material_floor=material_floor,
        partial=partial,
        control_per_domain_points=per_domain_points,
    )

    if loop_kind == LOOP_CONSUMING:
        notes = (
            "Run on the reuse-CONSUMING browse loop (make_reuse_consuming_loop): "
            "each arm plans n sub-questions and emits a real dispatch.call ONLY "
            "for the sub-questions NOT covered by the reuse pack, so the warm arm "
            "(more covered) has fewer dispatch.calls and a lower summed cost_usd "
            "than cold. The headline token_cost_usd delta (warm − cold) is the "
            "GENUINE compounding signal — negative when reuse pays — and is "
            "reported verbatim (never clamped). The irrelevant arm shares no "
            "salient tokens with the questions, so it covers nothing and stays "
            "flat (the §2 validity control). validity_reason: "
            f"{verdict.validity_reason}. headline_reason: {verdict.headline_reason}."
        )
    else:
        notes = (
            "MOCK run on the host-local demo loop (make_demo_loop), which is "
            "reuse-blind and makes no provider dispatch.call — so token_cost_usd "
            "is 0 for every arm and every delta is ~0. This is the keystone "
            "finding: the instrument measures compounding (proven by "
            "tests/test_falsifiability.py), but the demo loop does NOT consume "
            "reuse, so compounding is UNPROVEN on the real loop. A live "
            "mock_run=false run with a reuse-consuming browse loop + provider "
            "creds is the operator-window measurement. validity_reason: "
            f"{verdict.validity_reason}. headline_reason: {verdict.headline_reason}."
        )

    return BenchmarkResult(
        frozen_sha=qs.frozen_sha,
        seed=seed,
        n=n,
        ci_method="bias_corrected_bootstrap",
        bootstrap_resamples=resamples,
        mock_run=mock_run,
        validity=verdict.validity,
        headline_interpretation=verdict.interpretation,
        git_sha=git_sha or GIT_SHA_PLACEHOLDER,
        captured_at=_now_iso(),
        headline=headline,
        comparisons=[headline, internal_probe, partial, control],
        control_tolerance=control_tolerance,
        material_floor=material_floor,
        parameters_ratified=parameters_ratified,
        ratification_ref=ratification_ref,
        loop_kind=loop_kind,
        notes=notes,
    )


def _refuse_prod_run(profile: BenchmarkProfile) -> int:
    """SPR-11 — refuse to execute a prod-shaped LIVE run from this build
    environment and print the exact operator-window command instead.

    Honors the phase split + rigor #1: the prod RUN needs prod model-tier
    credentials, the box, AND a reuse-consuming browse loop that does not
    exist here. We do NOT fall back to the demo-loop mocks to manufacture a
    green ``prod-<sha>.json`` — a non-reproducing (or not-yet-run) prod curve
    is the honest finding, not a thing to fake. Returns exit 2
    (could-not-complete), matching the existing ``--mock-run false`` refusal."""
    sha = read_git_sha()
    out_name = profile.out_filename(sha)
    print(
        f"REFUSED: --profile {profile.name!r} is a PROD-SHAPED real-dispatch run "
        f"(mock_run={profile.mock_run}, dispatch_mode={profile.dispatch_mode!r}).\n"
        "SPR-11 BUILDS the selector but DEFERS the live run to the operator window — "
        "it needs (1) prod model-tier credentials, (2) the box (the live runtime), "
        "and (3) a reuse-CONSUMING browse loop (the host-local demo loop is "
        "reuse-blind). It will NOT fall back to mocks to fabricate a green curve.\n\n"
        "Operator-window run (on the box, with prod creds + a reuse-consuming loop):\n"
        f"    python -m compounding.benchmark.run --profile {profile.name} \\\n"
        f"        --n {profile.n} --material-floor {profile.material_floor} "
        f"--control-tolerance {profile.control_tolerance}\n"
        f"  → writes compounding/benchmark/results/{out_name}\n"
        f"    (the diff-able twin of the dev spr09_run.json; prod tiers: "
        f"{profile.model_tiers}).\n\n"
        "Then interpret per rigor #1: EITHER 'cost-to-resolve falls as the graph "
        "grows, slope reproduces dev within tolerance' OR 'does NOT reproduce — "
        "here is the curve + the gap'. A non-reproduction is a valid EXIT outcome."
    )
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AFF SPR-09 compounding benchmark (mock + pilot)")
    ap.add_argument("--question-set", default=QUESTION_SET_PATH)
    ap.add_argument("--n", type=int, default=MOCK_N,
                    help="runs per question×arm (mock default 20; live n is operator-ratified)")
    ap.add_argument("--resamples", type=int, default=MOCK_RESAMPLES)
    ap.add_argument(
        "--out", default=DEFAULT_RUN_OUT,
        help="output path. Default writes a GITIGNORED transient twin "
        "(results/spr09_run.local.json) so an exploratory run never dirties the "
        "tracked baseline. To re-mint the committed baseline, pass "
        "--out compounding/benchmark/results/spr09_run.json explicitly (then git add -f).",
    )
    ap.add_argument("--material-floor", type=float, default=0.0)
    ap.add_argument("--control-tolerance", type=float, default=0.0)
    ap.add_argument("--pilot", action="store_true",
                    help="run the pilot (5 runs/cell on representative questions), "
                         "print the DERIVED parameter proposal, AND persist a pilot-report "
                         "artifact (observed CV + proposed params) that --ratified references")
    ap.add_argument("--loop", default=LOOP_DEMO, choices=[LOOP_DEMO, LOOP_CONSUMING],
                    help="browse loop for the benchmark arms. 'demo' (default) = the "
                         "reuse-blind demo loop (the keystone null, kept for fast unit CI); "
                         "'consuming' = the reuse-CONSUMING loop that skips covered steps "
                         "(the REAL arm — warm does less work than cold, delta < 0).")
    ap.add_argument("--ratified", action="store_true",
                    help="record parameters_ratified=true in the artifact. OMITTING it "
                         "leaves it false (never silently true). A scored (mock_run=false) "
                         "artifact WITHOUT this fails the ratified-scoring CI gate "
                         "(tools/ratified_gate.py). This flag asserts the OPERATOR ratified "
                         "the pilot-derived n/floor/tolerance (decision-0.2 §A.6) — it is "
                         "the human ratification step's machine record, not a self-grade.")
    ap.add_argument("--ratification-ref", default=None,
                    help="the pilot-report artifact id / decision reference the --ratified "
                         "flag ratifies against (recorded as ratification_ref for audit). "
                         "Required to be non-empty when --ratified is passed.")
    ap.add_argument("--pilot-out", default=None,
                    help="path for the persisted pilot-report artifact (default: "
                         "results/pilot_report.json). Used with --pilot.")
    ap.add_argument("--mock-run", default="true",
                    help="true (the only Phase-1 path) | false (live; needs provider creds + "
                         "operator-ratified n — refused here)")
    ap.add_argument("--profile", default="dev",
                    help="benchmark profile selector (SPR-11). 'dev' (default) = the "
                         "autonomous mock run; 'prod' = the prod-shaped real-dispatch run "
                         "(profiles/prod.toml). A prod profile's LIVE run is the operator "
                         "window — run.py prints the exact command and REFUSES to execute "
                         "it here (it never mocks around to fabricate a green).")
    args = ap.parse_args(argv)

    qs = load_question_set(args.question_set)

    # SPR-11 — ADDITIVE profile selector. Loading a profile that uses real
    # dispatch (prod) flips mock_run False; this build environment cannot
    # execute it (no creds, no box, no reuse-consuming loop), so we REFUSE
    # and print the exact operator-window command rather than mock around.
    # The dev profile is the existing autonomous mock path, untouched.
    try:
        profile: BenchmarkProfile = load_profile(args.profile)
    except (FileNotFoundError, ValueError) as exc:
        print(f"REFUSED: could not load --profile {args.profile!r}: {exc}")
        return 2
    if profile.uses_real_dispatch:
        return _refuse_prod_run(profile)

    if str(args.mock_run).lower() == "false":
        print(
            "REFUSED: a live (mock_run=false) run needs provider credentials, an "
            "operator window, AND operator-ratified n/floor/tolerance (decision "
            "0.2). Phase 1 produces only the mock artifact + the live-run "
            "instructions (see compounding/benchmark/README.md)."
        )
        return 2

    tmp = tempfile.mkdtemp(prefix="spr09_")
    events_dir = os.path.join(tmp, "events")
    graphs_dir = os.path.join(tmp, "graphs")

    if args.pilot:
        rep = [q for q in qs.headline_questions()[:2]] + qs.by_class("zero_overlap_control")[:1]
        report = run_pilot(rep, events_dir=events_dir, graphs_dir=graphs_dir, runs_per_cell=5)
        proposal = propose_parameters(report.cv, cold_means=report.cold_means)
        print("PILOT — realized per-metric CV (cold arm):")
        for m, v in report.cv.items():
            print(f"  {m}: CV={v:.6g}  cold_mean={report.cold_means[m]:.6g}")
        print("\nPROPOSED parameters (operator ratifies before any scored run — §0.2):")
        print(f"  n                 = {proposal.n}")
        print(f"  material_floor    = {proposal.material_floor:.6g}")
        print(f"  control_tolerance = {proposal.control_tolerance:.6g}")
        print(f"  derivation        = {proposal.derivation}")
        # ACV SPR-06 (B3 / decision-0.2 §C.3): PERSIST the pilot report so the
        # operator ratifies a committed artifact and --ratified can reference it.
        pilot_out = args.pilot_out or PILOT_REPORT_PATH
        pilot_id = write_pilot_report(
            report, proposal, path=pilot_out,
            frozen_sha=qs.frozen_sha, git_sha=read_git_sha(),
        )
        print(f"\nwrote pilot report {pilot_out}")
        print(f"  pilot_report_id = {pilot_id}")
        print(
            "  NEXT (operator): ratify the derived n/floor/tolerance into "
            "decision-0.2 §A.6, then — ON THE OPERATOR WINDOW (prod creds + the "
            "box + a real reuse-consuming loop) — run the PROD path:\n"
            f"    run --profile prod --ratified --ratification-ref {pilot_id}\n"
            "  That emits the SCORED (mock_run=false) artifact the ratified gate "
            "fires on. NOTE: a dev `--loop consuming … --ratified` run records the "
            "ratification but stays mock_run=true (gate-EXEMPT) — it is NOT the "
            "scored artifact. (decision-0.2 §A.6/§C.4; "
            "docs/decisions/ratified-scoring-gate.md.)"
        )
        return 0

    # ACV SPR-06: --ratified requires a non-empty ratification ref so the scored
    # artifact records WHAT was ratified (M3 auditability — never a bare boolean).
    if args.ratified and not (args.ratification_ref and args.ratification_ref.strip()):
        print(
            "REFUSED: --ratified requires --ratification-ref <pilot_report_id|decision-ref> "
            "so the scored artifact records WHAT was ratified (decision-0.2 §A.6). "
            "Run --pilot first to produce a pilot_report_id."
        )
        return 2

    result = run_benchmark(
        qs,
        events_dir=events_dir,
        graphs_dir=graphs_dir,
        n=args.n,
        resamples=args.resamples,
        material_floor=args.material_floor,
        control_tolerance=args.control_tolerance,
        mock_run=True,
        git_sha=read_git_sha(),
        parameters_ratified=bool(args.ratified),
        ratification_ref=(args.ratification_ref.strip() if args.ratified else None),
        loop_kind=args.loop,
    )
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    result.write(args.out)

    print(f"wrote {args.out}")
    print(f"  frozen_sha = {result.frozen_sha}")
    print(f"  n          = {result.n}  mock_run = {result.mock_run}")
    print(f"  validity   = {result.validity}")
    print(f"  verdict    = {result.headline.metric(HEADLINE_METRIC).delta:+.6g} "
          f"[{result.headline.metric(HEADLINE_METRIC).ci_low:+.6g}, "
          f"{result.headline.metric(HEADLINE_METRIC).ci_high:+.6g}] {HEADLINE_METRIC}")
    print(f"  interpretation = {result.headline_interpretation}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
