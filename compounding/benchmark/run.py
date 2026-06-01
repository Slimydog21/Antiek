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
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from .aggregate import DEFAULT_BOOTSTRAP_RESAMPLES, aggregate_comparison
from .harness import ArmResult, ColdSeed, IrrelevantSeed, WarmSeed, run_arm
from .measure import CostToResolve
from .pilot import propose_parameters, run_pilot
from .question_set import QUESTION_SET_PATH, QuestionSet, load_question_set
from .result_schema import ArmComparison, BenchmarkResult
from .validity import HEADLINE_METRIC, decide

RESULTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "spr09_run.json")

# Documented placeholder. The recorded artifact's git_sha is set by the
# orchestrator's commit (the artifact is written BEFORE the commit exists), so a
# from-the-run artifact carries this sentinel until re-stamped. The README
# documents this; the verification gate notes the sha matches only post-commit.
GIT_SHA_PLACEHOLDER = "PENDING_COMMIT"

# Default mock parameters (§2): the mock artifact only. The LIVE n is operator-
# ratified after the pilot (decision 0.2) — never baked in here.
MOCK_N = 20
MOCK_RESAMPLES = DEFAULT_BOOTSTRAP_RESAMPLES


def read_git_sha(repo_root: Optional[str] = None) -> str:
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
        with open(os.path.join(git_dir, "HEAD"), "r", encoding="utf-8") as f:
            head = f.read().strip()
        if head.startswith("ref:"):
            ref = head[4:].strip()
            with open(os.path.join(git_dir, ref), "r", encoding="utf-8") as f:
                return f.read().strip()[:7]
        return head[:7]
    except OSError:
        return GIT_SHA_PLACEHOLDER


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_cell(
    questions: Sequence,
    arm_seed,
    *,
    events_dir: str,
    graphs_dir: str,
    n: int,
) -> Dict[str, List[CostToResolve]]:
    """Run ``n`` runs of ``arm_seed`` for each question. Returns
    ``{question_id: [CostToResolve, ...]}`` (n entries per question)."""
    out: Dict[str, List[CostToResolve]] = {}
    for q in questions:
        runs: List[CostToResolve] = []
        for run_index in range(n):
            res: ArmResult = run_arm(
                q, arm_seed, events_dir=events_dir, graphs_dir=graphs_dir,
                run_index=run_index,
            )
            runs.append(res.cost)
        out[q.question_id] = runs
    return out


def _pool(cell: Dict[str, List[CostToResolve]], question_ids: Sequence[str]) -> List[CostToResolve]:
    """Pool the per-run CostToResolve across the given questions into one list
    (run order preserved per question, questions concatenated) so the aggregator
    pairs warm[i] vs cold[i] within the pooled stream."""
    pooled: List[CostToResolve] = []
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
    git_sha: Optional[str] = None,
    parameters_ratified: bool = False,
) -> BenchmarkResult:
    """Drive every arm over the frozen set, aggregate, gate, and build the
    artifact. ``material_floor`` / ``control_tolerance`` are operator-ratified
    for a scored run; for the mock artifact they default to 0 (the demo loop's
    zero-variance null makes any positive floor trivially unmet — the verdict is
    null regardless, and the README is explicit about it)."""
    seed = qs.seed
    headline_qids = [q.question_id for q in qs.headline_questions()]
    internal_qids = [q.question_id for q in qs.by_class("high_overlap") if not q.headline_pooled]
    partial_qids = [q.question_id for q in qs.by_class("partial_overlap")]
    control_qids = [q.question_id for q in qs.control_questions()]
    all_qs = list(qs.questions)

    cold = _run_cell(all_qs, ColdSeed(), events_dir=events_dir, graphs_dir=graphs_dir, n=n)
    warm = _run_cell(all_qs, WarmSeed(), events_dir=events_dir, graphs_dir=graphs_dir, n=n)
    irrelevant = _run_cell(all_qs, IrrelevantSeed(), events_dir=events_dir, graphs_dir=graphs_dir, n=n)

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
    per_domain_points: List[float] = []
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
        notes=(
            "MOCK run on the host-local demo loop (make_demo_loop), which is "
            "reuse-blind and makes no provider dispatch.call — so token_cost_usd "
            "is 0 for every arm and every delta is ~0. This is the keystone "
            "finding: the instrument measures compounding (proven by "
            "tests/test_falsifiability.py), but the demo loop does NOT consume "
            "reuse, so compounding is UNPROVEN on the real loop. A live "
            "mock_run=false run with a reuse-consuming browse loop + provider "
            "creds is the operator-window measurement. validity_reason: "
            f"{verdict.validity_reason}. headline_reason: {verdict.headline_reason}."
        ),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="AFF SPR-09 compounding benchmark (mock + pilot)")
    ap.add_argument("--question-set", default=QUESTION_SET_PATH)
    ap.add_argument("--n", type=int, default=MOCK_N,
                    help="runs per question×arm (mock default 20; live n is operator-ratified)")
    ap.add_argument("--resamples", type=int, default=MOCK_RESAMPLES)
    ap.add_argument("--out", default=RESULTS_PATH)
    ap.add_argument("--material-floor", type=float, default=0.0)
    ap.add_argument("--control-tolerance", type=float, default=0.0)
    ap.add_argument("--pilot", action="store_true",
                    help="run the pilot (5 runs/cell on representative questions) and "
                         "print the DERIVED parameter proposal; does not write the artifact")
    ap.add_argument("--mock-run", default="true",
                    help="true (the only Phase-1 path) | false (live; needs provider creds + "
                         "operator-ratified n — refused here)")
    args = ap.parse_args(argv)

    qs = load_question_set(args.question_set)

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
        return 0

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
