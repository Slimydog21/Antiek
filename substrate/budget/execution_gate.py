"""Execution authorization gate — the price-ceiling-approval invariant.

The operator's vision (ask #8/#13, and the Antiek-bench harness brief §3
authority split): *every* live spend — a bench run, a Midnight-Oil swarm step, a
deep-research dispatch — must clear **operator consent + a budget gate** before
it executes. The pure propose paths (#1832 ``/runs/propose``, Midnight Oil #1000)
return ``live_dispatch_authorized=False`` always; the authorized runner is a
*separate* path that flips that flag only after the gate clears. This module IS
that gate — a pure decision function shared by every live-execution caller.

**Why it is a budget substrate, not a bench module.** The decision is generic:
"may this bounded spend execute, given the operator's approved ceiling and the
remaining budget?" The bench, Midnight Oil, and any future dispatch are callers
that hand in ``(CostCeiling, OperatorConsent, BudgetHeadroom)``. Keeping it here
makes the invariant reusable and keeps ``substrate/antiek_bench`` free of
authority logic (the harness brief: *"the pure layer never dispatches"*).

**The load-bearing invariant — an UNKNOWN never authorizes.** This is the
operator's "price ceiling to approve" ask made structural:

  * No consent (``granted`` False) → **deny**. Never auto-authorize.
  * Consent revoked / expired → **deny**.
  * Pricing unknown (``ceiling_usd`` None or ``pricing_known`` False) → **deny**.
    You cannot bound the spend, so you cannot approve it.
  * No approved ceiling (``approved_ceiling_usd`` None) → **deny**. The operator
    must name a ceiling — there is no "unlimited" consent (no inventing authority).
  * Run ceiling > approved ceiling → **deny**. The operator OK'd a *specific*
    bound; a costlier run needs fresh re-approval (consent is ceiling-specific,
    not blanket).
  * Budget headroom unknown (``remaining_usd`` None / ``headroom_known`` False)
    → **deny**. "Can't prove it fits" is not a green light.
  * Run ceiling > remaining budget → **deny**.

The ONLY path to ``authorized=True`` is: explicit, un-revoked, un-expired consent
naming a ceiling, known pricing whose high bound is <= the approved ceiling, AND
known headroom whose remaining is >= the high bound. Every missing fact closes
the gate — this is what makes the spend control "hard to vary."

**Pure — no I/O, no clock, no dispatch.** The clock is the caller's: consent
arrives with ``is_expired`` already resolved (the pure gate does not parse time).
The gate returns a *decision*; the caller invokes the runner iff authorized.
"""

from __future__ import annotations

from dataclasses import dataclass


class ExecutionGateError(ValueError):
    """A gate input violates a load-bearing invariant (e.g. negative ceiling)."""


@dataclass(frozen=True)
class CostCeiling:
    """The high-bound spend estimate for a proposed execution.

    ``ceiling_usd`` is the *worst-case* (high) estimate — the most the execution
    could cost. ``pricing_known`` mirrors ``projection.py``'s convention so a
    caller cannot pair a None ceiling with a谎ed-known flag.
    """

    ceiling_usd: float | None
    pricing_known: bool


@dataclass(frozen=True)
class OperatorConsent:
    """The operator's explicit approval of a price ceiling for this execution.

    ``approved_ceiling_usd`` is the upper bound the operator agreed to. ``None``
    means "no ceiling was named" — which the gate treats as NOT authorizing
    (there is no blanket consent). ``is_expired`` is caller-resolved so the pure
    gate owns no clock.
    """

    granted: bool
    approved_ceiling_usd: float | None
    is_expired: bool
    revoked: bool


@dataclass(frozen=True)
class BudgetHeadroom:
    """The remaining budget the execution must fit within.

    ``remaining_usd`` is cap minus spent (from #1841's ``KeyUsage.remaining_usd``
    or #1838's ``BudgetState.remaining_usd``). ``headroom_known`` mirrors the
    ``_known`` convention; a None remaining with ``headroom_known`` True would be
    a caller bug and is still denied defensively.
    """

    remaining_usd: float | None
    headroom_known: bool


