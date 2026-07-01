"""Consistency checks for privacy/trust control-plane documentation."""

from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_trust_center_public_names_live_deletion_worker_cli():
    text = (REPO / "docs" / "trust_center_public.md").read_text(encoding="utf-8")

    assert "python -m substrate.deletion_worker" in text
    assert "ANTIEK_TELEMETRY_PREFERENCES_PATH" in text
    assert "telemetry_preferences.sqlite" in text


def test_operator_actions_reflect_privacy_integration_evidence():
    text = (REPO / "docs" / "OPERATOR_ACTIONS.md").read_text(encoding="utf-8")
    api = (REPO / "interfaces" / "research" / "api" / "app.py").read_text(
        encoding="utf-8",
    )
    app = (REPO / "apps" / "reading" / "src" / "App.tsx").read_text(
        encoding="utf-8",
    )
    worker = (
        REPO / "substrate" / "deletion_worker" / "__main__.py"
    ).read_text(encoding="utf-8")
    compact_text = " ".join(text.split())
    table_rows = [
        line
        for line in text.splitlines()
        if line.startswith("| OA-") and " | " in line
    ]
    statuses = [row.split("|")[3].strip() for row in table_rows]

    assert len(table_rows) == 20
    assert sum(status.startswith("OPEN") for status in statuses) == 17
    assert statuses.count("PARTIALLY DONE") == 1
    assert statuses.count("AWAITING OPERATOR TEST") == 1
    assert statuses.count("PARTIALLY MITIGATED") == 1
    assert "Not closed:** 20 total — 17 OPEN, 1 PARTIALLY DONE" in compact_text
    assert "OA-010 | Integration-revert pattern resolved | PARTIALLY MITIGATED" in text
    assert "interfaces/research/api/app.py" in text
    assert "/trust-center/telemetry-preferences" in text
    assert "/trust-center/deletion-requests" in text
    assert "substrate/deletion_worker/__main__.py" in text
    assert "python -m substrate.deletion_worker" in text
    assert '"/trust-center"' in api
    assert '"/trust-center/telemetry-preferences"' in api
    assert '"/trust-center/deletion-requests"' in api
    assert "build_publication" in api
    assert "register_creator_payouts_routes(app)" in api
    assert "register_marketplace_routes(app)" in api
    assert "register_payout_dashboard_routes(app)" in api
    assert "register_operator_advertiser_campaign_routes(app)" in api
    assert 'path="/privacy"' in app
    assert 'path="/trust"' in app
    assert 'path="/marketplace"' in app
    assert 'path="/me/payouts"' in app
    assert 'path="/operator/advertiser-campaigns"' in app
    assert 'path="/operator/payouts/dashboard"' in app
    assert "python -m substrate.deletion_worker" in worker
