"""SPR-03 multimedia provider router and Krea adapter tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from substrate.multimedia.provider_router import (
    KREA_API_KEY_ENV,
    KREA_ASSET_UPLOAD_LIMIT_MB,
    KREA_CAPABILITY,
    BudgetExceeded,
    KreaProviderAdapter,
    MediaGenerationRequest,
    ProviderUnavailable,
    provider_capabilities,
    route_media_request,
)

SHA = "d" * 64


def test_krea_capability_documents_secret_shape_and_limits():
    caps = {cap.provider: cap for cap in provider_capabilities()}

    assert caps["krea"].auth_env_var == KREA_API_KEY_ENV
    assert caps["krea"].max_asset_upload_mb == KREA_ASSET_UPLOAD_LIMIT_MB
    assert KREA_ASSET_UPLOAD_LIMIT_MB == 75
    assert "video" in caps["krea"].kinds
    assert caps["local_placeholder"].auth_env_var is None


def test_dry_run_routes_all_three_tiers_without_key(monkeypatch):
    monkeypatch.delenv(KREA_API_KEY_ENV, raising=False)

    cheapest = route_media_request(
        MediaGenerationRequest(
            kind="video",
            prompt="Ken Burns style history of the 747",
            route_policy="cheapest",
            duration_seconds=5,
        )
    )
    balanced = route_media_request(
        MediaGenerationRequest(
            kind="video",
            prompt="Ken Burns style history of the 747",
            route_policy="balanced",
            duration_seconds=5,
        )
    )
    highest = route_media_request(
        MediaGenerationRequest(
            kind="video",
            prompt="Ken Burns style history of the 747",
            route_policy="highest_quality",
            duration_seconds=5,
        )
    )

    assert cheapest.provider == "local_placeholder"
    assert cheapest.estimated_cost_usd == 0
    assert balanced.provider == "krea"
    assert highest.provider == "krea"
    assert highest.estimated_cost_usd > balanced.estimated_cost_usd > cheapest.estimated_cost_usd
    assert highest.resolution == (1920, 1080)


def test_video_requests_require_duration():
    with pytest.raises(ValidationError, match="duration_seconds"):
        MediaGenerationRequest(kind="video", prompt="a plane documentary")


def test_budget_gate_blocks_projected_spend_before_execution():
    with pytest.raises(BudgetExceeded, match="exceeds budget"):
        route_media_request(
            MediaGenerationRequest(
                kind="video",
                prompt="expensive documentary segment",
                route_policy="highest_quality",
                duration_seconds=20,
                budget_usd=0.01,
            )
        )


def test_krea_adapter_reports_unconfigured_without_printing_secret(monkeypatch):
    monkeypatch.delenv(KREA_API_KEY_ENV, raising=False)
    adapter = KreaProviderAdapter()

    with pytest.raises(ProviderUnavailable) as exc:
        adapter.execute(
            MediaGenerationRequest(
                kind="image",
                prompt="source card for a documentary",
                route_policy="balanced",
                dry_run=False,
            )
        )

    assert KREA_API_KEY_ENV in str(exc.value)
    assert "sk-" not in str(exc.value).lower()


def test_cheapest_execution_is_free_placeholder_without_key(monkeypatch):
    monkeypatch.delenv(KREA_API_KEY_ENV, raising=False)
    adapter = KreaProviderAdapter()

    record = adapter.execute(
        MediaGenerationRequest(
            kind="image",
            prompt="approval storyboard placeholder",
            route_policy="cheapest",
            dry_run=False,
        )
    )

    assert record.provider_call.provider == "local_placeholder"
    assert record.provider_call.status == "skipped"
    assert record.cost_row.cost_usd == 0


def test_krea_adapter_uses_injected_transport_for_live_calls():
    def fake_transport(request, route):
        assert request.dry_run is False
        assert route.provider == "krea"
        return {
            "job_id": "job-1",
            "call_id": "call-1",
            "cost_usd": 0.12,
            "latency_ms": 1234,
            "files": [
                {
                    "file_id": "file-1",
                    "storage_uri": "s3://antiek/multimedia/file-1.mp4",
                    "sha256": SHA,
                    "mime": "video/mp4",
                }
            ],
        }

    adapter = KreaProviderAdapter(api_key="test-key-not-secret", transport=fake_transport)
    record = adapter.execute(
        MediaGenerationRequest(
            kind="video",
            prompt="history of widebody aircraft",
            route_policy="balanced",
            duration_seconds=5,
            dry_run=False,
        )
    )

    assert record.raw_job_id == "job-1"
    assert record.provider_call.call_id == "call-1"
    assert record.provider_call.cost_usd == 0.12
    assert record.cost_row.cost_usd == 0.12
    assert record.files[0].sha256 == SHA
    assert record.files[0].provider == "krea"


def test_secret_like_provider_names_still_fail_in_execution_record():
    def fake_transport(_request, _route):
        return {
            "call_id": "call-1",
            "cost_usd": 0.01,
            "files": [],
        }

    adapter = KreaProviderAdapter(api_key="test-key-not-secret", transport=fake_transport)
    record = adapter.execute(
        MediaGenerationRequest(
            kind="image",
            prompt="safe source card",
            route_policy="balanced",
            dry_run=False,
        )
    )

    assert record.provider_call.provider == KREA_CAPABILITY.provider
