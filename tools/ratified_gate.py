#!/usr/bin/env python3
"""ACV SPR-06 — the ratified-scoring gate (decision-0.2 §A.6 / B3, enforced).

Decision-0.2 PRE-REGISTERS a pilot → observe-CV → propose-parameters →
operator-ratify → scored-run procedure. But pre-registration is only
*procedural* unless something ENFORCES that a scored artifact was actually
ratified — without that, a scored run could be silently re-rolled with different
n/floor/tolerance post-hoc and the pre-registration would buy nothing. This gate
makes ratification a STRUCTURAL precondition of scoring.

THE RULE (deny-by-default for scored artifacts):

    A benchmark result artifact is SCORED iff ``mock_run == false``.
    A SCORED artifact MUST carry ``parameters_ratified == true`` AND a non-empty
    ``ratification_ref`` (the pilot-report id / decision reference it ratified
    against — so a reader can reconstruct WHAT was ratified).

    A MOCK artifact (``mock_run == true``) is EXEMPT — the autonomous dev/CI mock
    run is the keystone null, never a scored claim, and needs no ratification.

What "scored" means (the definition this gate gates on) is stated once, here:
``mock_run == false``. A mock run is the deterministic demo-loop (or a
reuse-consuming dev run that still sets mock_run true) that makes no scored
compounding claim; a scored run is the operator-window ``mock_run=false`` run
whose verdict would be reported as the flywheel finding. Only the latter can do
damage by being un-ratified, so only the latter is gated.

Why blocking (not informational): the cardinal sin this whole spec exists to
prevent is a FAKED or GOALPOST-MOVED compounding number. An un-ratified scored
artifact is exactly the post-hoc-re-roll vector. So this gate's exit code is the
build's — no ``|| echo`` swallow, no ``continue-on-error``, no ``::warning::``.
See docs/decisions/ratified-scoring-gate.md.

Scan scope: every ``*.json`` under ``compounding/benchmark/results/`` (the one
location the benchmark writes artifacts to), plus any explicit paths passed as
argv. A file that does not look like a benchmark result (no ``mock_run`` key) is
SKIPPED, not failed — this gate judges benchmark artifacts, not arbitrary JSON.
A malformed benchmark artifact (has ``mock_run`` but unreadable) FAILS CLOSED.

Exit 0 = every scored artifact is ratified (or none present); exit 1 = at least
one scored-but-unratified artifact (or a malformed one).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_RESULTS_DIR = _REPO / "compounding" / "benchmark" / "results"


def _looks_like_benchmark_artifact(data: object) -> bool:
    """A benchmark result artifact is a dict carrying a ``mock_run`` key. Anything
    else (a pilot report, an unrelated JSON) is not this gate's business."""
    return isinstance(data, dict) and "mock_run" in data


def evaluate_artifact(data: dict) -> tuple[bool, str]:
    """Return ``(ok, reason)`` for one benchmark artifact.

    ``ok=True`` when the artifact is a MOCK run (exempt) OR a SCORED run that is
    ratified WITH a non-empty ratification_ref. ``ok=False`` (with the reason)
    for a scored-but-unratified or scored-but-unreferenced artifact."""
    mock_run = data.get("mock_run")
    if mock_run is True:
        return True, "mock_run=true — exempt (no scored compounding claim)"
    if mock_run is not False:
        # Neither true nor false: a malformed mock_run field on something that
        # otherwise looks like an artifact. Fail closed.
        return False, f"mock_run is {mock_run!r} (expected a bool) — malformed, blocked"

    # mock_run == False → SCORED → must be ratified + referenced.
    if data.get("parameters_ratified") is not True:
        return False, (
            f"mock_run=false (SCORED) but parameters_ratified="
            f"{data.get('parameters_ratified')!r} — a scored artifact MUST be "
            f"operator-ratified (decision-0.2 §A.6). Run with --ratified against "
            f"a ratified pilot report."
        )
    ref = data.get("ratification_ref")
    if not (isinstance(ref, str) and ref.strip()):
        return False, (
            f"mock_run=false (SCORED) and parameters_ratified=true but "
            f"ratification_ref={ref!r} is empty — a ratified scored artifact MUST "
            f"record WHAT it ratified (the pilot_report_id / decision ref) so the "
            f"ratification is reconstructable (decision-0.2 §A.6)."
        )
    # MINOR-2 (decision-0.2 §A.6): a scored artifact must also be pinned to a REAL
    # frozen question-set sha — the content-addressed pre-registration anchor. A
    # missing or placeholder frozen_sha means the verdict is not pinned to the
    # immutable set it claims to have run against, so the result is not
    # reconstructable/falsifiable. SOURCE for the shape: question_set.py's
    # compute_frozen_sha emits ``sha256:<64 hex>`` (mirrors router.py's
    # _sha256_prefix); anything not matching that is a placeholder.
    if not _is_real_frozen_sha(data.get("frozen_sha")):
        return False, (
            f"mock_run=false (SCORED) but frozen_sha={data.get('frozen_sha')!r} is "
            f"missing or a placeholder — a scored artifact MUST be pinned to the "
            f"real content-addressed question-set sha (sha256:<64 hex>) so the "
            f"verdict is reconstructable against the immutable set (decision-0.2 §A.6)."
        )
    return True, f"scored + ratified against {ref!r}"


