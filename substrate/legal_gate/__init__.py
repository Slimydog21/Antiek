"""Retrieval-time legal gate.

Per `docs/master-product-spec.md` §9 the legal gate enforces the
Bartz / Hachette / AG MDL banned-corpus restrictions. Two
implementations ship here:

  - ``RegistryBackedLegalGate`` (default) — consults the
    operator-edited `registry.py` (banned domains / corpus ids /
    authors / titles / content-hash prefixes) via the pure-function
    matchers in `predicate.py`. The empty seed registry means the
    default behavior is permissive **as data** — but the substrate
    is correct, so adding a banned-corpus entry is a pure-data PR
    rather than an architecture change.

  - ``PermissiveLegalGate`` — Sprint 17 placeholder kept for
    explicit opt-in test paths. Requires
    ``ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED=1`` to construct via the
    factory; direct construction with ``_bypass_acknowledgment=True``
    is allowed for tests that want a known-permissive gate.

The spec at §6.9 states: "Wedge 1 cannot ship before the Sprint 18
retrieval-time legal gate is in production." This package satisfies
that — the gate ships with the real registry/predicate plumbing
and an empty seed list awaiting lawyer-reviewed entries.

Public surface:
    - LegalGate (Protocol)
    - LegalGateVerdict (frozen result type)
    - RegistryBackedLegalGate (real gate, the default)
    - PermissiveLegalGate (opt-in placeholder for tests)
    - LegalGatePlaceholderUnacknowledged (acknowledgment exception)
    - default_legal_gate() — env-aware factory

The broader SQL-WHERE enforcement at every documents/chunks read
and write path (per master-spec §9 deeper requirement) is a
separate substrate refactor — out of scope of this module. This
module owns the `check_url` / `check_document` seam.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Optional, Protocol


class LegalGatePlaceholderUnacknowledged(RuntimeError):
    """Raised when the placeholder gate is constructed without the
    operator-acknowledgment flag set.

    The intent: ship the seam, refuse to *operate* under the seam
    until the operator has consciously chosen to. The acknowledgment
    is a per-process env var (`ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED=1`)
    so it doesn't accidentally land in production deployment scripts
    without review.
    """


@dataclass(frozen=True)
class LegalGateVerdict:
    """Result of a legal-gate URL check.

    ``allowed`` is the only field callers should branch on. ``reason``
    is free-text for the audit trail (emitted into
    ``DiscoverySelectedPayload.rejection_reason`` when allowed=False).
    ``gate_kind`` distinguishes placeholder verdicts from real-registry
    verdicts so the trajectory log can tell the difference six months
    from now.
    """

    allowed: bool
    reason: Optional[str] = None
    gate_kind: Literal["placeholder", "sql_where_registry"] = "placeholder"


class LegalGate(Protocol):
    """The seam Wedge 1 + Wedge 2 callers route through.

    Real Sprint 18 implementation will be `SqlWhereLegalGate`
    consulting `substrate/legal_gate/registry.py`. This protocol
    pins the surface so the upstream callers don't change when the
    real implementation lands.
    """

    def check_url(self, url: str) -> LegalGateVerdict:
        """Return Allowed/Rejected for the given URL.

        MUST NOT raise on legal-gate misses (those are Allowed with
        reason=None). MUST raise if the gate itself is misconfigured
        (e.g. registry file missing) — silent permissive failure is
        worse than loud refusal.
        """
        ...


class PermissiveLegalGate:
    """Placeholder gate. Allows every URL.

    Use only via `default_legal_gate()` so the acknowledgment-flag
    check fires. Direct construction is allowed for tests (which
    skip the env-var requirement) but production code paths route
    through the factory.
    """

    def __init__(self, *, _bypass_acknowledgment: bool = False) -> None:
        if _bypass_acknowledgment:
            return
        if os.environ.get("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", "") != "1":
            raise LegalGatePlaceholderUnacknowledged(
                "PermissiveLegalGate is the Sprint-17 placeholder. The real "
                "registry lands Sprint 18 per docs/master-product-spec.md §9. "
                "Set ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED=1 to operate against "
                "the placeholder, or wait for the Sprint 18 registry."
            )

    def check_url(self, url: str) -> LegalGateVerdict:  # noqa: ARG002 (placeholder)
        return LegalGateVerdict(
            allowed=True, reason=None, gate_kind="placeholder"
        )


def default_legal_gate() -> LegalGate:
    """Factory. Returns the `RegistryBackedLegalGate` consulting
    the module-level registry — the **default and the
    operator-defensible choice**.

    Two escape hatches:

      - ``ANTIEK_LEGAL_GATE_DISABLED=1`` — returns the placeholder
        with the acknowledgment flag auto-set. Use ONLY for offline
        substrate work where the operator has consciously chosen to
        bypass the gate. The trajectory still records
        ``gate_kind="placeholder"`` so the bypass is audit-visible.

      - ``ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED=1`` — returns the
        placeholder explicitly (matches the Sprint-17 contract for
        any caller that still depends on the placeholder shape).
        Tests use this; production should NOT.

    Callers should not cache the result across requests — the
    factory is cheap and the right place for the
    implementation choice to live.
    """
    if os.environ.get("ANTIEK_LEGAL_GATE_DISABLED") == "1":
        return PermissiveLegalGate(_bypass_acknowledgment=True)
    if os.environ.get("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED") == "1":
        return PermissiveLegalGate()
    # Lazy import to avoid touching `gate.py` (which imports back
    # into this module for LegalGateVerdict) on every package
    # import.
    from .gate import RegistryBackedLegalGate
    return RegistryBackedLegalGate()


__all__ = [
    "LegalGate",
    "LegalGateVerdict",
    "PermissiveLegalGate",
    "LegalGatePlaceholderUnacknowledged",
    "default_legal_gate",
]

# Re-export the real-gate class so callers don't have to remember
# the submodule layout.
from .gate import RegistryBackedLegalGate  # noqa: E402

__all__.append("RegistryBackedLegalGate")
