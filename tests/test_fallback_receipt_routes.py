from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.settings_budget import settings_router
from substrate.research_spend import (
    FallbackChainManifest,
    FallbackRouteManifest,
    ResearchSpendLedger,
    RunBinding,
)


def _app(owner_id: str | None = "owner-a") -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def identify(request: Request, call_next):  # type: ignore[no-untyped-def]
        if owner_id is not None:
            request.state.user_id = owner_id
        return await call_next(request)

    app.include_router(settings_router)
    return app


def _seed(path: Path, *, owner_id: str = "owner-a", chain_id: str = "chain-a") -> None:
    ledger = ResearchSpendLedger(path)
    ledger.ensure_schema()
    binding = RunBinding("run-a", owner_id, "session-a", "plan-a", 1)
    ledger.create_or_reopen_run("create-a", binding, 200)
    route = FallbackRouteManifest(
        fallback_index=0,
        seam_id="research.answer",
        provider="provider-a",
        model="model-a",
        operation="generate",
        operation_digest="operation-digest",
        projection_digest="projection-digest",
        rate_snapshot="rates-a",
        projected_max_cents=75,
        reservation_key="private-reservation-key",
        provider_idempotency_key="private-provider-key",
    )
    ledger.register_fallback_manifest(
        "register-a",
        binding,
        FallbackChainManifest(chain_id, "private-logical-operation", "operation-digest", (route,)),
    )


def test_history_is_owner_derived_bounded_and_value_minimized(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    monkeypatch.setenv("ANTIEK_RESEARCH_SPEND_DB", str(db_path))
    _seed(db_path)

    response = TestClient(_app()).get("/settings/fallback-receipts?limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["authority"] == "read_only_fallback_receipt_history"
    assert body["items"][0]["outcome"] == "unattempted"
    assert body["items"][0]["routes"][0]["projected_max_cents"] == 75
    serialized = response.text
    for private in (
        "owner-a",
        "run-a",
        "private-logical-operation",
        "private-reservation-key",
        "private-provider-key",
    ):
        assert private not in serialized


def test_history_hides_other_owners_and_requires_identity(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    monkeypatch.setenv("ANTIEK_RESEARCH_SPEND_DB", str(db_path))
    _seed(db_path)

    assert TestClient(_app("owner-b")).get("/settings/fallback-receipts").json()["items"] == []
    assert TestClient(_app(None)).get("/settings/fallback-receipts").status_code == 401


def test_cursor_and_integrity_fail_value_free(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    monkeypatch.setenv("ANTIEK_RESEARCH_SPEND_DB", str(db_path))
    _seed(db_path)
    client = TestClient(_app())

    invalid = client.get("/settings/fallback-receipts?cursor=not-base64!!")
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "fallback history cursor is invalid"}

    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TRIGGER research_fallback_chains_no_update")
        connection.execute(
            "UPDATE research_fallback_chains SET manifest_sha256='corrupt' WHERE chain_id='chain-a'"
        )
    corrupt = client.get("/settings/fallback-receipts")
    assert corrupt.status_code == 503
    assert corrupt.json() == {"detail": "fallback receipt history is unavailable"}
    assert str(db_path) not in corrupt.text


def test_missing_ledger_is_unavailable_not_empty(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "missing.sqlite3"
    monkeypatch.setenv("ANTIEK_RESEARCH_SPEND_DB", str(db_path))

    response = TestClient(_app()).get("/settings/fallback-receipts")

    assert response.status_code == 503
    assert response.json() == {"detail": "fallback receipt history is unavailable"}
    assert not db_path.exists()


def test_conflicting_registration_receipt_fails_value_free(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    monkeypatch.setenv("ANTIEK_RESEARCH_SPEND_DB", str(db_path))
    _seed(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TRIGGER research_spend_commands_no_update")
        connection.execute(
            "UPDATE research_spend_commands SET command_kind='tampered' "
            "WHERE command_key='register-a'"
        )

    response = TestClient(_app()).get("/settings/fallback-receipts")

    assert response.status_code == 503
    assert response.json() == {"detail": "fallback receipt history is unavailable"}
    assert "register-a" not in response.text


def test_approval_is_exact_replayable_minimized_and_creates_no_hold(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    monkeypatch.setenv("ANTIEK_RESEARCH_SPEND_DB", str(db_path))
    _seed(db_path)
    client = TestClient(_app())
    manifest_sha256 = client.get("/settings/fallback-receipts").json()["items"][0][
        "manifest_sha256"
    ]
    payload = {
        "expected_manifest_sha256": manifest_sha256,
        "expected_ceiling_cents": 200,
    }

    first = client.post("/settings/fallback-receipts/chain-a/approval", json=payload)
    replay = client.post("/settings/fallback-receipts/chain-a/approval", json=payload)

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.headers["cache-control"] == "no-store"
    assert set(first.json()) == {
        "authority",
        "approval_id",
        "chain_id",
        "manifest_sha256",
        "currency",
        "ceiling_cents",
        "maximum_chain_exposure_cents",
        "approved_at",
    }
    assert first.json()["maximum_chain_exposure_cents"] == 75
    history = client.get("/settings/fallback-receipts").json()["items"][0]
    assert history["approval_id"] == first.json()["approval_id"]
    assert history["approved_at"] == first.json()["approved_at"]
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT count(*) FROM research_spend_holds").fetchone()[0] == 0


def test_approval_rejects_foreign_or_changed_authority_value_free(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    monkeypatch.setenv("ANTIEK_RESEARCH_SPEND_DB", str(db_path))
    _seed(db_path)
    client = TestClient(_app())
    digest = client.get("/settings/fallback-receipts").json()["items"][0]["manifest_sha256"]

    foreign = TestClient(_app("owner-b")).post(
        "/settings/fallback-receipts/chain-a/approval",
        json={"expected_manifest_sha256": digest, "expected_ceiling_cents": 200},
    )
    changed = client.post(
        "/settings/fallback-receipts/chain-a/approval",
        json={"expected_manifest_sha256": "0" * 64, "expected_ceiling_cents": 200},
    )
    extra = client.post(
        "/settings/fallback-receipts/chain-a/approval",
        json={
            "expected_manifest_sha256": digest,
            "expected_ceiling_cents": 200,
            "owner_id": "owner-a",
        },
    )

    assert foreign.status_code == 404
    assert changed.status_code == 409
    assert extra.status_code == 422
    assert foreign.headers["cache-control"] == "no-store"
    assert changed.headers["cache-control"] == "no-store"
    assert "owner-a" not in foreign.text + changed.text
