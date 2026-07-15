from __future__ import annotations

import logging
import sys
import types
from collections.abc import Sequence

import pytest

import runtime.notdiamond.adapter as adapter_mod
from runtime.notdiamond import (
    NotDiamondAPIError,
    NotDiamondAuthError,
    NotDiamondTimeout,
    Recommendation,
    select_model,
)

_MESSAGES = [{"role": "user", "content": "hello"}]
_CANDIDATES = ["openai/gpt-4o-mini", "anthropic/claude-3-5-haiku-20241022"]


class _FakeLLM:
    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model


def _fake_ok(
    api_key: str,
    messages: Sequence[dict[str, str]],
    candidates: Sequence[str],
    tradeoff: str,
    timeout_s: float,
) -> tuple[str, _FakeLLM]:
    return "sess-123", _FakeLLM("anthropic", "claude-3-5-haiku-20241022")


def test_import_does_not_load_sdk() -> None:
    assert "notdiamond" not in sys.modules


def test_missing_key_raises_auth_at_call_not_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTDIAMOND_API_KEY", raising=False)
    with pytest.raises(NotDiamondAuthError):
        select_model(_MESSAGES, _CANDIDATES, _selector=_fake_ok)


def test_empty_candidates_rejected_before_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTDIAMOND_API_KEY", raising=False)
    with pytest.raises(NotDiamondAPIError):
        select_model(_MESSAGES, [], _selector=_fake_ok)


def test_recommendation_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTDIAMOND_API_KEY", "sk-test-not-real")
    rec = select_model(_MESSAGES, _CANDIDATES, _selector=_fake_ok)
    assert isinstance(rec, Recommendation)
    assert rec.provider == "anthropic"
    assert rec.model == "claude-3-5-haiku-20241022"
    assert rec.session_id == "sess-123"
    assert rec.decision_latency_ms >= 0


def test_parse_best_string_form(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTDIAMOND_API_KEY", "sk-test-not-real")

    def _fake_string(
        api_key: str,
        messages: Sequence[dict[str, str]],
        candidates: Sequence[str],
        tradeoff: str,
        timeout_s: float,
    ) -> tuple[str, str]:
        return "sess-str", "openai/gpt-4o-mini"

    rec = select_model(_MESSAGES, _CANDIDATES, _selector=_fake_string)
    assert rec.provider == "openai"
    assert rec.model == "gpt-4o-mini"


def test_default_selector_uses_native_model_router_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class _Provider:
        provider = "anthropic"
        model = "claude-3-5-haiku-20241022"

    class _Response:
        session_id = "sess-native"
        providers = [_Provider()]

    class _Router:
        def select_model(self, **kwargs: object) -> _Response:
            calls.update(kwargs)
            return _Response()

    class _NotDiamond:
        def __init__(
            self,
            *,
            api_key: str,
            timeout: float,
            max_retries: int,
        ) -> None:
            calls["api_key"] = api_key
            calls["client_timeout"] = timeout
            calls["max_retries"] = max_retries
            self.model_router = _Router()

    fake_module = types.SimpleNamespace(NotDiamond=_NotDiamond)
    monkeypatch.setitem(sys.modules, "notdiamond", fake_module)

    session_id, best = adapter_mod._default_selector(
        "sk-test",
        _MESSAGES,
        _CANDIDATES,
        "cost",
        0.5,
    )

    assert session_id == "sess-native"
    assert best is _Response.providers[0]
    assert calls["api_key"] == "sk-test"
    assert calls["client_timeout"] == 0.5
    assert calls["max_retries"] == 0
    assert calls["llm_providers"] == [
        {"provider": "openai", "model": "gpt-4o-mini"},
        {"provider": "anthropic", "model": "claude-3-5-haiku-20241022"},
    ]
    assert calls["messages"] == _MESSAGES
    assert calls["tradeoff"] == "cost"
    assert calls["timeout"] == 0.5


def test_invalid_candidate_rejected_before_sdk_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NotDiamond:
        def __init__(self, **kwargs: object) -> None:
            self.model_router = object()

    monkeypatch.setitem(
        sys.modules,
        "notdiamond",
        types.SimpleNamespace(NotDiamond=_NotDiamond),
    )
    with pytest.raises(NotDiamondAPIError):
        adapter_mod._default_selector("sk-test", _MESSAGES, ["gpt-4o-mini"], "cost", 0.5)


def test_unparseable_best_raises_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTDIAMOND_API_KEY", "sk-test-not-real")

    def _fake_bad(
        api_key: str,
        messages: Sequence[dict[str, str]],
        candidates: Sequence[str],
        tradeoff: str,
        timeout_s: float,
    ) -> tuple[str, object]:
        return "sess", object()

    with pytest.raises(NotDiamondAPIError):
        select_model(_MESSAGES, _CANDIDATES, _selector=_fake_bad)


def test_malformed_sdk_return_maps_to_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOTDIAMOND_API_KEY", "sk-test-not-real")

    class _BadBest:
        provider = None
        model = None

        def __str__(self) -> str:
            raise RuntimeError("bad sdk object str")

        __repr__ = __str__

    def _fake_bad_obj(
        api_key: str,
        messages: Sequence[dict[str, str]],
        candidates: Sequence[str],
        tradeoff: str,
        timeout_s: float,
    ) -> tuple[str, _BadBest]:
        return "sess", _BadBest()

    with pytest.raises(NotDiamondAPIError):
        select_model(_MESSAGES, _CANDIDATES, _selector=_fake_bad_obj)


def test_timeout_maps_to_notdiamond_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTDIAMOND_API_KEY", "sk-test-not-real")

    def _fake_slow(
        api_key: str,
        messages: Sequence[dict[str, str]],
        candidates: Sequence[str],
        tradeoff: str,
        timeout_s: float,
    ) -> tuple[str, _FakeLLM]:
        assert timeout_s == 0.01
        raise TimeoutError

    with pytest.raises(NotDiamondTimeout):
        select_model(_MESSAGES, _CANDIDATES, timeout_ms=10, _selector=_fake_slow)


def test_sdk_exception_maps_to_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTDIAMOND_API_KEY", "sk-test-not-real")

    def _fake_raise(
        api_key: str,
        messages: Sequence[dict[str, str]],
        candidates: Sequence[str],
        tradeoff: str,
        timeout_s: float,
    ) -> tuple[str, _FakeLLM]:
        raise RuntimeError("boom from SDK")

    with pytest.raises(NotDiamondAPIError):
        select_model(_MESSAGES, _CANDIDATES, _selector=_fake_raise)


def test_key_never_appears_in_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "sk-super-secret-value-do-not-log"
    monkeypatch.setenv("NOTDIAMOND_API_KEY", secret)

    def _fake_raise(
        api_key: str,
        messages: Sequence[dict[str, str]],
        candidates: Sequence[str],
        tradeoff: str,
        timeout_s: float,
    ) -> tuple[str, _FakeLLM]:
        raise RuntimeError("provider exploded")

    with caplog.at_level(logging.DEBUG), pytest.raises(NotDiamondAPIError):
        select_model(_MESSAGES, _CANDIDATES, _selector=_fake_raise)
    assert secret not in caplog.text

    try:
        select_model(_MESSAGES, _CANDIDATES, _selector=_fake_raise)
    except NotDiamondAPIError as exc:
        assert secret not in str(exc)


def test_no_dispatch_import() -> None:
    import runtime.notdiamond.adapter as adapter_mod

    assert adapter_mod.__file__ is not None
    with open(adapter_mod.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "substrate.dispatch" not in text
    assert "runtime.dispatch" not in text
