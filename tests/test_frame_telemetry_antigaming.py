"""AFA-S2 — the anti-gaming pre-accrual filter on the frame-telemetry surface.

The route classifies each batch via frame_ivt, drops GIVT/SIVT-invalid seconds
BEFORE allocation (a REVIEW/BLOCK window is never allocated at all), reports
the honest filtered-seconds counts + verdict + signals in the response, and
enforces the per-identity dwell saturation cap when one is defined. Server-
minted value (AFA-S1) is untouched: every test prices the window through the
mint seam, never through the request body.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api import ad_routes
from interfaces.research.api.app import create_app
from substrate.ad_inventory.frame_attention import (
    FRAME_TELEMETRY_SCHEMA_VERSION,
    FrameAttentionSample,
    FrameSecond,
    WindowFrameBatch,
)
from substrate.anti_gaming.frame_ivt import (
    MIN_SIVT_WINDOW_SECONDS,
    REASON_CONSTANT_ATTENTION,
    REASON_DUPLICATE_INDEX,
    classify_batch,
)


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-ad-antigaming-")
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


def _seed_book(db_path, *, document_id):
    from runtime.db_lock import connect_write
    from substrate.books import ingest as bingest
    from substrate.graph.ops import insert_document

    with connect_write(db_path, purpose="test:seed_book") as con:
        insert_document(con, document_id=document_id, source_tier=2,
                        document_type="book", title="Earner", author="A",
                        raw_text="public domain body")
        bingest.register_book(con, document_id=document_id,
                              content_class="public_domain",
                              rights_holder_name="Earner Estate")


def _mint_value(monkeypatch, cents):
    """Patch the SERVER-side value seam (AFA-S1) — the request body never
    carries a value."""
    monkeypatch.setattr(
        ad_routes,
        "resolve_window_value_cents",
        lambda *, owner_user_id, window_id, con: cents,
    )


def _mint_cap(monkeypatch, cap_ms):
    """Patch the per-identity saturation-cap seam (AFA-S2 W2-S2)."""
    monkeypatch.setattr(
        ad_routes,
        "resolve_dwell_cap_ms",
        lambda *, owner_user_id: cap_ms,
    )


def _batch_n(
    window_id,
    n_seconds,
    *,
    asset_id="pd-earner",
    dwell=1000,
    duplicate_last_as=None,
):
    """A clean monotonic window of ``n_seconds`` identical seconds. Pass
    ``duplicate_last_as=i`` to make the last second a duplicate of index ``i``
    (a GIVT replay)."""
    seconds = []
    for i in range(n_seconds):
        idx = duplicate_last_as if (i == n_seconds - 1 and duplicate_last_as is not None) else i
        seconds.append({
            "second_index": idx,
            "lens": "read",
            "samples": [{
                "asset_id": asset_id,
                "viewport_area_fraction": 0.6,
                "prominence": 0.7,
                "focused_dwell_ms": dwell,
            }],
        })
    return {
        "window_id": window_id,
        "schema_version": FRAME_TELEMETRY_SCHEMA_VERSION,
        "seconds": seconds,
    }


def _dataclass_batch(window_id, seconds):
    """The frozen-contract mirror of ``_batch_n``'s wire shape (for comparing
    the response's counts against the classifier's own output)."""
    return WindowFrameBatch(
        window_id=window_id,
        seconds=tuple(
            FrameSecond(
                second_index=s["second_index"],
                lens=s["lens"],
                samples=tuple(
                    FrameAttentionSample(
                        asset_id=sm["asset_id"],
                        viewport_area_fraction=sm["viewport_area_fraction"],
                        prominence=sm["prominence"],
                        focused_dwell_ms=sm["focused_dwell_ms"],
                        content_class="public_domain",
                    )
                    for sm in s["samples"]
                ),
            )
            for s in seconds
        ),
        ad_value_usd_cents=1000,
    )


# ── valid passes ────────────────────────────────────────────────────────────


def test_valid_batch_passes_clean(isolated_db, monkeypatch):
    _mint_value(monkeypatch, 1000)
    _seed_book(isolated_db, document_id="pd-earner")
    resp = _client().post(
        "/api/ad/frame-telemetry", json=_batch_n("win:clean", 4)
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["fraud_verdict"] == "pass"
    assert body["filtered_seconds"] == 0
    assert body["filtered_second_counts"] == {}
    assert body["verdict_signals"] == {}
    assert body["clamped_dwell_ms"] == 0
    assert body["clamped_cents"] == 0
    assert body["contributor_cents"] == 1000
    assert body["reconciles"] is True


# ── GIVT filtered ───────────────────────────────────────────────────────────


def test_givt_duplicate_second_dropped_before_allocation(isolated_db, monkeypatch):
    _mint_value(monkeypatch, 1000)
    _seed_book(isolated_db, document_id="pd-earner")
    # 4 seconds; the last is a REPLAY of index 1 (GIVT). It must never be
    # allocated — the 3 valid seconds split the whole value (denominator 3).
    resp = _client().post(
        "/api/ad/frame-telemetry",
        json=_batch_n("win:givt", 4, duplicate_last_as=1),
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["fraud_verdict"] == "pass"  # 1/4 invalid → below REVIEW
    assert body["filtered_seconds"] == 1
    assert body["filtered_second_counts"] == {REASON_DUPLICATE_INDEX: 1}
    assert body["contributor_cents"] + body["house_cents"] == 1000
    assert body["contributor_cents"] == 1000  # nothing diluted, nothing earned by the replay
    assert body["reconciles"] is True


# ── SIVT filtered ───────────────────────────────────────────────────────────


def test_sivt_constant_attention_window_held_never_allocated(isolated_db, monkeypatch):
    _mint_value(monkeypatch, 2000)
    _seed_book(isolated_db, document_id="pd-earner")
    # Every second identical over a long window → SIVT constant-attention →
    # REVIEW. The WHOLE window is held: no contributor accrues, the value sits
    # in the house review-hold, and the response names the heuristic.
    n = MIN_SIVT_WINDOW_SECONDS + 4
    resp = _client().post(
        "/api/ad/frame-telemetry", json=_batch_n("win:sivt", n, dwell=800)
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["fraud_verdict"] == "review"
    assert body["contributor_cents"] == 0
    assert body["house_cents"] == 2000
    assert body["asset_count"] == 0
    assert body["filtered_seconds"] == n  # no second was allocated
    assert REASON_CONSTANT_ATTENTION in body["verdict_signals"]
    assert body["reconciles"] is True


# ── mixed partial + filtered count ──────────────────────────────────────────


def test_mixed_partial_filter_conserves(isolated_db, monkeypatch):
    _mint_value(monkeypatch, 1001)  # odd cents → rounding must still conserve
    _seed_book(isolated_db, document_id="pd-earner")
    resp = _client().post(
        "/api/ad/frame-telemetry",
        json=_batch_n("win:mixed", 8, duplicate_last_as=3),
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["fraud_verdict"] == "pass"  # 1/8 invalid → below REVIEW
    assert body["filtered_seconds"] == 1
    assert body["filtered_second_counts"] == {REASON_DUPLICATE_INDEX: 1}
    assert body["contributor_cents"] + body["house_cents"] == 1001
    assert body["reconciles"] is True


def test_filtered_count_matches_classifier_exactly(isolated_db, monkeypatch):
    _mint_value(monkeypatch, 1000)
    _seed_book(isolated_db, document_id="pd-earner")
    wire = _batch_n("win:count", 5, duplicate_last_as=2)
    resp = _client().post("/api/ad/frame-telemetry", json=wire)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    # The response's per-reason counts are EXACTLY the classifier's own counts
    # for the same batch — the honest report, not a summary.
    expected = classify_batch(_dataclass_batch("win:count", wire["seconds"]))
    assert body["filtered_second_counts"] == expected.counts_by_reason()
    assert body["filtered_seconds"] == len(expected.invalid_positions)


# ── saturation cap ──────────────────────────────────────────────────────────


def test_saturation_cap_clamps_and_reports(isolated_db, monkeypatch):
    _mint_value(monkeypatch, 1000)
    _mint_cap(monkeypatch, 1500)  # a tight test cap
    _seed_book(isolated_db, document_id="pd-earner")
    client = _client()
    # Window A: 2000 ms countable dwell, day prior 0 → 1500 counts, 500 clamped.
    r1 = client.post("/api/ad/frame-telemetry", json=_batch_n("win:capA", 2))
    assert r1.status_code == 202, r1.text
    a = r1.json()
    assert a["clamped_dwell_ms"] == 500
    assert a["clamped_cents"] == 250
    assert a["contributor_cents"] == 750
    assert a["house_cents"] == 250
    assert a["reconciles"] is True
    # Window B, same identity + asset + day: the day is saturated → NOTHING new
    # counts; the whole value routes to house (bounded extraction).
    r2 = client.post("/api/ad/frame-telemetry", json=_batch_n("win:capB", 2))
    assert r2.status_code == 202, r2.text
    b = r2.json()
    assert b["clamped_dwell_ms"] == 2000
    assert b["clamped_cents"] == 1000
    assert b["contributor_cents"] == 0
    assert b["house_cents"] == 1000
    assert b["reconciles"] is True


def test_no_saturation_cap_when_undefined(isolated_db, monkeypatch):
    _mint_value(monkeypatch, 1000)
    _mint_cap(monkeypatch, None)  # no cap defined for this identity
    _seed_book(isolated_db, document_id="pd-earner")
    resp = _client().post("/api/ad/frame-telemetry", json=_batch_n("win:noCap", 2))
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["clamped_dwell_ms"] == 0
    assert body["clamped_cents"] == 0
    assert body["contributor_cents"] == 1000


# ── post-filter conservation ────────────────────────────────────────────────


def test_post_filter_conservation_across_all_kinds(isolated_db, monkeypatch):
    """Whatever the filter does — clean, GIVT-dropped, SIVT-held, capped — the
    window always reconciles: Σ contributor + house == total, to the cent."""
    _mint_value(monkeypatch, 1000)
    _mint_cap(monkeypatch, 1500)
    _seed_book(isolated_db, document_id="pd-earner")
    client = _client()
    cases = [
        _batch_n("win:cons-clean", 4),
        _batch_n("win:cons-givt", 4, duplicate_last_as=1),
        _batch_n("win:cons-sivt", MIN_SIVT_WINDOW_SECONDS + 4, dwell=800),
        _batch_n("win:cons-capA", 2),
        _batch_n("win:cons-capB", 2),
    ]
    for case in cases:
        resp = client.post("/api/ad/frame-telemetry", json=case)
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["reconciles"] is True
        assert (
            body["contributor_cents"] + body["house_cents"]
            == body["total_ad_value_cents"]
        ), body
