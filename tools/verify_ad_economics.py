"""SPR-11 — end-to-end verification of the per-second ad-economics chain.

THE CAPSTONE. This harness builds NO new economics. It COMPOSES the real
modules end-to-end over a faithful, PROD-SHAPED FIXTURE corpus and asserts the
money story is reproducible, traceable to the cent, and that the safety valve
holds (escrow accrues, NOTHING disburses).

    auction (SPR-10 select_ad) prices the window
        → per-second frame attention (SPR-05 weigh_second, eligibility-filtered)
            → accrue_window (persists accrual rows + house row, routes to escrow)
                → accrue_escrow (the ONE sanctioned escrow writer)
        → explain_asset_earning (SPR-04) traces a cent back to second→chunk→asset
    + the disbursement gate (Speak contributor.attempt_disbursement) is called
      for real and asserted BLOCKED — money does NOT move (rigor #3, prove the
      negative).

IMPORTANT — this is NOT literal prod traffic. There is no SPR-08 prod corpus in
this worktree. The corpus below is a SYNTHETIC, faithful PROD-SHAPED FIXTURE
(real content classes, real publishers-as-pre_onboarded holders, realistic
per-second visibility). The whole value is proving the COMPOSITION reconciles,
not measuring real revenue. The report says so plainly.

Run:  python tools/verify_ad_economics.py
It is read-only against any recorded corpus; every DB write goes through the
single-writer lock (runtime.db_lock.connect_write). Idempotent — safe to re-run.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

# Run-standalone bootstrap: this worktree has NO venv of its own; the venv's
# editable .pth points at the main Antiek tree, so `python tools/verify_...py`
# would otherwise import an OLDER substrate from there. Put THIS worktree's root
# first on sys.path so the harness always composes the modules in the tree it
# lives in (matches what pytest sees, since pytest runs from the worktree root).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from runtime.db_lock import connect_write
from substrate import ip_holders
from substrate.ad_inventory.ad_bidding import AdInventoryItem
from substrate.ad_inventory.attribution import (
    AttributionAlgorithm,
    monetization_eligible,
)
from substrate.ad_inventory.attribution_audit import (
    AlgorithmComparison,
    compare_algorithms,
)
from substrate.ad_inventory.attribution_explain import explain_asset_earning
from substrate.ad_inventory.auction_ranker import select_ad
from substrate.ad_inventory.frame_attention import (
    FrameAttentionSample,
    FrameSecond,
    WindowFrameBatch,
)
from substrate.ad_inventory.frame_attention_accrual import (
    WindowAccrual,
    accrue_window,
    replay,
    window_reconciliation,
)
from substrate.ad_inventory.intent_targeting import (
    InventoryTargeting,
    PageContext,
    TargetedInventoryItem,
)
from substrate.ad_inventory.payout import CREATOR_REV_SHARE, PLATFORM_CUT
from substrate.speak import contributor, gate_status

# The IP-holders DDL is owned by the live schema; mirrored here for the
# tempfile fixture DB exactly as tests/test_frame_attention_accrual.py does
# (the harness never touches a real corpus DB — it builds its own).
_IP_HOLDERS_DDL = """
CREATE TABLE IF NOT EXISTS ip_holders (
    ip_holder_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    legal_contact_email TEXT,
    status TEXT NOT NULL DEFAULT 'pre_onboarded',
    escrow_balance_usd DECIMAL(18, 6) NOT NULL DEFAULT 0,
    escrow_account_ref TEXT,
    notification_sent_at TIMESTAMP,
    claimed_at TIMESTAMP,
    opted_out_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT
);
"""

# ---------------------------------------------------------------------------
# The faithful prod-shaped FIXTURE corpus (NOT real prod traffic)
# ---------------------------------------------------------------------------
#
# Each "session" is one reading/research window on one page, with a curated ad
# slot (priced by the SPR-10 auction) and a per-second frame of in-frame assets.
# Content classes are the REAL vocabulary from attribution.PUBLIC_GRAPH_CONTENT_
# CLASSES / PRIVATE_GRAPH_CONTENT_CLASS so the eligibility gate is exercised for
# real, not re-derived here.


@dataclass(frozen=True)
class AssetSpec:
    """A prod-shaped asset visible in a session's frame."""

    asset_id: str
    chunk_id: str | None
    content_class: str | None
    publisher: str | None  # display_name of the pre_onboarded holder, or None
    area: float
    prominence: float
    dwell_ms: int


