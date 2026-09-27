"""Optional provider send keys; no network calls or real email."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import pytest

from substrate.auth.email_provider import (
    AgentMailEmailProvider,
    EmailDeliveryFailure,
    MockEmailProvider,
    OutboundEmail,
    ResendEmailProvider,
)


@contextmanager
def _capture_request(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Any]]:
    requests: list[Any] = []

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"id": "email-1", "message_id": "email-1"}).encode()

    def urlopen(req: Any, *, timeout: int) -> Response:
        requests.append(req)
        return Response()

    with monkeypatch.context() as patch:
        patch.setattr(urllib.request, "urlopen", urlopen)
        yield requests


@pytest.mark.parametrize("bad", ["", "has space", "line\nbreak", "x" * 257, 3])
def test_send_key_rejects_invalid_header_values(bad: object) -> None:
    with pytest.raises(ValueError, match="idempotency key"):
        OutboundEmail(
            to="a@example.com", subject="s", text_body="b", idempotency_key=cast(Any, bad)
        )


def test_send_key_accepts_the_documented_maximum_length() -> None:
    email = OutboundEmail(to="a@example.com", subject="s", text_body="b", idempotency_key="x" * 256)
    assert email.idempotency_key == "x" * 256
    assert "idempotency_key" not in repr(email)


@pytest.mark.parametrize(
    "provider",
    [ResendEmailProvider(api_key="test"), AgentMailEmailProvider(api_key="test", inbox_id="inbox")],
)
def test_http_adapters_forward_optional_send_key(
    provider: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = OutboundEmail(
        to="a@example.com",
        subject="s",
        text_body="b",
        idempotency_key="reping-1.~",
    )
    with _capture_request(monkeypatch) as requests:
        provider.send(email)
        provider.send(OutboundEmail(to="a@example.com", subject="s", text_body="b"))
    assert requests[0].get_header("Idempotency-key") == "reping-1.~"
    assert requests[1].get_header("Idempotency-key") is None
    assert len(requests) == 2


def test_mock_replays_same_key_and_refuses_changed_payload() -> None:
    mock = MockEmailProvider(log_to_stdout=False)
    email = OutboundEmail(
        to="a@example.com",
        subject="s",
        text_body="b",
        idempotency_key="reping-1",
    )
    first = mock.send(email)
    assert mock.send(email) is first
    assert len(mock.sent) == 1
    with pytest.raises(EmailDeliveryFailure, match="different email"):
        mock.send(
            OutboundEmail(
                to="a@example.com",
                subject="s",
                text_body="changed",
                idempotency_key="reping-1",
            )
        )
    mock.clear()
    assert len(mock.sent) == 0
    assert mock.send(email) is not first


def test_mock_without_key_treats_calls_as_distinct_sends() -> None:
    mock = MockEmailProvider(log_to_stdout=False)
    email = OutboundEmail(to="a@example.com", subject="s", text_body="b")
    mock.send(email)
    mock.send(email)
    assert len(mock.sent) == 2
