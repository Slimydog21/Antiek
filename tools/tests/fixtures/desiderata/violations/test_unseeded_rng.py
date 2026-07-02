"""Fixture: unseeded random value asserted inline.

The lint must flag: the asserted value changes every run.
"""

from __future__ import annotations

import uuid


def test_token_matches_literal():
    assert uuid.uuid4().hex == "deadbeef"