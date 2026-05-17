"""Tests for middleware/temporal/.

What this file proves:

1. ``classify_relation`` returns the right claim_class for known
   relations from the catalogue, handles substring fallback, returns
   None for unknown / empty inputs.
2. ``evaluate_staleness`` applies the TTL correctly per claim_class
   (personnel 90d, fundamental_capability 730d, etc.) and rejects
   negative ages.
3. ``new_flag_id`` returns a non-empty string.
4. ``emit_staleness_flagged`` produces a typed event that round-trips
   through Event.model_validate with a ``StalenessFlaggedPayload``
   payload.
5. ``emit_staleness_resolve`` produces a typed event with a
   ``StalenessResolvePayload``, rejects unknown status values via the
   Pydantic Literal, and rejects unknown entity_kind values.
"""

from __future__ import annotations

import os
import sys

import pytest
from pydantic import ValidationError

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from middleware.temporal import (  # noqa: E402
    classify_relation,
    emit_staleness_flagged,
    emit_staleness_resolve,
    evaluate_staleness,
    new_flag_id,
)
from substrate.constants import STALENESS_TTL_DAYS  # noqa: E402
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Event,
    StalenessFlaggedPayload,
    StalenessResolvePayload,
)


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


# ---------------------------------------------------------------------------
# 1. classify_relation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relation,expected", [
    ("led_by", "personnel"),
    ("LED_BY", "personnel"),                 # case normalization
    ("supplies", "partnership"),
    ("constrains", "fundamental_capability"),
    ("raised", "funding_ownership"),
    ("raised_series_c", "funding_ownership"),
    ("raised_series_a", "funding_ownership"),  # substring fallback
    ("raised_seed", "funding_ownership"),      # substring fallback
])
def test_classify_relation_known_and_substring_fallback(relation, expected):
    assert classify_relation(relation) == expected


def test_classify_relation_unknown_returns_none():
    assert classify_relation("competes_with") is None
    assert classify_relation("") is None
    assert classify_relation(None) is None


# ---------------------------------------------------------------------------
# 2. evaluate_staleness
# ---------------------------------------------------------------------------


def test_evaluate_stale_when_age_exceeds_ttl():
    # personnel TTL is 90 days; 95 > 90 → stale.
    v = evaluate_staleness("led_by", 95)
    assert v.is_stale is True
    assert v.claim_class == "personnel"
    assert v.ttl_days == 90
    assert v.age_days == 95


def test_evaluate_fresh_when_age_within_ttl():
    v = evaluate_staleness("led_by", 30)
    assert v.is_stale is False


def test_evaluate_boundary_at_exactly_ttl_is_fresh():
    """At exactly TTL, the edge is still fresh (strict > comparison)."""
    v = evaluate_staleness("led_by", 90)
    assert v.is_stale is False


def test_evaluate_fundamental_capability_uses_long_ttl():
    """fundamental_capability is 730d — physics-level constants don't decay."""
    v = evaluate_staleness("constrains", 365)
    assert v.is_stale is False
    assert v.ttl_days == 730


def test_evaluate_unknown_relation_returns_not_stale():
    """If we can't classify the relation, we don't flag — fall through."""
    v = evaluate_staleness("competes_with", 5_000)
    assert v.is_stale is False
    assert v.claim_class is None
    assert v.ttl_days is None
    assert v.age_days == 5_000


def test_evaluate_rejects_negative_age():
    with pytest.raises(ValueError, match="non-negative"):
        evaluate_staleness("led_by", -1)


def test_every_ttl_constant_corresponds_to_a_valid_evaluate_outcome():
    """Sanity: every claim_class in STALENESS_TTL_DAYS produces a
    well-formed verdict when fed a matching relation."""
    # Pick representative relations for each claim_class we want to verify.
    samples = [
        ("led_by", "personnel"),
        ("raised", "funding_ownership"),
        ("supplies", "partnership"),
        ("constrains", "fundamental_capability"),
    ]
    for relation, expected_class in samples:
        v = evaluate_staleness(relation, age_days=STALENESS_TTL_DAYS[expected_class] + 1)
        assert v.is_stale is True
        assert v.claim_class == expected_class


# ---------------------------------------------------------------------------
# 3. new_flag_id
# ---------------------------------------------------------------------------


def test_new_flag_id_is_unique():
    ids = {new_flag_id() for _ in range(50)}
    assert len(ids) == 50


# ---------------------------------------------------------------------------
# 4. emit_staleness_flagged
# ---------------------------------------------------------------------------


def test_emit_staleness_flagged_round_trips_typed():
    fid = new_flag_id()
    eid = emit_staleness_flagged(
        investigation_id="inv-stale",
        flag_id=fid, edge_id="edge-7",
        relation="led_by", claim_class="personnel",
        ttl_days=90, age_days=120,
    )
    rows = trajectory("inv-stale")
    assert len(rows) == 1
    event = Event.model_validate(rows[0])
    assert event.event_id == eid
    assert event.action_type == ActionType.GRAPH_STALENESS_FLAGGED.value
    assert isinstance(event.payload, StalenessFlaggedPayload)
    assert event.payload.flag_id == fid
    assert event.payload.edge_id == "edge-7"
    assert event.payload.relation == "led_by"
    assert event.payload.claim_class == "personnel"
    assert event.payload.ttl_days == 90
    assert event.payload.age_days == 120


# ---------------------------------------------------------------------------
# 5. emit_staleness_resolve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["refreshed", "confirmed_stale", "dismissed"])
def test_emit_staleness_resolve_accepts_valid_status(status):
    fid = new_flag_id()
    eid = emit_staleness_resolve(
        investigation_id="inv-resolve",
        flag_id=fid, entity_kind="edge", entity_id="edge-9",
        status=status, notes="resolved by re-scan",
    )
    event = Event.model_validate(trajectory("inv-resolve")[0])
    assert event.event_id == eid
    assert isinstance(event.payload, StalenessResolvePayload)
    assert event.payload.status == status
    assert event.payload.notes == "resolved by re-scan"


def test_emit_staleness_resolve_rejects_unknown_status():
    with pytest.raises(ValidationError):
        emit_staleness_resolve(
            investigation_id="inv-bad",
            flag_id="f", entity_kind="edge", entity_id="e",
            status="archived",  # not in Literal
        )


def test_emit_staleness_resolve_rejects_unknown_entity_kind():
    with pytest.raises(ValidationError):
        emit_staleness_resolve(
            investigation_id="inv-bad",
            flag_id="f", entity_kind="document",  # not in Literal
            entity_id="e", status="refreshed",
        )


def test_staleness_flagged_payload_rejects_negative_ttl_or_age():
    """Defense at the schema level — Field(ge=0)."""
    with pytest.raises(ValidationError):
        StalenessFlaggedPayload(
            flag_id="f", edge_id="e", relation="led_by",
            claim_class="personnel", ttl_days=-1, age_days=10,
        )
    with pytest.raises(ValidationError):
        StalenessFlaggedPayload(
            flag_id="f", edge_id="e", relation="led_by",
            claim_class="personnel", ttl_days=90, age_days=-1,
        )