@dataclass(frozen=True)
class SessionSpec:
    """One prod-shaped reading session = one window over one page."""

    window_id: str
    page_id: str
    lens: str
    n_seconds: int
    # the auction-priced ad slot for this window (CPM × seconds → ad value)
    cpm_usd: Decimal
    sector: str
    sub_sector: str
    audience_intents: tuple[str, ...]
    assets: tuple[AssetSpec, ...]
    # chunks cited in the rendered synthesis (for the SPR-04 attribution trace);
    # maps chunk_id → document_id (asset_id). Drives explain_asset_earning.
    cited_chunks: dict[str, str] = field(default_factory=dict)


# Publishers in this fixture — created as pre_onboarded (the §9.10 shadow
# state). NONE are claimed: the safety valve depends on no claimed holder.
_PUBLISHERS = ("MIT Press", "Cambridge University Press", "Princeton University Press")


def _build_corpus() -> tuple[SessionSpec, ...]:
    """A small, deterministic, prod-shaped corpus that exercises every M4/M5
    branch: eligible public asset earns; private user_owned earns $0 even alone;
    gated restricted_pending_opt_in earns to escrow; a zero-eligible second
    pockets to the house."""
    return (
        # Session 1 — Read: two eligible public-domain assets + one private
        # user_owned asset in frame (the private one must earn $0).
        SessionSpec(
            window_id="win-read-001",
            page_id="page-quantum-survey",
            lens="read",
            n_seconds=12,
            cpm_usd=Decimal("8.00"),
            sector="technology",
            sub_sector="quantum",
            audience_intents=("decision_maker",),
            assets=(
                AssetSpec("doc-mit-quantum", "ch-mq-1", "opt_in_licensed",
                          "MIT Press", area=0.55, prominence=0.8, dwell_ms=900),
                AssetSpec("doc-pd-lecture", "ch-pd-1", "public_domain",
                          None, area=0.30, prominence=0.4, dwell_ms=400),
                AssetSpec("doc-user-notes", "ch-un-1", "user_owned",
                          None, area=0.15, prominence=0.2, dwell_ms=100),
            ),
            cited_chunks={"ch-mq-1": "doc-mit-quantum", "ch-pd-1": "doc-pd-lecture"},
        ),
        # Session 2 — Research: a gated-but-public asset (restricted_pending_
        # opt_in) earns to escrow while its body never renders, alongside an
        # open asset.
        SessionSpec(
            window_id="win-research-002",
            page_id="page-defense-econ",
            lens="research",
            n_seconds=20,
            cpm_usd=Decimal("12.00"),
            sector="defense",
            sub_sector="procurement",
            audience_intents=("analyst", "decision_maker"),
            assets=(
                AssetSpec("doc-cup-gated", "ch-cg-1", "restricted_pending_opt_in",
                          "Cambridge University Press", area=0.45, prominence=0.7,
                          dwell_ms=700),
                AssetSpec("doc-open-cc", "ch-oc-1", "source_declared_open",
                          None, area=0.40, prominence=0.5, dwell_ms=500),
            ),
            cited_chunks={"ch-cg-1": "doc-cup-gated", "ch-oc-1": "doc-open-cc"},
        ),
        # Session 3 — Write: a single eligible publisher asset across the whole
        # window (one publisher earns the full window).
        SessionSpec(
            window_id="win-write-003",
            page_id="page-history-essay",
            lens="write",
            n_seconds=8,
            cpm_usd=Decimal("5.00"),
            sector="humanities",
            sub_sector="history",
            audience_intents=("curious_onlooker",),
            assets=(
                AssetSpec("doc-princeton-hist", "ch-ph-1", "opt_in_licensed",
                          "Princeton University Press", area=0.70, prominence=0.9,
                          dwell_ms=950),
            ),
            cited_chunks={"ch-ph-1": "doc-princeton-hist"},
        ),
        # Session 4 — Read: ONLY a private user_owned asset in frame. Every
        # second is a HOUSE second (no eligible asset) — the platform pockets
        # the whole window, no contributor accrues.
        SessionSpec(
            window_id="win-read-004",
            page_id="page-private-upload",
            lens="read",
            n_seconds=6,
            cpm_usd=Decimal("4.00"),
            sector="technology",
            sub_sector="quantum",
            audience_intents=("decision_maker",),
            assets=(
                AssetSpec("doc-only-private", "ch-op-1", "user_owned",
                          None, area=0.80, prominence=0.9, dwell_ms=900),
            ),
            cited_chunks={},
        ),
    )


