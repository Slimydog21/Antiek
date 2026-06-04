"""Fixture: a STRUCTURE-ONLY test file.

Every assertion checks a mock's CALL SHAPE — ``assert_called_once_with`` and a
``.call_count`` read — never the unit's output. The census must label these
``structure`` with ``uses_mock=True``. This is the Beck 'predictive' failure
the flag exists to surface: the test passes if the collaborator was *called*
the right way, regardless of whether the unit produced the right result.

Parsed, not executed (see test_pure_behavior.py header).
"""

from __future__ import annotations

from unittest.mock import MagicMock


def notify(client, user_id: str) -> None:
    client.send(user_id)


def test_notify_calls_send_once():
    client = MagicMock()
    notify(client, "u-1")
    client.send.assert_called_once_with("u-1")


def test_notify_call_count_is_one():
    client = MagicMock()
    notify(client, "u-2")
    assert client.send.call_count == 1
