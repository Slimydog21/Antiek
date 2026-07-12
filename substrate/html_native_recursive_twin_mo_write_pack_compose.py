"""HTML-native view + recursive twin MO write pack (pure).

pdf_view_authorized / pdf_primary always False.
twin_written / charge_executed / live_execution_authorized always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.html_native_view_session_authority_compose import (
    HtmlNativeViewSessionAuthorityCompose,
    HtmlNativeViewSessionAuthorityComposeError,
    compose_html_native_view_session_authority,
)
from substrate.recursive_twin_mo_price_ceiling_write_pack_compose import (
    RecursiveTwinMoPriceCeilingWritePackCompose,
    RecursiveTwinMoPriceCeilingWritePackComposeError,
    compose_recursive_twin_mo_price_ceiling_write_pack,
)


class HtmlNativeRecursiveTwinMoWritePackComposeError(ValueError):
    """Fail-closed validation for HTML-native + recursive twin MO write pack."""


@dataclass(frozen=True)
class HtmlNativeRecursiveTwinMoWritePackCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    html_view: HtmlNativeViewSessionAuthorityCompose
    twin_mo: RecursiveTwinMoPriceCeilingWritePackCompose
    pack_ready: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
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
            "html_view": self.html_view.to_dict(),
            "twin_mo": self.twin_mo.to_dict(),
            "pack_ready": self.pack_ready,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
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
                "html_native_recursive_twin_mo_write_pack_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HtmlNativeRecursiveTwinMoWritePackComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_html_native_recursive_twin_mo_write_pack(
    *,
    html_view: object,
    twin_mo: object,
    operator_ack: object,
    require_both: object | None = None,
) -> HtmlNativeRecursiveTwinMoWritePackCompose:
    """HTML-native view + recursive twin MO write. Never PDF primary."""
    if not isinstance(operator_ack, bool):
        raise HtmlNativeRecursiveTwinMoWritePackComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(html_view, dict):
        raise HtmlNativeRecursiveTwinMoWritePackComposeError(
            "html_view must be an object"
        )
    if not isinstance(twin_mo, dict):
        raise HtmlNativeRecursiveTwinMoWritePackComposeError(
            "twin_mo must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise HtmlNativeRecursiveTwinMoWritePackComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "pdf_view_authorized=false · pdf_primary=false",
        "twin_written=false · charge_executed=false · live_execution_authorized=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
    ]

    try:
        hv = compose_html_native_view_session_authority(
            session_id=html_view.get("session_id"),
            asset_id=html_view.get("asset_id"),
            html_projection_sha=html_view.get("html_projection_sha"),
            view_requested=html_view.get("view_requested"),
            twin_bound=html_view.get("twin_bound"),
            operator_ack=operator_ack,
            twin_substrate_ready=html_view.get("twin_substrate_ready"),
            claimed_format=html_view.get("claimed_format"),
            reading=html_view.get("reading"),
            research=html_view.get("research"),
        )
    except HtmlNativeViewSessionAuthorityComposeError as e:
        raise HtmlNativeRecursiveTwinMoWritePackComposeError(str(e)) from e
    notes.extend(f"[html_view] {n}" for n in hv.notes)

    try:
        tm = compose_recursive_twin_mo_price_ceiling_write_pack(
            twin=twin_mo.get("twin"),
            mo_write=twin_mo.get("mo_write"),
            operator_ack=operator_ack,
            require_both=twin_mo.get("require_both"),
        )
    except RecursiveTwinMoPriceCeilingWritePackComposeError as e:
        raise HtmlNativeRecursiveTwinMoWritePackComposeError(str(e)) from e
    notes.extend(f"[twin_mo] {n}" for n in tm.notes)

    session = _require_nonempty(hv.session_id, field="session_id")
    parent = _require_nonempty(tm.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(tm.week_id, field="week_id")

    aligned = hv.session_id == tm.session_id and hv.asset_id == tm.parent_asset_id
    if not aligned:
        notes.append(
            "session/asset mismatch between html_view and twin_mo — pack_ready blocked"
        )

    if require:
        pack_ready = (
            aligned
            and hv.pack_ready is True
            and tm.pack_ready is True
            and tm.production_router_verdict == "REJECT"
            and hv.pdf_view_authorized is False
            and hv.pdf_primary is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            aligned
            and operator_ack is True
            and tm.production_router_verdict == "REJECT"
            and hv.pdf_primary is False
            and (hv.pack_ready is True or tm.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — HTML-native view + recursive twin MO write pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — html_view, twin_mo, alignment, or operator_ack gate open"
        )

    if (
        hv.pdf_view_authorized is not False
        or hv.pdf_primary is not False
        or hv.store_mutated is not False
        or tm.twin_written is not False
        or tm.charge_executed is not False
        or tm.live_execution_authorized is not False
        or tm.production_router_verdict != "REJECT"
        or tm.live_router_authorized is not False
    ):
        raise HtmlNativeRecursiveTwinMoWritePackComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
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

    return HtmlNativeRecursiveTwinMoWritePackCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        html_view=hv,
        twin_mo=tm,
        pack_ready=pack_ready,
        pdf_view_authorized=False,
        pdf_primary=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
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
        authority="html_native_recursive_twin_mo_write_pack_compose_advisory",
    )


def format_html_native_recursive_twin_mo_write_pack_summary(
    c: HtmlNativeRecursiveTwinMoWritePackCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"html_view_ready={c.html_view.pack_ready} · "
        f"twin_mo_ready={c.twin_mo.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"pdf_primary=false · twin_written=false · charge_executed=false"
    )


__all__ = [
    "HtmlNativeRecursiveTwinMoWritePackCompose",
    "HtmlNativeRecursiveTwinMoWritePackComposeError",
    "compose_html_native_recursive_twin_mo_write_pack",
    "format_html_native_recursive_twin_mo_write_pack_summary",
]
