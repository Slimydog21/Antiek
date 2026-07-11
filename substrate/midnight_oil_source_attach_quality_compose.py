"""Midnight Oil unattended + source attach quality pack (pure).

live_execution_authorized / remote_fetched / pdf_view_authorized /
live_dispatched / store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil_unattended_package_compose import (
    MidnightOilUnattendedPackageCompose,
    MidnightOilUnattendedPackageComposeError,
    compose_midnight_oil_unattended_package,
)
from substrate.source_publication_dr_attach_quality_compose import (
    SourcePublicationDrAttachQualityCompose,
    SourcePublicationDrAttachQualityComposeError,
    compose_source_publication_dr_attach_quality,
)


class MidnightOilSourceAttachQualityComposeError(ValueError):
    """Fail-closed validation for MO + source attach quality pack."""


@dataclass(frozen=True)
class MidnightOilSourceAttachQualityCompose:
    operator_id: str
    session_id: str
    parent_asset_id: str
    mo_unattended: MidnightOilUnattendedPackageCompose
    source_quality: SourcePublicationDrAttachQualityCompose
    pack_ready: bool
    live_execution_authorized: bool
    remote_fetched: bool
    pdf_view_authorized: bool
    live_dispatched: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "mo_unattended": self.mo_unattended.to_dict(),
            "source_quality": self.source_quality.to_dict(),
            "pack_ready": self.pack_ready,
            "live_execution_authorized": False,
            "remote_fetched": False,
            "pdf_view_authorized": False,
            "live_dispatched": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "midnight_oil_source_attach_quality_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MidnightOilSourceAttachQualityComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_midnight_oil_source_attach_quality(
    *,
    operator_id: object,
    work_minutes: object,
    goals: object,
    operator_ack: object,
    unattended_ack: object,
    spend_consent: object,
    session_id: object,
    parent_asset_id: object,
    requested_families: object,
    sources: object,
    quality_overall: object,
    would_exceed: object,
    usd_per_hour: object | None = None,
    approved_ceiling_usd: object | None = None,
    brief_dispatch_ready: object | None = None,
    citations: object | None = None,
    derive_citations_from_sources: object | None = None,
    quality_floor: object | None = None,
    operator_override: object | None = None,
    require_both: object | None = None,
) -> MidnightOilSourceAttachQualityCompose:
    """MO unattended + HTML source quality. Never launches/scrapes."""
    if not isinstance(operator_ack, bool):
        raise MidnightOilSourceAttachQualityComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(unattended_ack, bool):
        raise MidnightOilSourceAttachQualityComposeError(
            "unattended_ack must be an explicit boolean"
        )
    if not isinstance(spend_consent, bool):
        raise MidnightOilSourceAttachQualityComposeError(
            "spend_consent must be an explicit boolean"
        )
    op = _require_nonempty(operator_id, field="operator_id")
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MidnightOilSourceAttachQualityComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_execution_authorized=false — midnight oil never launches workers",
        "remote_fetched=false — no live arxiv/substack scrape",
        "pdf_view_authorized=false — HTML-native sources only",
        "live_dispatched=false · store_mutated=false",
    ]

    try:
        mo_unattended = compose_midnight_oil_unattended_package(
            operator_id=op,
            work_minutes=work_minutes,
            goals=goals,
            operator_ack=operator_ack,
            unattended_ack=unattended_ack,
            spend_consent=spend_consent,
            usd_per_hour=usd_per_hour,
            approved_ceiling_usd=approved_ceiling_usd,
            brief_dispatch_ready=brief_dispatch_ready,
        )
    except MidnightOilUnattendedPackageComposeError as e:
        raise MidnightOilSourceAttachQualityComposeError(str(e)) from e
    notes.extend(f"[mo] {n}" for n in mo_unattended.notes)

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
        raise MidnightOilSourceAttachQualityComposeError(str(e)) from e
    notes.extend(f"[source_quality] {n}" for n in source_quality.notes)

    if require:
        pack_ready = (
            mo_unattended.unattended_package_ready is True
            and source_quality.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            mo_unattended.unattended_package_ready is True
            or source_quality.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — MO unattended + source quality ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — MO package, source quality, or operator_ack "
            "gate open"
        )

    if (
        mo_unattended.live_execution_authorized is not False
        or source_quality.remote_fetched is not False
        or source_quality.pdf_view_authorized is not False
        or source_quality.live_dispatch_authorized is not False
        or source_quality.store_mutated is not False
    ):
        raise MidnightOilSourceAttachQualityComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_execution_authorized=false",
            "remote_fetched=false",
            "pdf_view_authorized=false",
            "live_dispatched=false",
            "store_mutated=false",
        )
    )

    return MidnightOilSourceAttachQualityCompose(
        operator_id=op,
        session_id=session,
        parent_asset_id=parent,
        mo_unattended=mo_unattended,
        source_quality=source_quality,
        pack_ready=pack_ready,
        live_execution_authorized=False,
        remote_fetched=False,
        pdf_view_authorized=False,
        live_dispatched=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="midnight_oil_source_attach_quality_compose_advisory",
    )


def format_midnight_oil_source_attach_quality_summary(
    c: MidnightOilSourceAttachQualityCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"mo_ready={c.mo_unattended.unattended_package_ready} · "
        f"source_ready={c.source_quality.pack_ready} · "
        f"sources={c.source_quality.attach.source_count} · "
        f"live_execution_authorized=false · remote_fetched=false · "
        f"pdf_view_authorized=false"
    )


__all__ = [
    "MidnightOilSourceAttachQualityCompose",
    "MidnightOilSourceAttachQualityComposeError",
    "compose_midnight_oil_source_attach_quality",
    "format_midnight_oil_source_attach_quality_summary",
]
