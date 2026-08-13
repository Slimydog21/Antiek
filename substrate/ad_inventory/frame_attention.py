"""Per-second frame-attention telemetry contract + weighting (SPR-05).

The "Times-Square border" economic engine. Antiek wraps every window
(Read / Research / Write / Speak) in an always-on ad border and monetizes,
PER SECOND, the attention-weighted contribution of every publicly-searchable
IP asset visible in frame. The per-second frame REPLACES "impression = once
per (session, slot)" as the economic unit; the impression/dwell telemetry
(``reader_impressions.py``) becomes one INPUT signal among several, not the
unit of account.

This module owns two things:

* **M2 — the per-second telemetry contract** (:class:`FrameAttentionSample`,
  :class:`FrameSecond`, :class:`WindowFrameBatch`): the typed wire-shape the
  SPR-07 frontend emitter must satisfy and that the backend consumes. Frozen
  dataclasses, matching the ``substrate/ad_inventory/`` convention (pydantic
  lives only in ``substrate/contracts/``).
* **M3 — the attention-weighting function** (:func:`weigh_second`): pure,
  deterministic, explainable. Given one second's in-frame samples it drops
  ineligible assets, computes a per-eligible-asset weight from
  area × prominence × focus, and normalizes the eligible weights to sum to
  EXACTLY 1.0 (decimal-safe) — or to 0 when nothing eligible is in frame
  (a house second).

The accrual + house-second persistence lives in the sibling module
``frame_attention_accrual.py`` (M4/M5); this module is pure computation.

================================================================================
M1 — DILIGENCE FINDINGS (verified against live code, file:line)
================================================================================
Every reuse below was read and confirmed in THIS tree before relying on it. I
invented no parallel mechanism for any of these.

* Eligibility — VERIFIED the single source is
  ``substrate/ad_inventory/attribution.py``:
    - ``monetization_eligible(content_class) -> bool`` at L165 (True iff
      content_class ∈ ``PUBLIC_GRAPH_CONTENT_CLASSES``, the frozenset at L82;
      NULL/unknown → deny-by-default).
    - ``eligibility_decision(content_class) -> EligibilityDecision`` at L125
      gives the field-level dispute reason (``deciding_field``,
      ``deciding_value``, ``reason``). This weighting CALLS both — it does NOT
      re-derive eligibility from any second stored truth (the module's own L69
      comment forbids a second stored truth, and the §9.0 retrieval gate derives
      from the same ``content_class``, so the earn gate cannot drift).

* Dwell / attention input — VERIFIED ``substrate/ad_inventory/
  reader_impressions.py``: ``ReaderImpression`` (frozen, L30) carries
  ``focused_dwell_ms`` / ``counted_attention`` / ``revenue_usd_cents`` at the
  per-(session, slot) granularity. CONFIRMED there is NO per-chunk / per-asset
  attention signal today — so the frame contract here INTRODUCES per-asset
  in-frame visibility features (``viewport_area_fraction``, ``prominence``,
  ``focused_dwell_ms``). Dwell feeds in as ONE weighting signal; this module
  does not re-capture dwell.

* Conservation primitive — VERIFIED ``substrate/ad_inventory/
  attribution_explain.py``: ``_largest_remainder_cents(weights, total_cents)``
  at L89 floors then hands leftover cents to the largest fractional remainders
  so the parts sum EXACTLY to ``total_cents``. The accrual module REUSES it via
  the thin public wrapper :func:`apportion_cents` below (it stays private in
  ``attribution_explain``; the wrapper imports it rather than copy-pasting the
  math).

* Escrow writer — VERIFIED ``substrate/ip_holders/__init__.py``:
  ``accrue_escrow(con, ip_holder_id, amount_usd: Decimal)`` at L159 is the ONLY
  ``SET escrow_balance_usd = …`` in the tree (asserted by
  ``tests/test_seam_single_escrow_writer.py``). The accrual module routes
  through it and is added to that test's ``_SANCTIONED_ESCROW_CALLERS`` set —
  the seam's intended path for a NEW sanctioned revenue source (its L40 comment:
  "Multiple revenue SOURCES legitimately route through that one writer … a NEW,
  unsanctioned caller still fails the guard"). I do NOT write the column myself.
  Pre-onboarded creation: ``create_pre_onboarded`` at L67.

* Single-writer lock — VERIFIED ``runtime/db_lock.py``:
  ``connect_write(db_path, *, timeout_s=300, poll_interval_s=0.25, purpose="")``
  at L255. All DB writes in the accrual module go through it.

* Audit + replay pattern — VERIFIED ``substrate/ad_inventory/
  attribution_audit.py``: ``record_attribution`` (L127), ``replay`` (L274),
  ``ATTRIBUTION_ALGORITHM_VERSION="attr-math-v1"`` (L42), ``_canonical_json``
  (sort_keys, tight separators) (L45). The accrual module MIRRORS this:
  canonical-JSON input snapshot, deterministic id, idempotent insert, replay.

* AccrualContract — VERIFIED ``substrate/contracts/accrual.py``: pydantic
  ``AccrualContract`` with ``source: Literal["publisher_impression",
  "speak_contribution"]`` (L45) and ``disbursable: Literal[False]`` (L70).
  DECISION (M4): a per-second frame-attention accrual is a THIRD source, so
  ``AccrualSource`` is extended with ``"frame_attention_second"`` (the canonical
  accrual wire-shape — the seam test asserts "both concerns emit the single
  shape"; a third source on the same shape is the consistent move, not a
  separate path). The two existing variants keep working; ``disbursable`` stays
  fixed ``False``. ``CONTRACT_SCHEMA_VERSION`` bumped 1 → 2.

DE-SCOPE confirmations (all six milestones in scope, none dropped): pricing the
second (its $-value) is SPR-10 and treated here as a given INPUT
(``ad_value_usd_cents``); the frontend emitter is SPR-07 (this module DEFINES
the contract it must satisfy and renders no UI); choosing the production
attribution algorithm is the operator's (SPR-04 ``compare_algorithms``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .attribution import eligibility_decision, monetization_eligible
from .attribution_explain import _largest_remainder_cents

# ---------------------------------------------------------------------------
# Versioning (mirror ATTRIBUTION_ALGORITHM_VERSION)
# ---------------------------------------------------------------------------

# The telemetry wire-shape version. Bump on ANY change to the contract field
# shape (a new visibility feature, a renamed field, a changed unit) so the
# SPR-07 emitter and the backend cannot silently diverge. Stamped onto every
# persisted accrual + house-second row so a dispute points at the exact shape.
#
# v1 -> v2 (AFA-S1, 2026-07-02): ``ad_value_usd_cents`` was REMOVED from the
# client-inbound wire shape. The client measures attention; it must never price
# it. The window's ad value is now MINTED SERVER-SIDE at accrual time (see
# ``interfaces/research/api/ad_routes.py::resolve_window_value_cents``). The
# server-side ``WindowFrameBatch`` dataclass below KEEPS the field — it is the
# value the accrual apportions — but it is now populated by the server, never
# echoed from the request. A v1 batch (which still carries a client value) is
# rejected 409 by the route's version gate, so no ordering window exists in
# which a client-priced batch accrues against v2 semantics.
#
# v2 -> v3 (ad-pipeline gap S1, 2026-08-12): server-minted ad value. The wire
# shape RE-ACCEPTS an optional client ``ad_value_usd_cents`` — as an IGNORED
# HINT: accepted so a legacy emitter that still sends it is not broken, NEVER
# trusted (the value the accrual apportions is minted SERVER-SIDE by joining
# the server's OWN fill/pricing record — ``ad_fill_decisions``, persisted at
# fill time by ``fill_decisions.decide_fills`` — on (owner_user_id, window_id);
# only a ``settled`` record feeds real cents, a missing/unpriced record mints
# 0 — honest house/zero, never a fabricated price), and logged as
# ``client_hint`` (``frame_telemetry_client_hints``) for auditability. v2 and
# v3 are wire-compatible (v2 is a strict subset: the hint simply absent), so
# the route's gate accepts BOTH — see
# ``SUPPORTED_FRAME_TELEMETRY_SCHEMA_VERSIONS``.
FRAME_TELEMETRY_SCHEMA_VERSION = "frame-telemetry-v3"

# Wire versions the /api/ad/frame-telemetry gate ACCEPTS. v2 is retained for
# backward compatibility (see the v2 -> v3 note above): a v2 emitter remains
# valid and simply carries no hint. v1 — the client-priced shape — stays
# rejected. The ``telemetry_version`` stamped on persisted rows is the version
# the EMITTER declared (both accepted shapes accrue under identical
# server-minted semantics).
SUPPORTED_FRAME_TELEMETRY_SCHEMA_VERSIONS = frozenset({
    "frame-telemetry-v2",
    FRAME_TELEMETRY_SCHEMA_VERSION,
})

# The weighting-PIPELINE version. Bump WHENEVER anything that changes a payout
# split moves: the math in :func:`weigh_second` (a new feature term, a different
# blend, a different tie-break) OR the aggregation that decides WHICH seconds
# contribute (:func:`frame_attention_accrual.aggregate_window`'s anti-gaming
# filter). Kept narrow and distinct from FRAME_TELEMETRY_SCHEMA_VERSION so a
# payout dispute can isolate "the contract changed" from "the split changed".
# The golden test (test_frame_attention_weighting::test_golden_weights_pin_the_
# blend_math) pins the exact normalized split and trips if the math moves.
#
# v1 -> v2 (AFA-S2 M5): aggregate_window now runs the frame IVT filter
# (substrate.anti_gaming.frame_ivt.classify_batch) before apportioning — invalid
# seconds are excluded from BOTH numerator and denominator, a BLOCK window and a
# fully-filtered window route to house. weigh_second's blend math is UNCHANGED
# (the golden weight literals are identical); the version bump marks the filtered
# era so a dispute can tell a pre-filter accrual from a post-filter one.
#
# v2 -> v3 (AFA-S2 W2-S2): the pre-accrual filter now also HOLDS REVIEW windows
# (whole value to house under "antigaming_review_hold" — never allocated to a
# contributor while the operator queue reviews it), and the writer applies the
# per-(user, asset, day) dwell saturation cap, rerouting clamped cents to house.
# weigh_second's blend math is STILL unchanged (the golden weight literals are
# identical); the bump marks the hold+cap era so a payout dispute can tell a
# pre-hold accrual from a post-hold one.
FRAME_WEIGHTING_VERSION = "frame-weight-v3"


# ---------------------------------------------------------------------------
# M2 — the per-second frame-attention telemetry contract
# ---------------------------------------------------------------------------
#
# BATCHING / FLUSH RULE (binding — read before SPR-07 implements the emitter):
#
#   Telemetry is NOT one DB row per second per user. The emitter BUFFERS samples
#   client-side for the lifetime of a window and FLUSHES a single compact
#   ``WindowFrameBatch`` per window (on window close, or on a periodic flush
#   ceiling, whichever comes first). The backend AGGREGATES the batch down to
#   per-(asset) accrual BEFORE any write (see ``frame_attention_accrual.py``).
#
#   Write-amplification ceiling: ONE accrual row per (window, eligible asset)
#   plus AT MOST ONE house-second tally row per window — never O(seconds) and
#   never O(seconds × assets) rows. For a 600-second window showing 5 eligible
#   assets that is ≤ 6 rows, not 3,000. This is the design constraint that keeps
#   the single DuckDB writer from being crushed (rigor #4: aggregation is
#   designed BEFORE the writer). The per-second granularity survives in the
#   summed weights stamped on each row, not in the row count.

# Lens vocabulary — which window the frame belongs to. The four product
# workflows. Kept as a str-tuple (not an enum) to match the lightweight
# ad_inventory dataclass convention; validated at construction.
VALID_LENSES: frozenset[str] = frozenset({"read", "research", "write", "speak"})


@dataclass(frozen=True)
class FrameAttentionSample:
    """One IP asset's in-frame VISIBILITY for one second.

    Units / ranges (documented per rigor #5 — every feature's meaning is
    auditable):

    * ``asset_id`` — the document/asset id (maps to ``documents.document_id``,
      which carries ``ip_holder_id`` and ``content_class``). The trace anchor.
    * ``chunk_id`` — the specific chunk visible in frame, or ``None`` when the
      asset is in frame with no resolved chunk (a cover/title card). An asset
      with no chunk still earns (it is the ASSET that is monetized); the chunk
      is trace detail, not an eligibility input.
    * ``content_class`` — the asset's classification AS REPORTED BY THE BACKEND
      lookup at aggregation time, fed to ``monetization_eligible``. The client
      MAY echo a hint but the backend NEVER trusts it; the authoritative value
      is resolved server-side. Carried here so the pure weighting function is
      self-contained and testable.
    * ``viewport_area_fraction`` — fraction of the window viewport the asset
      occupied this second, in [0.0, 1.0]. 1.0 = filled the whole viewport.
    * ``prominence`` — a position/salience signal in [0.0, 1.0]. 1.0 = center/
      foreground (eye-line); 0.0 = peripheral. The SPR-07 emitter derives it
      from on-screen geometry (center-weighting) the way ``reader_slots``
      models TOP/BOTTOM/LEFT/RIGHT position categoricals — but as a continuous
      prominence rather than a categorical, because the border wraps the frame.
    * ``focused_dwell_ms`` — milliseconds of FOCUSED, foregrounded dwell this
      asset accrued this second, in [0, 1000]. Mirrors
      ``reader_impressions.focused_dwell_ms`` semantics: dwell while the tab is
      backgrounded/idle does NOT count and the client must not report it. ≥ 0.
    """

    asset_id: str
    viewport_area_fraction: float
    prominence: float
    focused_dwell_ms: int
    content_class: str | None = None
    chunk_id: str | None = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.viewport_area_fraction <= 1.0):
            raise ValueError(
                f"viewport_area_fraction must be in [0,1], got "
                f"{self.viewport_area_fraction}"
            )
        if not (0.0 <= self.prominence <= 1.0):
            raise ValueError(f"prominence must be in [0,1], got {self.prominence}")
        if self.focused_dwell_ms < 0 or self.focused_dwell_ms > 1000:
            raise ValueError(
                f"focused_dwell_ms must be in [0,1000] (one second), got "
                f"{self.focused_dwell_ms}"
            )


@dataclass(frozen=True)
class FrameSecond:
    """One second of one window: the active lens + the in-frame assets.

    ``second_index`` is the 0-based second offset within the window (second 0
    is the first second the window was on screen). It is the per-second key the
    accrual aggregation sums over; it never becomes a DB row on its own."""

    second_index: int
    lens: str
    samples: tuple[FrameAttentionSample, ...]

    def __post_init__(self) -> None:
        if self.second_index < 0:
            raise ValueError(f"second_index must be >= 0, got {self.second_index}")
        if self.lens not in VALID_LENSES:
            raise ValueError(
                f"lens must be in {sorted(VALID_LENSES)}, got {self.lens!r}"
            )


@dataclass(frozen=True)
class WindowFrameBatch:
    """The compact per-window batch the SPR-07 emitter flushes (the unit the
    backend consumes — NOT one row per second).

    ``ad_value_usd_cents`` is the window's TOTAL ad value for the seconds in
    this batch. As of frame-telemetry-v3 (ad-pipeline gap S1) it is MINTED
    SERVER-SIDE by joining the server's own fill/pricing record
    (``ad_routes.resolve_window_value_cents`` → ``ad_fill_decisions``; a
    missing or unsettled record mints 0 — honest house/zero, never a
    fabricated price). The client MAY send a value hint on the wire but it is
    NEVER trusted: it is accepted, logged as ``client_hint``, and ignored. The
    value is apportioned per-second-equally across ``len(seconds)`` seconds
    before per-asset weighting, so the window reconciles exactly (M6).

    ``schema_version`` is stamped so a batch flushed by an old emitter is
    identifiable. ``window_id`` is the trace anchor for every accrual derived
    from this batch."""

    window_id: str
    seconds: tuple[FrameSecond, ...]
    ad_value_usd_cents: int
    schema_version: str = FRAME_TELEMETRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.ad_value_usd_cents < 0:
            raise ValueError(
                f"ad_value_usd_cents must be >= 0, got {self.ad_value_usd_cents}"
            )


# ---------------------------------------------------------------------------
# M3 — the attention-weighting function (pure, deterministic, explainable)
# ---------------------------------------------------------------------------
#
# WEIGHTING BLEND (rigor #2 — steelman the alternatives, defend the blend):
#
#   raw_weight(asset) = area_fraction × (1 + prominence) × (1 + dwell_fraction)
#
#   where dwell_fraction = focused_dwell_ms / 1000 ∈ [0,1].
#
# Why a multiplicative blend of three factors, and why these factors:
#
#   * PURE AREA (raw_weight = area) advantages large visual assets — a full-page
#     image earns the second even if the eye never rested on it and it sat in a
#     peripheral panel. It is the most gameable (inflate the rendered size) and
#     least correlated with attention. Rejected as the sole signal.
#   * PURE DWELL (raw_weight = dwell) advantages whatever the focus signal lands
#     on regardless of how much of the frame it occupies — a one-pixel tracked
#     element could capture the whole second. It is the closest proxy for
#     genuine attention but the noisiest per-second (focus jitters sub-second)
#     and ignores that a border monetizes VISIBLE area, not just gaze. Rejected
#     as the sole signal.
#   * The BLEND multiplies area (what the border actually shows) by a
#     prominence amplifier (where on screen — center beats periphery) and a
#     dwell amplifier (did focused attention land there). Multiplicative, not
#     additive, so an asset with zero visible area earns zero no matter how
#     prominent or dwelt-upon (you cannot monetize attention to something not on
#     screen) — area is the necessary gate, prominence and dwell are amplifiers.
#     The (1 + x) form keeps an asset with prominence/dwell = 0 from collapsing
#     to zero purely because a secondary signal was absent: a visible asset
#     always earns SOMETHING off its area. This is the production-shape default;
#     the operator can re-tune via FRAME_WEIGHTING_VERSION (the choice of the
#     PRODUCTION algorithm is explicitly SPR-04/operator territory, not pinned
#     here — this is a defensible default, version-stamped so a dispute knows
#     exactly which math ran).
#
#   Content-type note: the blend advantages a large, center-screen, dwelt-upon
#   asset (e.g. a full reading pane in Read) over a small peripheral citation
#   chip (e.g. a Research sidebar source). That is intended: the border pays for
#   visible, attended frame real estate. A future per-lens re-weighting (Speak
#   has no large visual asset) is a version bump, not a re-architecture.
#
# DECIMAL-SAFETY + DETERMINISM: weights are computed in float for the raw blend,
# then normalized to Decimal so the eligible weights sum to EXACTLY 1 (a float
# sum can land at 0.9999999999998). Assets are processed in a STABLE sorted
# order (by asset_id) so floor/remainder tie-breaks never depend on dict
# iteration order — same input → byte-identical output.

# Decimal quantum for normalized weights: 1e-9 (nano-weight). Fine enough that
# the cents apportionment downstream is never starved, coarse enough to keep the
# largest-remainder pass cheap. The normalized weights sum to EXACTLY 1 because
# we apportion this quantum's worth of "weight units" by largest remainder, the
# same conservation trick the money layer uses.
_WEIGHT_UNITS = 1_000_000_000  # 1e9 weight-units == 1.0


@dataclass(frozen=True)
class AssetWeight:
    """One eligible asset's normalized weight for one second, with the feature
    contributions that produced it (the explain hook's payload — answers
    'why did this asset get this weight this second')."""

    asset_id: str
    chunk_id: str | None
    weight: Decimal                 # normalized share of the second ∈ [0,1]
    raw_weight: float               # pre-normalization blend value
    viewport_area_fraction: float
    prominence: float
    focused_dwell_ms: int


@dataclass(frozen=True)
class SecondWeighting:
    """The full weighting of one second: the eligible assets' normalized
    weights (sum to EXACTLY 1, or empty when house), the ineligible assets that
    were EXCLUDED from the normalization base (with the dispute reason), and the
    house flag.

    ``is_house_second`` is True iff no eligible asset was in frame — the second
    the platform pockets (M5). The decision is derivable: ``eligible_weights``
    is empty AND ``ineligible`` lists exactly why each excluded asset was
    excluded."""

    second_index: int
    lens: str
    eligible_weights: tuple[AssetWeight, ...]
    ineligible: tuple[tuple[str, str], ...]  # (asset_id, eligibility reason)
    is_house_second: bool
    weighting_version: str = FRAME_WEIGHTING_VERSION


def _raw_weight(sample: FrameAttentionSample) -> float:
    """The pre-normalization attention blend for one in-frame asset. See the
    module-level WEIGHTING BLEND comment for the rationale of every term."""
    area = sample.viewport_area_fraction
    dwell_fraction = sample.focused_dwell_ms / 1000.0
    return area * (1.0 + sample.prominence) * (1.0 + dwell_fraction)


def weigh_second(second: FrameSecond) -> SecondWeighting:
    """Weight one second's in-frame samples (pure, deterministic, explainable).

    (a) Drops ineligible assets via :func:`monetization_eligible` and EXCLUDES
        them from the normalization base (an ineligible asset is removed, never
        zero-weighted-but-present — mirrors ``attribution.eligible_shares``).
    (b) Computes each eligible asset's raw weight from area × prominence ×
        focus (the blend above).
    (c) Normalizes so the eligible weights sum to EXACTLY 1.0 (Decimal, via the
        same largest-remainder conservation used at the money layer) — or to
        the empty set when zero eligible (a HOUSE SECOND).

    Same input → byte-identical output: assets are sorted by ``asset_id`` for a
    stable tie-break, and the normalization is integer-weight-unit
    largest-remainder, so there is no float-ordering drift."""
    eligible: list[FrameAttentionSample] = []
    ineligible: list[tuple[str, str]] = []
    # Stable order: sort by asset_id so tie-breaks and remainder distribution
    # are deterministic regardless of the emitter's sample order.
    for s in sorted(second.samples, key=lambda x: x.asset_id):
        if monetization_eligible(s.content_class):
            eligible.append(s)
        else:
            ineligible.append((s.asset_id, eligibility_decision(s.content_class).reason))

    if not eligible:
        # House second: nothing eligible in frame. Eligible weights empty; the
        # ineligible list (possibly empty for an empty window) is the audit
        # trail for WHY it is a house second.
        return SecondWeighting(
            second_index=second.second_index,
            lens=second.lens,
            eligible_weights=(),
            ineligible=tuple(ineligible),
            is_house_second=True,
        )

    raw = {s.asset_id: _raw_weight(s) for s in eligible}
    total_raw = sum(raw.values())

    if total_raw <= 0.0:
        # Every eligible asset had zero visible area (area is the gate). There
        # is eligible content in frame but it earned zero attention this second;
        # fall back to an EQUAL split across the eligible assets so the second
        # is still conserved to 1 (the money is real; the attention signal was
        # flat). This is a defensible, documented tie-break — not a silent drop.
        equal = {aid: 1.0 for aid in raw}
        units = _largest_remainder_cents(equal, _WEIGHT_UNITS)
    else:
        units = _largest_remainder_cents(raw, _WEIGHT_UNITS)

    weights: list[AssetWeight] = []
    by_id = {s.asset_id: s for s in eligible}
    for aid in sorted(units.keys()):
        s = by_id[aid]
        weights.append(AssetWeight(
            asset_id=aid,
            chunk_id=s.chunk_id,
            weight=Decimal(units[aid]) / Decimal(_WEIGHT_UNITS),
            raw_weight=raw[aid],
            viewport_area_fraction=s.viewport_area_fraction,
            prominence=s.prominence,
            focused_dwell_ms=s.focused_dwell_ms,
        ))

    return SecondWeighting(
        second_index=second.second_index,
        lens=second.lens,
        eligible_weights=tuple(weights),
        ineligible=tuple(ineligible),
        is_house_second=False,
    )


def explain_second(weighting: SecondWeighting) -> dict[str, Any]:
    """The explain hook: a JSON-friendly per-asset feature-contribution view of
    one weighted second (answers 'why did each asset get its weight'). Read-only.
    """
    return {
        "second_index": weighting.second_index,
        "lens": weighting.lens,
        "weighting_version": weighting.weighting_version,
        "is_house_second": weighting.is_house_second,
        "eligible": [
            {
                "asset_id": w.asset_id,
                "chunk_id": w.chunk_id,
                "weight": str(w.weight),
                "raw_weight": w.raw_weight,
                "features": {
                    "viewport_area_fraction": w.viewport_area_fraction,
                    "prominence": w.prominence,
                    "focused_dwell_ms": w.focused_dwell_ms,
                },
            }
            for w in weighting.eligible_weights
        ],
        "ineligible": [
            {"asset_id": aid, "reason": reason}
            for aid, reason in weighting.ineligible
        ],
    }


def apportion_cents(weights: dict[str, float], total_cents: int) -> dict[str, int]:
    """Thin public wrapper over ``attribution_explain._largest_remainder_cents``
    so the accrual module conserves cents EXACTLY without re-implementing
    rounding (rigor #4 — reuse the one rounding primitive). Kept here rather
    than copy-pasting the math; the private function stays private in
    ``attribution_explain``."""
    return _largest_remainder_cents(weights, total_cents)


__all__ = [
    "FRAME_TELEMETRY_SCHEMA_VERSION",
    "SUPPORTED_FRAME_TELEMETRY_SCHEMA_VERSIONS",
    "FRAME_WEIGHTING_VERSION",
    "VALID_LENSES",
    "FrameAttentionSample",
    "FrameSecond",
    "WindowFrameBatch",
    "AssetWeight",
    "SecondWeighting",
    "weigh_second",
    "explain_second",
    "apportion_cents",
]
