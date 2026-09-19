"""Attribution computation pipeline.

Reads a synthesis row + its thesis_components from DuckDB, resolves
chunk→document + document→source_tier, runs the three attribution
algorithms in parallel, and (optionally) emits a
``PAGE_ATTRIBUTION_COMPUTED`` event with the result.

This module is the public entry point used by the API and by Phase
2 batch jobs. Algorithm internals live in ``algorithms.py``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

import duckdb

from substrate.event_log import emit_typed, emit_typed_authorized_strict
from substrate.graph import default_db_path, ensure_initialized

from .algorithms import (
    ALGORITHMS,
    AttributionClaim,
    attribution_option_a,
    attribution_option_b,
    attribution_option_c,
)


@dataclass(frozen=True)
class AttributionResult:
    """One algorithm's per-document share map.

    ``shares`` keys are ``document_id``; values are share-of-total
    (sum to 1.0 modulo float rounding). ``document_titles`` is a
    parallel map for human readability; not load-bearing.

    ``document_ip_holders`` / ``document_ip_holder_status`` carry the
    provenance chain's last link — *whose work grounds this* (§9, SPR-10
    M1). A document with no resolved owner maps to ``None`` (honest
    "unknown owner", never invented). The status (``pre_onboarded`` …
    ``claimed``) lets the surface frame escrow as opt-in-only (§9.10):
    a ``pre_onboarded`` holder is escrow-framework-eligible, never shown
    as money waiting against an unconsenting rights holder."""

    algorithm: str  # "A" | "B" | "C"
    shares: Mapping[str, float]
    document_titles: Mapping[str, str]
    document_count: int
    claim_count: int
    # document_id → ip_holder_id (or None when the document has no owner).
    document_ip_holders: Mapping[str, str | None] = field(default_factory=dict)
    # ip_holder_id → status word (pre_onboarded | invited | claimed | opted_out).
    document_ip_holder_status: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SynthesisAttributionResult:
    """All three algorithms' results for one synthesis."""

    synthesis_id: str
    target_question: str
    option_a: AttributionResult
    option_b: AttributionResult
    option_c: AttributionResult


def _build_claims(
    con: duckdb.DuckDBPyConnection,
    thesis_components: list[dict],
    chunk_to_doc: Mapping[str, str],
    doc_to_tier: Mapping[str, int],
) -> list[AttributionClaim]:
    """Convert the synthesizer's thesis_components into the math-side
    shape. Skip components that don't cite any chunks (analogy-only
    claims aren't attributable to documents)."""
    claims: list[AttributionClaim] = []
    for i, comp in enumerate(thesis_components):
        chunk_ids = list(comp.get("supporting_chunk_ids") or [])
        if not chunk_ids:
            continue
        claims.append(AttributionClaim(
            claim_index=i,
            chunk_ids=tuple(chunk_ids),
            confidence=comp.get("confidence", "low"),
            chunk_to_document=chunk_to_doc,
            document_to_tier=doc_to_tier,
        ))
    return claims


