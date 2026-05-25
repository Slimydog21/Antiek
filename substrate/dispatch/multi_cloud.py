"""MULTI_CLOUD per-vendor-class secondary registry.

DDIA-execution SPR-10. Anchors philosophy P3 (multi-region / multi-cloud
is opt-in, NOT architectural baseline) and P2 (dispatch is vendor-
pluggable).

OFF BY DEFAULT. The flag and the registry exist so the operator can
flip per vendor-class without a code sprint. Today the routing of
primary → secondary is handled by the existing fallback-chain in
``router.py``'s ``TierConfig.fallback`` (the cd602c9 chaos-test
contract); MULTI_CLOUD adds a parallel axis — secondary CHOICE per
vendor CLASS — that lives one layer above the per-tier chain.

The classes are coarse:

    LLM            — any inference provider (Anthropic, xAI, OpenAI-
                     compat, OpenRouter, Hermes)
    BROWSER        — headless browser vendors (Browserbase, Anchor)
    COMPUTE        — serverless compute (Modal, Daytona)
    VECTOR_INDEX   — vector storage (turbopuffer, pgvector, in-process)
    OBJECT_STORE   — S3-like blob storage

For each class the operator picks ONE primary and ONE named secondary
(or "None — single-vendor" with justification). The MULTI_CLOUD flag
gates whether the secondary is actually consulted at failover time.

Why not put this in config.yaml: config.yaml is per-TIER (flash, pro,
synthesis, verify). MULTI_CLOUD is per-CLASS. The two are
complementary — within a tier, the fallback chain is per-tier; across
tiers OF THE SAME CLASS, the secondary is per-class. SPR-10's contract
is that the per-class fallback applies only when the per-tier chain is
exhausted.
"""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class VendorClass(str, enum.Enum):
    """The coarse classes the multi-cloud opt-in operates on."""

    LLM = "llm"
    BROWSER = "browser"
    COMPUTE = "compute"
    VECTOR_INDEX = "vector_index"
    OBJECT_STORE = "object_store"


@dataclass(frozen=True)
class VendorClassConfig:
    primary: str
    """The default provider for this class (e.g. ``hermes`` for LLM)."""

    secondary: Optional[str]
    """The named multi-cloud-opt-in fallback (e.g. ``openrouter`` for
    LLM). None means "no secondary; single-vendor by design."
    """

    reason: str
    """Why this primary/secondary pair. Cited in the operator-
    facing diagnostics when the secondary is consulted.
    """


# Default registry. Operator overrides via the same env-var / TOML
# mechanism as idle_policy.
#
# Pinned to Antiek 2026-05-24 state per memory entries:
# - LLM: hermes primary (project_antiek_hermes_bridge.md); openrouter
#   secondary (already in config.yaml as the per-tier fallback)
# - BROWSER: browserbase primary; anchor secondary (per
#   project_antiek_anchorbrowser_verdicts.md — AnchorBrowser as named
#   Plan B for Wedge 2)
# - COMPUTE: §16 REJECT-lists Modal+Daytona, so primary is the local
#   substrate. No secondary needed.
# - VECTOR_INDEX: turbopuffer is spike-only; the production primary is
#   the DuckDB-native cosine over pgvector. Secondary = turbopuffer
#   when it graduates.
# - OBJECT_STORE: master-spec uses host filesystem. No cloud secondary
#   today.
DEFAULT_REGISTRY: dict[VendorClass, VendorClassConfig] = {
    VendorClass.LLM: VendorClassConfig(
        primary="hermes",
        secondary="openrouter",
        reason=(
            "Hermes-bridge primary per Sprint-17 measurement window "
            "(master-spec §14.4). OpenRouter secondary catches the "
            "OAuth-refresh→503 case + bridge outages (I-DISPATCH-4)."
        ),
    ),
    VendorClass.BROWSER: VendorClassConfig(
        primary="browserbase",
        secondary="anchor_browser",
        reason=(
            "Browserbase as the Exa+Browserbase integration spec's "
            "primary for headless escalation. AnchorBrowser as named "
            "Plan B (project_antiek_anchorbrowser_verdicts.md)."
        ),
    ),
    VendorClass.COMPUTE: VendorClassConfig(
        primary="local_substrate",
        secondary=None,
        reason=(
            "§16 REJECT list bans Modal+Daytona as dispatch providers. "
            "Compute happens on the substrate; no secondary needed."
        ),
    ),
    VendorClass.VECTOR_INDEX: VendorClassConfig(
        primary="duckdb_native",
        secondary=None,
        reason=(
            "Cosine similarity over chunks.embedding via DuckDB. "
            "Turbopuffer is spike-only (scripts/turbopuffer_spike.py); "
            "the secondary slot stays empty until turbopuffer "
            "graduates."
        ),
    ),
    VendorClass.OBJECT_STORE: VendorClassConfig(
        primary="local_filesystem",
        secondary=None,
        reason=(
            "Master-spec uses host filesystem. P1 (local-first) — "
            "no cloud object-store dependency in the substrate today."
        ),
    ),
}


