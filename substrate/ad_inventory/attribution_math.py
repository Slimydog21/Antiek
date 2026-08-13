"""Published per-frame attribution split order — attribution-math-v2 (AFA-S5).

One versioned pipeline composes the six stages that previously lived as
disconnected primitives:

    carve-outs → 70/30 platform cut → filtered attention weights
    → synthesis composition → rights/T1/author gates → UNATTRIBUTED bucket

Every stage conserves integer cents. The composed version id is
``ATTRIBUTION_MATH_VERSION = "attribution-math-v2"``. Changing ANY stage
parameter without bumping that id is a defect (caught by the version-
completeness test).

================================================================================
SEMANTIC CHANGE (rigor #1 — authorized by PR #118 §7.1-S5 / AFA-S5)
================================================================================
BEFORE (frame_attention_accrual.py:12, pre-S5): the frame pipeline conserved
100% of window value to contributors + house seconds. The 70/30 creator/
platform split lived only in ``payout.py`` (impression path) and was
"deliberately deferred" for frames.

AFTER (this module + the S5 wire into ``frame_attention_accrual``): at the
pool boundary, 70% of post-carve-out value becomes the creator pool (split
across filtered eligible assets), and 30% + fully-filtered value + residuals
route to the house. Accrual still never disburses (``disbursable=False``);
escrow-only.

Rationale for placing the cut at the pool boundary (not at disbursement):
statements (AFA-S6) must show each payee's true effective rate at close. A
cut applied later would make every interim statement overstate earnings —
the exact "trust the dashboard" failure this program exists to kill.

================================================================================
STAGE ORDER (defended by counterfactual tests, not narrative)
================================================================================
1. Carve-outs     — pre-pool licensed fractions (registry ships empty).
2. Platform cut   — 70/30 at the pool boundary (CREATOR_REV_SHARE / PLATFORM_CUT).
3. Filtered weights — S2 classify+caps already applied by the caller; this stage
                      re-normalizes the surviving weight vector.
4. Composition    — synthesis share vectors (identity when no synthesis shares
                      are supplied; S3's compose_frame_value is DORMANT on this
                      base — see hatch handoff).
5. Rights/T1/author gates — monetization_eligible + ads_allowed(T1) + author
                      split (equal-v1). Failures route to residuals.
6. Residuals      — everything unresolvable → UNATTRIBUTED_RIGHTS_BUCKET with
                      reason codes.

Pool-scope parameter (OQ-2): ``pool_scope: "global" | "per-reader"``, default
``"global"`` (index.html decision log — coincident with per-reader until
multi-user). Per-reader bounds an attacker's damage to their own contribution
(sybil rationale); Sprint-22 multi-user is the operator ratification moment.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from substrate.ad_inventory.frame_attention import apportion_cents
from substrate.ad_inventory.payout import CREATOR_REV_SHARE, PLATFORM_CUT
from substrate.constants import UNATTRIBUTED_RIGHTS_BUCKET
from substrate.payouts.split import SPLIT_POLICY_VERSION, equal_split
from substrate.rights.ad_eligibility import ads_allowed
from substrate.rights.arxiv_tiers import resolve_tier

# ---------------------------------------------------------------------------
# Composed version id (bump on ANY stage parameter / constant / order change)
# ---------------------------------------------------------------------------

ATTRIBUTION_MATH_VERSION: str = "attribution-math-v2"

# Stage version pins composed into the math id. Changing a pin without
# bumping ATTRIBUTION_MATH_VERSION is the silent-history-rewriting defect
# the version-completeness test catches.
STAGE_VERSIONS: dict[str, str] = {
    "carve_outs": "carve-out-registry-v1",
    "platform_cut": "platform-cut-70-30-v1",
    "filtered_weights": "frame-weight-v2",
    "composition": "composition-identity-v1",  # S3 dormant → identity
    "holder_gates": f"holder-gates-t1+{SPLIT_POLICY_VERSION}",
    "residuals": "unattributed-bucket-v1",
}

PoolScope = Literal["global", "per-reader"]
DEFAULT_POOL_SCOPE: PoolScope = "global"

# House / residual reason codes (stable strings for audit + statements).
REASON_CARVE_OUT = "carve_out"
REASON_PLATFORM_CUT = "platform_cut"
REASON_FILTERED = "filtered_out"
REASON_INELIGIBLE_CONTENT = "ineligible_content_class"
REASON_T1_GATE = "rights_tier_not_t1"
REASON_NO_HOLDER = "no_resolvable_holder"
REASON_NO_AUTHORS = "no_attributable_authors"
REASON_UNATTRIBUTED = "unattributed"
REASON_HOUSE_SECONDS = "house_seconds"
REASON_EMPTY_POOL = "empty_creator_pool"


# ---------------------------------------------------------------------------
# Inputs / outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CarveOutEntry:
    """One licensed pre-pool carve-out for a document.

    ``fraction`` is in (0, 1]; the absolute cents are computed from the
    pre-pool window value. ``payee_ref`` is an opaque recipient id (license
    deal counterparty) — never an ip_holder auto-route (operator populates
    the registry; empty today).
    """

    document_id: str
    fraction: float
    payee_ref: str


@dataclass(frozen=True)
class AssetCandidate:
    """One asset competing for the creator pool after filtering.

    ``weight`` is the post-filter attention weight (already excluded from
    both numerator and denominator of invalid seconds by the caller).
    ``content_class`` feeds monetization_eligible; ``license_uri`` is
    re-derived into a tier at gate time (never trusted from a stored tier).
    ``n_authors`` drives the equal-split policy (0 → residual).
    """

    asset_id: str
    weight: float
    content_class: str | None = None
    license_uri: str | None = None
    ip_holder_id: str | None = None
    document_id: str | None = None
    n_authors: int = 0
    # Optional synthesis share vector: constituent_id → share in [0,1].
    # Empty/None means identity (the asset itself is the payee unit).
    synthesis_shares: Mapping[str, float] | None = None


@dataclass(frozen=True)
class PayeeLine:
    """One conserved payee slice after the full pipeline."""

    payee_ref: str
    amount_cents: int
    kind: str  # "creator" | "platform" | "carve_out" | "unattributed" | "house"
    reason: str
    asset_id: str | None = None
    document_id: str | None = None
    author_position: int | None = None


@dataclass(frozen=True)
class StageTrace:
    """Per-stage conservation audit: input cents == output cents + routed."""

    stage: str
    input_cents: int
    output_cents: int
    routed_cents: int
    detail: dict[str, Any] = field(default_factory=dict)

    def conserves(self) -> bool:
        return self.input_cents == self.output_cents + self.routed_cents


@dataclass(frozen=True)
class PipelineResult:
    """Full six-stage result for one window (or one pool unit)."""

    window_value_cents: int
    creator_pool_cents: int
    platform_cut_cents: int
    carve_out_cents: int
    unattributed_cents: int
    house_cents: int  # platform cut + filtered + house-seconds residuals
    payee_lines: tuple[PayeeLine, ...]
    stage_traces: tuple[StageTrace, ...]
    attribution_math_version: str
    stage_versions: dict[str, str]
    pool_scope: PoolScope

    def conserves(self) -> bool:
        """Σ all payee lines == window value, and every stage conserves."""
        total_lines = sum(p.amount_cents for p in self.payee_lines)
        return total_lines == self.window_value_cents and all(
            t.conserves() for t in self.stage_traces
        )

    def total_payee_cents(self) -> int:
        return sum(p.amount_cents for p in self.payee_lines)


@dataclass(frozen=True)
class PipelineParams:
    """Knobs that participate in the composed version id.

    Defaults are the published conservative choices. Mutating any field
    without bumping ATTRIBUTION_MATH_VERSION fails the completeness test.
    """

    creator_rev_share: Decimal = CREATOR_REV_SHARE
    platform_cut: Decimal = PLATFORM_CUT
    pool_scope: PoolScope = DEFAULT_POOL_SCOPE
    split_policy_version: str = SPLIT_POLICY_VERSION
    stage_versions: dict[str, str] = field(
        default_factory=lambda: dict(STAGE_VERSIONS)
    )


# ---------------------------------------------------------------------------
# Stage 1 — Carve-outs (pre-pool)
# ---------------------------------------------------------------------------


def stage_carve_outs(
    window_value_cents: int,
    carve_outs: Sequence[CarveOutEntry] = (),
) -> tuple[int, list[PayeeLine], StageTrace]:
    """Deduct licensed fractions from the window value before pooling.

    Multiple carve-outs on the same document stack by summing fractions,
    clamped so total carve-out cents cannot exceed the window value.
    Empty registry (the shipping default) is a pure pass-through.
    """
    if window_value_cents < 0:
        raise ValueError("window_value_cents must be non-negative")
    if not carve_outs or window_value_cents == 0:
        return (
            window_value_cents,
            [],
            StageTrace(
                stage="carve_outs",
                input_cents=window_value_cents,
                output_cents=window_value_cents,
                routed_cents=0,
                detail={"n_entries": 0},
            ),
        )

    # Weight by fraction; apportion so parts sum exactly to the carved total
    # (and the carved total is floor(sum(fraction)*value) conserved).
    weights: dict[str, float] = {}
    meta: dict[str, CarveOutEntry] = {}
    for i, entry in enumerate(carve_outs):
        if entry.fraction <= 0:
            continue
        key = f"{entry.document_id}\x00{entry.payee_ref}\x00{i}"
        weights[key] = float(entry.fraction)
        meta[key] = entry

    if not weights:
        return (
            window_value_cents,
            [],
            StageTrace(
                stage="carve_outs",
                input_cents=window_value_cents,
                output_cents=window_value_cents,
                routed_cents=0,
                detail={"n_entries": 0},
            ),
        )

    total_fraction = sum(weights.values())
    # Cap: carve-outs cannot claim more than 100% of the window.
    carve_total = (
        window_value_cents
        if total_fraction >= 1.0
        else int(Decimal(window_value_cents) * Decimal(str(total_fraction)))
    )
    # Use largest-remainder over the fraction weights against carve_total so
    # the payee lines sum exactly to carve_total.
    split = apportion_cents(weights, carve_total) if carve_total > 0 else {}
    lines: list[PayeeLine] = []
    for key, cents in split.items():
        if cents <= 0:
            continue
        entry = meta[key]
        lines.append(
            PayeeLine(
                payee_ref=entry.payee_ref,
                amount_cents=cents,
                kind="carve_out",
                reason=REASON_CARVE_OUT,
                document_id=entry.document_id,
            )
        )
    routed = sum(line.amount_cents for line in lines)
    remaining = window_value_cents - routed
    return (
        remaining,
        lines,
        StageTrace(
            stage="carve_outs",
            input_cents=window_value_cents,
            output_cents=remaining,
            routed_cents=routed,
            detail={"n_entries": len(lines), "total_fraction": total_fraction},
        ),
    )


# ---------------------------------------------------------------------------
# Stage 2 — Platform cut (70/30 at the pool boundary)
# ---------------------------------------------------------------------------


def stage_platform_cut(
    post_carve_cents: int,
    *,
    creator_rev_share: Decimal = CREATOR_REV_SHARE,
) -> tuple[int, int, list[PayeeLine], StageTrace]:
    """Split post-carve-out value into creator pool (70%) and platform (30%).

    Uses integer truncation on the creator share so platform gets the
    remainder — identical to ``payout.distribute_session_ad_revenue``:
    ``creator = int(total * 0.70); platform = total - creator``.
    """
    if post_carve_cents < 0:
        raise ValueError("post_carve_cents must be non-negative")
    creator_pool = int(post_carve_cents * float(creator_rev_share))
    platform = post_carve_cents - creator_pool
    lines: list[PayeeLine] = []
    if platform > 0:
        lines.append(
            PayeeLine(
                payee_ref="__platform__",
                amount_cents=platform,
                kind="platform",
                reason=REASON_PLATFORM_CUT,
            )
        )
    return (
        creator_pool,
        platform,
        lines,
        StageTrace(
            stage="platform_cut",
            input_cents=post_carve_cents,
            output_cents=creator_pool,
            routed_cents=platform,
            detail={
                "creator_rev_share": str(creator_rev_share),
                "platform_cut": str(Decimal("1") - creator_rev_share),
            },
        ),
    )


# ---------------------------------------------------------------------------
# Stage 3 — Filtered weights (re-normalize survivors)
# ---------------------------------------------------------------------------


def stage_filtered_weights(
    candidates: Sequence[AssetCandidate],
) -> tuple[dict[str, float], StageTrace]:
    """Re-normalize post-filter attention weights to sum to 1.0.

    The caller is responsible for having already excluded invalid seconds
    (S2 classify+caps) from both numerator and denominator. Candidates with
    non-positive weight are dropped here. An empty survivor set yields an
    empty weight dict — the creator pool then routes to residuals/house.
    """
    positive = {c.asset_id: c.weight for c in candidates if c.weight > 0}
    total = sum(positive.values())
    if total <= 0:
        return (
            {},
            StageTrace(
                stage="filtered_weights",
                input_cents=0,
                output_cents=0,
                routed_cents=0,
                detail={"n_survivors": 0, "n_dropped": len(candidates)},
            ),
        )
    normalized = {aid: w / total for aid, w in positive.items()}
    return (
        normalized,
        StageTrace(
            stage="filtered_weights",
            input_cents=0,  # weight-only stage; cents enter at composition
            output_cents=0,
            routed_cents=0,
            detail={
                "n_survivors": len(normalized),
                "n_dropped": len(candidates) - len(positive),
                "weight_sum": sum(normalized.values()),
            },
        ),
    )


# ---------------------------------------------------------------------------
# Stage 4 — Synthesis composition
# ---------------------------------------------------------------------------


def stage_composition(
    creator_pool_cents: int,
    weights: Mapping[str, float],
    candidates: Sequence[AssetCandidate],
) -> tuple[dict[str, int], list[PayeeLine], StageTrace]:
    """Apportion the creator pool across assets, then expand synthesis shares.

    When an asset carries ``synthesis_shares``, its cents are further split
    across constituents (S3 compose_frame_value shape). When shares are
    absent, the asset is the identity payee unit (S3 dormant default).
    """
    if creator_pool_cents < 0:
        raise ValueError("creator_pool_cents must be non-negative")
    if not weights or creator_pool_cents == 0:
        return (
            {},
            [],
            StageTrace(
                stage="composition",
                input_cents=creator_pool_cents,
                output_cents=0,
                routed_cents=creator_pool_cents,
                detail={"mode": "empty"},
            ),
        )

    by_id = {c.asset_id: c for c in candidates}
    asset_cents = apportion_cents(dict(weights), creator_pool_cents)

    # Expand synthesis shares (or identity).
    unit_cents: dict[str, int] = {}  # key: asset_id or asset_id\x00constituent
    unit_meta: dict[str, tuple[str, str | None]] = {}  # key → (asset_id, constituent?)
    for aid, cents in asset_cents.items():
        cand = by_id.get(aid)
        shares = cand.synthesis_shares if cand is not None else None
        if not shares:
            unit_cents[aid] = unit_cents.get(aid, 0) + cents
            unit_meta[aid] = (aid, None)
            continue
        # Filter non-positive shares, re-normalize via apportion_cents.
        pos = {k: float(v) for k, v in shares.items() if float(v) > 0}
        if not pos:
            unit_cents[aid] = unit_cents.get(aid, 0) + cents
            unit_meta[aid] = (aid, None)
            continue
        sub = apportion_cents(pos, cents)
        for cid, sc in sub.items():
            key = f"{aid}\x00{cid}"
            unit_cents[key] = unit_cents.get(key, 0) + sc
            unit_meta[key] = (aid, cid)

    assigned = sum(unit_cents.values())
    residual = creator_pool_cents - assigned
    residual_lines: list[PayeeLine] = []
    if residual > 0:
        # Should not happen with largest-remainder, but belt-and-suspenders:
        residual_lines.append(
            PayeeLine(
                payee_ref=UNATTRIBUTED_RIGHTS_BUCKET,
                amount_cents=residual,
                kind="unattributed",
                reason=REASON_UNATTRIBUTED,
            )
        )
    return (
        unit_cents,
        residual_lines,
        StageTrace(
            stage="composition",
            input_cents=creator_pool_cents,
            output_cents=assigned,
            routed_cents=residual,
            detail={
                "n_units": len(unit_cents),
                "n_assets": len(asset_cents),
            },
        ),
    )


# ---------------------------------------------------------------------------
# Stage 5 — Rights / T1 / author gates
# ---------------------------------------------------------------------------


def _asset_passes_gates(
    cand: AssetCandidate | None,
) -> tuple[bool, str]:
    """Return (passes, reason_if_not). Deny-by-default."""
    if cand is None:
        return False, REASON_NO_HOLDER
    from substrate.ad_inventory.attribution import monetization_eligible

    if not monetization_eligible(cand.content_class):
        return False, REASON_INELIGIBLE_CONTENT
    # T1 gate: only when a license_uri is supplied do we enforce ads_allowed.
    # Assets without a license_uri (non-arXiv books, public_domain docs that
    # already passed monetization_eligible) are admitted — matching the
    # pre-S5 frame path where content_class was the sole earn gate. This is
    # the conservative "compose, don't re-implement" default: the T1 check
    # is additive for arXiv papers that carry a license_uri.
    if cand.license_uri is not None:
        tier = resolve_tier(cand.license_uri)
        if not ads_allowed(tier):
            return False, REASON_T1_GATE
    return True, ""


def stage_holder_gates(
    unit_cents: Mapping[str, int],
    candidates: Sequence[AssetCandidate],
    *,
    split_policy_version: str = SPLIT_POLICY_VERSION,
) -> tuple[list[PayeeLine], list[PayeeLine], StageTrace]:
    """Apply monetization + T1 + author-split gates; failures → residual lines.

    Outer earn / inner pay: a gated-but-present asset still "earns" into
    escrow-shaped lines (payee_ref = ip_holder or author position); a failed
    gate routes to UNATTRIBUTED with a reason code. Author split uses
    ``equal_split`` (author-split-equal-v1) when n_authors > 0; otherwise the
    whole unit goes to the ip_holder_id if present, else unattributed.
    """
    by_id = {c.asset_id: c for c in candidates}
    creator_lines: list[PayeeLine] = []
    residual_lines: list[PayeeLine] = []
    input_total = sum(unit_cents.values())

    for key, cents in unit_cents.items():
        if cents <= 0:
            continue
        asset_id = key.split("\x00", 1)[0]
        cand = by_id.get(asset_id)
        ok, reason = _asset_passes_gates(cand)
        if not ok:
            residual_lines.append(
                PayeeLine(
                    payee_ref=UNATTRIBUTED_RIGHTS_BUCKET,
                    amount_cents=cents,
                    kind="unattributed",
                    reason=reason,
                    asset_id=asset_id,
                    document_id=cand.document_id if cand else None,
                )
            )
            continue

        assert cand is not None
        # Author split when n_authors > 0.
        if cand.n_authors > 0:
            weights = equal_split(cand.n_authors)
            if not weights:
                residual_lines.append(
                    PayeeLine(
                        payee_ref=UNATTRIBUTED_RIGHTS_BUCKET,
                        amount_cents=cents,
                        kind="unattributed",
                        reason=REASON_NO_AUTHORS,
                        asset_id=asset_id,
                        document_id=cand.document_id,
                    )
                )
                continue
            split = apportion_cents(weights, cents)
            for pos_str, sc in split.items():
                if sc <= 0:
                    continue
                payee = (
                    f"{cand.ip_holder_id or cand.document_id or asset_id}"
                    f":author:{pos_str}"
                )
                creator_lines.append(
                    PayeeLine(
                        payee_ref=payee,
                        amount_cents=sc,
                        kind="creator",
                        reason=split_policy_version,
                        asset_id=asset_id,
                        document_id=cand.document_id,
                        author_position=int(pos_str),
                    )
                )
            continue

        # No author split: route to ip_holder if known, else unattributed.
        if cand.ip_holder_id:
            creator_lines.append(
                PayeeLine(
                    payee_ref=cand.ip_holder_id,
                    amount_cents=cents,
                    kind="creator",
                    reason="ip_holder",
                    asset_id=asset_id,
                    document_id=cand.document_id,
                )
            )
        else:
            residual_lines.append(
                PayeeLine(
                    payee_ref=UNATTRIBUTED_RIGHTS_BUCKET,
                    amount_cents=cents,
                    kind="unattributed",
                    reason=REASON_NO_HOLDER,
                    asset_id=asset_id,
                    document_id=cand.document_id,
                )
            )

    out = sum(line.amount_cents for line in creator_lines)
    routed = sum(line.amount_cents for line in residual_lines)
    return (
        creator_lines,
        residual_lines,
        StageTrace(
            stage="holder_gates",
            input_cents=input_total,
            output_cents=out,
            routed_cents=routed,
            detail={
                "n_creator_lines": len(creator_lines),
                "n_residual_lines": len(residual_lines),
                "split_policy_version": split_policy_version,
            },
        ),
    )


# ---------------------------------------------------------------------------
# Stage 6 — Residuals → UNATTRIBUTED bucket (explicit, never silent)
# ---------------------------------------------------------------------------


def stage_residuals(
    residual_lines: Sequence[PayeeLine],
    empty_pool_cents: int = 0,
) -> tuple[list[PayeeLine], StageTrace]:
    """Collapse residual lines into the UNATTRIBUTED bucket (reason-coded).

    ``empty_pool_cents`` covers the case where the creator pool had no
    surviving weights (fully-filtered / house-only window): those cents
    route here with REASON_EMPTY_POOL rather than vanishing.
    """
    lines = list(residual_lines)
    if empty_pool_cents > 0:
        lines.append(
            PayeeLine(
                payee_ref=UNATTRIBUTED_RIGHTS_BUCKET,
                amount_cents=empty_pool_cents,
                kind="unattributed",
                reason=REASON_EMPTY_POOL,
            )
        )
    # Coalesce same-(reason) unattributed lines for a clean audit surface,
    # preserving per-reason totals (do not merge distinct reasons).
    by_reason: dict[str, int] = {}
    for line in lines:
        if line.kind != "unattributed":
            continue
        by_reason[line.reason] = by_reason.get(line.reason, 0) + line.amount_cents
    coalesced = [
        PayeeLine(
            payee_ref=UNATTRIBUTED_RIGHTS_BUCKET,
            amount_cents=cents,
            kind="unattributed",
            reason=reason,
        )
        for reason, cents in sorted(by_reason.items())
        if cents > 0
    ]
    # Preserve any non-unattributed residual lines (should be empty today).
    other = [line for line in lines if line.kind != "unattributed"]
    final = other + coalesced
    total = sum(line.amount_cents for line in final)
    return (
        final,
        StageTrace(
            stage="residuals",
            input_cents=total,
            output_cents=0,
            routed_cents=total,
            detail={"n_reasons": len(coalesced), "reasons": sorted(by_reason)},
        ),
    )


# ---------------------------------------------------------------------------
# Composed pipeline
# ---------------------------------------------------------------------------


def run_pipeline(
    window_value_cents: int,
    candidates: Sequence[AssetCandidate] = (),
    *,
    carve_outs: Sequence[CarveOutEntry] = (),
    house_seconds_cents: int = 0,
    params: PipelineParams | None = None,
) -> PipelineResult:
    """Run the full six-stage published split order.

    Parameters
    ----------
    window_value_cents:
        Server-minted window ad value (AFA-S1). Non-negative integer cents.
    candidates:
        Post-filter asset candidates with weights (stage 3 input). The
        caller applies S2 classify+caps; this pipeline does not re-filter
        seconds.
    carve_outs:
        Stage-1 licensed fractions (empty registry is the shipping default).
    house_seconds_cents:
        Cents already identified as house seconds (no eligible asset in
        frame) by the caller's per-second aggregation. These are ADDED to
        the platform/house bucket after the 70/30 cut on the *eligible*
        pool. Pass 0 when the window value is purely the eligible pool
        (tests of pure stage math).
    params:
        Versioned knobs; defaults are the published constants.

    Conservation identity (integer equality, no tolerances)::

        Σ creator payees
        + platform cut
        + carve-outs
        + unattributed
        + house_seconds
        == window_value_cents

    Note on house_seconds_cents vs the 70/30 cut
    -------------------------------------------
    The published order takes the platform cut on the post-carve pool, then
    weights the creator pool. House-seconds (no eligible asset) are a
    SEPARATE residual of the per-second engine and are not subject to a
    second cut — they already belong to the house. Callers that have already
    split window value into (eligible_pool, house_seconds) should pass
    ``window_value_cents = eligible + house`` and ``house_seconds_cents =
    house`` so the pipeline accounts for both.
    """
    params = params or PipelineParams()
    if window_value_cents < 0:
        raise ValueError("window_value_cents must be non-negative")
    if house_seconds_cents < 0:
        raise ValueError("house_seconds_cents must be non-negative")
    if house_seconds_cents > window_value_cents:
        raise ValueError("house_seconds_cents cannot exceed window_value_cents")

    # The pool the 70/30 cut applies to is (window - house_seconds). House
    # seconds are already the platform's; carving and cutting them would
    # misstate the effective rate on statements.
    pool_input = window_value_cents - house_seconds_cents

    all_lines: list[PayeeLine] = []
    traces: list[StageTrace] = []

    # 1. Carve-outs
    post_carve, carve_lines, t1 = stage_carve_outs(pool_input, carve_outs)
    all_lines.extend(carve_lines)
    traces.append(t1)
    carve_total = sum(line.amount_cents for line in carve_lines)

    # 2. Platform cut
    creator_pool, platform, plat_lines, t2 = stage_platform_cut(
        post_carve, creator_rev_share=params.creator_rev_share,
    )
    all_lines.extend(plat_lines)
    traces.append(t2)

    # 3. Filtered weights
    weights, t3 = stage_filtered_weights(candidates)
    traces.append(t3)

    # 4. Composition
    unit_cents, comp_residual, t4 = stage_composition(
        creator_pool, weights, candidates,
    )
    traces.append(t4)
    # Empty survivor weights → the whole creator pool is residual.
    empty_pool = creator_pool if not unit_cents else 0

    # 5. Holder gates
    creator_lines, gate_residuals, t5 = stage_holder_gates(
        unit_cents,
        candidates,
        split_policy_version=params.split_policy_version,
    )
    all_lines.extend(creator_lines)
    traces.append(t5)

    # 6. Residuals
    residual_in = list(comp_residual) + list(gate_residuals)
    residual_lines, t6 = stage_residuals(residual_in, empty_pool_cents=empty_pool)
    all_lines.extend(residual_lines)
    traces.append(t6)

    # House seconds (caller-identified) — explicit house line.
    if house_seconds_cents > 0:
        all_lines.append(
            PayeeLine(
                payee_ref="__platform__",
                amount_cents=house_seconds_cents,
                kind="house",
                reason=REASON_HOUSE_SECONDS,
            )
        )

    unattributed = sum(
        line.amount_cents for line in all_lines if line.kind == "unattributed"
    )
    house = sum(
        line.amount_cents for line in all_lines if line.kind in ("platform", "house")
    )

    return PipelineResult(
        window_value_cents=window_value_cents,
        creator_pool_cents=creator_pool,
        platform_cut_cents=platform,
        carve_out_cents=carve_total,
        unattributed_cents=unattributed,
        house_cents=house,
        payee_lines=tuple(all_lines),
        stage_traces=tuple(traces),
        attribution_math_version=ATTRIBUTION_MATH_VERSION,
        stage_versions=dict(params.stage_versions),
        pool_scope=params.pool_scope,
    )


def composed_version_id(params: PipelineParams | None = None) -> str:
    """Return the composed math version id for the given params.

    Today the published id is the constant ``attribution-math-v2``. The
    completeness test mutates params and asserts that a *fingerprint* of
    the params differs — see ``params_fingerprint``. Callers that need a
    params-sensitive stamp should use the fingerprint; the row stamp stays
    the stable published id so S6 can group by era.
    """
    return ATTRIBUTION_MATH_VERSION


def params_fingerprint(params: PipelineParams) -> str:
    """Stable fingerprint of every versioned knob.

    Used by the version-completeness test: mutate any stage constant →
    fingerprint must change. The published row stamp remains
    ATTRIBUTION_MATH_VERSION (era label); the fingerprint is the
    intra-version audit hash.
    """
    import hashlib
    import json

    payload = {
        "attribution_math_version": ATTRIBUTION_MATH_VERSION,
        "creator_rev_share": str(params.creator_rev_share),
        "platform_cut": str(params.platform_cut),
        "pool_scope": params.pool_scope,
        "split_policy_version": params.split_policy_version,
        "stage_versions": dict(sorted(params.stage_versions.items())),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


__all__ = [
    "ATTRIBUTION_MATH_VERSION",
    "STAGE_VERSIONS",
    "DEFAULT_POOL_SCOPE",
    "PoolScope",
    "CarveOutEntry",
    "AssetCandidate",
    "PayeeLine",
    "StageTrace",
    "PipelineResult",
    "PipelineParams",
    "stage_carve_outs",
    "stage_platform_cut",
    "stage_filtered_weights",
    "stage_composition",
    "stage_holder_gates",
    "stage_residuals",
    "run_pipeline",
    "composed_version_id",
    "params_fingerprint",
    "REASON_CARVE_OUT",
    "REASON_PLATFORM_CUT",
    "REASON_FILTERED",
    "REASON_INELIGIBLE_CONTENT",
    "REASON_T1_GATE",
    "REASON_NO_HOLDER",
    "REASON_NO_AUTHORS",
    "REASON_UNATTRIBUTED",
    "REASON_HOUSE_SECONDS",
    "REASON_EMPTY_POOL",
    "UNATTRIBUTED_RIGHTS_BUCKET",
]
