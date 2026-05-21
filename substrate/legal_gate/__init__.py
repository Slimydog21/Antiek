"""Retrieval-time legal gate (Sprint 18 deliverable, placeholder shipped Sprint 17).

Per `docs/master-product-spec.md` §9 the legal gate enforces the
Bartz / Hachette / AG MDL banned-corpus restrictions at the SQL-WHERE
level. The real Sprint 18 work lands `registry.py` (the curated
banned-corpora list), `predicate.py` (the SQL-WHERE generator), and
`gate.py` (the runtime gate wrapping `runtime/db_lock.connect_write`).

This Sprint-17 placeholder ships only the **interface** so the
upstream callers (the Exa & Browserbase Wedge 1 + Wedge 2 ingestion
path) can route through the gate seam without a future refactor. The
default `PermissiveLegalGate` allows every URL. The acknowledgment
flag is OFF by default so any production caller fails loudly on
boot until the operator (a) consciously accepts the placeholder is
permissive or (b) wires the real Sprint 18 implementation.

The spec at §6.9 states: "Wedge 1 cannot ship before the Sprint 18
retrieval-time legal gate is in production." This placeholder
preserves the architectural seam — Wedge 1 callers always route
through `check_url(...)` — so the real registry drops in by
replacing the gate instance, not by editing the adapter.

Public surface:
    - LegalGate (abstract base)
    - LegalGateVerdict (frozen result type)
    - PermissiveLegalGate (placeholder default)
    - LegalGatePlaceholderUnacknowledged (boot-time exception)
    - default_legal_gate() — env-aware factory

When Sprint 18 lands `registry.py` + `predicate.py`, the new
`SqlWhereLegalGate` is added here and `default_legal_gate()` switches
its default. Callers don't change.
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
    """Factory. Returns the real gate when Sprint 18 lands it; until
    then, returns the placeholder (with acknowledgment-flag enforced).

    Callers should not cache the result across requests — the factory
    is cheap and the right place to swap implementations.
    """
    # Sprint 18 will branch here on the presence of the real registry.
    # For now: only the placeholder exists.
    return PermissiveLegalGate()


__all__ = [
    "LegalGate",
    "LegalGateVerdict",
    "PermissiveLegalGate",
    "LegalGatePlaceholderUnacknowledged",
    "default_legal_gate",
]
