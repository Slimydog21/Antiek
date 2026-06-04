"""Fixture: a MIXED test file.

``test_dispatches_and_returns`` asserts BOTH the unit's real output
(``result == "done"``) AND the collaborator's call shape
(``client.send.call_count == 1``). The census must label this ``mixed`` — it is
the common, legitimate shape where a test verifies output and also pins a
call-cadence invariant (e.g. "synthesis must run exactly once").

Parsed, not executed (see test_pure_behavior.py header).
"""

from __future__ import annotations

from unittest.mock import MagicMock


def process(client, payload: str) -> str:
    client.send(payload)
    return "done"


def test_dispatches_and_returns():
    client = MagicMock()
    result = process(client, "p")
    assert result == "done"
    assert client.send.call_count == 1
