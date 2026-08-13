"""Own Your Mind P0 — objective-card endpoint (C1a, read-only).

``GET /ops/objective-card`` renders the live decision surfaces the platform
optimizes today, read straight from the code and config that own them — no
inference dressed as fact, no hand-maintained duplicate of a constant:

- **dispatch** — parsed from ``substrate/dispatch/config.yaml`` (the routing
  config is the source of truth; the parser returns its ACTUAL structure:
  version, role_tiers, tiers with pricing + nested fallback chains,
  tier_defaults, cost_tracking). Pricing values are operator-owned
  placeholders (0.0 = cost tracking disabled for that tier) and the payload
  reports ``pricing_placeholder`` so the reader never mistakes 0.0 for
  "free".
- **gap_scoring** — the continuous daemon's objective constants
  (``orchestration/continuous/scoring.py``) + the spawn parameters
  (``orchestration/continuous/daemon.py`` DaemonConfig defaults).
- **retrieval_gates** — the deny-by-default retrieval gate
  (``substrate/graph/retrieval_gate.py``): privileged policy tags + the
  withheld content classes.
- **quality_gate** — the §13.9 checks' thresholds
  (``substrate/quality_gate/checks.py``): voice-style threshold, source-tier
  bounds, verification rule, extraction-quality floor.
- **budgets** — the research-runner aggregate cap
  (``substrate.constants.TOTAL_ACQUISITION_BUDGET_USD``) + the continuous
  daemon's dollar caps (``orchestration/continuous/budget.py``).
- **reuse_gate** — the flywheel groundedness bar
  (``substrate/flywheel/reuse_gate.py``), env-overridable.

Values are read mechanically at request time (module constants, function
signature defaults, YAML) so the card cannot drift from the code it
renders. GET-only; zero mutation endpoints.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, FastAPI

ops_router = APIRouter(prefix="/ops", tags=["ops"])

_DISPATCH_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "substrate" / "dispatch" / "config.yaml"
)


def _load_dispatch_config() -> dict[str, Any] | None:
    """Parse ``substrate/dispatch/config.yaml``, respecting its actual
    structure. Returns None only when the file is missing (never raises —
    a broken card is a 500-free honest surface)."""
    if not _DISPATCH_CONFIG_PATH.exists():
        return None
    with open(_DISPATCH_CONFIG_PATH, encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
        return loaded if isinstance(loaded, dict) else None


def _pricing_is_placeholder(tiers: dict[str, Any] | None) -> bool:
    """True when every tier's pricing block is all-zeros (the config's own
    convention: ``0.0`` = "set 0.0 until pricing is verified")."""
    if not tiers:
        return True
    for tier in tiers.values():
        pricing = tier.get("pricing", {}) if isinstance(tier, dict) else {}
        for key in ("input_per_mtok", "output_per_mtok", "cached_input_per_mtok"):
            if pricing.get(key, 0.0) != 0.0:
                return False
    return True


def _dispatch_section() -> dict[str, Any]:
    config = _load_dispatch_config() or {}
    tiers = config.get("tiers", {})
    return {
        "source": "substrate/dispatch/config.yaml",
        "version": config.get("version"),
        "role_tiers": config.get("role_tiers", {}),
        "tiers": tiers,
        "tier_defaults": config.get("tier_defaults", {}),
        "cost_tracking": config.get("cost_tracking", {}),
        # 0.0 in config.yaml means "unverified placeholder", not free.
        "pricing_placeholder": _pricing_is_placeholder(tiers),
        "pricing_note": (
            "All tier pricing values are 0.0 placeholders — the operator "
            "owns these values and has not verified per-provider pricing "
            "yet (config.yaml header)."
        ),
    }


def _gap_scoring_section() -> dict[str, Any]:
    from orchestration.continuous import scoring
    from orchestration.continuous.daemon import DaemonConfig

    spawn = DaemonConfig()
    return {
        "constants": {
            "MAX_CHASE_COUNT": scoring.MAX_CHASE_COUNT,
            "RECENCY_HALF_LIFE_DAYS": scoring.RECENCY_HALF_LIFE_DAYS,
            "CO_OCCURRENCE_CAP": scoring.CO_OCCURRENCE_CAP,
            "INTERACTION_BOOST": scoring.INTERACTION_BOOST,
        },
        "objective": (
            "score_gap = recency * co_occurrence * interaction_boost; "
            "decays to 0.0 once a gap has been chased MAX_CHASE_COUNT times "
            "(orchestration/continuous/scoring.py)"
        ),
        "daemon_spawn_params": {
            "expected_cost_per_spawn_usd": spawn.expected_cost_per_spawn_usd,
            "max_spawns_per_iteration": spawn.max_spawns_per_iteration,
            "min_score_to_spawn": spawn.min_score_to_spawn,
            "spawn_policy_id": spawn.spawn_policy_id,
            "sleep_seconds": spawn.sleep_seconds,
        },
    }


def _retrieval_gates_section() -> dict[str, Any]:
    from substrate.graph import retrieval_gate

    return {
        "policy": "deny_by_default",
        "privileged_policy_tags": sorted(retrieval_gate.PRIVILEGED_POLICY_TAGS),
        "restricted_content_classes": sorted(
            retrieval_gate.RESTRICTED_CONTENT_CLASSES
        ),
        "personal_only_content_classes": sorted(
            retrieval_gate.PERSONAL_ONLY_CONTENT_CLASSES
        ),
        "non_privileged_excluded_content_classes": sorted(
            retrieval_gate.RESTRICTED_CONTENT_CLASSES
            | retrieval_gate.PERSONAL_ONLY_CONTENT_CLASSES
        ),
        "note": (
            "Non-privileged retrieval excludes restricted + owner-only "
            "classes (NULL content_class is grandfathered); privileged "
            "policy tags bypass rights withholding but still require exact "
            "ownership (substrate/graph/retrieval_gate.py)."
        ),
    }


def _quality_gate_section() -> dict[str, Any]:
    from substrate.quality_gate import checks

    voice_threshold = inspect.signature(checks.check_voice_style).parameters[
        "threshold"
    ].default
    bounds = checks.SourceTierBounds()
    return {
        "checks": {
            "verification": {
                "rule": "every declared claim must cite >= 1 evidence chunk; "
                        "a note with zero claims is rejected",
            },
            "voice_style": {"threshold": voice_threshold},
            "source_tier": {
                "min_acceptable": bounds.min_acceptable,
                "max_acceptable": bounds.max_acceptable,
                "note": "tier 4-5 sources reroute to private",
            },
            "extraction_quality": {
                "min_distinct_chars": checks._MIN_DISTINCT_CHARS,
                "note": "single-repeated-glyph / near-empty text is not prose",
            },
        },
        "source": "substrate/quality_gate/checks.py",
    }


def _budgets_section() -> dict[str, Any]:
    from orchestration.continuous import budget as continuous_budget
    from substrate.constants import TOTAL_ACQUISITION_BUDGET_USD

    return {
        "research_runner": {
            "aggregate_cap_usd": TOTAL_ACQUISITION_BUDGET_USD,
            "scope": "sum across all researches in one fan-out; per-research "
                     "caps are set at launch (runtime/research_runner/budget.py)",
        },
        "continuous_daemon": {
            "per_investigation_cap_usd": continuous_budget.PER_INVESTIGATION_CAP_USD,
            "default_daily_cap_usd": continuous_budget.DEFAULT_DAILY_CAP_USD,
            "daily_cap_env_override": "ANTIEK_DAEMON_HOURLY_BUDGET_USD",
            "max_topic_depth": continuous_budget.MAX_TOPIC_DEPTH,
            "scope": "orchestration/continuous/budget.py",
        },
    }


def _reuse_gate_section() -> dict[str, Any]:
    from substrate.flywheel.reuse_gate import REUSE_GROUNDEDNESS_THRESHOLD

    return {
        "groundedness_threshold": REUSE_GROUNDEDNESS_THRESHOLD,
        "env_override": "REUSE_GROUNDEDNESS_THRESHOLD",
        "rule": (
            "a knowledge unit is reusable iff groundedness >= threshold AND "
            "it serves full text; every excluded unit emits one reuse.gated "
            "event (substrate/flywheel/reuse_gate.py)"
        ),
    }


def objective_card() -> dict[str, Any]:
    """Assemble the live objective card. Pure function, no I/O beyond the
    config read — testable without HTTP."""
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "dispatch": _dispatch_section(),
        "gap_scoring": _gap_scoring_section(),
        "retrieval_gates": _retrieval_gates_section(),
        "quality_gate": _quality_gate_section(),
        "budgets": _budgets_section(),
        "reuse_gate": _reuse_gate_section(),
    }


@ops_router.get("/objective-card")
async def get_objective_card() -> dict[str, Any]:
    """Render the live decision surfaces (Own Your Mind P0 C1a)."""
    return objective_card()


def register_ops_objective_routes(app: FastAPI) -> None:
    """Mount ``GET /ops/objective-card``. One call from ``create_app``."""
    app.include_router(ops_router)


__all__ = ["register_ops_objective_routes", "objective_card"]
