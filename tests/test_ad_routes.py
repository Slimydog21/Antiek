"""Read SPR-09 — ad-border HTTP surfaces.

Mechanical gates:
  * POST /api/ad/frame-telemetry accepts a valid WindowFrameBatch, accrues via
    the SPR-05 engine through the ONE escrow seam, reconciles to the cent, and
    is idempotent on re-post.
  * a schema_version mismatch is rejected (409); an out-of-range sample is
    rejected (422) by the frozen-dataclass __post_init__.
  * the client-supplied content_class hint is NOT trusted — eligibility is
    resolved server-side from the documents gate columns.
  * GET /api/ad/fill returns a HOUSE fill (never blank) when no advertiser
    matches, promoting a servable book and never the book being read.
  * §9.0 — no gated body text in any ad payload.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.ad_inventory.frame_attention import FRAME_TELEMETRY_SCHEMA_VERSION

_GATED_BODY = "GATED_BOOK_BODY_should_never_appear_in_an_ad_payload_qwxz"


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-ad-routes-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client():
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def _seed_book(db_path, *, document_id, title, author, content_class, raw_text,
               rights_holder_name=None):
    from runtime.db_lock import connect_write
    from substrate.books import ingest as bingest
    from substrate.graph.ops import insert_document

    with connect_write(db_path, purpose="test:seed_book") as con:
        insert_document(con, document_id=document_id, source_tier=2,
                        document_type="book", title=title, author=author,
                        raw_text=raw_text)
        bingest.register_book(con, document_id=document_id,
                              content_class=content_class,
                              rights_holder_name=rights_holder_name)


def _ip_holder_of(db_path, document_id):
    from runtime.db_lock import connect_read

    con = connect_read(db_path)
    try:
        row = con.execute(
            "SELECT ip_holder_id FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def _escrow_of(db_path, ip_holder_id):
    from runtime.db_lock import connect_read
    from substrate import ip_holders

    con = connect_read(db_path)
    try:
        holder = ip_holders.get(con, ip_holder_id)
    finally:
        con.close()
    return holder.escrow_balance_usd if holder else None


# ── frame-telemetry: happy path + accrual through the SPR-05 seam ────


def _batch(window_id="win-1", *, asset_id="pd-earner", cents=1000):
    return {
        "window_id": window_id,
        "ad_value_usd_cents": cents,
        "schema_version": FRAME_TELEMETRY_SCHEMA_VERSION,
        "seconds": [
            {
                "second_index": 0,
                "lens": "read",
                "samples": [
                    {
                        "asset_id": asset_id,
                        "viewport_area_fraction": 0.8,
                        "prominence": 0.9,
                        "focused_dwell_ms": 800,
                    }
                ],
            },
            {
                "second_index": 1,
                "lens": "read",
                "samples": [
                    {
                        "asset_id": asset_id,
                        "viewport_area_fraction": 0.7,
                        "prominence": 0.6,
                        "focused_dwell_ms": 1000,
                    }
                ],
            },
        ],
    }


def test_frame_telemetry_accepts_and_accrues(isolated_db):
    _seed_book(isolated_db, document_id="pd-earner", title="Earner",
               author="A", content_class="public_domain",
               raw_text="public domain body", rights_holder_name="Earner Estate")
    holder = _ip_holder_of(isolated_db, "pd-earner")
    assert holder is not None
    before = _escrow_of(isolated_db, holder)

    resp = _client().post("/api/ad/frame-telemetry", json=_batch(cents=1000))
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["window_id"] == "win-1"
    assert body["total_ad_value_cents"] == 1000
    # The single eligible asset earns the whole window; reconciles to the cent.
    assert body["contributor_cents"] + body["house_cents"] == 1000
    assert body["asset_count"] == 1
    assert body["reconciles"] is True
    assert body["telemetry_version"] == FRAME_TELEMETRY_SCHEMA_VERSION

    # Escrow grew via the ONE sanctioned seam (composed, not re-implemented).
    after = _escrow_of(isolated_db, holder)
    assert after > before


def test_frame_telemetry_idempotent_on_repost(isolated_db):
    _seed_book(isolated_db, document_id="pd-earner", title="Earner", author="A",
               content_class="public_domain", raw_text="body",
               rights_holder_name="Earner Estate")
    holder = _ip_holder_of(isolated_db, "pd-earner")
    client = _client()
    client.post("/api/ad/frame-telemetry", json=_batch())
    once = _escrow_of(isolated_db, holder)
    # Re-posting the identical batch must not double-accrue.
    r2 = client.post("/api/ad/frame-telemetry", json=_batch())
    assert r2.status_code == 202
    twice = _escrow_of(isolated_db, holder)
    assert once == twice


def test_unknown_asset_is_house_not_an_earner(isolated_db):
    # No documents row for this asset → NULL content_class → ineligible
    # (deny-by-default). The whole window becomes a house second.
    resp = _client().post(
        "/api/ad/frame-telemetry", json=_batch(asset_id="ghost-asset", cents=500)
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["asset_count"] == 0
    assert body["house_cents"] == 500
    assert body["contributor_cents"] == 0
    assert body["reconciles"] is True


def test_client_content_class_hint_is_not_trusted(isolated_db):
    # A private user_owned book is INELIGIBLE to earn. A malicious client echoes
    # content_class="public_domain"; the backend must resolve the real class
    # (user_owned) server-side and refuse to accrue.
    _seed_book(isolated_db, document_id="private-1", title="Private", author="Me",
               content_class="user_owned", raw_text="private body",
               rights_holder_name="Me Estate")
    batch = _batch(asset_id="private-1", cents=400)
    batch["seconds"][0]["samples"][0]["content_class"] = "public_domain"  # lie
    batch["seconds"][1]["samples"][0]["content_class"] = "public_domain"
    resp = _client().post("/api/ad/frame-telemetry", json=batch)
    assert resp.status_code == 202
    body = resp.json()
    # Resolved server-side as ineligible → house, not an earner.
    assert body["asset_count"] == 0
    assert body["house_cents"] == 400


# ── frame-telemetry: rejection paths ─────────────────────────────────


def test_frame_telemetry_version_mismatch_rejected(isolated_db):
    batch = _batch()
    batch["schema_version"] = "frame-telemetry-vOLD"
    resp = _client().post("/api/ad/frame-telemetry", json=batch)
    assert resp.status_code == 409
    assert "schema mismatch" in resp.json()["detail"]


def test_frame_telemetry_out_of_range_sample_rejected(isolated_db):
    batch = _batch()
    batch["seconds"][0]["samples"][0]["viewport_area_fraction"] = 1.5  # out of [0,1]
    resp = _client().post("/api/ad/frame-telemetry", json=batch)
    assert resp.status_code == 422
    assert "viewport_area_fraction" in resp.json()["detail"]


def test_frame_telemetry_bad_lens_rejected(isolated_db):
    batch = _batch()
    batch["seconds"][0]["lens"] = "doodle"
    resp = _client().post("/api/ad/frame-telemetry", json=batch)
    assert resp.status_code == 422


# ── fill: house fill is the zero-buyer default ───────────────────────


def test_fill_returns_house_when_no_advertiser(isolated_db):
    _seed_book(isolated_db, document_id="pd-other", title="Promotable", author="X",
               content_class="public_domain", raw_text="body")
    _seed_book(isolated_db, document_id="pd-current", title="Reading Now", author="Y",
               content_class="public_domain", raw_text="body")
    resp = _client().get("/api/ad/fill?document_id=pd-current&page_index=3&position=top")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "house"
    assert body["revenue_usd_cents"] == 0
    assert body["slot_id"] == "slot:pd-current:p3:top"
    # House promotes a servable book that is NOT the one being read.
    assert body["house"] is not None
    assert body["house"]["promoted_document_id"] == "pd-other"
    assert body["ad"] is None


def test_fill_house_with_no_candidates_is_still_house(isolated_db):
    # Only the book being read is servable → nothing else to promote → a neutral
    # house fill (null promo), never blank/broken.
    _seed_book(isolated_db, document_id="pd-current", title="Only Book", author="Y",
               content_class="public_domain", raw_text="body")
    body = _client().get(
        "/api/ad/fill?document_id=pd-current&page_index=0&position=bottom"
    ).json()
    assert body["kind"] == "house"
    assert body["house"] is None


def test_fill_rejects_unknown_position(isolated_db):
    resp = _client().get("/api/ad/fill?document_id=d&page_index=0&position=middle")
    assert resp.status_code == 422


# ── §9.0 — no gated body in any ad payload ───────────────────────────


def test_no_gated_body_in_fill_payload(isolated_db):
    _seed_book(isolated_db, document_id="gated-1", title="Gated", author="Z",
               content_class="restricted_pending_opt_in", raw_text=_GATED_BODY)
    _seed_book(isolated_db, document_id="pd-current", title="Reading", author="Y",
               content_class="public_domain", raw_text="body")
    # A gated book is never servable → never a house-promo candidate, and its
    # body never appears regardless.
    resp = _client().get("/api/ad/fill?document_id=pd-current&page_index=1&position=top")
    assert resp.status_code == 200
    assert _GATED_BODY not in resp.text


def test_no_gated_body_in_telemetry_payload(isolated_db):
    # A gated book IS eligible to earn (to escrow, §9.10) but its body must never
    # surface in the accrual response.
    _seed_book(isolated_db, document_id="gated-earner", title="Gated", author="Z",
               content_class="restricted_pending_opt_in", raw_text=_GATED_BODY,
               rights_holder_name="Pending Estate")
    resp = _client().post(
        "/api/ad/frame-telemetry", json=_batch(asset_id="gated-earner", cents=600)
    )
    assert resp.status_code == 202
    assert _GATED_BODY not in resp.text
    body = resp.json()
    # Gated-but-public earns to escrow → it is a contributor, not house.
    assert body["asset_count"] == 1
    assert body["contributor_cents"] > 0
