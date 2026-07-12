"""Pure tests for MO unattended over draft-before-merge multiselect ND twin."""

from __future__ import annotations

from substrate.mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose import (
    compose_mo_unattended_draft_before_merge_floating_multiselect_nd_twin,
    format_mo_unattended_draft_before_merge_floating_multiselect_nd_twin_summary,
)
from tests.test_draft_before_merge_floating_multiselect_model_decision_nd_twin_compose import (
    DRAFT_GATE,
    MULTI_PACK,
)
from tests.test_floating_multiselect_model_decision_nd_twin_compose import DECISION

MO = {
    "operator_id": "op-1",
    "work_minutes": 120,
    "goals": [
        {"goal_id": "g1", "title": "Map arxiv competition gaps"},
        {"goal_id": "g2", "title": "Synthesize twin notes"},
    ],
    "usd_per_hour": 15,
    "approved_ceiling_usd": 50,
    "unattended_ack": True,
    "spend_consent": True,
    "brief_dispatch_ready": True,
}

DRAFT_PACK = {
    "draft_gate": DRAFT_GATE,
    "multi_pack": MULTI_PACK,
}


def test_mo_unattended_draft_multiselect_nd_twin_ready():
    c = compose_mo_unattended_draft_before_merge_floating_multiselect_nd_twin(
        mo=MO,
        draft_pack=DRAFT_PACK,
        operator_ack=True,
    )
    assert c.mo.unattended_package_ready is True
    assert c.draft_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_execution_authorized is False
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose_advisory"
    )
    assert "live_execution_authorized=false" in (
        format_mo_unattended_draft_before_merge_floating_multiselect_nd_twin_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_mo_unattended_draft_before_merge_floating_multiselect_nd_twin(
        mo=MO,
        draft_pack=DRAFT_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_spend_consent_false_blocks_mo():
    c = compose_mo_unattended_draft_before_merge_floating_multiselect_nd_twin(
        mo={**MO, "spend_consent": False},
        draft_pack=DRAFT_PACK,
        operator_ack=True,
    )
    assert c.mo.unattended_package_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_mo_unattended_draft_before_merge_floating_multiselect_nd_twin(
        mo=MO,
        draft_pack={
            **DRAFT_PACK,
            "multi_pack": {
                **MULTI_PACK,
                "decision_pack": {
                    **MULTI_PACK["decision_pack"],
                    "decision": {
                        **DECISION,
                        "projected_cost_usd_high": 100,
                        "daily_cap_usd": 50,
                        "spent_usd": 10,
                    },
                },
            },
        },
        operator_ack=True,
    )
    assert c.draft_pack.multi_pack.decision_pack.decision.would_exceed is True
    assert c.draft_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"
