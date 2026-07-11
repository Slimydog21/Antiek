"""Pure tests for MO price-ceiling approval compose."""

from __future__ import annotations

from substrate.midnight_oil_price_ceiling_approval_compose import (
    compose_midnight_oil_price_ceiling_approval,
    format_midnight_oil_price_ceiling_approval_summary,
)

GOALS = [
    {"goal_id": "g1", "title": "Map scaling literature"},
    {"goal_id": "g2", "title": "Synthesize open problems"},
]


def test_recommend_only():
    c = compose_midnight_oil_price_ceiling_approval(
        operator_id="op-1",
        work_minutes=120,
        goals=GOALS,
        usd_per_hour=30,
        price_ceiling_ack=False,
        operator_ack=False,
        stage="recommend_only",
    )
    assert c.recommend.recommended_ceiling_usd is not None
    assert c.recommend.recommended_ceiling_usd > 0
    assert c.ceiling_approved is False
    assert c.pack_ready is True
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert "charge_executed=false" in format_midnight_oil_price_ceiling_approval_summary(
        c
    )


def test_approve_ceiling():
    rec = compose_midnight_oil_price_ceiling_approval(
        operator_id="op-1",
        work_minutes=60,
        goals=GOALS,
        usd_per_hour=20,
        price_ceiling_ack=False,
        operator_ack=False,
        stage="recommend_only",
    )
    recommended = rec.recommend.recommended_ceiling_usd
    assert recommended is not None
    c = compose_midnight_oil_price_ceiling_approval(
        operator_id="op-1",
        work_minutes=60,
        goals=GOALS,
        usd_per_hour=20,
        approved_ceiling_usd=recommended,
        price_ceiling_ack=True,
        operator_ack=True,
        stage="approve_ceiling",
    )
    assert c.ceiling_approved is True
    assert c.pack_ready is True
    assert c.charge_executed is False
    assert c.unattended is None


def test_below_blocks():
    rec = compose_midnight_oil_price_ceiling_approval(
        operator_id="op-1",
        work_minutes=60,
        goals=GOALS,
        usd_per_hour=50,
        price_ceiling_ack=False,
        operator_ack=False,
        stage="recommend_only",
    )
    recommended = rec.recommend.recommended_ceiling_usd
    assert recommended is not None
    c = compose_midnight_oil_price_ceiling_approval(
        operator_id="op-1",
        work_minutes=60,
        goals=GOALS,
        usd_per_hour=50,
        approved_ceiling_usd=max(0.0, recommended - 10),
        price_ceiling_ack=True,
        operator_ack=True,
        stage="approve_ceiling",
    )
    assert c.ceiling_approved is False
    assert c.pack_ready is False


def test_unattended_pack():
    rec = compose_midnight_oil_price_ceiling_approval(
        operator_id="op-1",
        work_minutes=90,
        goals=GOALS,
        usd_per_hour=25,
        price_ceiling_ack=False,
        operator_ack=False,
        stage="recommend_only",
    )
    recommended = rec.recommend.recommended_ceiling_usd
    assert recommended is not None
    c = compose_midnight_oil_price_ceiling_approval(
        operator_id="op-1",
        work_minutes=90,
        goals=GOALS,
        usd_per_hour=25,
        approved_ceiling_usd=recommended + 5,
        price_ceiling_ack=True,
        operator_ack=True,
        unattended_ack=True,
        spend_consent=True,
        stage="unattended_pack",
    )
    assert c.ceiling_approved is True
    assert c.unattended is not None
    assert c.unattended.live_execution_authorized is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False


def test_null_rate():
    c = compose_midnight_oil_price_ceiling_approval(
        operator_id="op-1",
        work_minutes=60,
        goals=GOALS,
        usd_per_hour=None,
        price_ceiling_ack=False,
        operator_ack=False,
        stage="recommend_only",
    )
    assert c.recommend.recommended_ceiling_usd is None
    assert c.charge_executed is False


def test_override_below():
    rec = compose_midnight_oil_price_ceiling_approval(
        operator_id="op-1",
        work_minutes=60,
        goals=GOALS,
        usd_per_hour=40,
        price_ceiling_ack=False,
        operator_ack=False,
        stage="recommend_only",
    )
    recommended = rec.recommend.recommended_ceiling_usd
    assert recommended is not None
    c = compose_midnight_oil_price_ceiling_approval(
        operator_id="op-1",
        work_minutes=60,
        goals=GOALS,
        usd_per_hour=40,
        approved_ceiling_usd=recommended * 0.5,
        below_recommend_override=True,
        price_ceiling_ack=True,
        operator_ack=True,
        stage="approve_ceiling",
    )
    assert c.ceiling_approved is True
    assert c.pack_ready is True