@dataclass(frozen=True)
class AuthorizationDecision:
    """The gate's verdict. ``authorized`` is the only flag a caller dispatches on."""

    authorized: bool
    reason: str
    notes: tuple[str, ...] = ()


def _validate_nonneg(value: float, name: str) -> float:
    if value < 0:
        raise ExecutionGateError(
            f"{name} must be >= 0 (got {value}); a spend ceiling/budget cannot be negative"
        )
    return value


def authorize_execution(
    ceiling: CostCeiling,
    consent: OperatorConsent,
    headroom: BudgetHeadroom,
) -> AuthorizationDecision:
    """Return the authorization decision for one proposed execution.

    Ordered gates — the first failure denies and names the reason. Pure: no I/O,
    no clock, no dispatch. A caller executes the run iff ``decision.authorized``.
    """
    if ceiling.ceiling_usd is not None:
        _validate_nonneg(ceiling.ceiling_usd, "ceiling.ceiling_usd")
    if consent.approved_ceiling_usd is not None:
        _validate_nonneg(consent.approved_ceiling_usd, "consent.approved_ceiling_usd")
    if headroom.remaining_usd is not None:
        _validate_nonneg(headroom.remaining_usd, "headroom.remaining_usd")

    notes: list[str] = []

    # Gate 1 — explicit consent.
    if not consent.granted:
        return AuthorizationDecision(False, "no operator consent", tuple(notes))
    if consent.revoked:
        return AuthorizationDecision(False, "operator consent revoked", tuple(notes))
    if consent.is_expired:
        return AuthorizationDecision(False, "operator consent expired", tuple(notes))

    # Gate 2 — a named ceiling to approve against.
    if consent.approved_ceiling_usd is None:
        notes.append("consent names no price ceiling; blanket consent is not authorized")
        return AuthorizationDecision(
            False, "consent specifies no price ceiling", tuple(notes)
        )

    # Gate 3 — bounded pricing.
    if not ceiling.pricing_known or ceiling.ceiling_usd is None:
        notes.append("pricing unknown — spend cannot be bounded, so it cannot be approved")
        return AuthorizationDecision(
            False, "pricing unknown; spend unbounded", tuple(notes)
        )

    # Gate 4 — the run fits what the operator approved.
    if ceiling.ceiling_usd > consent.approved_ceiling_usd:
        notes.append(
            f"run ceiling {ceiling.ceiling_usd} exceeds approved ceiling "
            f"{consent.approved_ceiling_usd} — re-approval required"
        )
        return AuthorizationDecision(
            False, "run ceiling exceeds approved ceiling", tuple(notes)
        )

    # Gate 5 — known headroom.
    if not headroom.headroom_known or headroom.remaining_usd is None:
        notes.append("budget headroom unknown — affordability cannot be proven")
        return AuthorizationDecision(
            False, "budget headroom unknown", tuple(notes)
        )

    # Gate 6 — the run fits the remaining budget.
    if ceiling.ceiling_usd > headroom.remaining_usd:
        notes.append(
            f"run ceiling {ceiling.ceiling_usd} exceeds remaining budget "
            f"{headroom.remaining_usd}"
        )
        return AuthorizationDecision(
            False, "run ceiling exceeds remaining budget", tuple(notes)
        )

    notes.append(
        f"authorized: ceiling {ceiling.ceiling_usd} <= approved "
        f"{consent.approved_ceiling_usd} and <= remaining {headroom.remaining_usd}"
    )
    return AuthorizationDecision(True, "all gates passed", tuple(notes))


__all__ = [
    "ExecutionGateError",
    "CostCeiling",
    "OperatorConsent",
    "BudgetHeadroom",
    "AuthorizationDecision",
    "authorize_execution",
]
