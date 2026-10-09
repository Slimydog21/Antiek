"""Ordinary request binding with real builders and synthetic HTTP responses."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import Any

import httpx
import pytest

from interfaces.research.api.settings_models_admin import UserModelRecord, _make_provider
from substrate.dispatch.base import ProviderError
from substrate.dispatch.providers.openai_compat import OpenAICompatProvider

_CORE: dict[str, Any] = {
    "model": "selected-model",
    "max_tokens": 32,
    "temperature": 0.2,
    "messages": [{"role": "user", "content": "selected prompt"}],
}


def _call(provider: OpenAICompatProvider, extra_body: Mapping[str, Any] | None = None) -> None:
    result = provider.call(
        model="selected-model",
        prompt="selected prompt",
        max_tokens=32,
        temperature=0.2,
        extra_body=extra_body,
    )
    assert result.text == "synthetic response"
    assert result.finish_reason == "stop"
    usage = provider.normalize_usage(result.raw_usage)
    assert usage.input_tokens == 3
    assert usage.output_tokens == 2
    assert result.latency_ms >= 0


def _transport(requests: list[httpx.Request]) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "synthetic response"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )

    return httpx.MockTransport(respond)


@pytest.mark.parametrize("source", ["constructor", "caller"])
@pytest.mark.parametrize("field", list(_CORE))
@pytest.mark.parametrize("equal", [False, True])
def test_core_vendor_presence_refuses_before_effects(
    source: str, field: str, equal: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = _CORE[field] if equal else "synthetic forbidden value"
    extra = {field: value}
    effects = {"resolve": 0, "client": 0}
    provider = OpenAICompatProvider(
        name="selected-provider",
        base_url="https://provider.invalid",
        extra_body=extra if source == "constructor" else None,
    )

    def resolve() -> str:
        effects["resolve"] += 1
        return "synthetic-key"

    def client() -> httpx.Client:
        effects["client"] += 1
        raise AssertionError("client must not be acquired for a refused request")

    monkeypatch.setattr(provider, "_resolve_api_key", resolve)
    monkeypatch.setattr(provider, "_ensure_client", client)
    with pytest.raises(ProviderError) as caught:
        _call(provider, extra if source == "caller" else None)
    assert caught.value.provider == "selected-provider"
    assert caught.value.model == "selected-model"
    assert caught.value.retryable is False
    assert caught.value.latency_ms == 0
    assert "synthetic forbidden value" not in str(caught.value)
    assert effects == {"resolve": 0, "client": 0}


def test_noncore_defaults_restore_across_calls() -> None:
    requests: list[httpx.Request] = []
    defaults = {"thinking": {"type": "enabled"}, "stop": ["constructor"]}
    with httpx.Client(transport=_transport(requests)) as client:
        provider = OpenAICompatProvider(
            name="synthetic",
            base_url="https://provider.invalid",
            api_key="synthetic-key",
            client=client,
            extra_body=defaults,
        )
        _call(provider, {"thinking": {"type": "disabled"}, "stop": ["caller"]})
        _call(provider)
        _call(provider, {})
    bodies = [json.loads(request.content) for request in requests]
    assert bodies[0] == {**_CORE, "thinking": {"type": "disabled"}, "stop": ["caller"]}
    assert bodies[1] == bodies[2] == {**_CORE, **defaults}
    assert provider._extra_body == defaults
    assert all(
        str(request.url) == "https://provider.invalid/v1/chat/completions" for request in requests
    )
    assert all(request.headers["authorization"] == "Bearer synthetic-key" for request in requests)


class _ChangingMapping(Mapping[str, Any]):
    def __init__(self) -> None:
        self.enumerations = 0
        self.reads: list[str] = []
        self.data: dict[str, Any] = {"stop": ["captured"]}

    def __iter__(self) -> Iterator[str]:
        self.enumerations += 1
        return iter(self.data if self.enumerations == 1 else {"model": "replacement"})

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, key: str) -> Any:
        self.reads.append(key)
        return self.data[key]


def test_one_mapping_enumeration_before_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []
    caller = _ChangingMapping()
    with httpx.Client(transport=_transport(requests)) as client:
        provider = OpenAICompatProvider(
            name="synthetic",
            base_url="https://provider.invalid",
            client=client,
            extra_body={"seed": 7},
        )

        def resolve() -> str:
            assert caller.enumerations == 1
            provider._extra_body.clear()
            provider._extra_body.update({"model": "replacement", "seed": 99})
            caller.data = {"model": "replacement", "stop": ["changed"]}
            return "synthetic-key"

        monkeypatch.setattr(provider, "_resolve_api_key", resolve)
        _call(provider, caller)
    assert caller.enumerations == 1
    assert caller.reads == ["stop"]
    assert json.loads(requests[0].content) == {**_CORE, "seed": 7, "stop": ["captured"]}


def test_empty_snapshots_survive_resolver_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []
    caller: dict[str, Any] = {}
    with httpx.Client(transport=_transport(requests)) as client:
        provider = OpenAICompatProvider(
            name="synthetic",
            base_url="https://provider.invalid",
            client=client,
        )

        def resolve() -> str:
            provider._extra_body.update({"model": "replacement", "stop": ["late default"]})
            caller.update({"max_tokens": 1000, "stop": ["late caller"]})
            return "synthetic-key"

        monkeypatch.setattr(provider, "_resolve_api_key", resolve)
        _call(provider, caller)
    assert json.loads(requests[0].content) == _CORE


@pytest.mark.parametrize(
    ("model", "thinking"), [("deepseek-flash", "enabled"), ("deepseek-chat", "disabled")]
)
def test_catalogue_snapshot_uses_real_variant_then_caller(
    model: str, thinking: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = UserModelRecord(
        id="user-synthetic",
        provider_kind="openai_compat",
        provider_catalog_id="deepseek",
        model_id=model,
        display_name="Synthetic",
        base_url="https://api.deepseek.com",
        cred_ref="synthetic-no-store-access",
    )
    provider = _make_provider(record)
    assert isinstance(provider, OpenAICompatProvider)
    provider._extra_body = {"thinking": {"type": "constructor"}, "seed": 7}
    requests: list[httpx.Request] = []
    caller = {"thinking": {"type": "caller"}, "stop": ["captured"]}

    def resolve() -> str:
        provider._extra_body.update({"model": "replacement", "seed": 99})
        caller.update({"max_tokens": 1000, "stop": ["changed"]})
        return "synthetic-key"

    monkeypatch.setattr(provider, "_resolve_api_key", resolve)
    with httpx.Client(transport=_transport(requests)) as client:
        monkeypatch.setattr(provider, "_client", client)
        first = provider.call(model=model, prompt="selected prompt", max_tokens=32, temperature=0.2)
        provider._extra_body = {"thinking": {"type": "constructor"}, "seed": 7}
        caller.clear()
        caller.update({"thinking": {"type": "caller"}, "stop": ["captured"]})
        provider.call(
            model=model,
            prompt="selected prompt",
            max_tokens=32,
            temperature=0.2,
            extra_body=caller,
        )
    assert first.text == "synthetic response"
    first_body, second_body = [json.loads(request.content) for request in requests]
    assert first_body == {
        **_CORE,
        "model": "deepseek-flash",
        "thinking": {"type": thinking},
        "seed": 7,
    }
    assert second_body == {
        **_CORE,
        "model": "deepseek-flash",
        "thinking": {"type": "caller"},
        "seed": 7,
        "stop": ["captured"],
    }
    assert all(
        str(request.url) == "https://api.deepseek.com/chat/completions" for request in requests
    )


@pytest.mark.parametrize("source", ["constructor", "caller"])
@pytest.mark.parametrize("field", list(_CORE))
def test_pure_builder_keeps_core_override_construction(source: str, field: str) -> None:
    extra = {field: "synthetic replacement"}
    provider = OpenAICompatProvider(
        name="synthetic",
        base_url="https://provider.invalid",
        extra_body=extra if source == "constructor" else None,
    )
    built = provider.build_request(
        model="selected-model",
        prompt="selected prompt",
        max_tokens=32,
        temperature=0.2,
        api_key="synthetic-key",
        extra_body=extra if source == "caller" else None,
    )
    assert built.body == {**_CORE, **extra}


def test_private_empty_snapshot_replaces_only_constructor_defaults() -> None:
    provider = OpenAICompatProvider(
        name="synthetic",
        base_url="https://provider.invalid",
        extra_body={"seed": 99},
    )
    built = provider.build_request(
        model="selected-model",
        prompt="selected prompt",
        max_tokens=32,
        temperature=0.2,
        api_key="synthetic-key",
        _vendor_defaults={},
        extra_body={"stop": ["caller"]},
    )
    assert built.body == {**_CORE, "stop": ["caller"]}
    assert provider._extra_body == {"seed": 99}
