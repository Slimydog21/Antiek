"""Midnight Oil unattended + model decision + HTML-native competition (pure).

live_execution_authorized always False.
live_router_authorized / secrets_stored / live_meter_read always False.
pdf_view_authorized / pdf_primary always False.
live_dispatch / remote / write honesty flags always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil_unattended_package_compose import (
    MidnightOilUnattendedPackageCompose,
    MidnightOilUnattendedPackageComposeError,
    compose_midnight_oil_unattended_package,
)
from substrate.model_decision_html_native_competition_compose import (
    ModelDecisionHtmlNativeCompetitionCompose,
    ModelDecisionHtmlNativeCompetitionComposeError,
    compose_model_decision_html_native_competition,
)


class MoModelDecisionHtmlNativeCompetitionComposeError(ValueError):
    """Fail-closed validation for MO + model decision + HTML competition."""


@dataclass(frozen=True)
class MoModelDecisionHtmlNativeCompetitionCompose:
    mo: MidnightOilUnattendedPackageCompose
    research: ModelDecisionHtmlNativeCompetitionCompose
    pack_ready: bool
    live_execution_authorized: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    remote_index_queried: bool
    twin_written: bool
    draft_written: bool
    store_mutated: bool
    live_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mo": self.mo.to_dict(),
            "research": self.research.to_dict(),
            "pack_ready": self.pack_ready,
            "live_execution_authorized": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "remote_index_queried": False,
            "twin_written": False,
            "draft_written": False,
            "store_mutated": False,
            "live_dispatched": False,
            "notes": list(self.notes),
            "authority": (
                "mo_model_decision_html_native_competition_compose_advisory"
            ),
        }


def compose_mo_model_decision_html_native_competition(
    *,
    mo: object,
    research: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MoModelDecisionHtmlNativeCompetitionCompose:
    """MO unattended + model decision HTML competition. Never live-executes."""
    if not isinstance(operator_ack, bool):
        raise MoModelDecisionHtmlNativeCompetitionComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(mo, dict):
        raise MoModelDecisionHtmlNativeCompetitionComposeError(
            "mo must be an object"
        )
    if not isinstance(research, dict):
        raise MoModelDecisionHtmlNativeCompetitionComposeError(
            "research must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MoModelDecisionHtmlNativeCompetitionComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_execution_authorized=false — midnight oil never launches workers",
        "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
        "pdf_view_authorized=false · pdf_primary=false",
        "live_dispatch_authorized=false · remote_fetched=false · remote_index_queried=false",
        "twin_written=false · draft_written=false · store_mutated=false · live_dispatched=false",
    ]

    try:
        mo_pack = compose_midnight_oil_unattended_package(
            operator_id=mo.get("operator_id"),
            work_minutes=mo.get("work_minutes"),
            goals=mo.get("goals"),
            operator_ack=operator_ack,
            unattended_ack=mo.get("unattended_ack"),
            spend_consent=mo.get("spend_consent"),
            usd_per_hour=mo.get("usd_per_hour"),
            approved_ceiling_usd=mo.get("approved_ceiling_usd"),
            brief_dispatch_ready=mo.get("brief_dispatch_ready"),
        )
    except MidnightOilUnattendedPackageComposeError as e:
        raise MoModelDecisionHtmlNativeCompetitionComposeError(str(e)) from e
    notes.extend(f"[mo] {n}" for n in mo_pack.notes)

    try:
        research_pack = compose_model_decision_html_native_competition(
            decision=research.get("decision"),
            competition_view=research.get("competition_view"),
            operator_ack=operator_ack,
            require_both=research.get("require_both"),
            block_on_budget_exceed=research.get("block_on_budget_exceed"),
        )
    except ModelDecisionHtmlNativeCompetitionComposeError as e:
        raise MoModelDecisionHtmlNativeCompetitionComposeError(str(e)) from e
    notes.extend(f"[research] {n}" for n in research_pack.notes)

    if require:
        pack_ready = (
            mo_pack.unattended_package_ready is True
            and research_pack.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            mo_pack.unattended_package_ready is True
            or research_pack.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — MO unattended + model decision HTML competition ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — mo, research, or operator_ack gate open"
        )

    if (
        mo_pack.live_execution_authorized is not False
        or research_pack.live_router_authorized is not False
        or research_pack.secrets_stored is not False
        or research_pack.live_meter_read is not False
        or research_pack.pdf_view_authorized is not False
        or research_pack.pdf_primary is not False
        or research_pack.live_dispatch_authorized is not False
        or research_pack.remote_fetched is not False
        or research_pack.remote_index_queried is not False
        or research_pack.twin_written is not False
        or research_pack.draft_written is not False
        or research_pack.store_mutated is not False
    ):
        raise MoModelDecisionHtmlNativeCompetitionComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_execution_authorized=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "remote_index_queried=false",
            "twin_written=false",
            "draft_written=false",
            "store_mutated=false",
            "live_dispatched=false",
        )
    )

    return MoModelDecisionHtmlNativeCompetitionCompose(
        mo=mo_pack,
        research=research_pack,
        pack_ready=pack_ready,
        live_execution_authorized=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        remote_index_queried=False,
        twin_written=False,
        draft_written=False,
        store_mutated=False,
        live_dispatched=False,
        notes=tuple(notes),
        authority="mo_model_decision_html_native_competition_compose_advisory",
    )


def format_mo_model_decision_html_native_competition_summary(
    c: MoModelDecisionHtmlNativeCompetitionCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"mo_ready={c.mo.unattended_package_ready} · "
        f"research_ready={c.research.pack_ready} · "
        f"model={c.research.decision.driver.decision.selected_model_id} · "
        f"live_execution_authorized=false · live_router_authorized=false · "
        f"pdf_view_authorized=false · twin_written=false"
    )


__all__ = [
    "MoModelDecisionHtmlNativeCompetitionCompose",
    "MoModelDecisionHtmlNativeCompetitionComposeError",
    "compose_mo_model_decision_html_native_competition",
    "format_mo_model_decision_html_native_competition_summary",
]