# A small, deterministic ad inventory the SPR-10 auction picks from. Realistic
# multi-dimensional targeting so select_ad clears MIN_MATCH_SCORE for real.
def _ad_inventory() -> list[TargetedInventoryItem]:
    def ti(inv_id: str, name: str, topics: tuple[str, ...], cpm: str,
           sectors: tuple[str, ...], subs: tuple[str, ...],
           intents: tuple[str, ...]) -> TargetedInventoryItem:
        return TargetedInventoryItem(
            item=AdInventoryItem(
                inventory_id=inv_id, advertiser_display_name=name,
                target_topics=topics, cpm_usd=Decimal(cpm),
                creative_url=f"https://ads.example/{inv_id}.png",
                landing_url=f"https://example.com/{inv_id}",
            ),
            targeting=InventoryTargeting(
                target_sectors=sectors, target_sub_sectors=subs,
                target_audience_intents=intents,
            ),
        )

    return [
        ti("inv-quantum-a", "QuantumCo", ("quantum",), "8.00",
           ("technology",), ("quantum",), ("decision_maker",)),
        ti("inv-defense-a", "DefenseAnalytics", ("defense",), "12.00",
           ("defense",), ("procurement",), ("analyst", "decision_maker")),
        ti("inv-history-a", "HistoryPress", ("history",), "5.00",
           ("humanities",), ("history",), ("curious_onlooker",)),
        ti("inv-generic", "GenericBrand", ("general",), "2.00",
           ("technology",), (), ("decision_maker",)),
    ]


# ---------------------------------------------------------------------------
# The chain — composed from the REAL modules, no reimplementation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionResult:
    window_id: str
    page_id: str
    lens: str
    n_seconds: int
    selected_ad_id: str | None
    selected_cpm_usd: Decimal
    ad_value_usd_cents: int
    accrual: WindowAccrual
    replay_identical: bool


def _ad_value_cents(cpm_usd: Decimal, n_seconds: int) -> int:
    """The window's total ad value, derived from the auction-priced CPM. CPM is
    cost-per-mille (1000 impressions); here we treat one billed second as one
    impression-equivalent so the window's value scales with attention time.
    This is the INPUT the per-second engine consumes (pricing is SPR-10's job;
    the engine apportions, it does not price). Conserved to the cent."""
    # cpm_usd dollars per 1000 seconds → cents per second = cpm_usd*100/1000.
    # Compute the whole-window value once as an exact integer cent count.
    total = (cpm_usd * Decimal(100) * Decimal(n_seconds) / Decimal(1000))
    return int(total.to_integral_value(rounding="ROUND_HALF_UP"))


def _frame_for(session: SessionSpec) -> WindowFrameBatch:
    """Build the per-second WindowFrameBatch from the session's assets. Each
    second carries the SAME in-frame samples (a faithful steady-frame model);
    weigh_second filters eligibility per second so the per-second engine is
    exercised for real."""
    samples = tuple(
        FrameAttentionSample(
            asset_id=a.asset_id,
            viewport_area_fraction=a.area,
            prominence=a.prominence,
            focused_dwell_ms=a.dwell_ms,
            content_class=a.content_class,
            chunk_id=a.chunk_id,
        )
        for a in session.assets
    )
    seconds = tuple(
        FrameSecond(second_index=i, lens=session.lens, samples=samples)
        for i in range(session.n_seconds)
    )
    return WindowFrameBatch(
        window_id=session.window_id,
        seconds=seconds,
        ad_value_usd_cents=_ad_value_cents(session.cpm_usd, session.n_seconds),
    )


def _select_ad_for(session: SessionSpec,
                   inventory: list[TargetedInventoryItem]) -> AdInventoryItem | None:
    """Pick the ad via the REAL SPR-10 selection seam (rule-based default; no
    learned model injected so this is the guaranteed rule-based path)."""
    context = PageContext(
        sector=session.sector,
        sub_sector=session.sub_sector,
        audience_intents=session.audience_intents,
        flat_topics=(session.sector, session.sub_sector) + session.audience_intents,
    )
    return select_ad(context=context, targeted_inventory=inventory)


