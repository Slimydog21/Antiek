"""Floating multi-select cohesive pack + source attach quality (pure).

live_dispatched / pack_dispatched / merge_executed / analysis_written /
remote_fetched / pdf_view_authorized / store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_multi_select_collective_cohesive_compose import (
    FloatingMultiSelectCollectiveCohesiveCompose,
    FloatingMultiSelectCollectiveCohesiveComposeError,
    compose_floating_multi_select_collective_cohesive,
)
from substrate.source_publication_dr_attach_quality_compose import (
    SourcePublicationDrAttachQualityCompose,
    SourcePublicationDrAttachQualityComposeError,
    compose_source_publication_dr_attach_quality,
)


class FloatingMultiSelectSourceAttachQualityComposeError(ValueError):
    """Fail-closed validation for multi-select + source quality pack."""


@dataclass(frozen=True)
class FloatingMultiSelectSourceAttachQualityCompose:
    session_id: str
    parent_asset_id: str
    multi_select: FloatingMultiSelectCollectiveCohesiveCompose
    source_quality: SourcePublicationDrAttachQualityCompose
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    analysis_written: bool
    remote_fetched: bool
    pdf_view_authorized: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "multi_select": self.multi_select.to_dict(),
            "source_quality": self.source_quality.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "analysis_written": False,
            "remote_fetched": False,
            "pdf_view_authorized": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "floating_multi_select_source_attach_quality_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingMultiSelectSourceAttachQualityComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_floating_multi_select_source_attach_quality(
    *,
    session_id: object,
    parent_asset_id: object,
    members: object,
    selected_instance_ids: object,
    pack_mode: object,
    cohesive_prompt: object,
    operator_ack: object,
    requested_families: object,
    sources: object,
    quality_overall: object,
    would_exceed: object,
    extra_context: object | None = None,
    analysis_kind: object | None = None,
    extra_findings: object | None = None,
    citations: object | None = None,
    derive_citations_from_sources: object | None = None,
    quality_floor: object | None = None,
    operator_override: object | None = None,
    require_both: object | None = None,
) -> FloatingMultiSelectSourceAttachQualityCompose:
    """Multi-select cohesive + HTML source quality. Never dispatches/scrapes."""
    if not isinstance(operator_ack, bool):
        raise FloatingMultiSelectSourceAttachQualityComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise FloatingMultiSelectSourceAttachQualityComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · pack_dispatched=false",
        "merge_executed=false · analysis_written=false",
        "remote_fetched=false — no live arxiv/substack scrape",
        "pdf_view_authorized=false — HTML-native sources only",
    ]

    try:
        multi_select = compose_floating_multi_select_collective_cohesive(
            session_id=session,
            parent_asset_id=parent,
            members=members,
            selected_instance_ids=selected_instance_ids,
            pack_mode=pack_mode,
            cohesive_prompt=cohesive_prompt,
            operator_ack=operator_ack,
            extra_context=extra_context,
            analysis_kind=analysis_kind,
            extra_findings=extra_findings,
        )
    except FloatingMultiSelectCollectiveCohesiveComposeError as e:
        raise FloatingMultiSelectSourceAttachQualityComposeError(str(e)) from e
    notes.extend(f"[multi_select] {n}" for n in multi_select.notes)

    try:
        source_quality = compose_source_publication_dr_attach_quality(
            session_id=session,
            parent_asset_id=parent,
            requested_families=requested_families,
            sources=sources,
            quality_overall=quality_overall,
            would_exceed=would_exceed,
            operator_ack=operator_ack,
            citations=citations,
            derive_citations_from_sources=derive_citations_from_sources,
            quality_floor=quality_floor,
            operator_override=operator_override,
        )
    except SourcePublicationDrAttachQualityComposeError as e:
        raise FloatingMultiSelectSourceAttachQualityComposeError(str(e)) from e
    notes.extend(f"[source_quality] {n}" for n in source_quality.notes)

    if require:
        pack_ready = (
            multi_select.pack_ready is True
            and source_quality.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            multi_select.pack_ready is True or source_quality.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — multi-select cohesive + source quality ready; "
            "still pure"
        )
    else:
        notes.append(
            "pack_ready=false — multi-select, source quality, or operator_ack "
            "gate open"
        )

    if (
        multi_select.live_dispatched is not False
        or multi_select.pack_dispatched is not False
        or multi_select.merge_executed is not False
        or multi_select.analysis_written is not False
        or source_quality.remote_fetched is not False
        or source_quality.pdf_view_authorized is not False
        or source_quality.store_mutated is not False
    ):
        raise FloatingMultiSelectSourceAttachQualityComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "analysis_written=false",
            "remote_fetched=false",
            "pdf_view_authorized=false",
            "store_mutated=false",
        )
    )

    return FloatingMultiSelectSourceAttachQualityCompose(
        session_id=session,
        parent_asset_id=parent,
        multi_select=multi_select,
        source_quality=source_quality,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        analysis_written=False,
        remote_fetched=False,
        pdf_view_authorized=False,
        store_mutated=False,
        notes=tuple(notes),
        authority=(
            "floating_multi_select_source_attach_quality_compose_advisory"
        ),
    )


def format_floating_multi_select_source_attach_quality_summary(
    c: FloatingMultiSelectSourceAttachQualityCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"multi_ready={c.multi_select.pack_ready} · "
        f"source_ready={c.source_quality.pack_ready} · "
        f"sources={c.source_quality.attach.source_count} · "
        f"live_dispatched=false · remote_fetched=false · analysis_written=false"
    )


__all__ = [
    "FloatingMultiSelectSourceAttachQualityCompose",
    "FloatingMultiSelectSourceAttachQualityComposeError",
    "compose_floating_multi_select_source_attach_quality",
    "format_floating_multi_select_source_attach_quality_summary",
]
