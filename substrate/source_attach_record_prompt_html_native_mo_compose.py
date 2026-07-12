"""Source publication DR attach + record→prompt HTML pack (pure).

remote_fetched / live_dispatch_authorized always False.
record_persisted / prompts_injected always False.
pdf_view_authorized / pdf_primary always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.record_prompt_html_native_recursive_twin_mo_compose import (
    RecordPromptHtmlNativeRecursiveTwinMoCompose,
    RecordPromptHtmlNativeRecursiveTwinMoComposeError,
    compose_record_prompt_html_native_recursive_twin_mo,
)
from substrate.source_publication_dr_attach_quality_compose import (
    SourcePublicationDrAttachQualityCompose,
    SourcePublicationDrAttachQualityComposeError,
    compose_source_publication_dr_attach_quality,
)


class SourceAttachRecordPromptHtmlNativeMoComposeError(ValueError):
    """Fail-closed validation for source attach + record→prompt HTML pack."""


@dataclass(frozen=True)
class SourceAttachRecordPromptHtmlNativeMoCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    sources: SourcePublicationDrAttachQualityCompose
    record_html: RecordPromptHtmlNativeRecursiveTwinMoCompose
    pack_ready: bool
    remote_fetched: bool
    live_dispatch_authorized: bool
    record_persisted: bool
    prompts_injected: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    twin_written: bool
    charge_executed: bool
    live_execution_authorized: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    backlog_mutated: bool
    store_mutated: bool
    production_router_verdict: str
    live_router_authorized: bool
    purchase_executed: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "sources": self.sources.to_dict(),
            "record_html": self.record_html.to_dict(),
            "pack_ready": self.pack_ready,
            "remote_fetched": False,
            "live_dispatch_authorized": False,
            "record_persisted": False,
            "prompts_injected": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "twin_written": False,
            "charge_executed": False,
            "live_execution_authorized": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "purchase_executed": False,
            "notes": list(self.notes),
            "authority": (
                "source_attach_record_prompt_html_native_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceAttachRecordPromptHtmlNativeMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_source_attach_record_prompt_html_native_mo(
    *,
    sources: object,
    record_html: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SourceAttachRecordPromptHtmlNativeMoCompose:
    """arxiv/substack attach + record→prompt HTML pack. Never fetches."""
    if not isinstance(operator_ack, bool):
        raise SourceAttachRecordPromptHtmlNativeMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(sources, dict):
        raise SourceAttachRecordPromptHtmlNativeMoComposeError(
            "sources must be an object"
        )
    if not isinstance(record_html, dict):
        raise SourceAttachRecordPromptHtmlNativeMoComposeError(
            "record_html must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SourceAttachRecordPromptHtmlNativeMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "remote_fetched=false · live_dispatch_authorized=false",
        "record_persisted=false · prompts_injected=false",
        "pdf_view_authorized=false · pdf_primary=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
    ]

    try:
        src = compose_source_publication_dr_attach_quality(
            session_id=sources.get("session_id"),
            parent_asset_id=sources.get("parent_asset_id"),
            requested_families=sources.get("requested_families"),
            sources=sources.get("sources"),
            quality_overall=sources.get("quality_overall"),
            would_exceed=sources.get("would_exceed"),
            operator_ack=operator_ack,
            citations=sources.get("citations"),
            derive_citations_from_sources=sources.get(
                "derive_citations_from_sources"
            ),
            quality_floor=sources.get("quality_floor"),
            operator_override=sources.get("operator_override"),
        )
    except SourcePublicationDrAttachQualityComposeError as e:
        raise SourceAttachRecordPromptHtmlNativeMoComposeError(str(e)) from e
    notes.extend(f"[sources] {n}" for n in src.notes)

    try:
        rh = compose_record_prompt_html_native_recursive_twin_mo(
            record_prompt=record_html.get("record_prompt"),
            html_pack=record_html.get("html_pack"),
            operator_ack=operator_ack,
            require_both=record_html.get("require_both"),
        )
    except RecordPromptHtmlNativeRecursiveTwinMoComposeError as e:
        raise SourceAttachRecordPromptHtmlNativeMoComposeError(str(e)) from e
    notes.extend(f"[record_html] {n}" for n in rh.notes)

    session = _require_nonempty(src.session_id, field="session_id")
    parent = _require_nonempty(src.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(rh.week_id, field="week_id")

    aligned = rh.session_id == session and rh.parent_asset_id == parent
    if not aligned:
        notes.append(
            "session/parent mismatch between sources and record_html — pack_ready blocked"
        )

    if require:
        pack_ready = (
            aligned
            and src.pack_ready is True
            and rh.pack_ready is True
            and rh.production_router_verdict == "REJECT"
            and src.remote_fetched is False
            and src.pdf_view_authorized is False
            and rh.prompts_injected is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            aligned
            and operator_ack is True
            and rh.production_router_verdict == "REJECT"
            and src.remote_fetched is False
            and (src.pack_ready is True or rh.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — arxiv/substack attach + record→prompt HTML pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — sources, record_html, alignment, or operator_ack gate open"
        )

    if (
        src.remote_fetched is not False
        or src.live_dispatch_authorized is not False
        or src.pdf_view_authorized is not False
        or src.store_mutated is not False
        or rh.record_persisted is not False
        or rh.prompts_injected is not False
        or rh.pdf_primary is not False
        or rh.twin_written is not False
        or rh.production_router_verdict != "REJECT"
        or rh.live_router_authorized is not False
    ):
        raise SourceAttachRecordPromptHtmlNativeMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "remote_fetched=false",
            "live_dispatch_authorized=false",
            "record_persisted=false",
            "prompts_injected=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "twin_written=false",
            "charge_executed=false",
            "live_execution_authorized=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "purchase_executed=false",
        )
    )

    return SourceAttachRecordPromptHtmlNativeMoCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        sources=src,
        record_html=rh,
        pack_ready=pack_ready,
        remote_fetched=False,
        live_dispatch_authorized=False,
        record_persisted=False,
        prompts_injected=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        twin_written=False,
        charge_executed=False,
        live_execution_authorized=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        backlog_mutated=False,
        store_mutated=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        purchase_executed=False,
        notes=tuple(notes),
        authority="source_attach_record_prompt_html_native_mo_compose_advisory",
    )


def format_source_attach_record_prompt_html_native_mo_summary(
    c: SourceAttachRecordPromptHtmlNativeMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"sources_ready={c.sources.pack_ready} · "
        f"citations={c.sources.citation_pack.citation_count} · "
        f"record_html_ready={c.record_html.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"remote_fetched=false · prompts_injected=false · pdf_primary=false"
    )


__all__ = [
    "SourceAttachRecordPromptHtmlNativeMoCompose",
    "SourceAttachRecordPromptHtmlNativeMoComposeError",
    "compose_source_attach_record_prompt_html_native_mo",
    "format_source_attach_record_prompt_html_native_mo_summary",
]
