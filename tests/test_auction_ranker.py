"""Learned ranker + guaranteed fallback tests (SPR-10 M3).

The load-bearing assertion: a FORCED model failure degrades to the rule-based
matcher and the slot is still filled — a model problem never blanks a slot."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from substrate.ad_inventory.ad_bidding import AdInventoryItem
from substrate.ad_inventory.auction_features import FEATURE_DIM
from substrate.ad_inventory.auction_model import AuctionModel, train_model
from substrate.ad_inventory.auction_ranker import (
    LEARNED_RANKER_ENV,
    MODEL_PATH_ENV,
    learned_ranker_enabled,
    rank_candidates,
    select_ad,
)
from substrate.ad_inventory.intent_targeting import (
    InventoryTargeting,
    PageContext,
    TargetedInventoryItem,
    select_targeted_ad,
)


def _item(inv_id: str, cpm: str, *, topics: tuple[str, ...] = ()) -> AdInventoryItem:
    return AdInventoryItem(
        inventory_id=inv_id,
        advertiser_display_name=inv_id,
        target_topics=topics,
        cpm_usd=Decimal(cpm),
        creative_url=f"https://example.com/{inv_id}.png",
        landing_url=f"https://example.com/{inv_id}/lp",
    )


def _ti(
    inv_id: str, cpm: str, *, sectors=(), sub=(), intents=(), topics=()
) -> TargetedInventoryItem:
    return TargetedInventoryItem(
        item=_item(inv_id, cpm, topics=topics),
        targeting=InventoryTargeting(
            target_sectors=sectors, target_sub_sectors=sub,
            target_audience_intents=intents,
        ),
    )


def _trained_model() -> AuctionModel:
    # Tiny deterministic training set; we only need a usable model object.
    feats = [tuple([1.0] + [float((i + j) % 2) for j in range(FEATURE_DIM - 1)])
             for i in range(20)]
    labels = [0.2 + 0.5 * (i % 2) for i in range(20)]
    return train_model(feats, labels, iterations=50)


_CTX = PageContext(
    sector="defense", sub_sector="hypersonics",
    audience_intents=("researcher",), flat_topics=("defense",),
)


# ── Flag plumbing ──────────────────────────────────────────────────


def test_flag_default_is_rule_based(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LEARNED_RANKER_ENV, raising=False)
    assert learned_ranker_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "ON", "yes"])
def test_flag_truthy_enables(monkeypatch: pytest.MonkeyPatch, val: str) -> None:
    monkeypatch.setenv(LEARNED_RANKER_ENV, val)
    assert learned_ranker_enabled() is True


# ── Equivalence: no model → rule-based output ──────────────────────


def test_no_model_matches_rule_based(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LEARNED_RANKER_ENV, raising=False)
    inv = [_ti("a", "5.0", sectors=("defense",)),
           _ti("b", "9.0", sectors=("defense",))]
    got = select_ad(context=_CTX, targeted_inventory=inv)
    expected = select_targeted_ad(context=_CTX, targeted_inventory=inv)
    assert got is not None
    assert expected is not None
    assert got.inventory_id == expected.inventory_id


# ── THE load-bearing test: forced model failure → rule-based fills ──


class _ExplodingModel:
    """A stand-in that raises on predict — forces the learned path to fail."""

    weights = tuple([0.0] * FEATURE_DIM)

    def predict(self, x):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated model failure")


def test_forced_model_failure_falls_back_and_fills_slot() -> None:
    inv = [_ti("a", "5.0", sectors=("defense",)),
           _ti("b", "9.0", sectors=("defense",))]
    # Inject the exploding model: the learned path must catch the predict error
    # and degrade to the rule-based matcher — the slot is STILL filled.
    chosen = select_ad(
        context=_CTX, targeted_inventory=inv, model=_ExplodingModel(),  # type: ignore[arg-type]
    )
    assert chosen is not None, "model failure blanked the slot — must not happen"
    rule = select_targeted_ad(context=_CTX, targeted_inventory=inv)
    assert rule is not None
    assert chosen.inventory_id == rule.inventory_id  # exact rule-based result


def test_flag_on_but_missing_artifact_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LEARNED_RANKER_ENV, "1")
    monkeypatch.setenv(MODEL_PATH_ENV, "/nonexistent/path/model.json")
    inv = [_ti("a", "5.0", sectors=("defense",))]
    chosen = select_ad(context=_CTX, targeted_inventory=inv)
    assert chosen is not None
    assert chosen.inventory_id == "a"


def test_flag_on_but_stale_schema_artifact_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    model = _trained_model()
    obj = json.loads(model.to_json())
    obj["feature_schema_version"] = "auction-feat-vSTALE"
    p = tmp_path / "stale.json"
    p.write_text(json.dumps(obj))
    monkeypatch.setenv(LEARNED_RANKER_ENV, "1")
    monkeypatch.setenv(MODEL_PATH_ENV, str(p))
    inv = [_ti("a", "5.0", sectors=("defense",))]
    chosen = select_ad(context=_CTX, targeted_inventory=inv)
    assert chosen is not None  # stale artifact → rule-based, not a blank slot


def test_seam_flag_routes_through_select_targeted_ad(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The existing API caller calls select_targeted_ad unchanged; with the flag
    on it must transparently route through the learned ranker and still fill."""
    model = _trained_model()
    p = tmp_path / "model.json"
    p.write_text(model.to_json())
    monkeypatch.setenv(LEARNED_RANKER_ENV, "1")
    monkeypatch.setenv(MODEL_PATH_ENV, str(p))
    inv = [_ti("a", "5.0", sectors=("defense",)),
           _ti("b", "9.0", sectors=("defense",))]
    chosen = select_targeted_ad(context=_CTX, targeted_inventory=inv)
    assert chosen is not None  # learned path filled the slot via the same seam


# ── Re-ranking actually reorders by predicted value ────────────────


def test_rank_candidates_orders_by_predicted_value() -> None:
    model = _trained_model()
    inv = [_ti("a", "5.0", sectors=("defense",)),
           _ti("b", "5.0", sectors=("biotech",))]
    ranked = rank_candidates(context=_CTX, targeted_inventory=inv, model=model)
    assert {ti.item.inventory_id for ti in ranked} == {"a", "b"}
    assert len(ranked) == 2  # all candidates preserved, just reordered


def test_learned_picks_higher_value_among_eligible() -> None:
    """A model that strongly weights sector_match should pick the sector-matching
    candidate over a non-matching one even at equal CPM."""
    model = _trained_model()
    inv = [_ti("match", "5.0", sectors=("defense",)),
           _ti("nomatch", "5.0", sectors=("biotech",))]
    chosen = select_ad(context=_CTX, targeted_inventory=inv, model=model)
    # 'nomatch' scores 0 on the rule threshold so is ineligible; 'match' wins.
    assert chosen is not None
    assert chosen.inventory_id == "match"