def compute_attribution_for_synthesis(
    synthesis_id: str,
    *,
    db_path: str | None = None,
    emit_event: bool = False,
    investigation_id: str | None = None,
    _authority: object | None = None,
) -> SynthesisAttributionResult:
    """Compute attribution for one archived synthesis. Returns all
    three algorithms' results.

    When ``emit_event`` is true, emits a
    ``PAGE_ATTRIBUTION_COMPUTED`` event tagged to ``investigation_id``
    (defaults to the synthesis's investigation_id). The phase-1
    pipeline uses ``emit_event=True``; ad-hoc analytic dashboards
    use ``emit_event=False`` to compute without writing to the log."""
    resolved = db_path or default_db_path()
    ensure_initialized(resolved)
    con = duckdb.connect(resolved, read_only=True)
    try:
        where = "synthesis_id = ?"
        params: list[object] = [synthesis_id]
        if _authority is not None:
            from substrate.graph.tenancy import assert_graph_authority_read
            from substrate.investigation_tenancy import InvestigationAuthority

            if not isinstance(_authority, InvestigationAuthority):
                raise TypeError("attribution requires InvestigationAuthority")
            assert_graph_authority_read(con, _authority)
            if (
                investigation_id is not None
                and investigation_id != _authority.investigation_id
            ):
                raise ValueError("attribution investigation authority mismatch")
            where += " AND account_digest = ? AND investigation_digest = ?"
            params.extend(
                [_authority.account_digest, _authority.investigation_digest]
            )
        row = con.execute(
            "SELECT synthesis_id, target_question, thesis, investigation_id, "
            "account_digest, investigation_digest FROM syntheses WHERE " + where,
            params,
        ).fetchone()
        if row is None:
            raise ValueError(f"synthesis {synthesis_id!r} not found")
        _, target_question, thesis_json, syn_inv_id = row[:4]
        if not thesis_json:
            thesis = {}
        else:
            try:
                thesis = json.loads(thesis_json)
            except (TypeError, ValueError):
                thesis = {}
        thesis_components = thesis.get("thesis_components") or []

        all_chunk_ids: set[str] = set()
        for comp in thesis_components:
            for cid in comp.get("supporting_chunk_ids") or []:
                all_chunk_ids.add(cid)
        if _authority is not None and all_chunk_ids:
            manifest_chunk_ids = {
                manifest_row[0]
                for manifest_row in con.execute(
                    "SELECT entity_id FROM synthesis_substrate_manifest "
                    "WHERE synthesis_id = ? AND entity_kind = 'chunk'",
                    [synthesis_id],
                ).fetchall()
            }
            all_chunk_ids.intersection_update(manifest_chunk_ids)
            thesis_components = [
                {
                    **component,
                    "supporting_chunk_ids": [
                        chunk_id
                        for chunk_id in component.get("supporting_chunk_ids") or []
                        if chunk_id in manifest_chunk_ids
                    ],
                }
                for component in thesis_components
            ]
        import os

        from substrate.legal_gate.read import attribution_sources_compatibility

        chunk_to_doc, documents = attribution_sources_compatibility(
            con,
            all_chunk_ids,
            authority=_authority,
            enforce=(
                _authority is not None
                or os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1"
            ),
        )
        doc_to_tier: dict[str, int] = {
            key: int(value["source_tier"]) for key, value in documents.items()
        }
        doc_to_title: dict[str, str] = {
            key: (value["title"] or "") for key, value in documents.items()
        }
        doc_to_content_class: dict[str, str | None] = {
            key: value["content_class"] for key, value in documents.items()
        }
        doc_to_ip_holder: dict[str, str | None] = {
            key: value["ip_holder_id"] for key, value in documents.items()
        }

        # §9.0 retrieval-time gating, on the SURFACED (attribution) path.
        # Two content_classes must NOT surface into an attribution-triggering
        # synthesis — neither body, nor title, nor a share:
        #   - restricted_pending_opt_in (gated-but-public copyrighted work
        #     withheld pending opt-in), and
        #   - personal_reading (the owner's private third-party reading — the
        #     Personal-Reading Lane, SPR-01).
        # This endpoint resolves WHATEVER chunks a given synthesis cited, so a
        # synthesis built on a privileged (private_research / operator_only)
        # path could legitimately have included personal_reading chunks; when
        # attribution is later computed here — an attribution-ELIGIBLE surface,
        # not a privileged owner read — both classes must be dropped so they
        # receive zero display share and zero title (personal_reading accrues
        # zero ad attribution by construction, master-spec §9.0 / lane invariant).
        # We filter on the SAME non-privileged exclusion union the public
        # chunk-search gate uses (substrate/graph/search.py
        # _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES = RESTRICTED ∪ PERSONAL_ONLY)
        # so the two surfaces can never drift apart. (SPR-01 M2 defense-in-depth;
        # supersedes the RESTRICTED-only filter from SPR-10 M1.)
        from substrate.graph.retrieval_gate import (
            _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES,
        )

        excluded_docs = {
            d for d, cc in doc_to_content_class.items()
            if cc in _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES
        }
        if excluded_docs:
            chunk_to_doc = {
                cid: d for cid, d in chunk_to_doc.items()
                if d not in excluded_docs
            }
            for d in excluded_docs:
                doc_to_tier.pop(d, None)
                doc_to_title.pop(d, None)
                doc_to_ip_holder.pop(d, None)

        # Resolve the ip_holder status word for each surfaced (non-restricted)
        # owner. Drives the opt-in-only escrow framing on the surface: a
        # pre_onboarded holder is escrow-framework-eligible, never "money
        # waiting" (§9.10 / Google Books opt-out rejection).
        owner_ids = {h for h in doc_to_ip_holder.values() if h}
        ip_status: dict[str, str] = {}
        if owner_ids:
            placeholders = ",".join("?" for _ in owner_ids)
            for hid, status in con.execute(
                f"SELECT ip_holder_id, status FROM ip_holders "
                f"WHERE ip_holder_id IN ({placeholders})",
                list(owner_ids),
            ).fetchall():
                ip_status[hid] = status
    finally:
        con.close()

    claims = _build_claims(None, thesis_components, chunk_to_doc, doc_to_tier)

    a_shares = attribution_option_a(claims)
    b_shares = attribution_option_b(claims)
    c_shares = attribution_option_c(claims)

    def _r(algo: str, shares: dict[str, float]) -> AttributionResult:
        owners = {k: doc_to_ip_holder.get(k) for k in shares}
        return AttributionResult(
            algorithm=algo,
            shares=shares,
            document_titles={k: doc_to_title.get(k, "") for k in shares},
            document_count=len(shares),
            claim_count=len(claims),
            document_ip_holders=owners,
            document_ip_holder_status={
                h: ip_status.get(h, "pre_onboarded")
                for h in owners.values() if h
            },
        )

    result = SynthesisAttributionResult(
        synthesis_id=synthesis_id,
        target_question=target_question or "",
        option_a=_r("A", a_shares),
        option_b=_r("B", b_shares),
        option_c=_r("C", c_shares),
    )

    if emit_event:
        from substrate.schemas import PageAttributionComputedPayload
        payload = PageAttributionComputedPayload(
            synthesis_id=synthesis_id,
            algorithm_shares={
                "A": dict(a_shares),
                "B": dict(b_shares),
                "C": dict(c_shares),
            },
            claim_count=len(claims),
            document_count=max(
                len(a_shares), len(b_shares), len(c_shares),
            ),
        )
        event_kwargs = {
            "synthesis_id": synthesis_id,
            "role": "attribution",
            "policy_id": "attribution/phase1",
        }
        if _authority is None:
            emit_typed(
                investigation_id or syn_inv_id or "__operator__",
                payload,
                **event_kwargs,
            )
        else:
            emit_typed_authorized_strict(
                _authority,
                payload,
                **event_kwargs,
            )

    return result


def compute_attribution_for_synthesis_authorized(
    authority: object,
    synthesis_id: str,
    *,
    db_path: str | None = None,
    emit_event: bool = False,
) -> SynthesisAttributionResult:
    """Compute attribution only through an exact synthesis authority."""
    return compute_attribution_for_synthesis(
        synthesis_id,
        db_path=db_path,
        emit_event=emit_event,
        _authority=authority,
    )


__all__ = [
    "AttributionResult",
    "SynthesisAttributionResult",
    "compute_attribution_for_synthesis",
    "compute_attribution_for_synthesis_authorized",
    "ALGORITHMS",
]
