"""BYO-tools connectors — users connect their OWN data-vendor accounts + keys.

Spec: ``byo-tools-connectors.md`` (goal-2026-08-06-usable-v1). The v1 lane is
three chassis kinds (``ChassisKind``); this package ships the shared base +
the paste-a-key chassis (``base.py`` — keyless is the degenerate case, e.g.
SEC EDGAR) and the host-global per-vendor rate governor (``rate_governor.py``,
generalizing the arXiv governor's flock + state-sidecar mechanism).

Posture invariants every connector inherits:

  * SECRETS — keys live in ``runtime.byok.store`` (encrypted at rest), held
    here only as non-secret ``cred_id`` handles, decrypted lazily at call time
    behind a redacting ``SecretStr``. Never logged, never echoed.
  * HTTP — ``httpx`` only, no vendor SDKs (spec §5.0; the integration-tier CI
    gate stays green with zero new package rows).
  * RIGHTS — connector-ingested content lands ``personal_reading`` explicitly
    at the adapter layer (the ``youtube-transcript-at-user-owned`` invariant);
    this package fetches + parses only and does NO DuckDB writes (the
    single-writer invariant is untouched).
  * FAIL CLOSED — malformed keys rejected before storing; missing required
    identity (EDGAR's contact) refuses the send; a 429 ban sentinel pauses the
    connector rather than re-hitting the vendor.
"""

from runtime.connectors.base import (
    KEY_MAX_LEN,
    AuthModel,
    ChassisKind,
    Connector,
    ConnectorDescriptor,
    ConnectorError,
    KeyShape,
    KeyShapeError,
    PasteKeyConnector,
    RateSpec,
)
from runtime.connectors.quota_meter import (
    YOUTUBE_RESET_TZ,
    YOUTUBE_UNIT_COSTS,
    YOUTUBE_UNITS_PER_DAY,
    QuotaExhausted,
    QuotaMeter,
    QuotaSnapshot,
    default_quota_dir,
)
from runtime.connectors.rate_governor import (
    GovernorLockTimeout,
    VendorBanned,
    VendorRateGovernor,
    default_state_dir,
)

__all__ = [
    "KEY_MAX_LEN",
    "AuthModel",
    "ChassisKind",
    "Connector",
    "ConnectorDescriptor",
    "ConnectorError",
    "GovernorLockTimeout",
    "KeyShape",
    "KeyShapeError",
    "PasteKeyConnector",
    "QuotaExhausted",
    "QuotaMeter",
    "QuotaSnapshot",
    "RateSpec",
    "VendorBanned",
    "VendorRateGovernor",
    "YOUTUBE_RESET_TZ",
    "YOUTUBE_UNIT_COSTS",
    "YOUTUBE_UNITS_PER_DAY",
    "default_quota_dir",
    "default_state_dir",
]
