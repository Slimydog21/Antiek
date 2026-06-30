"""Deliberately nondeterministic fixture — outcome varies per shuffle seed.

Uses the harness shuffle seed (not unseeded ``random``) so the same
``--shuffle-seeds`` reproduce the same pass/fail pattern across harness runs.
"""

from __future__ import annotations

import os


def test_rng_flap():
    seed = int(os.environ.get("FLAKY_QUARANTINE_SHUFFLE_SEED", "0"))
    # Passes on seeds 1 and 3, fails on seed 2 → mixed across N=3 runs.
    assert seed in (1, 3)