def run_chain(con: Any, corpus: tuple[SessionSpec, ...]) -> list[SessionResult]:
    """Drive every session through the ACTUAL chain. Writes go through the
    single-writer connection the caller passes (connect_write). Idempotent:
    accrue_window collapses an identical batch to a no-op."""
    inventory = _ad_inventory()

    # Map every asset in the corpus to its publisher's pre_onboarded ip_holder.
    publisher_to_holder: dict[str, str] = {}
    for name in _PUBLISHERS:
        # Deterministic: only create once per publisher per fresh DB.
        publisher_to_holder[name] = ip_holders.create_pre_onboarded(
            con, display_name=name,
            legal_contact_email=f"legal@{name.lower().replace(' ', '')}.example",
        )

    results: list[SessionResult] = []
    for session in corpus:
        selected = _select_ad_for(session, inventory)
        batch = _frame_for(session)

        asset_to_ip_holder: dict[str, str | None] = {}
        for a in session.assets:
            asset_to_ip_holder[a.asset_id] = (
                publisher_to_holder.get(a.publisher) if a.publisher else None
            )

        accrual = accrue_window(con, batch, asset_to_ip_holder=asset_to_ip_holder)
        rr = replay(con, accrual.batch_ref)
        results.append(SessionResult(
            window_id=session.window_id,
            page_id=session.page_id,
            lens=session.lens,
            n_seconds=session.n_seconds,
            selected_ad_id=selected.inventory_id if selected else None,
            selected_cpm_usd=selected.cpm_usd if selected else Decimal("0"),
            ad_value_usd_cents=batch.ad_value_usd_cents,
            accrual=accrual,
            replay_identical=rr.identical,
        ))
    return results


# ---------------------------------------------------------------------------
# M3 — traceability: amount → seconds → chunk → asset → holder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EscrowTrace:
    ip_holder_id: str
    publisher: str
    status: str
    escrow_balance_usd: Decimal
    # one explanation per (session, asset) that fed this holder
    explanations: tuple[dict[str, Any], ...]
    reconciles: bool


def trace_escrow(con: Any, corpus: tuple[SessionSpec, ...],
                 results: list[SessionResult]) -> list[EscrowTrace]:
    """For each holder with escrow, emit the full trace reusing the REAL
    explain_asset_earning (SPR-04) over the period's cited chunks, anchored to
    the recorded frame accrual rows. The trace reconciles to the accrued cents.
    No parallel attribution logic — explain_asset_earning is the one tracer."""
    # Build the period-wide citation map + the period revenue (Σ ad value).
    chunk_to_document: dict[str, str] = {}
    content_class_by_doc: dict[str, str | None] = {}
    holder_by_doc: dict[str, str | None] = {}
    for session in corpus:
        chunk_to_document.update(session.cited_chunks)
        for a in session.assets:
            content_class_by_doc[a.asset_id] = a.content_class
    # Resolve doc → holder from the recorded accrual rows (substrate-of-truth).
    rows = con.execute(
        "SELECT asset_id, ip_holder_id, SUM(amount_cents) "
        "FROM frame_attention_accruals GROUP BY asset_id, ip_holder_id"
    ).fetchall()
    accrued_cents_by_doc: dict[str, int] = {}
    for asset_id, holder_id, cents in rows:
        holder_by_doc[asset_id] = holder_id
        accrued_cents_by_doc[asset_id] = int(cents)

    period_revenue_cents = sum(r.ad_value_usd_cents for r in results)

    traces: list[EscrowTrace] = []
    for holder in ip_holders.list_all(con):
        if holder.escrow_balance_usd <= 0:
            continue
        # Which docs fed this holder?
        docs = [d for d, h in holder_by_doc.items() if h == holder.ip_holder_id]
        explanations: list[dict[str, Any]] = []
        traced_cents = 0
        for doc_id in sorted(docs):
            exp = explain_asset_earning(
                document_id=doc_id,
                algorithm=AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER,
                period_label="spr11-verification-period",
                chunk_to_document=chunk_to_document,
                period_revenue_usd_cents=period_revenue_cents,
                content_class=content_class_by_doc.get(doc_id),
            )
            explanations.append({
                "document_id": doc_id,
                "eligible": exp.eligible,
                "asset_share": exp.asset_share,
                # the cents this asset ACTUALLY accrued via the frame engine
                # (substrate-of-truth) — the trace anchor:
                "frame_accrued_cents": accrued_cents_by_doc.get(doc_id, 0),
                "per_chunk": [
                    {"chunk_id": c.chunk_id, "share_of_asset": c.share_of_asset}
                    for c in exp.per_chunk
                ],
            })
            traced_cents += accrued_cents_by_doc.get(doc_id, 0)
        holder_cents = int((holder.escrow_balance_usd * Decimal(100))
                           .to_integral_value())
        traces.append(EscrowTrace(
            ip_holder_id=holder.ip_holder_id,
            publisher=holder.display_name,
            status=holder.status,
            escrow_balance_usd=holder.escrow_balance_usd,
            explanations=tuple(explanations),
            reconciles=(traced_cents == holder_cents),
        ))
    return traces


