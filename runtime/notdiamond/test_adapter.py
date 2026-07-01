"""ANT-ND SPR-01 — adapter unit tests (no SDK, no key; CI-runnable).

The live round-trip lives in ``test_smoke.py`` (skips without
``NOTDIAMOND_API_KEY``). These tests inject a fake selector so the adapter's
contract — lazy import, fail-loud auth, timeout mapping, exception mapping,
recommendation shape, no-key-in-logs — is exercised on every CI run without the
optional SDK or a network call.
"""

from __future__ import annotations

import logging
import sys
import time

import pytest

from runtime.notdiamond import (
    NotDiamondAPIError,
    NotDiamondAuthError,
    NotDiamondTimeout,
    Recommendation,
    select_model,
)

_MSGS = [{"role": "user", "content": "hello"}]
_CANDS = ["openai/gpt-4o-mini", "anthropic/claude-3-5-haiku-20241022"]


class _FakeLLM:
    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model


def _fake_ok(api_key, messages, candidates, tradeoff):
    return "sess-123", _FakeLLM("anthropic", "claude-3-5-haiku-20241022")


def test_import_does_not_load_sdk() -> None:
    """Importing the package must not import the ND SDK (lazy-import invariant)."""
    assert "notdiamond" not in sys.modules, "ND SDK imported at package import time"


def test_missing_key_raises_auth_at_call_not_import(monkeypatch) -> None:
    monkeypatch.delenv("NOTDIAMOND_API_KEY", raising=False)
    with pytest.raises(NotDiamondAuthError):
        select_model(_MSGS, _CANDS, _selector=_fake_ok)


def test_empty_candidates_rejected_before_key(monkeypatch) -> None:
    # No candidates is a caller bug; caught before we even resolve the key.
    monkeypatch.delenv("NOTDIAMOND_API_KEY", raising=False)
    with pytest.raises(NotDiamondAPIError):
        select_model(_MSGS, [], _selector=_fake_ok)


def test_recommendation_shape(monkeypatch) -> None:
    monkeypatch.setenv("NOTDIAMOND_API_KEY", "sk-test-not-a-real-key")
    rec = select_model(_MSGS, _CANDS, _selector=_fake_ok)
    assert isinstance(rec, Recommendation)
    assert rec.provider == "anthropic"
    assert rec.model == "claude-3-5-haiku-20241022"
    assert rec.session_id == "sess-123"
    assert rec.decision_latency_ms >= 0


def test_parse_best_string_form(monkeypatch) -> None:
    monkeypatch.setenv("NOTDIAMOND_API_KEY", "sk-test-not-a-real-key")

    def _fake_string(api_key, messages, candidates, tradeoff):
        return "sess-str", "openai/gpt-4o-mini"

    rec = select_model(_MSGS, _CANDS, _selector=_fake_string)
    assert rec.provider == "openai"
    assert rec.model == "gpt-4o-mini"


def test_unparseable_best_raises_api_error(monkeypatch) -> None:
    monkeypatch.setenv("NOTDIAMOND_API_KEY", "sk-test-not-a-real-key")

    def _fake_bad(api_key, messages, candidates, tradeoff):
        return "sess", object()  # neither attrs nor "provider/model" string

    with pytest.raises(NotDiamondAPIError):
        select_model(_MSGS, _CANDS, _selector=_fake_bad)


def test_malformed_sdk_return_maps_to_api_error(monkeypatch) -> None:
    """Regression (codex GPT-5.5 adversarial review, 2026-07-01): a malformed SDK
    return object — one with no provider/model and a ``__str__`` that raises —
    must surface as NotDiamondAPIError, NOT leak a raw RuntimeError. ND is
    advisory; every failure must be catchable as NotDiamondError."""
    monkeypatch.setenv("NOTDIAMOND_API_KEY", "sk-test-not-a-real-key")

    class _BadBest:
        provider = None
        model = None

        def __str__(self) -> str:
            raise RuntimeError("bad sdk object str")

        __repr__ = __str__

    def _fake_bad_obj(api_key, messages, candidates, tradeoff):
        return "sess", _BadBest()

    with pytest.raises(NotDiamondAPIError):
        select_model(_MSGS, _CANDS, _selector=_fake_bad_obj)


def test_timeout_maps_to_notdiamond_timeout(monkeypatch) -> None:
    monkeypatch.setenv("NOTDIAMOND_API_KEY", "sk-test-not-a-real-key")

    def _fake_slow(api_key, messages, candidates, tradeoff):
        time.sleep(0.5)
        return "sess", _FakeLLM("openai", "gpt-4o-mini")

    with pytest.raises(NotDiamondTimeout):
        select_model(_MSGS, _CANDS, timeout_ms=10, _selector=_fake_slow)


def test_sdk_exception_maps_to_api_error(monkeypatch) -> None:
    monkeypatch.setenv("NOTDIAMOND_API_KEY", "sk-test-not-a-real-key")

    def _fake_raise(api_key, messages, candidates, tradeoff):
        raise RuntimeError("boom from SDK")

    with pytest.raises(NotDiamondAPIError):
        select_model(_MSGS, _CANDS, _selector=_fake_raise)


def test_key_never_appears_in_logs(monkeypatch, caplog) -> None:
    secret = "sk-super-secret-value-DO-NOT-LOG"
    monkeypatch.setenv("NOTDIAMOND_API_KEY", secret)

    def _fake_raise(api_key, messages, candidates, tradeoff):
        raise RuntimeError("provider exploded")

    with caplog.at_level(logging.DEBUG), pytest.raises(NotDiamondAPIError):
        select_model(_MSGS, _CANDS, _selector=_fake_raise)
    assert secret not in caplog.text
    # And the mapped error message must not carry the key either.
    try:
        select_model(_MSGS, _CANDS, _selector=_fake_raise)
    except NotDiamondAPIError as exc:
        assert secret not in str(exc)


def test_no_dispatch_import() -> None:
    """SPR-01 must not couple the adapter to dispatch. Importing the package
    must not pull substrate.dispatch."""
    # Fresh sub-check: the package is already imported at top; assert dispatch
    # is not a transitive import of the adapter itself.
    import runtime.notdiamond.adapter as adapter_mod

    src = adapter_mod.__file__
    assert src is not None
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    assert "substrate.dispatch" not in text
    assert "runtime.dispatch" not in text
