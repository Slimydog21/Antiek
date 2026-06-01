#!/usr/bin/env python3
"""Source-onboarding kill-gate (reframe finding #2) — the WIRED stop-rule that
blocks onboarding any source AFTER arXiv whose corpus-value census falls below the
bar.

This replaces the arXiv spec's PROSE "measure before build" success-criterion with
a machine-checked gate node: it reads the per-source census at
``reports/source_census.json`` and exits non-zero if any non-reference source
violates a corpus-value threshold (metadata-completeness / link-back-resolvability /
dedup-overlap). The thresholds + the contract + the predicate live in
``tools/source_census.py`` (the one home); this is the thin CLI that runs them, in
the house ``tools/lint/*`` exit-code convention (0 = clean, 1 = a source is blocked).

The census itself is produced by the operator-gated P3b producer
(``compute_source_census`` over the real corpus); until a census exists for a new
source, there is nothing to gate and this exits 0 with a clear message. When P3b
wires the producer into CI, that CI step must guarantee a census row exists for each
onboarded source so this gate has something to evaluate.

Exit 0 = clean (or no census present); exit 1 = at least one source is blocked.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

# tools/ is importable as a package from the repo root (cwd-based import, the house
# convention); add the repo root so this runs both as a module and as a script.
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.source_census import (  # noqa: E402
    REFERENCE_SOURCE,
    evaluate,
    load_censuses,
)

_CENSUS_PATH = _REPO / "reports" / "source_census.json"


def _census_path() -> Path:
    """The census to gate: an explicit ``argv[1]`` path, else
    ``$ANTIEK_SOURCE_CENSUS``, else the committed ``reports/source_census.json``.
    The override exists so the gate is pointable at a fixture census WITHOUT
    mutating the repo — a kill-gate must be testable in isolation."""
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    env = os.environ.get("ANTIEK_SOURCE_CENSUS")
    return Path(env) if env else _CENSUS_PATH


def main() -> int:
    path = _census_path()
    if not path.exists():
        print(
            f"OK: no source census at {path} yet — nothing to gate. (The P3b "
            f"producer writes it from the real corpus; until then no source-after-"
            f"{REFERENCE_SOURCE} has been onboarded.)"
        )
        return 0

    try:
        results = evaluate(load_censuses(path))
    except ValueError as exc:
        # A malformed / invalid census (bad JSON, a missing or non-finite field, a
        # duplicate reference row) FAILS CLOSED — a kill-gate never passes on input
        # it cannot trust. json.JSONDecodeError is a ValueError subclass.
        print(f"Source census at {path} is INVALID — blocked (deny-by-default): {exc}")
        return 1

    blocked = {source: fails for source, fails in results.items() if fails}
    if blocked:
        print("Source onboarding BLOCKED — corpus-value gate failed:")
        for source in sorted(blocked):
            print(f"  {source}:")
            for fail in blocked[source]:
                print(f"    - {fail}")
        print(
            f"\nA source after {REFERENCE_SOURCE!r} must clear the corpus-value bar "
            f"before it is onboarded (reframe finding #2): the corpus's worth is "
            f"feeding the products, so an incomplete / un-resolvable / mostly-"
            f"duplicate source is rejected. Thresholds are in tools/source_census.py "
            f"(PROVISIONAL — calibrate on the first real arXiv census)."
        )
        return 1

    gated = sorted(results)
    print(
        f"OK: {len(gated)} source(s) after {REFERENCE_SOURCE!r} clear the corpus-"
        f"value gate"
        + (f": {', '.join(gated)}." if gated else " (none onboarded yet).")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