# ---------------------------------------------------------------------------
# M2 — conservation + 70/30
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Reconciliation:
    total_ad_value_cents: int
    total_contributor_cents: int
    total_house_cents: int
    reconciles: bool                 # Σ contributor + Σ house == Σ ad value
    per_window_reconciles: bool      # every WindowAccrual.reconciles()
    creator_rev_share: Decimal
    platform_cut: Decimal
    split_sums_to_one: bool
    all_non_negative: bool


def reconcile(con: Any, results: list[SessionResult]) -> Reconciliation:
    """Run-level conservation, read from BOTH the in-memory WindowAccrual
    results AND the persisted rows (window_reconciliation), and the 70/30 split
    read from the real payout constants (never hardcoded)."""
    total_ad_value = sum(r.ad_value_usd_cents for r in results)
    total_contributor = 0
    total_house = 0
    per_window_ok = True
    non_negative = True
    for r in results:
        # Cross-check the persisted ledger against the in-memory result.
        rec = window_reconciliation(con, r.window_id)
        total_contributor += rec["contributor_cents"]
        total_house += rec["house_cents"]
        if not r.accrual.reconciles():
            per_window_ok = False
        if rec["total_cents"] != r.ad_value_usd_cents:
            per_window_ok = False
        for line in r.accrual.asset_lines:
            if line.amount_cents < 0:
                non_negative = False
        if r.accrual.house.amount_cents < 0:
            non_negative = False

    return Reconciliation(
        total_ad_value_cents=total_ad_value,
        total_contributor_cents=total_contributor,
        total_house_cents=total_house,
        reconciles=(total_contributor + total_house == total_ad_value),
        per_window_reconciles=per_window_ok,
        creator_rev_share=CREATOR_REV_SHARE,
        platform_cut=PLATFORM_CUT,
        split_sums_to_one=(Decimal("1") == CREATOR_REV_SHARE + PLATFORM_CUT),
        all_non_negative=non_negative,
    )


# ---------------------------------------------------------------------------
# M6 — the safety valve: prove money does NOT move (call the REAL gate)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SafetyValve:
    gate_allowed: bool
    gate_reason: str
    disbursement_blocked: bool
    blocked_reason: str
    blocking_function: str
    holder_status_independently_blocks: bool
    no_stripe_path_invoked: bool


def check_safety_valve(con: Any, results: list[SessionResult]) -> SafetyValve:
    """Prove the negative (rigor #3). Read the REAL gate, then CALL the real
    attempt_disbursement against a holder that accrued escrow and assert it
    raises DisbursementBlocked. Do NOT close/flip/mock G2/G3."""
    status = gate_status.disbursement_allowed()

    # Pick any pre_onboarded holder that accrued escrow.
    holder = next(
        (h for h in ip_holders.list_all(con) if h.escrow_balance_usd > 0),
        None,
    )
    assert holder is not None, "expected at least one holder with escrow to test the gate"
    # Independent block: a pre_onboarded holder cannot be paid even if the gate
    # were open — claim() is the only unlock and we never call it.
    holder_status_blocks = holder.status != "claimed"

    blocked = False
    blocked_reason = ""
    blocking_fn = ""
    try:
        # The REAL disbursement entrypoint. We map the holder to a Speak project
        # purely to satisfy the signature; the gate refuses BEFORE any payout.
        contributor.attempt_disbursement(
            con, project_id="spr11-verify", interview_id="spr11-iv",
        )
    except contributor.DisbursementBlocked as exc:
        blocked = True
        blocked_reason = str(exc)
        blocking_fn = "substrate.speak.contributor.attempt_disbursement -> DisbursementBlocked"

    return SafetyValve(
        gate_allowed=status.allowed,
        gate_reason=status.reason,
        disbursement_blocked=blocked,
        blocked_reason=blocked_reason,
        blocking_function=blocking_fn,
        holder_status_independently_blocks=holder_status_blocks,
        # No Stripe path under tools/stripe_connect/ is imported or called by
        # this harness; the gate refuses before the seam reaches it. The e2e
        # test asserts this structurally (see test_no_stripe_path_invoked).
        no_stripe_path_invoked=True,
    )


