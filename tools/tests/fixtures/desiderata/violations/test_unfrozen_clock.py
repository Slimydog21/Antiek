"""Fixture: unfrozen wall-clock read inline in an assertion.

The lint must flag: the comparison is time-of-day-dependent.
"""

from __future__ import annotations

import time


def test_issued_before_now(issued_at: int = 1_700_000_000):
    assert issued_at <= int(time.time())