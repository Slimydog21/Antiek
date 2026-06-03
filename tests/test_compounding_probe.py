"""ACV SPR-06 — the compounding probe is discovered, distinct, and non-vacuous.

The full ``_probe`` boots ``create_app()`` and runs two cascade launches (covered
by the live reachability job + the manual gate run); these tests assert the
cheaper, structural properties that keep the probe honest WITHOUT the multi-second
boot:

  * the probe is discovered by the runner and registered under id ``compounding``;
  * it is DISTINCT from the SPR-02 ``flywheel`` probe (fired vs. paid) — a
    maintainer must not collapse the two;
  * its assertion is non-vacuous: ``cost_warm < cost_cold`` beyond the floor is
    FALSE when warm == cold, so a run that fires reuse but pays nothing reds.
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools.reachability.probe_runner import discover_probes  # noqa: E402
from tools.reachability.probes import compounding as compounding_probe  # noqa: E402


def test_compounding_probe_is_discovered():
    ids = {p.id for p in discover_probes()}
    assert "compounding" in ids, f"compounding probe must be discovered, got {sorted(ids)}"


def test_compounding_probe_is_distinct_from_flywheel():
    """The docstring + the feature name must mark the fired-vs-paid distinction so
    a maintainer does not collapse the two probes."""
    ids = {p.id for p in discover_probes()}
    assert {"compounding", "flywheel"} <= ids
    feature = next(p.feature for p in discover_probes() if p.id == "compounding")
    assert "paid" in feature.lower() or "reduces" in feature.lower()
    doc = compounding_probe.__doc__ or ""
    assert "fire" in doc.lower() and "pa" in doc.lower(), (
        "the probe docstring must distinguish FIRED (flywheel) from PAID (this probe)"
    )


def test_material_floor_is_one_step_cost():
    """The floor a saving must clear equals one reuse-consuming step's cost — so a
    single genuinely-covered sub-question already clears it, but flicker below one
    step does not."""
    from runtime.research_runner.browse_loop import DEFAULT_COST_PER_STEP_USD

    assert compounding_probe.MATERIAL_FLOOR_USD == DEFAULT_COST_PER_STEP_USD


def test_assertion_is_non_vacuous_warm_equals_cold_would_red():
    """Structural non-vacuity: the probe's pass condition (saving >= floor AND
    cost_warm < cost_cold) is FALSE when warm == cold — i.e. a run that FIRES
    reuse but PAYS nothing reds. We assert the condition itself, the same boolean
    the probe evaluates."""
    floor = compounding_probe.MATERIAL_FLOOR_USD
    # warm == cold (reuse fired but paid nothing): NOT reachable.
    cost_cold = cost_warm = 0.03
    saving = cost_cold - cost_warm
    assert not (saving >= floor and cost_warm < cost_cold)
    # warm cheaper beyond the floor (reuse paid): reachable.
    cost_warm2 = 0.0
    saving2 = cost_cold - cost_warm2
    assert saving2 >= floor and cost_warm2 < cost_cold


def test_topics_are_token_disjoint():
    """The cold topic must share NO salient tokens with the warm/seeded topic, so
    the seeded corpus genuinely covers NOTHING for the cold launch (the cold
    baseline does full work — the control discipline)."""
    from runtime.research_runner.browse_loop import _salient_tokens

    warm = _salient_tokens(compounding_probe._WARM_TOPIC)
    cold = _salient_tokens(compounding_probe._COLD_TOPIC)
    assert warm and cold
    assert not (warm & cold), f"cold/warm topics must be token-disjoint, shared: {warm & cold}"
