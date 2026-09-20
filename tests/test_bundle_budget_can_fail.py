"""A budgeted chunk that cannot be found must fail, not be skipped.

check_bundle.ts used to `continue` past a budget whose chunk prefix matched
nothing — printing a warning and ending "All chunks within budget." with exit
0. Rename an entry, change vite's manualChunks, or break the split, and that
ceiling silently stopped being enforced while the job stayed green.

Verified against origin/main with index present-and-within-budget and lemon
absent: rc=0, "All chunks within budget." The ceiling was unenforced and the
gate said everything was fine.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "apps" / "reading" / "scripts" / "check_bundle.ts"


def _source() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def test_the_premise_still_holds() -> None:
    """Not vacuous: a missing script or empty BUDGETS passes everything below."""
    assert _SCRIPT.is_file(), f"{_SCRIPT.relative_to(_ROOT)} is missing"
    src = _source()
    assert "BUDGETS" in src
    entries = re.findall(r"\{\s*chunk:\s*\"([^\"]+)\"", src)
    assert len(entries) >= 2, (
        f"expected the budget list to be populated, found {entries} — an "
        "empty list makes this gate pass over nothing"
    )


def test_a_missing_budgeted_chunk_counts_as_a_failure() -> None:
    """The not-found branch must increment the failure counter."""
    src = _source()
    match = re.search(r"if \(!f\) \{(.*?)\n  \}", src, re.DOTALL)
    assert match, "the not-found branch in the budget loop is gone or reshaped"
    branch = match.group(1)

    assert "failed += 1" in branch, (
        "check_bundle.ts skips a budget whose chunk it cannot find without "
        "counting a failure, so the script exits 0 and prints 'All chunks "
        "within budget' while that ceiling is unenforced. A budget that "
        "cannot find its chunk is not a passing budget."
    )


def test_the_script_still_exits_nonzero_on_failure() -> None:
    src = _source()
    assert re.search(r"if \(failed > 0\)[\s\S]{0,400}process\.exit\(1\)", src), (
        "the failure counter no longer drives a non-zero exit; nothing the "
        "loop discovers can change the job's outcome"
    )
