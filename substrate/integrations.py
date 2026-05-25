"""
Antiek's canonical Tier-3 vendor allowlist.

This module exists so production code can ask "is X an adopted
integration?" in one place. The single source of truth for tier
state is ``integrations.toml`` at the repo root; this module
re-exports the Tier-3 subset as a Python frozenset so a grep for
``PROD_VENDORS`` lands on the canonical adopted-vendor set.

The CI gate at ``scripts/check_integration_tiers.py`` cross-checks
this allowlist against the registry on every push — drift between
the two would silently let a Tier-3-in-TOML vendor be missing from
PROD_VENDORS or vice versa.

Why a Python module rather than a generator output:

- The frozenset is read at substrate startup by future call sites
  (e.g., "log a warning if a dispatch decision picks a non-PROD_VENDORS
  provider"). Reading TOML at import time would pull tomllib + filesystem
  into the substrate hot path needlessly.
- A static frozenset is grep-friendly: a maintainer searching for
  ``"hermes"`` finds this file as the authoritative answer.

Update protocol: when you change a tier in ``integrations.toml``, run
``python scripts/check_integration_tiers.py`` — if it surfaces a
"Tier 3 integrations missing from PROD_VENDORS" finding, mirror the
change here.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e3-vouching.html
"""

from __future__ import annotations

# Tier 3 integrations as of 2026-05-24. Names match the table headers
# in integrations.toml exactly. CI asserts this set matches the
# registry on every push (see tests/test_integration_tiers.py
# ::test_tier_3_packages_are_in_prod_vendors_allowlist).
PROD_VENDORS: frozenset[str] = frozenset(
    {
        # ---- foundational substrate deps ----
        "duckdb",
        "pydantic",
        "pydantic_settings",
        "fastapi",
        "uvicorn",
        "httpx",
        "tenacity",
        "structlog",
        "pyyaml",
        "python_dateutil",
        "orjson",
        # ---- named vendor integrations, in production ----
        "hermes",        # LLM bridge (commit cd602c9)
        "agentmail",     # magic-link email (per CLAUDE.md)
        "exa",           # discovery layer (acquisition/search/exa/)
    }
)


def is_prod_vendor(name: str) -> bool:
    """Return True iff ``name`` is an adopted Tier-3 integration.

    Names are matched against ``integrations.toml``'s table headers
    (e.g., ``"hermes"``, ``"agentmail"``), not against the underlying
    PyPI package names. Use ``is_prod_vendor("hermes")`` not
    ``is_prod_vendor("hermes-client-sdk")``.
    """
    return name in PROD_VENDORS