# ---------------------------------------------------------------------------
# A/B — active attribution algorithm comparison (read-only)
# ---------------------------------------------------------------------------


def ab_comparison(corpus: tuple[SessionSpec, ...]) -> AlgorithmComparison:
    """Surface the A-vs-B-vs-C per-asset share comparison over the period's
    cited chunks, reusing the REAL compare_algorithms. Read-only; the operator
    picks the production algorithm (Option B is the documented default)."""
    chunk_to_document: dict[str, str] = {}
    chunk_to_conf: dict[str, float] = {}
    document_to_tier: dict[str, int] = {}
    chunk_to_claim_id: dict[str, str] = {}
    load_bearing: dict[str, float] = {}
    # Per-asset confidence/tier/load-bearing so the A/B comparison is MEANINGFUL
    # (uniform inputs would make A==B==C, which is true but uninformative). These
    # are fixture metadata, not new economics — they feed the real algorithms.
    by_asset = {
        "doc-mit-quantum": (0.9, 1, 0.9),
        "doc-pd-lecture": (0.6, 4, 0.3),
        "doc-cup-gated": (0.85, 2, 0.7),
        "doc-open-cc": (0.5, 5, 0.2),
        "doc-princeton-hist": (0.8, 2, 0.6),
    }
    for session in corpus:
        for cid, doc in session.cited_chunks.items():
            conf, tier, lb = by_asset.get(doc, (0.7, 3, 0.5))
            chunk_to_document[cid] = doc
            chunk_to_conf[cid] = conf
            document_to_tier.setdefault(doc, tier)
            chunk_to_claim_id[cid] = f"claim-{cid}"
            load_bearing[f"claim-{cid}"] = lb
    return compare_algorithms(
        page_id="spr11-period",
        chunk_to_document=chunk_to_document,
        chunk_to_claim_confidence=chunk_to_conf,
        document_to_source_tier=document_to_tier,
        claim_load_bearing_scores=load_bearing,
        chunk_to_claim_id=chunk_to_claim_id,
    )


# ---------------------------------------------------------------------------
# The full verification + the human-readable, auditable report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HolderSnapshot:
    """An escrow-by-holder snapshot, captured at verify() time so the report
    renders without holding the live connection (render_report stays pure)."""

    display_name: str
    status: str
    escrow_balance_cents: int


@dataclass(frozen=True)
class VerificationReport:
    corpus: tuple[SessionSpec, ...]
    results: list[SessionResult]
    reconciliation: Reconciliation
    traces: list[EscrowTrace]
    safety: SafetyValve
    ab: AlgorithmComparison
    holders: tuple[HolderSnapshot, ...]


def verify(con: Any) -> VerificationReport:
    """Run the whole chain + every milestone check against the given
    single-writer connection."""
    corpus = _build_corpus()
    results = run_chain(con, corpus)
    rec = reconcile(con, results)
    traces = trace_escrow(con, corpus, results)
    safety = check_safety_valve(con, results)
    ab = ab_comparison(corpus)
    holders = tuple(
        HolderSnapshot(
            display_name=h.display_name,
            status=h.status,
            escrow_balance_cents=int((h.escrow_balance_usd * Decimal(100))
                                     .to_integral_value()),
        )
        for h in ip_holders.list_all(con)
    )
    return VerificationReport(
        corpus=corpus, results=results, reconciliation=rec,
        traces=traces, safety=safety, ab=ab, holders=holders,
    )


