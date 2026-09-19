from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import substrate.dispatch.router as router
from substrate.dispatch import (
    DispatchConfig,
    NormalizedUsage,
    ProviderCallNotAttempted,
    ProviderError,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    dispatch,
    register_provider,
    reset_provider_registry,
)
from substrate.dispatch.breaker import default_breaker
from substrate.dispatch.research_quote import build_research_route_manifest
from substrate.event_log import (
    ResearchBudgetExceeded,
    append_event_once_authorized,
    investigation_authority_context,
    prepare_typed_event,
    trajectory_authorized,
)
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas import InvestigationStartRequestedPayload, ResearchQuotedRoute


class _IdempotentProvider:
    name = "paid"
    idempotency_guaranteed = True

    def __init__(
        self,
        *,
        fail: ProviderError | None = None,
        barrier: threading.Barrier | None = None,
    ) -> None:
        self.fail = fail
        self.barrier = barrier
        self.calls: list[dict[str, Any]] = []

    def call(self, **_: Any) -> RawProviderResponse:
        raise AssertionError("interactive research must use call_idempotent")

    def call_idempotent(self, **kwargs: Any) -> RawProviderResponse:
        self.calls.append(dict(kwargs))
        if self.barrier is not None:
            self.barrier.wait(timeout=5)
        if self.fail is not None:
            raise self.fail
        return RawProviderResponse(
            text="budgeted result",
            raw_usage={"input_tokens": 10, "output_tokens": 5},
            finish_reason="stop",
            latency_ms=7,
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(
            input_tokens=int(raw_usage["input_tokens"]),
            output_tokens=int(raw_usage["output_tokens"]),
        )


class _NoCallProvider(_IdempotentProvider):
    name = "no-call"

    def call_idempotent(self, **kwargs: Any) -> RawProviderResponse:
        self.calls.append(dict(kwargs))
        raise ProviderCallNotAttempted(
            "credential missing before network",
            provider=self.name,
            model=str(kwargs["model"]),
            latency_ms=0,
            retryable=False,
        )


class _FallbackProvider(_IdempotentProvider):
    name = "fallback"


def _authoritative_pricing(
    *,
    input_per_mtok: float = 10.0,
    output_per_mtok: float = 20.0,
    cached_input_per_mtok: float = 1.0,
) -> TierPricing:
    return TierPricing(
        input_per_mtok=input_per_mtok,
        output_per_mtok=output_per_mtok,
        cached_input_per_mtok=cached_input_per_mtok,
        currency="USD",
        billing_unit="per_million_tokens",
        source_url="https://provider.example/pricing",
        verified_at="2026-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
    )


@pytest.fixture(autouse=True)
def _clean_router() -> None:
    reset_provider_registry()
    default_breaker.reset()
    yield
    reset_provider_registry()
    default_breaker.reset()


def _route(
    provider: str,
    *,
    model: str = "model",
    fallback: TierConfig | None = None,
    pricing: TierPricing | None = None,
) -> TierConfig:
    return TierConfig(
        name="pro",
        provider=provider,
        model=model,
        max_tokens=100,
        temperature=0.2,
        context_budget_tokens=1000,
        pricing=pricing or _authoritative_pricing(),
        fallback=fallback,
    )


def _config(route: TierConfig) -> DispatchConfig:
    return DispatchConfig(role_tiers={"decomposer": "pro"}, tiers={"pro": route})


def _authority(
    tmp_path: Path,
    *,
    config: DispatchConfig | None = None,
    ceiling: float = 1.0,
    investigation_id: str = "inv-budgeted-dispatch",
    selected_driver: ResearchQuotedRoute | None = None,
) -> tuple[InvestigationAuthority, str]:
    accepted = config or _config(_route("paid"))
    manifest = build_research_route_manifest(accepted)
    authority = InvestigationAuthority("alice", investigation_id, tmp_path)
    start = prepare_typed_event(
        authority.investigation_id,
        InvestigationStartRequestedPayload(
            question="What is true?",
            approved_run_ceiling_usd=ceiling,
            research_quote_id="a" * 64,
            research_quote_payload_sha256="b" * 64,
            research_route_manifest_fingerprint=manifest.fingerprint,
            research_quote_expires_at_ms=4_102_444_800_000,
            research_route_manifest=tuple(
                ResearchQuotedRoute(**row.__dict__) for row in manifest.routes
            ),
            selected_driver_role=(selected_driver.role if selected_driver else None),
            selected_driver_provider=(
                selected_driver.provider if selected_driver else None
            ),
            selected_driver_model=(selected_driver.model if selected_driver else None),
            selected_driver_pricing_fingerprint=(
                selected_driver.pricing_fingerprint if selected_driver else None
            ),
        ),
        event_id="evt-start",
    )
    append_event_once_authorized(authority, start)
    return authority, start.event_id


def _dispatch(
    authority: InvestigationAuthority,
    parent_event_id: str,
    config: DispatchConfig,
):
    with investigation_authority_context(authority):
        return dispatch(
            "bounded prompt",
            "decomposer",
            investigation_id=authority.investigation_id,
            parent_event_id=parent_event_id,
            config=config,
        )


def test_success_reserves_before_call_and_settles_canonical_dispatch(tmp_path):
    authority, parent = _authority(tmp_path)
    provider = _IdempotentProvider()
    register_provider(provider)

    result = _dispatch(authority, parent, _config(_route(provider.name)))

    assert result.text == "budgeted result"
    assert len(provider.calls) == 1
    key = provider.calls[0]["idempotency_key"]
    assert isinstance(key, str) and key.startswith("antiek-research-v1-")
    rows = trajectory_authorized(authority)
    assert [row["action_type"] for row in rows] == [
        "investigation.start_requested",
        "research.call_reserved",
        "dispatch.call",
        "research.call_settled",
    ]
    reservation = rows[1]["payload"]
    assert reservation["projected_max_cost_usd"] >= result.cost_usd
    assert key not in str(rows)
    assert reservation["provider_idempotency_key_sha256"] != key


def test_exact_selected_driver_collapses_role_fallback_without_config_override(tmp_path):
    fallback = _route("fallback", model="model-b")
    primary = _route("paid", model="model-a", fallback=fallback)
    config = _config(primary)
    manifest = build_research_route_manifest(config)
    selected = ResearchQuotedRoute(
        **next(
            row.__dict__
            for row in manifest.routes
            if row.role == "decomposer" and row.fallback_index == 1
        )
    )
    authority, parent = _authority(
        tmp_path, config=config, selected_driver=selected
    )
    primary_provider = _IdempotentProvider()
    fallback_provider = _FallbackProvider()
    register_provider(primary_provider)
    register_provider(fallback_provider)

    result = _dispatch(authority, parent, config)

    assert result.provider == "fallback"
    assert primary_provider.calls == []
    assert len(fallback_provider.calls) == 1
    reservation = trajectory_authorized(authority)[1]["payload"]
    assert reservation["provider"] == "fallback"
    assert reservation["model"] == "model-b"
    assert reservation["fallback_chain_index"] == 0


def test_ceiling_denial_and_unknown_pricing_make_zero_provider_calls(tmp_path):
    authority, parent = _authority(tmp_path, ceiling=0.0001)
    provider = _IdempotentProvider()
    register_provider(provider)
    with pytest.raises(ProviderCallNotAttempted, match="budget authority") as denied:
        _dispatch(authority, parent, _config(_route(provider.name)))
    assert isinstance(denied.value.__cause__, ResearchBudgetExceeded)
    assert provider.calls == []
    assert [row["action_type"] for row in trajectory_authorized(authority)] == [
        "investigation.start_requested"
    ]

    for investigation_id in ("inv-unknown-price", "inv-stale-price"):
        with pytest.raises(ValueError, match="requires quote authority"):
            prepare_typed_event(
                investigation_id,
                InvestigationStartRequestedPayload(
                    question="No unsigned paid start",
                    approved_run_ceiling_usd=1.0,
                ),
            )
    assert provider.calls == []

    no_consent = InvestigationAuthority("alice", "inv-no-run-ceiling", tmp_path)
    no_consent_start = prepare_typed_event(
        no_consent.investigation_id,
        InvestigationStartRequestedPayload(question="No implicit consent"),
    )
    append_event_once_authorized(no_consent, no_consent_start)
    with pytest.raises(ProviderCallNotAttempted, match="budget authority"):
        _dispatch(
            no_consent,
            no_consent_start.event_id,
            _config(_route(provider.name)),
        )
    assert provider.calls == []


def test_unregistered_and_pre_network_failure_release_before_fallback(tmp_path):
    fallback_provider = _IdempotentProvider()
    register_provider(fallback_provider)
    fallback = _route(fallback_provider.name, model="fallback-model")
    config = _config(_route("missing-primary", fallback=fallback))
    authority, parent = _authority(tmp_path, config=config)
    result = _dispatch(
        authority,
        parent,
        config,
    )
    assert result.model == "fallback-model"
    rows = trajectory_authorized(authority)
    assert [row["action_type"] for row in rows] == [
        "investigation.start_requested",
        "research.call_reserved",
        "research.call_released",
        "research.call_reserved",
        "dispatch.call",
        "research.call_settled",
    ]

    no_call = _NoCallProvider()
    register_provider(no_call)
    no_call_config = _config(_route(no_call.name, fallback=fallback))
    no_call_authority, no_call_start_id = _authority(
        tmp_path,
        config=no_call_config,
        investigation_id="inv-no-call",
    )
    _dispatch(
        no_call_authority,
        no_call_start_id,
        no_call_config,
    )
    assert len(no_call.calls) == 1
    assert "dispatch.call" not in [
        row["action_type"]
        for row in trajectory_authorized(no_call_authority)
    ][:3]


def test_open_breaker_releases_without_calling_primary(tmp_path):
    primary = _IdempotentProvider()
    fallback = _FallbackProvider()
    register_provider(primary)
    register_provider(fallback)
    for _ in range(5):
        default_breaker.record_failure(primary.name)

    config = _config(
        _route(primary.name, fallback=_route(fallback.name, model="fallback"))
    )
    authority, parent = _authority(tmp_path, config=config)
    result = _dispatch(
        authority,
        parent,
        config,
    )
    assert result.model == "fallback"
    assert primary.calls == []
    assert len(fallback.calls) == 1
    releases = [
        row["payload"]
        for row in trajectory_authorized(authority)
        if row["action_type"] == "research.call_released"
    ]
    assert [payload["reason"] for payload in releases] == ["circuit_open"]


def test_ambiguous_failure_retains_hold_and_retry_reuses_key(tmp_path):
    authority, parent = _authority(tmp_path)
    provider = _IdempotentProvider(
        fail=ProviderError(
            "timeout after send",
            provider="paid",
            model="model",
            latency_ms=10,
            retryable=True,
        )
    )
    fallback = _FallbackProvider()
    register_provider(provider)
    register_provider(fallback)
    config = _config(_route(provider.name, fallback=_route(fallback.name, model="fb")))

    with pytest.raises(ProviderError, match="timeout after send"):
        _dispatch(authority, parent, config)
    assert fallback.calls == []
    first_key = provider.calls[0]["idempotency_key"]
    rows = trajectory_authorized(authority)
    assert [row["action_type"] for row in rows] == [
        "investigation.start_requested",
        "research.call_reserved",
        "dispatch.call",
    ]

    provider.fail = None
    result = _dispatch(authority, parent, config)
    assert result.text == "budgeted result"
    assert provider.calls[1]["idempotency_key"] == first_key
    assert fallback.calls == []
    assert [row["action_type"] for row in trajectory_authorized(authority)].count(
        "research.call_settled"
    ) == 1


def test_crash_after_dispatch_receipt_replays_provider_and_settles_once(
    tmp_path, monkeypatch
):
    authority, parent = _authority(tmp_path)
    provider = _IdempotentProvider()
    register_provider(provider)
    config = _config(_route(provider.name))
    real_settle = router.settle_research_call_authorized

    def crash(*_: Any, **__: Any):
        raise RuntimeError("crash after dispatch receipt")

    monkeypatch.setattr(router, "settle_research_call_authorized", crash)
    with pytest.raises(RuntimeError, match="after dispatch"):
        _dispatch(authority, parent, config)
    key = provider.calls[0]["idempotency_key"]
    monkeypatch.setattr(router, "settle_research_call_authorized", real_settle)

    result = _dispatch(authority, parent, config)
    assert result.text == "budgeted result"
    assert provider.calls[1]["idempotency_key"] == key
    rows = trajectory_authorized(authority)
    assert sum(row["action_type"] == "dispatch.call" for row in rows) == 1
    assert sum(row["action_type"] == "research.call_settled" for row in rows) == 1


def test_concurrent_same_operation_uses_one_dispatch_and_settlement(tmp_path):
    authority, parent = _authority(tmp_path)
    provider = _IdempotentProvider(barrier=threading.Barrier(2))
    register_provider(provider)
    config = _config(_route(provider.name))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: _dispatch(authority, parent, config),
                range(2),
            )
        )
    assert [result.text for result in results] == ["budgeted result"] * 2
    assert len(provider.calls) == 2
    assert len({call["idempotency_key"] for call in provider.calls}) == 1
    rows = trajectory_authorized(authority)
    assert sum(row["action_type"] == "research.call_reserved" for row in rows) == 1
    assert sum(row["action_type"] == "dispatch.call" for row in rows) == 1
    assert sum(row["action_type"] == "research.call_settled" for row in rows) == 1


