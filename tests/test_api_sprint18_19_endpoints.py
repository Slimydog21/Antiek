"""API endpoint contract tests for Sprint 18-25+ additions."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


def _client():
    app = create_app(register_wrestling=False)
    return TestClient(app)


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


def test_trust_center_loop3_unlock_all_false():
    """Loop 3 unlock criteria all start False until operator
    affirmatively ratifies."""
    client = _client()
    resp = client.get("/trust-center")
    body = resp.json()
    for criterion, met in body["loop_3_unlock_status"].items():
        assert met is False
