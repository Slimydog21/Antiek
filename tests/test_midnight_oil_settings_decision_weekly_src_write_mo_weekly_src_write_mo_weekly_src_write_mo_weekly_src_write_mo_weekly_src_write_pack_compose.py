"""Pure tests for Midnight Oil over settings decision competition DR pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    compose_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
    format_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_summary,
)
from tests.test_settings_decision_competition_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    COMPETITION_PACK,
    SETTINGS,
)

MO = {
    "operator_id": "op-1",
    "work_minutes": 120,
    "goals": [
        {"goal_id": "g1", "title": "Map scaling literature"},
        {"goal_id": "g2", "title": "Synthesize open problems"},
    ],
    "usd_per_hour": 30,
    "approved_ceiling_usd": 500,
    "price_ceiling_ack": True,
    "unattended_ack": True,
    "spend_consent": True,
    "stage": "unattended_pack",
}

SETTINGS_PACK = {
    "settings": SETTINGS,
    "competition_pack": COMPETITION_PACK,
}


def test_mo_settings_decision_competition_ready():
    c = compose_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        mo=MO,
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.mo.pack_ready is True
    assert c.settings_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert c.remote_fetched is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
    )
    assert "live_execution_authorized=false" in (
        format_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        mo=MO,
        settings_pack=SETTINGS_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_price_ceiling_ack_false_blocks_unattended():
    c = compose_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        mo={**MO, "price_ceiling_ack": False},
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.mo.pack_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_recommend_only_stage_ready():
    c = compose_midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        mo={
            "operator_id": "op-1",
            "work_minutes": 120,
            "goals": [
                {"goal_id": "g1", "title": "Map scaling literature"},
                {"goal_id": "g2", "title": "Synthesize open problems"},
            ],
            "usd_per_hour": 30,
            "price_ceiling_ack": False,
            "stage": "recommend_only",
        },
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.mo.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.production_router_verdict == "REJECT"
    assert c.settings_pack.pack_ready is True
    assert c.mo.pack_ready is True
    assert c.pack_ready is True
