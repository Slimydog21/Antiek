"""Learned ranker at the matcher seam, with guaranteed rule-based fallback (SPR-10 M3).

Wires the M2 scorer behind the EXISTING selection interface
(``intent_targeting.select_targeted_ad``) so callers — chiefly
``interfaces/research/api/ad_impressions.py`` — are UNCHANGED. The learned
ranker re-orders the candidate inventory by predicted value, then hands the
re-ordered list to the same rule-based selection that already exists; the
rule-based matcher remains the guaranteed fallback.

THE FLAG (flips learned↔rule with NO code change):
  ANTIEK_LEARNED_AD_RANKER     "1"/"true"/"on" → learned path; anything else
                               (or unset) → rule-based (the safe default).
  ANTIEK_AD_RANKER_MODEL_PATH  filesystem path to the M2 JSON artifact. The
                               learned path loads it at selection time
                               (cheap: a few floats) — there is no server, no
                               warm process, no GPU.

SAFE DEGRADATION (rigor #1 — a model problem never blanks a slot):
On ANY failure of the learned path — flag off, missing/unreadable artifact,
feature-extraction error, predict error, a stale feature schema — the ranker
falls back to ``select_targeted_ad_rule_based`` (the flag-independent rule-based
core, so the fallback never re-enters the flag check and recurses). The slot is
filled by the same logic that fills it today; the model is a re-ranking
PREFERENCE, never a gate. ``select_ad`` therefore returns exactly what the
rule-based matcher would return whenever the learned path cannot run.

WHAT THE LEARNED PATH ACTUALLY CHANGES:
It does NOT bypass ``MIN_MATCH_SCORE`` or the flat-topic fallback — it only
reorders the targeted candidates by predicted value before the existing
selection runs, and (when ≥1 candidate clears the rule threshold) picks the
clearing candidate with the highest predicted value × CPM. The rule-based
selection's invariants (threshold, flat-fallback, determinism) are preserved.
"""

from __future__ import annotations

import os
from typing import Optional

from .ad_bidding import AdInventoryItem
from .auction_features import AuctionCandidate, extract_features
from .auction_model import AuctionModel
from .intent_targeting import (
    MIN_MATCH_SCORE,
    PageContext,
    TargetedInventoryItem,
    score_inventory_match,
    select_targeted_ad_rule_based,
)

LEARNED_RANKER_ENV = "ANTIEK_LEARNED_AD_RANKER"
MODEL_PATH_ENV = "ANTIEK_AD_RANKER_MODEL_PATH"

_TRUTHY = frozenset({"1", "true", "on", "yes"})


def learned_ranker_enabled() -> bool:
    """True iff the flag is set truthy. Default (unset) is rule-based — the
    learned path is opt-in, so a fresh deploy is the safe rule-based matcher."""
    return os.environ.get(LEARNED_RANKER_ENV, "").strip().lower() in _TRUTHY


def _load_model_from_env() -> Optional[AuctionModel]:
    """Load the artifact named by ``ANTIEK_AD_RANKER_MODEL_PATH``. Returns None
    (NOT raises) on any problem — a missing/unreadable/stale artifact must
    degrade to rule-based, not error. In-process file read only; no network."""
    path = os.environ.get(MODEL_PATH_ENV, "").strip()
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return AuctionModel.from_json(fh.read())
    except Exception:
        # Missing file, bad JSON, stale feature schema — all degrade silently to
        # rule-based. The slot is never blanked by a model artifact problem.
        return None


def rank_candidates(
    *,
    context: PageContext,
    targeted_inventory: list[TargetedInventoryItem],
    model: AuctionModel,
) -> list[TargetedInventoryItem]:
    """Re-order the targeted inventory by the model's predicted value.

    PURE w.r.t. the model (no I/O): for each candidate, extract M1 features and
    score them. Sort descending by predicted value, tie-break by CPM then
    inventory_id (matching the rule-based determinism). Any per-candidate
    feature/predict error places that candidate at the BACK rather than
    aborting the whole ranking — one bad candidate cannot blank the slot."""
    scored: list[tuple[float, float, str, TargetedInventoryItem]] = []
    for ti in targeted_inventory:
        try:
            cand = AuctionCandidate(item=ti.item, targeting=ti.targeting)
            value = model.predict(extract_features(context, cand))
        except Exception:
            value = -1.0  # demote a candidate that errors; never abort
        scored.append((value, float(ti.item.cpm_usd), ti.item.inventory_id, ti))
    scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
    return [t[3] for t in scored]


