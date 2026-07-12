"""HTML-native view over recursive twin settings fullscreen MO pack (pure).

pdf_view_authorized / pdf_primary always False.
twin_written / secrets_stored / charge_executed always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.html_native_view_session_authority_compose import (
    HtmlNativeViewSessionAuthorityCompose,
    HtmlNativeViewSessionAuthorityComposeError,
    compose_html_native_view_session_authority,
)
from substrate.recursive_twin_settings_fullscreen_mo_compose import (
    RecursiveTwinSettingsFullscreenMoCompose,
    RecursiveTwinSettingsFullscreenMoComposeError,
    compose_recursive_twin_settings_fullscreen_mo,
)


class HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError(ValueError):
    """Fail-closed validation for HTML-native + recursive twin settings MO pack."""


@dataclass(frozen=True)
class HtmlNativeRecursiveTwinSettingsFullscreenMoCompose:
    session_id: str
    parent_asset_id: str
    asset_id: str
    html_view: HtmlNativeViewSessionAuthorityCompose
    twin_pack: RecursiveTwinSettingsFullscreenMoCompose
    pack_ready: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    store_mutated: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    live_execution_authorized: bool
    charge_executed: bool
    draft_written: bool
    record_persisted: bool
    remote_index_queried: bool
    analysis_written: bool
    production_router_verdict: str
    purchase_executed: bool
    hosted: bool
    backlog_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "html_view": self.html_view.to_dict(),
            "twin_pack": self.twin_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "store_mutated": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "remote_index_queried": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "purchase_executed": False,
            "hosted": False,
            "backlog_mutated": False,
            "notes": list(self.notes),
            "authority": "html_native_recursive_twin_settings_fullscreen_mo_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_html_native_recursive_twin_settings_fullscreen_mo(
    *,
    html_view: object,
    twin_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> HtmlNativeRecursiveTwinSettingsFullscreenMoCompose:
    """HTML-native view + recursive twin settings MO. Never PDF-primary."""
    if not isinstance(operator_ack, bool):
        raise HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(html_view, dict):
        raise HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError(
            "html_view must be an object"
        )
    if not isinstance(twin_pack, dict):
        raise HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError(
            "twin_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "pdf_view_authorized=false · pdf_primary=false · store_mutated=false",
        "twin_written=false · secrets_stored=false · charge_executed=false",
        "production_router_verdict=REJECT",
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
        raise HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[html_view] {n}" for n in hv.notes)

    try:
        tp = compose_recursive_twin_settings_fullscreen_mo(
            twin=twin_pack.get("twin"),
            settings_pack=twin_pack.get("settings_pack"),
            operator_ack=operator_ack,
            require_both=twin_pack.get("require_both"),
        )
    except RecursiveTwinSettingsFullscreenMoComposeError as e:
        raise HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin_pack] {n}" for n in tp.notes)

    session = _require_nonempty(hv.session_id, field="session_id")
    asset = _require_nonempty(hv.asset_id, field="asset_id")
    parent = _require_nonempty(tp.parent_asset_id, field="parent_asset_id")

    session_aligned = tp.session_id == session
    parent_aligned = tp.parent_asset_id == asset
    if not session_aligned:
        notes.append(
            "session_id mismatch between html_view and twin_pack — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "asset_id/parent_asset_id mismatch between html_view and twin_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and hv.pack_ready is True
            and tp.pack_ready is True
            and tp.production_router_verdict == "REJECT"
            and hv.pdf_view_authorized is False
            and hv.pdf_primary is False
            and tp.twin_written is False
            and tp.secrets_stored is False
            and tp.charge_executed is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and tp.production_router_verdict == "REJECT"
            and hv.pdf_view_authorized is False
            and hv.pdf_primary is False
            and (hv.pack_ready is True or tp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — HTML-native view + recursive twin settings fullscreen MO ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — html_view, twin_pack, alignment, or operator_ack gate open"
        )

    if (
        hv.pdf_view_authorized is not False
        or hv.pdf_primary is not False
        or hv.store_mutated is not False
        or tp.twin_written is not False
        or tp.prompts_injected is not False
        or tp.secrets_stored is not False
        or tp.charge_executed is not False
        or tp.production_router_verdict != "REJECT"
    ):
        raise HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "store_mutated=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "remote_index_queried=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
            "purchase_executed=false",
            "hosted=false",
            "backlog_mutated=false",
        )
    )

    return HtmlNativeRecursiveTwinSettingsFullscreenMoCompose(
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        html_view=hv,
        twin_pack=tp,
        pack_ready=pack_ready,
        pdf_view_authorized=False,
        pdf_primary=False,
        store_mutated=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        live_execution_authorized=False,
        charge_executed=False,
        draft_written=False,
        record_persisted=False,
        remote_index_queried=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        purchase_executed=False,
        hosted=False,
        backlog_mutated=False,
        notes=tuple(notes),
        authority="html_native_recursive_twin_settings_fullscreen_mo_compose_advisory",
    )


def format_html_native_recursive_twin_settings_fullscreen_mo_summary(
    c: HtmlNativeRecursiveTwinSettingsFullscreenMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"html_ready={c.html_view.pack_ready} · "
        f"twin_ready={c.twin_pack.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"pdf_view_authorized=false · pdf_primary=false · twin_written=false"
    )


__all__ = [
    "HtmlNativeRecursiveTwinSettingsFullscreenMoCompose",
    "HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError",
    "compose_html_native_recursive_twin_settings_fullscreen_mo",
    "format_html_native_recursive_twin_settings_fullscreen_mo_summary",
]
