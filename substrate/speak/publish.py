"""Speak SPR-09 — publishing + serving (reuse Read).

Where a finished biography goes out, routed by its economics mode
(SPR-07):

  • private-never-published → NOT served, creator-paid (no split);
  • public → registered in Read's servable corpus as
    ``platform_authored`` + the 70% contributor split routed (SPR-06),
    but ONLY after passing every SPR-01 gate (consent + verification +
    subject consent + G2/G3).

Reuses Read's servable-corpus contract directly: a public biography's
content_class is ``user_public_contribution``, which
``substrate.books.servability.servability_of`` maps to the
``PLATFORM_AUTHORED`` servable status. We do not fork a Speak-specific
serving pipeline.

Public publishing must pass EVERY gate, not just the mode check — the
gate is the SPR-01 ``check_public_publish`` (the legal spine), and we
refuse with its specific reason.

Covered by ``./scripts/canonical_verify.sh speak-publishing-physical``:
publish gate enforcement, Speak→Read servability, contributor split routing,
and the Speak publish/quote UI. Live POD vendor, shipping, payment, and
fulfillment remain operator-side proof in the platform matrix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from substrate.books.servability import is_servable_full_text, servability_of
from substrate.books.model import upsert_book_asset
from substrate.event_log import emit_typed
from substrate.graph.ops import insert_document
from substrate.schemas.events import SeamSpeakToReadPayload

from . import contributor as contributor_mod
from . import economics_mode, publish_gate
from .contributor import AccrualLine
from .events import SPEAK_PUBLISHED, record_speak_event
from .ids import new_publication_id
from .publish_gate import PublishBlocked
from .schema import ensure_speak_schema

# A published Speak biography is platform-authored content posted to the
# public graph → this content_class resolves to ServabilityStatus
# PLATFORM_AUTHORED (servable full text) via substrate.books.servability.
PUBLIC_BIOGRAPHY_CONTENT_CLASS = "user_public_contribution"


@dataclass(frozen=True)
class PublishResult:
    publication_id: str
    visibility: str            # 'private' | 'public'
    served: bool
    servability: str           # ServabilityStatus value
    content_class: str | None
    accrual_lines: tuple[AccrualLine, ...] = field(default_factory=tuple)


def _deliverable_text(con: Any, deliverable_id: str | None) -> tuple[str | None, str | None]:
    """Return (title, body) for a Write deliverable, if one backs the publish.

    Speak publishing registers the publication id as the Read document id. The
    served body is the persisted Write prose, ordered by section. Empty sections
    are ignored; no body is fabricated when no prose exists.
    """
    if deliverable_id is None:
        return None, None
    title_row = con.execute(
        "SELECT title FROM deliverables WHERE deliverable_id = ?",
        [deliverable_id],
    ).fetchone()
    rows = con.execute(
        "SELECT title, prose_text FROM deliverable_sections "
        "WHERE deliverable_id = ? ORDER BY section_index, created_at",
        [deliverable_id],
    ).fetchall()
    parts: list[str] = []
    for section_title, prose_text in rows:
        text = (prose_text or "").strip()
        if not text:
            continue
        heading = (section_title or "").strip()
        parts.append(f"## {heading}\n\n{text}" if heading else text)
    return (title_row[0] if title_row else None), "\n\n".join(parts) if parts else None


def publish(
    con: Any,
    *,
    project_id: str,
    deliverable_id: str | None = None,
    subject_ref: str | None = None,
    ad_revenue_usd: Decimal = Decimal("0"),
    quality_scores: dict[str, float] | None = None,
    impression_ref: str | None = None,
) -> PublishResult:
    """Publish a finished biography per its economics mode.

    Public publishing is REFUSED (``PublishBlocked``) unless every SPR-01
    gate passes. A private project is unaffected by the public gate, is
    never served, and routes no contributor split."""
    ensure_speak_schema(con)
    ad_revenue = contributor_mod.require_non_negative_decimal(
        ad_revenue_usd, "ad_revenue_usd"
    )
    policy = economics_mode.policy_for_project(con, project_id)
    publication_id = new_publication_id()

    if policy.publishing == "public":
        # M3 — the full public gate (G2/G3 + subject consent +
        # verification + no takedown). Refuse with the specific reason.
        decision = publish_gate.check_public_publish(
            con, project_id=project_id, subject_ref=subject_ref
        )
        if not decision.allowed:
            raise PublishBlocked(decision.reason)

        content_class = PUBLIC_BIOGRAPHY_CONTENT_CLASS
        status = servability_of(content_class)  # → PLATFORM_AUTHORED
        served = is_servable_full_text(status)

        con.execute(
            "INSERT INTO speak_publications "
            "(publication_id, project_id, deliverable_id, visibility, content_class, served) "
            "VALUES (?, ?, ?, 'public', ?, ?)",
            [publication_id, project_id, deliverable_id, content_class, served],
        )
        title, body = _deliverable_text(con, deliverable_id)
        insert_document(
            con,
            document_id=publication_id,
            source_tier=1,
            document_type="book",
            title=title or "Published biography",
            raw_text=body,
            investigation_id=project_id,
            content_class=content_class,
            metadata={
                "provenance_class": "speak_derived",
                "speak_project_id": project_id,
                "speak_publication_id": publication_id,
                "speak_deliverable_id": deliverable_id,
                "speak_publish_gate_passed": True,
            },
            on_conflict="ignore",
        )
        upsert_book_asset(
            con,
            document_id=publication_id,
            provenance="Speak public biography publish",
            license_basis="Speak SPR-01 public publish gate passed",
        )
        # M2 — route the contributor split (SPR-06). Zero buyers → $0,
        # share tracked. Accrue, never disburse.
        accrual = contributor_mod.accrue_contributions(
            con, project_id=project_id, publication_id=publication_id,
            ad_revenue_usd=ad_revenue, quality_scores=quality_scores,
            impression_ref=impression_ref,
        )
    else:
        # private-never-published: not served, creator-paid, no split.
        content_class = None
        status = servability_of(content_class)  # GATED_METADATA_ONLY
        served = False
        con.execute(
            "INSERT INTO speak_publications "
            "(publication_id, project_id, deliverable_id, visibility, content_class, served) "
            "VALUES (?, ?, ?, 'private', NULL, FALSE)",
            [publication_id, project_id, deliverable_id],
        )
        accrual = []

    publish_event_id = record_speak_event(
        SPEAK_PUBLISHED,
        {"publication_id": publication_id, "visibility": policy.publishing,
         "served": served, "servability": status.value,
         "ad_revenue_usd": str(ad_revenue)},
        project_id=project_id,
    )
    if policy.publishing == "public" and served:
        emit_typed(
            project_id,
            SeamSpeakToReadPayload(
                entity_id=publication_id,
                provenance_ref=publish_event_id or publication_id,
                publish_gate_passed=True,
            ),
            parent_event_id=publish_event_id,
            role="speak_publishing",
        )
    return PublishResult(
        publication_id=publication_id,
        visibility="public" if policy.publishing == "public" else "private",
        served=served,
        servability=status.value,
        content_class=content_class,
        accrual_lines=tuple(accrual),
    )


def get_publication(con: Any, publication_id: str) -> dict | None:
    row = con.execute(
        "SELECT publication_id, project_id, visibility, content_class, served, taken_down "
        "FROM speak_publications WHERE publication_id = ?",
        [publication_id],
    ).fetchone()
    if row is None:
        return None
    return {"publication_id": row[0], "project_id": row[1], "visibility": row[2],
            "content_class": row[3], "served": bool(row[4]), "taken_down": bool(row[5])}
