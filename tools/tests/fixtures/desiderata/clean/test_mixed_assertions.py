"""Guard fixture: mixed test — call-shape PLUS a real behavior assertion.

Must NOT flag: the test asserts the unit's output, so it is not structure-only.
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
    client.send.assert_called_once_with("p")