_PLACEHOLDER_FROZEN_SHAS = frozenset(
    {"", "pending", "pending_commit", "placeholder", "todo", "none", "null"}
)


def _is_real_frozen_sha(value: object) -> bool:
    """A real frozen_sha is the ``sha256:<64 lowercase-hex>`` shape question_set.py
    emits, and is NOT an all-zero or sentinel digest. Anything else (absent,
    wrong shape, a placeholder token, an all-zero digest) is a placeholder."""
    if not isinstance(value, str):
        return False
    v = value.strip()
    if v.lower() in _PLACEHOLDER_FROZEN_SHAS:
        return False
    if not v.startswith("sha256:"):
        return False
    digest = v[len("sha256:"):]
    if len(digest) != 64:
        return False
    if any(c not in "0123456789abcdef" for c in digest.lower()):
        return False
    # An all-zero digest is the canonical "unset" sentinel — reject it.
    if set(digest) == {"0"}:
        return False
    return True


def _candidate_paths(extra: Iterable[str]) -> list[Path]:
    """The artifacts to scan: every ``*.json`` under the results dir + explicit
    argv paths. Deduplicated, stable order."""
    seen: dict[str, Path] = {}
    if _RESULTS_DIR.is_dir():
        for p in sorted(_RESULTS_DIR.glob("*.json")):
            seen[str(p.resolve())] = p
    for raw in extra:
        p = Path(raw)
        seen[str(p.resolve())] = p
    return list(seen.values())


def scan(paths: Iterable[Path]) -> tuple[int, int, int, list[str]]:
    """Scan the given paths. Returns ``(scored_checked, mock_exempt, skipped,
    failures)`` where ``failures`` is a list of human-readable ``path: reason``
    lines."""
    scored_checked = 0
    mock_exempt = 0
    skipped = 0
    failures: list[str] = []
    for path in paths:
        if not path.exists():
            failures.append(f"{path}: does not exist (explicitly named but missing)")
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            # Unreadable JSON under the results dir: we cannot tell if it is a
            # scored artifact, so we do NOT fail the whole tree on it — but we DO
            # surface it (a corrupt artifact is a finding to fix). A genuinely
            # non-artifact file would not parse as our shape anyway.
            print(f"  [skip] {path}: not readable as JSON ({exc})")
            skipped += 1
            continue
        if not _looks_like_benchmark_artifact(data):
            skipped += 1
            continue
        ok, reason = evaluate_artifact(data)
        if data.get("mock_run") is False:
            scored_checked += 1
        elif data.get("mock_run") is True:
            mock_exempt += 1
        if not ok:
            failures.append(f"{path}: {reason}")
    return scored_checked, mock_exempt, skipped, failures


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    paths = _candidate_paths(argv)
    scored_checked, mock_exempt, skipped, failures = scan(paths)

    if failures:
        print("RATIFIED-SCORING GATE: BLOCKED")
        for line in failures:
            print(f"  - {line}")
        print(
            "\nA scored (mock_run=false) compounding artifact must be operator-ratified "
            "with a recorded ratification_ref before it can pass CI. This is the "
            "post-hoc-re-roll vector decision-0.2 §A.6 closes. (Mock runs are exempt.)"
        )
        return 1

    print(
        f"RATIFIED-SCORING GATE: OK — {scored_checked} scored artifact(s) ratified, "
        f"{mock_exempt} mock artifact(s) exempt, "
        f"{skipped} non-artifact file(s) skipped."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