def _learned_select(
    *,
    context: PageContext,
    ranked: list[TargetedInventoryItem],
    model: AuctionModel,
    flat_inventory_fallback: Optional[list[AdInventoryItem]],
) -> Optional[AdInventoryItem]:
    """Pick from the rule-eligible candidates by predicted value × CPM.

    Preserves the rule-based invariants: only candidates clearing
    ``MIN_MATCH_SCORE`` (and with non-empty targeting) are eligible; if none
    clear, delegate to the rule-based core so the flat-topic fallback still
    runs. Among clearing candidates the learned path orders by
    predicted_value × CPM (the Axon "expected value of the impression" objective),
    tie-broken by CPM then inventory_id for determinism."""
    eligible: list[tuple[float, float, str, AdInventoryItem]] = []
    for ti in ranked:
        if ti.targeting.is_empty:
            continue
        if score_inventory_match(context, ti.targeting) < MIN_MATCH_SCORE:
            continue
        cand = AuctionCandidate(item=ti.item, targeting=ti.targeting)
        value = model.predict(extract_features(context, cand))
        ev = value * float(ti.item.cpm_usd)
        eligible.append((ev, float(ti.item.cpm_usd), ti.item.inventory_id, ti.item))

    if eligible:
        eligible.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
        return eligible[0][3]

    # No targeted candidate cleared the threshold — defer to the rule-based
    # matcher so the flat-topic fallback (un-retagged advertisers) still serves.
    return select_targeted_ad_rule_based(
        context=context,
        targeted_inventory=ranked,
        flat_inventory_fallback=flat_inventory_fallback,
    )


def select_ad(
    *,
    context: PageContext,
    targeted_inventory: list[TargetedInventoryItem],
    flat_inventory_fallback: Optional[list[AdInventoryItem]] = None,
    model: Optional[AuctionModel] = None,
) -> Optional[AdInventoryItem]:
    """The seam-compatible selection entrypoint.

    Identical signature/return to ``select_targeted_ad`` plus an optional
    ``model`` (injected for tests; production loads it from the env). Routes
    learned vs rule by the flag and degrades to rule-based on ANY learned-path
    failure — the slot is filled by the same logic that fills it today whenever
    the model cannot run.

    Pass ``model`` to force the learned path in a test without the env flag; in
    production the flag + ``ANTIEK_AD_RANKER_MODEL_PATH`` drive it."""
    use_learned = model is not None or learned_ranker_enabled()
    if not use_learned:
        return select_targeted_ad_rule_based(
            context=context,
            targeted_inventory=targeted_inventory,
            flat_inventory_fallback=flat_inventory_fallback,
        )

    eff_model = model if model is not None else _load_model_from_env()
    if eff_model is None:
        # Flag on but no usable artifact → degrade to rule-based (do not blank).
        return select_targeted_ad_rule_based(
            context=context,
            targeted_inventory=targeted_inventory,
            flat_inventory_fallback=flat_inventory_fallback,
        )

    try:
        ranked = rank_candidates(
            context=context,
            targeted_inventory=targeted_inventory,
            model=eff_model,
        )
        return _learned_select(
            context=context,
            ranked=ranked,
            model=eff_model,
            flat_inventory_fallback=flat_inventory_fallback,
        )
    except Exception:
        # ANY learned-path exception → guaranteed rule-based fallback. A model
        # problem must never blank a slot (rigor #1).
        return select_targeted_ad_rule_based(
            context=context,
            targeted_inventory=targeted_inventory,
            flat_inventory_fallback=flat_inventory_fallback,
        )


__all__ = [
    "LEARNED_RANKER_ENV",
    "MODEL_PATH_ENV",
    "learned_ranker_enabled",
    "rank_candidates",
    "select_ad",
]
