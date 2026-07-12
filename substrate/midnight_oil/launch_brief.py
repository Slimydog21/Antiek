"""Midnight Oil launch brief — the immutable trust anchor (ask #13).

The operator's vision (ask #13): *"...set a time of work and goals (and the
system provides the user a recommended price ceiling to approve) then the agent
goes off to execute that task."* The spine is complete: the cost estimator
(#1849) names the ceiling, the planner (#1854) schedules the phases, the gate
(#1842) authorizes per phase, the ledger (#1841) tracks actuals, and the receipt
(#1867) reconciles on return. But there is a gap between "operator approved a
ceiling" and "the swarm launched against a specific plan": the operator approves a
NUMBER, then a PLAN is built, then the swarm goes. **Who freezes the binding
between the approved ceiling and the specific plan, immutably, so the unattended
swarm — and the receipt — can prove fidelity to what the operator actually OK'd?**
THIS module is that binding: the launch brief.

**Why a launch brief is load-bearing.** An unattended swarm runs for hours with no
operator watching. Without a frozen record of "the operator approved ceiling $X
against plan P (hash h)," three trust failures are possible:
  1. **Ceiling drift.** The swarm could spend against a looser ceiling than
     approved (a later re-estimate, a config reload). A frozen brief pins the
     ceiling at launch; the gate (#1842) checks each phase against the BRIEF's
     ceiling, not a live re-read.
  2. **Plan drift.** The plan could be re-scheduled mid-run (more phases, heavier
     budgets). A frozen brief pins the plan hash; any divergence is detectable.
  3. **Consent repudiation.** Without a content-addressed record of what the
     operator consented to, "I didn't approve THAT" is unresolvable. The brief
     carries the consent signature so the receipt can prove the run matched.

**The launch brief is immutable and content-addressed.** Once built, it never
changes — ``brief_id`` is sha256 over (ceiling, plan hash, goals, consent). To
change any input is to build a DIFFERENT brief (different id). The unattended
swarm receives the brief at launch and carries it as its immutable mandate; the
receipt (#1867) reconciles actuals against the brief's frozen ceiling. This is
the structural realization of "hard to vary": the mandate is a hash, not a
mutable reference.

**Why pure + import-free of the siblings.** #1849/#1854/#1842 ship in separate
off-main PRs. Hard-importing them would stack PRs and break independent
bar-cleanliness on a frozen main. Instead the brief takes the approved ceiling +
the plan envelope as injectable inputs (compatible shapes); the launch layer that
has all modules on hand assembles them. The brief owns the ONE thing no other
module does: the **frozen binding** + the **launch-authorization invariant**.

**The load-bearing invariants (each is a test):**

1. **The brief's ceiling is the plan's HIGH-bound total, NOT a fresh estimate.**
   The operator approves a ceiling; the plan produces a high-bound total. The
   brief's ``approved_ceiling_usd`` is the MINIMUM of (operator's approved
   ceiling, plan's high-bound total) — the swarm never gets a looser ceiling than
   the operator approved, and never more than the plan could cost. If the plan's
   total EXCEEDS the approved ceiling, the brief is NOT buildable (launch refused)
   — the operator must re-approve a higher ceiling or trim the plan. A brief that
   launched an over-ceiling plan would betray the operator's trust at the start.
2. **A brief requires explicit, unexpired, unrevoked consent naming a ceiling.**
   No consent / expired / revoked / no ceiling → ``LaunchRefusal`` (never a brief
   with ``authorized=False`` silently — the refusal is explicit and named). This
   mirrors #1842's "an unknown never authorizes" but at launch granularity.
3. **The brief is immutable + content-addressed.** ``brief_id`` is deterministic
   over the frozen inputs. Re-building with the same inputs yields the same id;
   changing ANY input (ceiling, plan hash, a goal, the consent operator id) yields
   a different id. There is no mutation API — the dataclass is frozen.
4. **Plan-ceiling consistency is checked at build time.** The plan's high-bound
   total must be <= the approved ceiling (invariant #1). An unknown plan total
   (unpriced tiers) → the brief's ``ceiling_known = False`` and the brief is still
   buildable ONLY if the operator's approved ceiling is known (the swarm then runs
   gated per-phase; the receipt reports ``within_budget`` against the operator's
   ceiling). But a KNOWN plan total > approved ceiling → REFUSAL (never launch).
5. **The consent token is NEVER stored in the brief.** The brief stores the
   consent's ``operator_id`` + a redacted token hash (the #1846 pattern), NEVER the
   raw token. The brief may be persisted/shared for audit; it must not leak the
   credential. The raw token stays in the ephemeral launch envelope.
6. **Goals are carried verbatim + counted.** The operator named N goals; the brief
   carries all N in order. A goal dropped at launch would silently shrink the
   mandate. ``goal_count`` is exact.
7. **Deterministic + pure.** Same (ceiling, plan, goals, consent) → byte-identical
   brief. No I/O, no clock, no dispatch. ``launched_at_label`` is caller-resolved.

**Composition (where the brief sits in the MO trust loop):**

    estimate (#1849) → operator approves ceiling
    planner (#1854) → plan with high-bound total
        ↓
    build_launch_brief(ceiling, plan, consent) → LaunchBrief | LaunchRefusal (THIS)
        ↓ if Brief
    swarm launches against the brief; per-phase gate (#1842) checks the BRIEF ceiling
        ↓
    receipt (#1867) reconciles actuals against the BRIEF's frozen ceiling

The brief is the contract between "the operator approved this" and "the swarm did
not drift from it."
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


class LaunchBriefError(ValueError):
    """A launch-brief input violates a load-bearing invariant."""


@dataclass(frozen=True)
class PlanSummary:
    """The frozen projection of a plan the brief binds to.

    Mirrors the fields #1854's ``ExecutionPlan`` exposes. ``plan_id`` and
    ``plan_total_high_cost_usd`` are the two load-bearing pins: the brief freezes
    the plan by its id and checks the cost ceiling against its total.
    ``plan_total_high_cost_usd`` is ``None`` when the plan has unpriced tiers.
    """

    plan_id: str
    phase_count: int
    total_duration_minutes: int
    goals: tuple[str, ...]
    plan_total_high_cost_usd: float | None
    pricing_known: bool


@dataclass(frozen=True)
class OperatorApproval:
    """The operator's explicit approval of a ceiling for this launch.

    Mirrors #1842's ``OperatorConsent`` shape. ``approved_ceiling_usd`` is the
    number the operator OK'd (None = no ceiling named → refuses launch).
    ``is_expired`` / ``revoked`` are caller-resolved (the pure brief owns no clock).
    ``consent_token`` is the raw credential — used ONLY to compute the redacted
    hash; NEVER stored on the brief.
    """

    operator_id: str
    granted: bool
    approved_ceiling_usd: float | None
    is_expired: bool
    revoked: bool
    consent_token: str


@dataclass(frozen=True)
class LaunchBrief:
    """The immutable mandate an unattended swarm launches against.

    ``brief_id`` is content-addressed over the frozen inputs. ``effective_ceiling``
    is the ceiling the gate enforces per-phase (min of approved and plan-total when
    both known). ``token_hash`` is the redacted consent credential (never raw).
    """

    brief_id: str
    operator_id: str
    plan: PlanSummary
    goals: tuple[str, ...]
    effective_ceiling_usd: float | None
    ceiling_known: bool
    token_hash: str  # sha256:<16hex> — proves consent identity, never leaks the raw token
    launched_at_label: str
    honesty_notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def goal_count(self) -> int:
        return len(self.goals)


@dataclass(frozen=True)
class LaunchRefusal:
    """The launch was refused. Names the reason; no brief is built."""

    reason: str
    detail: str = ""
    notes: tuple[str, ...] = ()


LaunchResult = LaunchBrief | LaunchRefusal


def _redact_token(token: str) -> str:
    """Hash a consent token — proves identity, never leaks the raw secret.

    Mirrors the #1846 draft-promotion redaction pattern: the brief is an auditable
    artifact that may be persisted/shared; it must never carry the raw credential.
    """
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _brief_id(
    operator_id: str,
    plan: PlanSummary,
    goals: tuple[str, ...],
    effective_ceiling: float | None,
    token_hash: str,
) -> str:
    payload = json.dumps(
        {
            "operator_id": operator_id,
            "plan_id": plan.plan_id,
            "phase_count": plan.phase_count,
            "duration": plan.total_duration_minutes,
            "goals": list(goals),
            "effective_ceiling": effective_ceiling,
            "token_hash": token_hash,
        },
        sort_keys=True,
    )
    return "mo-brief-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_launch_brief(
    *,
    plan: PlanSummary,
    approval: OperatorApproval,
    launched_at_label: str,
) -> LaunchResult:
    """Bind an approved ceiling to a plan into an immutable launch brief.

    Returns :class:`LaunchBrief` when the launch is authorized and plan-ceiling
    consistent, or :class:`LaunchRefusal` (explicit, named) when it is not. Pure:
    no I/O, no clock, no dispatch.
    """
    if not launched_at_label.strip():
        raise LaunchBriefError("launched_at_label must be non-empty")
    if not plan.plan_id.strip():
        raise LaunchBriefError("plan.plan_id must be non-empty")
    if plan.phase_count < 1:
        raise LaunchBriefError("plan.phase_count must be >= 1")
    if not plan.goals:
        raise LaunchBriefError("plan.goals must be non-empty")
    if not approval.operator_id.strip():
        raise LaunchBriefError("approval.operator_id must be non-empty")
    if not approval.consent_token.strip():
        raise LaunchBriefError("approval.consent_token must be non-empty (consent required)")

    notes: list[str] = []

    # Invariant #2 — explicit, unexpired, unrevoked consent naming a ceiling.
    if not approval.granted:
        return LaunchRefusal("no operator consent", "consent not granted", tuple(notes))
    if approval.revoked:
        return LaunchRefusal("consent revoked", "operator revoked approval", tuple(notes))
    if approval.is_expired:
        return LaunchRefusal("consent expired", "operator approval expired before launch", tuple(notes))
    if approval.approved_ceiling_usd is None:
        return LaunchRefusal(
            "no ceiling named",
            "consent specifies no price ceiling; blanket launch is not authorized",
            tuple(notes),
        )

    approved_ceiling = approval.approved_ceiling_usd
    if approved_ceiling < 0:
        raise LaunchBriefError(
            f"approved_ceiling_usd must be >= 0 (got {approved_ceiling})"
        )

    plan_total = plan.plan_total_high_cost_usd
    token_hash = _redact_token(approval.consent_token)

    # Invariant #1 + #4 — the effective ceiling + plan-ceiling consistency.
    if plan_total is not None and plan.pricing_known:
        # Plan total known. Over-ceiling plan → REFUSE (invariant #1).
        if plan_total > approved_ceiling:
            return LaunchRefusal(
                "plan exceeds approved ceiling",
                f"plan high-bound total ${plan_total:.4f} exceeds approved ceiling "
                f"${approved_ceiling:.4f} — re-approve a higher ceiling or trim the plan",
                tuple(notes),
            )
        effective_ceiling = min(approved_ceiling, plan_total)
        ceiling_known = True
    else:
        # Plan total unknown (unpriced tiers). Effective ceiling is the operator's
        # approved ceiling; the per-phase gate enforces it; the receipt reports
        # against it. pricing_known False surfaced honestly.
        effective_ceiling = approved_ceiling
        ceiling_known = False
        notes.append(
            "plan pricing incomplete — effective ceiling is the operator's approved "
            "ceiling; per-phase gate enforces it"
        )

    return LaunchBrief(
        brief_id=_brief_id(approval.operator_id, plan, plan.goals, effective_ceiling, token_hash),
        operator_id=approval.operator_id,
        plan=plan,
        goals=plan.goals,
        effective_ceiling_usd=effective_ceiling,
        ceiling_known=ceiling_known,
        token_hash=token_hash,
        launched_at_label=launched_at_label,
        honesty_notes=tuple(notes),
    )


__all__ = [
    "LaunchBriefError",
    "PlanSummary",
    "OperatorApproval",
    "LaunchBrief",
    "LaunchRefusal",
    "LaunchResult",
    "build_launch_brief",
]