_OVERRIDE_ENV_PREFIX = "ANTIEK_MULTI_CLOUD_"
_OVERRIDE_FILE_NAME = "multi_cloud.toml"


def _override_file_path() -> Optional[Path]:
    home = os.environ.get("ANTIEK_HOME")
    if home:
        candidate = Path(home) / _OVERRIDE_FILE_NAME
    else:
        candidate = Path.home() / ".antiek" / _OVERRIDE_FILE_NAME
    return candidate if candidate.exists() else None


def _parse_toml(path: Path) -> dict[str, dict[str, str]]:
    """Tiny TOML parser for ``[<class>]`` tables with ``primary``,
    ``secondary``, ``reason`` keys. Same approach as idle_policy.
    """
    out: dict[str, dict[str, str]] = {}
    current: Optional[str] = None
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            out.setdefault(current, {})
            continue
        if current is None or "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[current][key.strip()] = val.strip().strip("'\"")
    return out


def is_enabled(vendor_class: VendorClass) -> bool:
    """Is MULTI_CLOUD opt-in active for this vendor class?

    Off by default. The operator opts in per class via:
        ANTIEK_MULTI_CLOUD_<CLASS>=1     (env-var precedence)
        $ANTIEK_HOME/multi_cloud.toml    ([<class>] enabled = true)
    """
    env_key = f"{_OVERRIDE_ENV_PREFIX}{vendor_class.value.upper()}"
    env_val = os.environ.get(env_key, "").strip().lower()
    if env_val in ("1", "true", "yes", "on"):
        return True
    if env_val in ("0", "false", "no", "off", ""):
        # explicit-off or unset; fall through to file check
        if env_val:
            return False
    file_path = _override_file_path()
    if file_path:
        parsed = _parse_toml(file_path)
        cfg = parsed.get(vendor_class.value, {})
        file_val = cfg.get("enabled", "").strip().lower()
        if file_val in ("1", "true", "yes", "on"):
            return True
    return False


def resolve(
    vendor_class: VendorClass,
) -> VendorClassConfig:
    """Return the (primary, secondary, reason) for the class, honoring
    operator overrides if present.
    """
    default = DEFAULT_REGISTRY.get(vendor_class)
    if default is None:
        raise KeyError(f"Unknown VendorClass: {vendor_class}")

    file_path = _override_file_path()
    if not file_path:
        return default

    parsed = _parse_toml(file_path)
    cfg = parsed.get(vendor_class.value, {})
    if not cfg:
        return default

    return VendorClassConfig(
        primary=cfg.get("primary", default.primary),
        secondary=(
            None if cfg.get("secondary", "").strip().lower() in ("", "none")
            else cfg.get("secondary", default.secondary or "")
        ),
        reason=cfg.get(
            "reason",
            f"operator override at {file_path}; default reason was: "
            f"{default.reason}",
        ),
    )


def should_failover_to_secondary(
    vendor_class: VendorClass,
    primary_failed: bool,
) -> tuple[bool, Optional[str]]:
    """Decision shim that callers in ``router.py`` invoke after the
    per-tier fallback chain exhausts.

    Returns ``(should_failover, secondary_name)``. ``should_failover``
    is True only if the per-class flag is ON, the primary actually
    failed, and a named secondary exists.

    The router currently does NOT invoke this — SPR-10 lands the flag
    + registry; wiring is a separate operator-authorized step. The
    shim's signature exists so the wiring is mechanical when the
    operator flips MULTI_CLOUD for any class.
    """
    if not primary_failed:
        return (False, None)
    if not is_enabled(vendor_class):
        return (False, None)
    cfg = resolve(vendor_class)
    if cfg.secondary is None:
        return (False, None)
    return (True, cfg.secondary)
