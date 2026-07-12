"""Write twin collective + settings draft fullscreen weekly ND pack (pure).

draft_written / analysis_written / merge_executed always False.
secrets_stored / inventory_mutated always False.
live_dispatched / pack_dispatched / backlog_mutated / store_mutated always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.settings_add_model_draft_fullscreen_weekly_nd_mo_compose import (
    SettingsAddModelDraftFullscreenWeeklyNdMoCompose,
    SettingsAddModelDraftFullscreenWeeklyNdMoComposeError,
    compose_settings_add_model_draft_fullscreen_weekly_nd_mo,
)
from substrate.write_mode_twin_collective_analysis_compose import (
    WriteModeTwinCollectiveAnalysisCompose,
    WriteModeTwinCollectiveAnalysisComposeError,
    compose_write_mode_twin_collective_analysis,
)


class WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError(ValueError):
    """Fail-closed validation for write twin + settings draft fullscreen ND."""


@dataclass(frozen=True)
class WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    write: WriteModeTwinCollectiveAnalysisCompose
    settings_research: SettingsAddModelDraftFullscreenWeeklyNdMoCompose
    pack_ready: bool
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
    twin_written: bool
    live_execution_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "write": self.write.to_dict(),
            "settings_research": self.settings_research.to_dict(),
            "pack_ready": self.pack_ready,
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
            "twin_written": False,
            "live_execution_authorized": False,
            "notes": list(self.notes),
            "authority": (
                "write_twin_collective_settings_draft_fullscreen_nd_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_write_twin_collective_settings_draft_fullscreen_nd_mo(
    *,
    write: object,
    settings_research: object,
    operator_ack: object,
    require_both: object | None = None,
) -> WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose:
    """Write twin collective + settings draft fullscreen ND. Never writes."""
    if not isinstance(operator_ack, bool):
        raise WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(write, dict):
        raise WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError(
            "write must be an object"
        )
    if not isinstance(settings_research, dict):
        raise WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError(
            "settings_research must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "draft_written=false · analysis_written=false · merge_executed=false",
        "secrets_stored=false · inventory_mutated=false",
        "live_dispatched=false · pack_dispatched=false · backlog_mutated=false · store_mutated=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
    ]

    try:
        w = compose_write_mode_twin_collective_analysis(
            session_id=write.get("session_id"),
            draft_id=write.get("draft_id"),
            parent_asset_id=write.get("parent_asset_id"),
            twin_slices=write.get("twin_slices"),
            chase_slots=write.get("chase_slots"),
            analysis_kind=write.get("analysis_kind"),
            operator_ack=operator_ack,
            base_draft_html=write.get("base_draft_html"),
            extra_findings=write.get("extra_findings"),
            require_both=write.get("require_both"),
        )
    except WriteModeTwinCollectiveAnalysisComposeError as e:
        raise WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[write] {n}" for n in w.notes)

    try:
        sr = compose_settings_add_model_draft_fullscreen_weekly_nd_mo(
            settings=settings_research.get("settings"),
            research_pack=settings_research.get("research_pack"),
            operator_ack=operator_ack,
            require_both=settings_research.get("require_both"),
        )
    except SettingsAddModelDraftFullscreenWeeklyNdMoComposeError as e:
        raise WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[settings_research] {n}" for n in sr.notes)

    session = _require_nonempty(w.session_id, field="session_id")
    parent = _require_nonempty(w.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(sr.week_id, field="week_id")

    aligned = sr.session_id == session and sr.parent_asset_id == parent
    if not aligned:
        notes.append(
            "session/parent mismatch between write and settings_research — pack_ready blocked"
        )

    if require:
        pack_ready = (
            aligned
            and w.pack_ready is True
            and sr.pack_ready is True
            and sr.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            aligned
            and operator_ack is True
            and sr.production_router_verdict == "REJECT"
            and (w.pack_ready is True or sr.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — write twin collective + settings draft fullscreen ND ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — write, settings_research, alignment, or operator_ack gate open"
        )

    if (
        w.draft_written is not False
        or w.analysis_written is not False
        or w.merge_executed is not False
        or w.store_mutated is not False
        or w.live_dispatched is not False
        or sr.secrets_stored is not False
        or sr.inventory_mutated is not False
        or sr.draft_written is not False
        or sr.merge_executed is not False
        or sr.live_dispatched is not False
        or sr.production_router_verdict != "REJECT"
        or sr.live_router_authorized is not False
    ):
        raise WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
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
            "twin_written=false",
            "live_execution_authorized=false",
        )
    )

    return WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        write=w,
        settings_research=sr,
        pack_ready=pack_ready,
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
        twin_written=False,
        live_execution_authorized=False,
        notes=tuple(notes),
        authority=(
            "write_twin_collective_settings_draft_fullscreen_nd_mo_compose_advisory"
        ),
    )


def format_write_twin_collective_settings_draft_fullscreen_nd_mo_summary(
    c: WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"write_ready={c.write.pack_ready} · "
        f"settings_research_ready={c.settings_research.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"analysis_written=false · draft_written=false · merge_executed=false"
    )


__all__ = [
    "WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose",
    "WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError",
    "compose_write_twin_collective_settings_draft_fullscreen_nd_mo",
    "format_write_twin_collective_settings_draft_fullscreen_nd_mo_summary",
]
