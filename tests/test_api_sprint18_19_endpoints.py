"""API endpoint contract tests for Sprint 18-25+ additions."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.multi_user import (
    encode_verified_claims_header,
    sign_verified_claims_header,
)


def _client():
    app = create_app(register_wrestling=False)
    return TestClient(app)


def _external_headers(
    monkeypatch,
    *,
    sub: str,
) -> dict[str, str]:
    secret = "trusted-hop-secret"
    monkeypatch.setenv("ANTIEK_EXTERNAL_AUTH_VENDOR", "supabase")
    monkeypatch.setenv("ANTIEK_EXTERNAL_AUTH_HEADER_SECRET", secret)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    encoded = encode_verified_claims_header({
        "sub": sub,
        "email": f"{sub}@example.com",
        "app_metadata": {"antiek_scopes": ["private_research"]},
    })
    signature = sign_verified_claims_header(
        vendor="supabase",
        encoded_claims=encoded,
        secret=secret,
    )
    return {
        "X-Antiek-Verified-Claims": encoded,
        "X-Antiek-Verified-Claims-Signature": signature,
    }


@pytest.fixture()
def isolated_telemetry_preferences(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "ANTIEK_TELEMETRY_PREFERENCES_PATH",
        str(tmp_path / "telemetry_preferences.sqlite"),
    )
    from substrate.trust_center import reset_default_registry

    reset_default_registry()
    yield
    reset_default_registry()


# ── Quality gate endpoint (§13.9) ────────────────────────────────────


def test_quality_gate_evaluate_passes_clean_content():
    client = _client()
    resp = client.post(
        "/quality-gate/evaluate",
        json={
            "text_content": (
                "Neutral-atom platforms demonstrated gate error rates "
                "below 10⁻³ at 100-qubit scale. The cross-comparison "
                "with trapped-ion systems shows similar performance."
            ),
            "cited_chunk_tiers": [1, 2, 2],
            "corpus_sector_terms": ["neutral-atom", "trapped-ion", "qubit"],
            "rubric_score": 0.85,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] is True
    assert body["voice_style_passed"] is True
    assert body["source_tier_passed"] is True
    assert body["verification_passed"] is True


def test_quality_gate_evaluate_rejects_slop():
    client = _client()
    resp = client.post(
        "/quality-gate/evaluate",
        json={
            "text_content": (
                "It is important to note that—indeed—the results show—indeed—"
                "the expected pattern. Furthermore, it is worth noting that—"
                "indeed—the cross-comparison—indeed—is robust. Additionally, "
                "it can be argued that—indeed—the data supports it."
            ),
            "cited_chunk_tiers": [1, 2],
            "corpus_sector_terms": ["pattern"],
            "rubric_score": 0.85,
        },
    )
    body = resp.json()
    assert body["accepted"] is False
    assert body["voice_style_passed"] is False


# ── Billing summary endpoint ──────────────────────────────────────────


def test_billing_summary_empty_returns_zeros():
    client = _client()
    resp = client.get("/billing/summary/__operator__/2026-05")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "__operator__"
    assert body["period"] == "2026-05"
    assert body["record_count"] == 0
    assert body["free_tokens_remaining"] == 5_000_000  # full cap


# ── Cross-graph ask-experts endpoint ──────────────────────────────────


def test_ask_experts_empty_returns_empty():
    """No opted-in users yet; endpoint returns empty candidates."""
    client = _client()
    resp = client.post(
        "/cross-graph/ask-experts",
        json={"topic_query": "quantum", "limit": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidates"] == []


# ── Attribution computation endpoint ─────────────────────────────────


def test_attribution_compute_option_a():
    client = _client()
    resp = client.post(
        "/attribution/compute",
        json={
            "page_id": "page-1",
            "chunk_to_document": {"c-1": "doc-A", "c-2": "doc-A", "c-3": "doc-B"},
            "algorithm": "option_a",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert abs(body["shares"]["doc-A"] - 2/3) < 1e-9
    assert abs(body["shares"]["doc-B"] - 1/3) < 1e-9


def test_attribution_compute_option_b():
    client = _client()
    resp = client.post(
        "/attribution/compute",
        json={
            "page_id": "page-1",
            "chunk_to_document": {"c-1": "doc-tier1", "c-2": "doc-tier3"},
            "chunk_to_claim_confidence": {"c-1": 0.9, "c-2": 0.4},
            "document_to_source_tier": {"doc-tier1": 1, "doc-tier3": 3},
            "algorithm": "option_b",
        },
    )
    body = resp.json()
    assert body["shares"]["doc-tier1"] > body["shares"]["doc-tier3"]


def test_attribution_compute_unknown_algorithm_rejected():
    client = _client()
    resp = client.post(
        "/attribution/compute",
        json={
            "page_id": "page-1",
            "chunk_to_document": {"c-1": "doc-A"},
            "algorithm": "garbage",
        },
    )
    assert resp.status_code == 400


def test_attribution_compute_validation_error_is_client_error():
    client = _client()
    resp = client.post(
        "/attribution/compute",
        json={
            "page_id": "page-1",
            "chunk_to_document": {"c-1": "doc-A"},
            "chunk_to_claim_confidence": {"c-1": 1.5},
            "document_to_source_tier": {"doc-A": 1},
            "algorithm": "option_b",
        },
    )
    assert resp.status_code == 422
    assert "chunk_to_claim_confidence" in resp.json()["detail"]


# ── Auth probe endpoint ─────────────────────────────────────────────


def test_auth_whoami_returns_operator():
    client = _client()
    resp = client.get("/auth/whoami")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "__operator__"
    assert body["is_operator"] is True
    assert "operator" in body["scopes"]


# ── Trust Center endpoint ────────────────────────────────────────────


def test_trust_center_publishes_dp_budgets():
    client = _client()
    resp = client.get("/trust-center")
    assert resp.status_code == 200
    body = resp.json()
    assert body["differential_privacy_epsilon_budgets"]["query_content_telemetry"] == 0.0
    assert body["differential_privacy_epsilon_budgets"]["skill_invocation_frequency"] == 2.0
    assert body["deletion_sla_days"] == 30
    # Per §16.2 REJECT canon
    for epsilon in body["differential_privacy_epsilon_budgets"].values():
        assert epsilon <= 10.0


def test_trust_center_endpoint_reads_live_epsilon_registry():
    from substrate.dp_shuffler import SurfaceConfig
    from substrate.trust_center import default_registry, reset_default_registry

    reset_default_registry()
    default_registry().register(SurfaceConfig(
        surface_name="dispatch_tier_telemetry",
        epsilon_per_day=0.5,
        sensitivity="high",
        description="dispatch tier hint sampling",
        opt_in_required=True,
    ))
    try:
        client = _client()
        resp = client.get("/trust-center")
    finally:
        reset_default_registry()

    assert resp.status_code == 200
    assert (
        resp.json()["differential_privacy_epsilon_budgets"][
            "dispatch_tier_telemetry"
        ]
        == 0.5
    )


def test_trust_center_loop3_unlock_all_false():
    """Loop 3 unlock criteria all start False until operator
    affirmatively ratifies."""
    client = _client()
    resp = client.get("/trust-center")
    body = resp.json()
    for met in body["loop_3_unlock_status"].values():
        assert met is False


def test_telemetry_preferences_seed_from_live_registry(
    isolated_telemetry_preferences,
):
    client = _client()

    resp = client.get("/trust-center/telemetry-preferences")

    assert resp.status_code == 200, resp.text
    by_name = {p["surface_name"]: p for p in resp.json()["preferences"]}
    assert by_name["skill_invocation_frequency"]["enabled"] is True
    assert by_name["source_tier_preference_signals"]["enabled"] is False
    assert by_name["query_content_telemetry"]["enabled"] is False
    assert by_name["query_content_telemetry"]["sensitivity"] == "forbidden"


def test_telemetry_preferences_include_new_registry_surface(
    isolated_telemetry_preferences,
):
    from substrate.dp_shuffler import SurfaceConfig
    from substrate.trust_center import default_registry

    default_registry().register(SurfaceConfig(
        surface_name="dispatch_tier_telemetry",
        epsilon_per_day=0.5,
        sensitivity="high",
        description="dispatch tier hint sampling",
        opt_in_required=True,
    ))
    client = _client()

    resp = client.get("/trust-center/telemetry-preferences")

    assert resp.status_code == 200, resp.text
    by_name = {p["surface_name"]: p for p in resp.json()["preferences"]}
    assert by_name["dispatch_tier_telemetry"]["epsilon_per_day"] == 0.5
    assert by_name["dispatch_tier_telemetry"]["sensitivity"] == "high"
    assert by_name["dispatch_tier_telemetry"]["description"] == (
        "dispatch tier hint sampling"
    )
    assert by_name["dispatch_tier_telemetry"]["enabled"] is False


def test_telemetry_preference_patch_persists(
    isolated_telemetry_preferences,
):
    client = _client()

    patched = client.patch(
        "/trust-center/telemetry-preferences/skill_invocation_frequency",
        json={"enabled": False},
    )
    listed = client.get("/trust-center/telemetry-preferences")

    assert patched.status_code == 200, patched.text
    assert patched.json()["enabled"] is False
    by_name = {p["surface_name"]: p for p in listed.json()["preferences"]}
    assert by_name["skill_invocation_frequency"]["enabled"] is False
    assert by_name["skill_invocation_frequency"]["updated_at"] is not None


def test_telemetry_preference_refuses_forbidden_enable(
    isolated_telemetry_preferences,
):
    client = _client()

    resp = client.patch(
        "/trust-center/telemetry-preferences/query_content_telemetry",
        json={"enabled": True},
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "forbidden_surface"


def test_external_user_telemetry_preferences_are_scoped_to_claims_user(
    isolated_telemetry_preferences, monkeypatch,
):
    client = _client()
    user_a = _external_headers(monkeypatch, sub="reader-a")
    patch_a = client.patch(
        "/trust-center/telemetry-preferences/skill_invocation_frequency",
        json={"enabled": False},
        headers=user_a,
    )
    assert patch_a.status_code == 200, patch_a.text
    assert patch_a.json()["enabled"] is False

    list_a = client.get("/trust-center/telemetry-preferences", headers=user_a)
    by_name_a = {p["surface_name"]: p for p in list_a.json()["preferences"]}
    assert by_name_a["skill_invocation_frequency"]["enabled"] is False
    assert by_name_a["skill_invocation_frequency"]["updated_at"] is not None

    user_b = _external_headers(monkeypatch, sub="reader-b")
    list_b = client.get("/trust-center/telemetry-preferences", headers=user_b)
    by_name_b = {p["surface_name"]: p for p in list_b.json()["preferences"]}
    assert by_name_b["skill_invocation_frequency"]["enabled"] is True
    assert by_name_b["skill_invocation_frequency"]["updated_at"] is not None


def test_external_user_telemetry_preferences_refuse_forbidden_enable(
    isolated_telemetry_preferences, monkeypatch,
):
    client = _client()
    resp = client.patch(
        "/trust-center/telemetry-preferences/query_content_telemetry",
        json={"enabled": True},
        headers=_external_headers(monkeypatch, sub="reader-a"),
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "forbidden_surface"
