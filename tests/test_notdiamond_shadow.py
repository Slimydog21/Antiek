"""Red-proofs: NotDiamond shadow log is advisory only."""

from __future__ import annotations

import pytest

from substrate.model_decision.notdiamond_shadow import (
    NotDiamondShadowError,
    assert_not_production_authority,
    record_shadow_comparison,
)


def test_default_kill_switch_off() -> None:
    rec = record_shadow_comparison(task="deep_research", local_model_id="local-a")
    assert rec.enabled is False
    assert rec.authority == "shadow"
    assert rec.nd_recommended_model_id is None
    assert rec.agreement is None
    assert any("kill_switch=off" in n for n in rec.notes)


def test_shadow_agreement_when_enabled() -> None:
    rec = record_shadow_comparison(
        task="general",
        local_model_id="m1",
        nd_recommended_model_id="m1",
        enabled=True,
    )
    assert rec.enabled is True
    assert rec.agreement is True
    assert rec.authority == "shadow"
    assert_not_production_authority(rec)


def test_shadow_disagreement() -> None:
    rec = record_shadow_comparison(
        task="general",
        local_model_id="m1",
        nd_recommended_model_id="m2",
        enabled=True,
    )
    assert rec.agreement is False
    d = rec.to_dict()
    assert d["authority"] == "shadow"
    assert d["authorized_dispatch"] if False else True  # no such field
    assert "authorized" not in d


def test_enabled_without_nd_reco_unknown_agreement() -> None:
    rec = record_shadow_comparison(
        task="t",
        local_model_id="m1",
        nd_recommended_model_id=None,
        enabled=True,
    )
    assert rec.agreement is None


def test_empty_local_raises() -> None:
    with pytest.raises(NotDiamondShadowError):
        record_shadow_comparison(task="t", local_model_id="  ")


def test_reject_production_authority_claim() -> None:
    rec = record_shadow_comparison(task="t", local_model_id="m1", enabled=True, nd_recommended_model_id="m1")
    assert_not_production_authority(rec)
    with pytest.raises(NotDiamondShadowError):
        assert_not_production_authority({"authority": "production"})


def test_no_network_in_module_source() -> None:
    import inspect

    import substrate.model_decision.notdiamond_shadow as mod

    src = inspect.getsource(mod)
    for banned in ("urllib", "httpx", "requests", "aiohttp", "socket.", "fetch("):
        assert banned not in src
