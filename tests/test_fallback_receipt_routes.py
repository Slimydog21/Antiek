from __future__ import annotations

import base64
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


def _configure(monkeypatch, db_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ANTIEK_RESEARCH_SPEND_DB", str(db_path))
    monkeypatch.setenv("ANTIEK_FALLBACK_CURSOR_SIGNING_KEY", "k" * 32)


def _app(owner_id: str | None = "owner-a") -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def identify(request: Request, call_next):  # type: ignore[no-untyped-def]
        if owner_id is not None:
            request.state.user_id = owner_id
        return await call_next(request)

    app.include_router(settings_router)
    return app


def _seed(
    path: Path,
    *,
    owner_id: str = "owner-a",
    chain_id: str = "chain-a",
    ceiling_cents: int = 200,
) -> None:
    ledger = ResearchSpendLedger(path)
    ledger.ensure_schema()
    binding = RunBinding("run-a", owner_id, "session-a", "plan-a", 1)
    ledger.create_or_reopen_run("create-a", binding, ceiling_cents)
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
        route_authority_digest="private-authority-digest",
    )
    ledger.register_fallback_manifest(
        "register-a",
        binding,
        FallbackChainManifest(chain_id, "private-logical-operation", "operation-digest", (route,)),
    )


def test_history_is_owner_derived_bounded_and_value_minimized(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    _configure(monkeypatch, db_path)
    _seed(db_path)

    response = TestClient(_app()).get("/settings/fallback-receipts?limit=1")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert body["authority"] == "read_only_fallback_receipt_history"
    assert body["items"][0]["outcome"] == "unattempted"
    assert body["items"][0]["routes"][0]["projected_max_cents"] == 75
    assert body["items"][0]["currency"] == "USD"
    assert body["items"][0]["ceiling_cents"] == 200
    assert body["items"][0]["maximum_chain_exposure_cents"] == 75
    assert body["items"][0]["approval_eligible"] is True
    serialized = response.text
    for private in (
        "owner-a",
        "run-a",
        "private-logical-operation",
        "private-reservation-key",
        "private-provider-key",
    ):
        assert private not in serialized


def test_over_ceiling_history_remains_visible_but_ineligible(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    _configure(monkeypatch, db_path)
    _seed(db_path, ceiling_cents=50)

    response = TestClient(_app()).get("/settings/fallback-receipts")

    assert response.status_code == 200
    chain = response.json()["items"][0]
    assert chain["maximum_chain_exposure_cents"] == 75
    assert chain["ceiling_cents"] == 50
    assert chain["approval_eligible"] is False


def test_history_hides_other_owners_and_requires_identity(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    _configure(monkeypatch, db_path)
    _seed(db_path)

    assert TestClient(_app("owner-b")).get("/settings/fallback-receipts").json()["items"] == []
    assert TestClient(_app(None)).get("/settings/fallback-receipts").status_code == 401


def test_cursor_and_integrity_fail_value_free(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    _configure(monkeypatch, db_path)
    _seed(db_path)
    client = TestClient(_app())

    invalid = client.get("/settings/fallback-receipts?cursor=not-base64!!")
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "fallback history cursor is invalid"}
    assert invalid.headers["cache-control"] == "private, no-store"

    forged = (
        base64.urlsafe_b64encode(
            b'{"chain_id":"chain-a","created_at":"9999","owner_id":"owner-a","version":1}.bad'
        )
        .decode()
        .rstrip("=")
    )
    tampered = client.get(f"/settings/fallback-receipts?cursor={forged}")
    assert tampered.status_code == 422
    assert tampered.json() == {"detail": "fallback history cursor is invalid"}
    assert tampered.headers["cache-control"] == "private, no-store"

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
    _configure(monkeypatch, db_path)

    response = TestClient(_app()).get("/settings/fallback-receipts")

    assert response.status_code == 503
    assert response.json() == {"detail": "fallback receipt history is unavailable"}
    assert not db_path.exists()


def test_conflicting_registration_receipt_fails_value_free(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    _configure(monkeypatch, db_path)
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
    _configure(monkeypatch, db_path)
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
    assert first.headers["cache-control"] == "private, no-store"
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
    assert history["approval_eligible"] is False
    assert history["ceiling_cents"] == 200
    assert history["maximum_chain_exposure_cents"] == 75
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT count(*) FROM research_spend_holds").fetchone()[0] == 0


def test_approval_rejects_foreign_or_changed_authority_value_free(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    _configure(monkeypatch, db_path)
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
    assert foreign.headers["cache-control"] == "private, no-store"
    assert changed.headers["cache-control"] == "private, no-store"
    assert extra.headers["cache-control"] == "private, no-store"
    assert "owner-a" not in foreign.text + changed.text


def test_approval_validation_failures_are_private_and_value_free(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    _configure(monkeypatch, db_path)
    _seed(db_path)
    client = TestClient(_app())

    missing = client.post("/settings/fallback-receipts/chain-a/approval", json={})
    malformed = client.post(
        "/settings/fallback-receipts/chain-a/approval",
        content=b'{"expected_manifest_sha256":',
        headers={"content-type": "application/json"},
    )

    for response in (missing, malformed):
        assert response.status_code == 422
        assert response.headers["cache-control"] == "private, no-store"
        assert response.json() == {"detail": "fallback approval request is invalid"}


def test_approval_rejects_declared_and_streamed_oversized_bodies_without_caching(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "spend.sqlite3"
    _configure(monkeypatch, db_path)
    _seed(db_path)
    client = TestClient(_app())
    oversized = b"{" + b" " * 4_096 + b"}"

    declared = client.post(
        "/settings/fallback-receipts/chain-a/approval",
        content=oversized,
        headers={"content-type": "application/json"},
    )

    def chunks():  # type: ignore[no-untyped-def]
        yield oversized[:3_000]
        yield oversized[3_000:]

    streamed = client.post(
        "/settings/fallback-receipts/chain-a/approval",
        content=chunks(),
        headers={"content-type": "application/json", "transfer-encoding": "chunked"},
    )

    for response in (declared, streamed):
        assert response.status_code == 413
        assert response.headers["cache-control"] == "private, no-store"
        assert response.json() == {"detail": "fallback approval request is too large"}
