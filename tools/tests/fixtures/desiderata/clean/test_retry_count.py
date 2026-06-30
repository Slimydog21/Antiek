"""Guard fixture: retry-count steelman — call_count IS the behavior under test.

Must NOT flag: for a retry wrapper the invocation count is the unit's contract,
not incidental structure coupling.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def retry_three(inner) -> None:
    for _ in range(3):
        inner()


def test_retry_fires_exactly_three_times():
    inner = MagicMock()
    retry_three(inner)
    assert inner.call_count == 3