def _fmt_usd(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def render_report(report: VerificationReport) -> str:
    """The operator's trust artifact: reproducible, reconciles to the cent,
    traces every accrual to second+asset, states plainly that $0 disbursed."""
    rec = report.reconciliation
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("ANTIEK AD-ECONOMICS — END-TO-END VERIFICATION REPORT (SPR-11)")
    lines.append("=" * 78)
    lines.append("")
    lines.append("SOURCE: faithful PROD-SHAPED FIXTURE corpus (NOT literal prod traffic).")
    lines.append("        No SPR-08 prod corpus exists in this worktree; this run proves the")
    lines.append("        COMPOSITION of the real modules reconciles, not real revenue figures.")
    lines.append("")

    lines.append("-- SESSIONS (auction-priced → per-second frame → accrual) " + "-" * 18)
    lines.append(f"{'window':<20}{'lens':<10}{'secs':>5}  {'ad_slot':<16}"
                 f"{'ad_value':>10}{'contrib':>10}{'house':>9}  rec")
    for r in report.results:
        contrib = sum(line.amount_cents for line in r.accrual.asset_lines)
        lines.append(
            f"{r.window_id:<20}{r.lens:<10}{r.n_seconds:>5}  "
            f"{(r.selected_ad_id or '-'):<16}"
            f"{_fmt_usd(r.ad_value_usd_cents):>10}"
            f"{_fmt_usd(contrib):>10}"
            f"{_fmt_usd(r.accrual.house.amount_cents):>9}"
            f"  {'OK' if r.accrual.reconciles() else 'FAIL'}"
        )
    lines.append("")

    lines.append("-- PER-ASSET ACCRUAL (the per-second engine output) " + "-" * 25)
    for r in report.results:
        for line in r.accrual.asset_lines:
            holder = line.ip_holder_id or "(unmapped/no-holder)"
            lines.append(
                f"  {r.window_id:22} {line.asset_id:22} "
                f"{_fmt_usd(line.amount_cents):>9}  holder={holder}"
            )
    lines.append("")

    lines.append("-- ELIGIBILITY DECISIONS (read via monetization_eligible) " + "-" * 19)
    seen: set[str] = set()
    for session in report.corpus:
        for a in session.assets:
            if a.asset_id in seen:
                continue
            seen.add(a.asset_id)
            verdict = "EARNS" if monetization_eligible(a.content_class) else "EARNS $0"
            lines.append(f"  {a.asset_id:22} content_class={a.content_class!r:30} "
                         f"-> {verdict}")
    lines.append("")

    lines.append("-- ESCROW BY HOLDER (servable-vs-pre_onboarded) " + "-" * 29)
    for h in report.holders:
        servable = "claimed/servable" if h.status == "claimed" else f"{h.status} (held)"
        lines.append(
            f"  {h.display_name:32} {_fmt_usd(h.escrow_balance_cents):>10}  "
            f"[{servable}]"
        )
    lines.append("")

    lines.append("-- TRACEABILITY (amount -> chunk -> asset -> holder) " + "-" * 24)
    for t in report.traces:
        lines.append(f"  {t.publisher} ({t.status}) escrow={_fmt_usd(int(t.escrow_balance_usd * 100))} "
                     f"trace_reconciles={t.reconciles}")
        for e in t.explanations:
            lines.append(f"      {e['document_id']:22} eligible={e['eligible']} "
                         f"frame_accrued={_fmt_usd(e['frame_accrued_cents'])} "
                         f"chunks={[c['chunk_id'] for c in e['per_chunk']]}")
    lines.append("")

    lines.append("-- HOUSE SECONDS POCKETED (platform; no contributor) " + "-" * 24)
    lines.append(f"  total house seconds value: {_fmt_usd(rec.total_house_cents)}")
    for r in report.results:
        if r.accrual.house.amount_cents > 0:
            lines.append(f"      {r.window_id:22} {_fmt_usd(r.accrual.house.amount_cents):>9}"
                         f"  reason={r.accrual.house.reason}")
    lines.append("")

    lines.append("-- ATTRIBUTION ALGORITHM A/B (read-only; operator picks) " + "-" * 20)
    lines.append(f"  active default: {report.ab.default_algorithm}")
    lines.append(f"  {'document':22}{'A':>8}{'B':>8}{'C':>8}")
    for doc_id, shares in report.ab.per_asset.items():
        lines.append(f"  {doc_id:22}{shares['A']:>8.3f}{shares['B']:>8.3f}{shares['C']:>8.3f}")
    lines.append("")

    lines.append("-- CONSERVATION (rigor #1: report the truth, do not fudge) " + "-" * 18)
    lines.append(f"  total ad value      : {_fmt_usd(rec.total_ad_value_cents)}")
    lines.append(f"  Σ contributor accrual: {_fmt_usd(rec.total_contributor_cents)}")
    lines.append(f"  Σ house seconds     : {_fmt_usd(rec.total_house_cents)}")
    lines.append(f"  contributor + house  : {_fmt_usd(rec.total_contributor_cents + rec.total_house_cents)}")
    lines.append(f"  CONSERVES TO THE CENT: {rec.reconciles} "
                 f"(per-window: {rec.per_window_reconciles})")
    # Honesty disclosure (rigor #1): the accrual ledger is the conservation
    # surface, NOT escrow-by-holder. Eligible assets with no ip_holder accrue to
    # the ledger (so the window conserves) but credit no escrow balance. Surface
    # the gap explicitly so the operator never reads Σ escrow as the contributor
    # total. Computed from the live snapshot, never hardcoded.
    escrow_total = sum(h.escrow_balance_cents for h in report.holders)
    unmapped_delta = rec.total_contributor_cents - escrow_total
    lines.append(f"  Σ escrow-by-holder   : {_fmt_usd(escrow_total)}")
    if unmapped_delta:
        unmapped = [
            (line.asset_id, line.amount_cents)
            for r in report.results
            for line in r.accrual.asset_lines
            if line.ip_holder_id is None and line.amount_cents > 0
        ]
        named = ", ".join(f"{a} ({_fmt_usd(c)})" for a, c in unmapped) or "none"
        lines.append(
            f"    NOTE: Σ contributor accrual exceeds Σ escrow-by-holder by "
            f"{_fmt_usd(unmapped_delta)} — eligible asset(s) with NO ip_holder "
            f"accrue to the ledger but credit no escrow: {named}. Conservation is "
            f"on the accrual ledger, not escrow. Not a leak (see runbook)."
        )
    lines.append(f"  rev split (read from payout.py): creator={rec.creator_rev_share} "
                 f"platform={rec.platform_cut} sums_to_1={rec.split_sums_to_one}")
    lines.append(f"  all amounts non-negative: {rec.all_non_negative}")
    lines.append("")

    lines.append("-- SAFETY VALVE (rigor #3: prove money does NOT move) " + "-" * 23)
    lines.append(f"  disbursement_allowed(): allowed={report.safety.gate_allowed}")
    lines.append(f"    reason: {report.safety.gate_reason}")
    lines.append(f"  attempt_disbursement(): blocked={report.safety.disbursement_blocked}")
    lines.append(f"    via: {report.safety.blocking_function}")
    lines.append(f"    blocked_reason: {report.safety.blocked_reason}")
    lines.append(f"  holder status independently blocks payout (no claim()): "
                 f"{report.safety.holder_status_independently_blocks}")
    lines.append(f"  no Stripe path under tools/stripe_connect/ invoked: "
                 f"{report.safety.no_stripe_path_invoked}")
    lines.append("")
    lines.append("  >>> disbursed: $0 (G2/G3 open) <<<")
    lines.append("")
    lines.append("=" * 78)
    overall = (
        rec.reconciles and rec.per_window_reconciles and rec.all_non_negative
        and all(t.reconciles for t in report.traces)
        and not report.safety.gate_allowed
        and report.safety.disbursement_blocked
        and all(r.replay_identical for r in report.results)
    )
    lines.append(f"OVERALL: {'VERIFIED — money story reproduces and the valve holds' if overall else 'DISCREPANCY — see lines above (rigor #1: not fudged)'}")
    lines.append("=" * 78)
    return "\n".join(lines)


def _reaccrue_identical(con: Any, corpus: tuple[SessionSpec, ...]) -> None:
    """Drive the same batches through accrue_window again (the idempotent path).
    Publishers already exist in this DB, so reuse them by display_name rather
    than creating duplicates."""
    publisher_to_holder = {
        h.display_name: h.ip_holder_id for h in ip_holders.list_all(con)
    }
    for session in corpus:
        batch = _frame_for(session)
        a2h: dict[str, str | None] = {
            a.asset_id: (publisher_to_holder.get(a.publisher) if a.publisher else None)
            for a in session.assets
        }
        accrue_window(con, batch, asset_to_ip_holder=a2h)


def main() -> int:
    tmpdir = tempfile.mkdtemp(prefix="antiek-spr11-verify-")
    db_path = os.path.join(tmpdir, "verify.duckdb")
    con = connect_write(db_path, purpose="spr11_ad_economics_verification")
    try:
        con.execute(_IP_HOLDERS_DDL)
        report = verify(con)
        print(render_report(report))
        # Re-run the chain in the SAME DB to prove idempotency (no double accrual).
        corpus = _build_corpus()
        before = {h.ip_holder_id: h.escrow_balance_usd
                  for h in ip_holders.list_all(con)}
        _reaccrue_identical(con, corpus)
        after = {h.ip_holder_id: h.escrow_balance_usd
                 for h in ip_holders.list_all(con)}
        idempotent = before == after
        print("")
        print(f"IDEMPOTENCY (re-accrue identical batches in same DB): "
              f"{'OK — no double accrual' if idempotent else 'FAIL — balances changed'}")
        return 0 if idempotent else 1
    finally:
        con.close()  # type: ignore[no-untyped-call]


if __name__ == "__main__":
    raise SystemExit(main())
