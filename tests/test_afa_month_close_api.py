"""AFA S6 M4 — month-close API surface tests (escrow-only, owner-scoped)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from interfaces.research.api.app import create_app

    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", str(tmp_path / "events"))
    # seed minimal ad/accrual tables so a close can run
    from runtime.db_lock import connect_write
    from substrate.ad_inventory import monthly_close
    from substrate.graph import default_db_path
    from substrate.graph.schema import init_database

    # Hermetic artifacts: redirect the close's default artifact dir into tmp
    # (the default is a CWD-relative data/ dir that accumulates across runs).
    monthly_close.default_artifact_dir = lambda period, *, base=None: (  # type: ignore[assignment]
        Path(base) if base is not None else tmp_path / "close-art"
    ) / period

    db = default_db_path()
    with connect_write(db, purpose="test/afa/api/schema") as con:
        init_database(con)
    return create_app(register_wrestling=False, register_providers=False)


def _seed_accrual(tmp_path: Path) -> None:
    """Accrue one real window (server-minted value) into 2026-07 so close_month has data."""

    from runtime.db_lock import connect_write
    from substrate import ip_holders
    from substrate.ad_inventory.frame_attention import (
        FrameAttentionSample,
        FrameSecond,
        WindowFrameBatch,
    )
    from substrate.ad_inventory.frame_attention_accrual import accrue_window
    from substrate.graph import default_db_path
    from substrate.graph.schema import init_database

    db = default_db_path()
    with connect_write(db, purpose="test/afa/api/seed") as con:
        init_database(con)
        holder = ip_holders.create_pre_onboarded(con, display_name="payee-a")
        sample = FrameAttentionSample(
            asset_id="doc-a",
            viewport_area_fraction=0.6,
            prominence=0.8,
            focused_dwell_ms=900,
            content_class="public_domain",
            chunk_id="c-a",
        )
        samples = (sample,)
        batch = WindowFrameBatch(
            window_id="w1",
            seconds=tuple(
                FrameSecond(second_index=i, lens="read", samples=samples)
                for i in range(5)
            ),
            ad_value_usd_cents=1000,
        )
        accrue_window(con, batch, asset_to_ip_holder={"doc-a": holder})
        con.execute(
            "UPDATE frame_attention_accruals SET accrued_at = CAST(? AS TIMESTAMP) "
            "WHERE window_id = ?",
            ["2026-07-10 12:00:00", "w1"],
        )


def test_month_close_api_read_and_close(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """POST closes a month; GET reads the record; statement endpoint verifies."""
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app)

    # nothing closed yet
    assert client.get("/ops/afa/month-close/2026-07").status_code == 404

    # seed + close
    _seed_accrual(tmp_path)
    resp = client.post("/ops/afa/month-close/2026-07")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["period"] == "2026-07"
    assert body["month_root_hex"]
    assert body["statement_count"] >= 1
    assert body["attribution_math_version"] == "attribution-math-v2"

    # idempotent re-close
    resp2 = client.post("/ops/afa/month-close/2026-07")
    assert resp2.status_code == 201
    assert resp2.json()["month_root_hex"] == body["month_root_hex"]

    # read record
    resp3 = client.get("/ops/afa/month-close/2026-07")
    assert resp3.status_code == 200
    assert resp3.json()["month_root_hex"] == body["month_root_hex"]

    # statement + proof (server-verified) — discover the payee id from artifacts
    import json as _json
    from pathlib import Path as _Path

    stmt_files = sorted((_Path(body["artifact_dir"]) / "statements").glob("*.json"))
    assert stmt_files, "no statement artifacts written"
    payee_id = _json.loads(stmt_files[0].read_text(encoding="utf-8"))["payee_id"]
    resp4 = client.get(f"/ops/afa/month-close/2026-07/statement/{payee_id}")
    assert resp4.status_code == 200, resp4.text
    sb = resp4.json()
    assert sb["verified"] is True
    assert sb["statement"]["payee_id"] == payee_id


def test_month_close_api_rejects_bad_period(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app)
    assert client.post("/ops/afa/month-close/not-a-month").status_code == 422
