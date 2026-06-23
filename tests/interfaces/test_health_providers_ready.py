"""HealthResponse.providers_ready field (DRW honest failure)."""

from __future__ import annotations

from interfaces.research.api.app import HealthResponse


def test_health_response_declares_providers_ready():
    assert "providers_ready" in HealthResponse.model_fields
    blank = HealthResponse(
        status="ok",
        param_version="x",
        schema_version=1,
        subscriber_count=0,
    )
    assert blank.providers_ready is False