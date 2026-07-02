#!/usr/bin/env python3
"""Flaky-quarantine harness — re-run-N with order-shuffle, propose isolation entries.

Antiek × Beck Test-Integrity, SPR-04. Dynamically confirms what SPR-03's static
desiderata lint cannot: tests that flap across shuffled runs or fail only in the
full-suite context. Quarantine ISOLATES — it never deletes, skips, or edits tests.

CLI::

    python -m tools.flaky_quarantine --n 3 [--paths tests/...] [--shuffle-seeds 1,2,3]
    python -m tools.flaky_quarantine --propose ...
    python -m tools.flaky_quarantine --check ...

STDLIB + existing repo test env only. No live model, no network dependency beyond
what the existing mocked suite already uses.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

_REPO = Path(__file__).resolve().parents[1]
_DEFAULT_QUARANTINE = _REPO / "tests" / "quarantine.toml"

# SPR-03 dog-food candidate list (determinism + isolation findings).
SPR03_DEFAULT_PATHS: tuple[str, ...] = (
    "tests/test_magic_link_auth.py",
    "tests/test_retrieval_gate_matrix.py",
)

# Default N=3: catches common order-dependence + high-rate flappers within the
# repo's 40-minute CI ceiling. A 1-in-20 rare flapper needs a nightly higher-N
# pass — do not silently raise N here.
DEFAULT_N = 3
DEFAULT_SHUFFLE_SEEDS: tuple[int, ...] = (1, 2, 3)

FailureClass = Literal["nondeterministic", "non-composable"]
Reason = Literal[
    "order-dependent",
    "rng-flap",
    "clock-flap",
    "async-race",
    "resource-leak",
    "unknown-flap",
]

REASONS: tuple[Reason, ...] = (
    "order-dependent",
    "rng-flap",
    "clock-flap",
    "async-race",
    "resource-leak",
    "unknown-flap",
)

_PYTEST_BASE: tuple[str, ...] = (
    sys.executable,
    "-m",
    "pytest",
    "-q",
    "-p",
    "no:cacheprovider",
    "-p",
    "no:xdist",
    "-p",
    "tools.flaky_quarantine_pytest",
)


@dataclass(frozen=True)
class QuarantineEntry:
    nodeid: str
    reason: str
    evidence: str
    quarantined_at: str
    quarantined_by: str
    promote_when: str
    ignore_failures: bool = True


@dataclass
class FlapperFinding:
    nodeid: str
    failure_class: FailureClass
    reason: Reason
    evidence: str
    seeds: list[int] = field(default_factory=list)


def load_quarantine(path: Path | None = None) -> list[QuarantineEntry]:
    """Load committed quarantine ledger entries from ``tests/quarantine.toml``."""
    ledger = path or _DEFAULT_QUARANTINE
    if not ledger.is_file():
        return []
    raw = tomllib.loads(ledger.read_text(encoding="utf-8"))
    entries: list[QuarantineEntry] = []
    for row in raw.get("quarantine", []):
        entries.append(
            QuarantineEntry(
                nodeid=str(row["nodeid"]),
                reason=str(row["reason"]),
                evidence=str(row["evidence"]),
                quarantined_at=str(row["quarantined_at"]),
                quarantined_by=str(row["quarantined_by"]),
                promote_when=str(row["promote_when"]),
                ignore_failures=bool(row.get("ignore_failures", True)),
            )
        )
    return entries


def _parse_seeds(raw: str | None, n: int) -> list[int]:
    if raw is None:
        return list(DEFAULT_SHUFFLE_SEEDS[:n])
    seeds = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if len(seeds) < n:
        raise SystemExit(
            f"--shuffle-seeds has {len(seeds)} seed(s) but --n is {n}; "
            "provide at least N seeds."
        )
    return seeds[:n]


def _spr03_findings(root: Path) -> dict[str, tuple[str, str]]:
    """Map test file path -> (rule, message) from SPR-03 desiderata lint."""
    from tools.lint.test_desiderata_check import find_violations

    paths = [root / p for p in SPR03_DEFAULT_PATHS]
    out: dict[str, tuple[str, str]] = {}
    for v in find_violations(paths, rules=("isolation", "determinism"), root=root):
        if v.severity != "violation":
            continue
        out[v.path] = (v.rule, v.message)
    return out


def _infer_reason(
    nodeid: str,
    failure_class: FailureClass,
    spr03: dict[str, tuple[str, str]],
) -> Reason:
    file_path = nodeid.split("::", 1)[0]
    for path, (rule, message) in spr03.items():
        if file_path == path or file_path.endswith(path):
            if rule == "isolation":
                return "order-dependent"
            if rule == "determinism":
                lower = message.lower()
                if "time" in lower or "clock" in lower:
                    return "clock-flap"
                if "random" in lower or "rng" in lower or "uuid" in lower:
                    return "rng-flap"
                if "network" in lower:
                    return "async-race"
    if failure_class == "non-composable":
        return "order-dependent"
    lower_nid = nodeid.lower()
    if "rng" in lower_nid or "random" in lower_nid:
        return "rng-flap"
    if "clock" in lower_nid or "time" in lower_nid:
        return "clock-flap"
    if "order" in lower_nid:
        return "order-dependent"
    return "unknown-flap"


def _run_pytest(
    selector: list[str],
    *,
    repo: Path,
    shuffle_seed: int | None,
    timeout_s: int,
) -> dict[str, bool | None]:
    """Run pytest and return nodeid -> passed (None if not collected/ran)."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        results_path = tmp.name
    env = os.environ.copy()
    env["FLAKY_QUARANTINE_RESULTS_FILE"] = results_path
    if shuffle_seed is not None:
        env["FLAKY_QUARANTINE_SHUFFLE_SEED"] = str(shuffle_seed)
    else:
        env.pop("FLAKY_QUARANTINE_SHUFFLE_SEED", None)
    cmd = [*_PYTEST_BASE, *selector]
    try:
        subprocess.run(
            cmd,
            cwd=str(repo),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    finally:
        pass
    outcomes: dict[str, bool | None] = {}
    results_file = Path(results_path)
    if results_file.is_file():
        for line in results_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            outcomes[str(rec["nodeid"])] = bool(rec["passed"])
        results_file.unlink(missing_ok=True)
    return outcomes


def _collect_nodeids(paths: list[str], repo: Path, timeout_s: int) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-p",
        "no:xdist",
        *paths,
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    nodeids: list[str] = []
    for line in (proc.stdout + proc.stderr).splitlines():
        s = line.strip()
        if s.startswith("<") or "test session starts" in s or not s:
            continue
        if "::" in s and not s.startswith("="):
            token = s.split()[0]
            if "::" in token:
                nodeids.append(token)
    return sorted(set(nodeids))


def _format_evidence(
    *,
    failure_class: FailureClass,
    outcomes: list[bool | None],
    seeds: list[int],
    alone: bool | None,
) -> str:
    passed = sum(1 for o in outcomes if o is True)
    total = len(outcomes)
    fail_seeds = [str(seeds[i]) for i, o in enumerate(outcomes) if o is False]
    seed_note = f"failed at shuffle-seed {', '.join(fail_seeds)}" if fail_seeds else "no shuffle failures"
    base = f"{passed}/{total} runs passed; {seed_note}"
    if failure_class == "non-composable" and alone is not None:
        alone_txt = "passed" if alone else "failed"
        base += f"; alone-run {alone_txt} vs suite"
    return base


def detect_flappers(
    paths: list[str],
    *,
    n: int = DEFAULT_N,
    seeds: list[int] | None = None,
    repo: Path = _REPO,
    timeout_s: int = 600,
    spr03: dict[str, tuple[str, str]] | None = None,
) -> list[FlapperFinding]:
    """Run N shuffled suite passes and detect nondeterministic / non-composable tests."""
    seed_list = seeds or list(DEFAULT_SHUFFLE_SEEDS[:n])
    spr03 = spr03 if spr03 is not None else _spr03_findings(repo)

    collect_timeout = min(timeout_s, 300)
    nodeids = _collect_nodeids(paths, repo, collect_timeout)
    selector = nodeids if nodeids else paths

    per_run: list[dict[str, bool | None]] = []
    for seed in seed_list:
        per_run.append(
            _run_pytest(selector, repo=repo, shuffle_seed=seed, timeout_s=timeout_s)
        )
    for run in per_run:
        nodeids = sorted(set(nodeids) | set(run.keys()))
    if not nodeids:
        return []

    findings: dict[tuple[str, FailureClass], FlapperFinding] = {}

    for nodeid in nodeids:
        outcomes = [run.get(nodeid) for run in per_run]
        observed = [o for o in outcomes if o is not None]
        if not observed:
            continue

        nondeterministic = len({o for o in observed}) > 1
        if nondeterministic:
            reason = _infer_reason(nodeid, "nondeterministic", spr03)
            key = (nodeid, "nondeterministic")
            findings[key] = FlapperFinding(
                nodeid=nodeid,
                failure_class="nondeterministic",
                reason=reason,
                evidence=_format_evidence(
                    failure_class="nondeterministic",
                    outcomes=outcomes,
                    seeds=seed_list,
                    alone=None,
                ),
                seeds=seed_list,
            )

        alone = _run_pytest([nodeid], repo=repo, shuffle_seed=None, timeout_s=timeout_s).get(nodeid)
        suite_all_pass = observed and all(o is True for o in observed)
        suite_any_fail = any(o is False for o in observed)
        non_composable = False
        if alone is True and suite_any_fail:
            non_composable = True
        if alone is False and suite_all_pass:
            non_composable = True

        if non_composable:
            reason = _infer_reason(nodeid, "non-composable", spr03)
            key = (nodeid, "non-composable")
            findings[key] = FlapperFinding(
                nodeid=nodeid,
                failure_class="non-composable",
                reason=reason,
                evidence=_format_evidence(
                    failure_class="non-composable",
                    outcomes=outcomes,
                    seeds=seed_list,
                    alone=alone,
                ),
                seeds=seed_list,
            )

    return sorted(findings.values(), key=lambda f: (f.nodeid, f.failure_class))


def propose_entries(
    findings: list[FlapperFinding],
    *,
    quarantined_by: str = "flaky_quarantine --propose",
    promote_n: int = DEFAULT_N,
) -> list[QuarantineEntry]:
    today = date.today().isoformat()
    promote_when = f"passes {promote_n} consecutive shuffled runs"
    by_nodeid: dict[str, FlapperFinding] = {}
    for f in findings:
        prev = by_nodeid.get(f.nodeid)
        if prev is None or f.failure_class == "nondeterministic":
            by_nodeid[f.nodeid] = f
    entries: list[QuarantineEntry] = []
    for f in sorted(by_nodeid.values(), key=lambda x: x.nodeid):
        entries.append(
            QuarantineEntry(
                nodeid=f.nodeid,
                reason=f.reason,
                evidence=f.evidence,
                quarantined_at=today,
                quarantined_by=quarantined_by,
                promote_when=promote_when,
                ignore_failures=True,
            )
        )
    return entries


def render_proposal_toml(entries: list[QuarantineEntry]) -> str:
    if not entries:
        return "# No flapper proposals for this run.\n"
    lines = ["# Proposed quarantine entries — operator reviews before committing.\n"]
    for e in entries:
        lines.extend(
            [
                "[[quarantine]]",
                f'nodeid = "{e.nodeid}"',
                f'reason = "{e.reason}"',
                f'evidence = "{e.evidence}"',
                f'quarantined_at = "{e.quarantined_at}"',
                f'quarantined_by = "{e.quarantined_by}"',
                f'promote_when = "{e.promote_when}"',
                f"ignore_failures = {'true' if e.ignore_failures else 'false'}",
                "",
            ]
        )
    return "\n".join(lines)


def check_promote_candidates(
    entries: list[QuarantineEntry],
    *,
    n: int = DEFAULT_N,
    seeds: list[int] | None = None,
    repo: Path = _REPO,
    timeout_s: int = 600,
) -> list[tuple[QuarantineEntry, bool]]:
    """Return (entry, passes_all_n) for each quarantined nodeid."""
    seed_list = seeds or list(DEFAULT_SHUFFLE_SEEDS[:n])
    results: list[tuple[QuarantineEntry, bool]] = []
    for entry in entries:
        outcomes: list[bool | None] = []
        for seed in seed_list:
            run = _run_pytest([entry.nodeid], repo=repo, shuffle_seed=seed, timeout_s=timeout_s)
            outcomes.append(run.get(entry.nodeid))
        observed = [o for o in outcomes if o is not None]
        passes_all = bool(observed) and all(o is True for o in observed)
        results.append((entry, passes_all))
    return results


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-run tests N times with order-shuffle; detect and propose flaky quarantine entries.",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=DEFAULT_N,
        help=f"Number of shuffled runs (default {DEFAULT_N}).",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Test paths to scan (default: SPR-03 candidate list).",
    )
    parser.add_argument(
        "--shuffle-seeds",
        default=None,
        help="Comma-separated shuffle seeds (default 1,2,3 — one per run).",
    )
    parser.add_argument(
        "--propose",
        action="store_true",
        help="Emit proposed quarantine.toml entries to stdout.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check committed quarantine.toml for promote-back candidates.",
    )
    parser.add_argument(
        "--quarantine-toml",
        default=str(_DEFAULT_QUARANTINE),
        help="Path to quarantine ledger.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Per-pytest-invocation timeout in seconds.",
    )
    return parser.parse_args(argv if argv is not None else sys.argv[1:])


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo = _REPO
    paths = args.paths if args.paths else list(SPR03_DEFAULT_PATHS)
    seeds = _parse_seeds(args.shuffle_seeds, args.n)
    ledger = Path(args.quarantine_toml)

    if args.check:
        entries = load_quarantine(ledger)
        if not entries:
            print("No committed quarantine entries.")
            return 0
        print(f"Checking {len(entries)} quarantined nodeid(s) over {args.n} shuffled run(s)...")
        for entry, passes_all in check_promote_candidates(
            entries, n=args.n, seeds=seeds, repo=repo, timeout_s=args.timeout
        ):
            status = "PROMOTE-CANDIDATE" if passes_all else "still-quarantined"
            print(f"{entry.nodeid}: {status} ({entry.promote_when})")
        return 0

    findings = detect_flappers(
        paths,
        n=args.n,
        seeds=seeds,
        repo=repo,
        timeout_s=args.timeout,
    )

    if args.propose:
        entries = propose_entries(findings, promote_n=args.n)
        sys.stdout.write(render_proposal_toml(entries))
        return 0

    if not findings:
        print(f"OK: no flappers detected across {args.n} shuffled run(s) on {paths!r}.")
        return 0
    print(f"Flappers detected: {len(findings)}")
    for f in findings:
        print(f"  {f.nodeid} [{f.failure_class}] reason={f.reason} evidence={f.evidence}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())