def test_settled_replay_reconstructs_text_with_same_provider_key(tmp_path):
    authority, parent = _authority(tmp_path)
    provider = _IdempotentProvider()
    register_provider(provider)
    config = _config(_route(provider.name))
    first = _dispatch(authority, parent, config)
    replay = _dispatch(authority, parent, config)
    assert replay.text == first.text
    assert len(provider.calls) == 2
    assert provider.calls[0]["idempotency_key"] == provider.calls[1]["idempotency_key"]
    rows = trajectory_authorized(authority)
    assert sum(row["action_type"] == "dispatch.call" for row in rows) == 1
    assert sum(row["action_type"] == "research.call_settled" for row in rows) == 1


def test_authenticated_dispatch_rejects_caller_key_and_uses_accepted_pricing_on_drift(
    tmp_path
):
    authority, parent = _authority(tmp_path)
    provider = _IdempotentProvider(
        fail=ProviderError(
            "ambiguous",
            provider="paid",
            model="model",
            latency_ms=1,
            retryable=True,
        )
    )
    register_provider(provider)
    config = _config(_route(provider.name))
    with investigation_authority_context(authority), pytest.raises(
        ValueError, match="derives its idempotency key"
    ):
        dispatch(
            "bounded prompt",
            "decomposer",
            investigation_id=authority.investigation_id,
            parent_event_id=parent,
            config=config,
            idempotency_key="caller-controlled",
        )
    assert provider.calls == []

    with pytest.raises(ProviderError, match="ambiguous"):
        _dispatch(authority, parent, config)
    provider.fail = None
    changed = _config(
        replace(
            _route(
                "mutable-config-provider",
                model="mutable-config-model",
                pricing=_authoritative_pricing(
                    input_per_mtok=11.0,
                    output_per_mtok=20.0,
                    cached_input_per_mtok=1.0,
                ),
            ),
            max_tokens=7,
            temperature=0.9,
            context_budget_tokens=2000,
            fallback=None,
        )
    )
    result = _dispatch(authority, parent, changed)
    assert result.text == "budgeted result"
    assert len(provider.calls) == 2
    assert provider.calls[0]["idempotency_key"] == provider.calls[1]["idempotency_key"]
    assert provider.calls[1]["temperature"] == 0.2
    assert provider.calls[1]["max_tokens"] == 100
    assert provider.calls[1]["model"] == "model"
    settled = trajectory_authorized(authority)[-1]
    assert settled["action_type"] == "research.call_settled"
    assert settled["payload"]["actual_cost_usd"] == pytest.approx(0.0002)
    reservation = trajectory_authorized(authority)[1]["payload"]
    assert reservation["temperature"] == 0.2
    assert reservation["context_budget_tokens"] == 1000


def test_authenticated_route_override_cannot_reuse_primary_pricing(tmp_path):
    base_config = _config(_route("primary", model="primary-model"))
    authority, parent = _authority(tmp_path, config=base_config)
    provider = _IdempotentProvider()
    register_provider(provider)
    with investigation_authority_context(authority), pytest.raises(
        ValueError, match="route is fixed by its quote"
    ):
        dispatch(
            "bounded prompt",
            "decomposer",
            investigation_id=authority.investigation_id,
            parent_event_id=parent,
            config=base_config,
            provider_override=provider.name,
            model_override="override-model",
        )
    assert provider.calls == []
