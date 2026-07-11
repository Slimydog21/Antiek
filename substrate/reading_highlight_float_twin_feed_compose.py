"""Reading highlight → float tray + twin feed compose (pure).

live_dispatched, merge_executed, pack_dispatched, twin_written,
record_persisted always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.reading_highlight_float_merge_tray_compose import (
    ReadingHighlightFloatMergeTrayCompose,
    ReadingHighlightFloatMergeTrayComposeError,
    compose_reading_highlight_float_merge_tray,
)
from substrate.twin_chase_analysis_feed_compose import (
    TwinChaseAnalysisFeedCompose,
    TwinChaseAnalysisFeedComposeError,
    compose_twin_chase_analysis_feed,
)


class ReadingHighlightFloatTwinFeedComposeError(ValueError):
    """Fail-closed validation for highlight float + twin feed pack."""


@dataclass(frozen=True)
class ReadingHighlightFloatTwinFeedCompose:
    session_id: str
    surface: ReadingHighlightFloatMergeTrayCompose
    twin_feed: TwinChaseAnalysisFeedCompose | None
    pack_ready: bool
    live_dispatched: bool
    merge_executed: bool
    pack_dispatched: bool
    twin_written: bool
    record_persisted: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "surface": self.surface.to_dict(),
            "twin_feed": self.twin_feed.to_dict() if self.twin_feed else None,
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "merge_executed": False,
            "pack_dispatched": False,
            "twin_written": False,
            "record_persisted": False,
            "notes": list(self.notes),
            "authority": "reading_highlight_float_twin_feed_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReadingHighlightFloatTwinFeedComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_reading_highlight_float_twin_feed(
    *,
    session_id: object,
    parent_asset_id: object,
    highlight: object,
    gated: object,
    would_exceed: object,
    surface_action: object,
    operator_ack: object,
    prompt: object | None = None,
    preferred_view_mode: object | None = None,
    operator_override: object | None = None,
    selected_model_id: object | None = None,
    source_families: object | None = None,
    existing_members: object | None = None,
    selected_instance_ids: object | None = None,
    twin_findings: object | None = None,
    existing_twin_asset_id: object | None = None,
    mark_for_prompt_context: object | None = None,
    include_twin_feed: object | None = None,
) -> ReadingHighlightFloatTwinFeedCompose:
    """Compose reading float/tray + twin feed from highlight. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise ReadingHighlightFloatTwinFeedComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    include_twin = True if include_twin_feed is None else include_twin_feed
    if not isinstance(include_twin, bool):
        raise ReadingHighlightFloatTwinFeedComposeError(
            "include_twin_feed must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false — reading float/twin pack is pure intent",
        "merge_executed=false",
        "pack_dispatched=false",
        "twin_written=false",
        "record_persisted=false",
    ]

    try:
        surface = compose_reading_highlight_float_merge_tray(
            parent_asset_id=parent_asset_id,
            highlight=highlight,
            gated=gated,
            would_exceed=would_exceed,
            surface_action=surface_action,
            operator_ack=operator_ack,
            prompt=prompt,
            preferred_view_mode=preferred_view_mode,
            operator_override=operator_override,
            selected_model_id=selected_model_id,
            source_families=source_families,
            existing_members=existing_members,
            selected_instance_ids=selected_instance_ids,
        )
    except ReadingHighlightFloatMergeTrayComposeError as e:
        raise ReadingHighlightFloatTwinFeedComposeError(str(e)) from e
    notes.extend(surface.notes)

    twin_feed: TwinChaseAnalysisFeedCompose | None = None
    if include_twin:
        hl = _require_nonempty(highlight, field="highlight")
        findings: list[dict[str, Any]] = [
            {
                "source_id": f"highlight_{session}",
                "body": hl,
                "kind": "question",
            }
        ]
        if twin_findings is not None:
            if not isinstance(twin_findings, list):
                raise ReadingHighlightFloatTwinFeedComposeError(
                    "twin_findings must be an array when set"
                )
            for f in twin_findings:
                if not isinstance(f, dict):
                    raise ReadingHighlightFloatTwinFeedComposeError(
                        "twin_findings entries must be objects"
                    )
                findings.append(dict(f))
        try:
            twin_feed = compose_twin_chase_analysis_feed(
                session_id=session,
                parent_asset_id=parent_asset_id,
                findings=findings,
                analysis_excerpt=f"highlight seed: {hl}",
                existing_twin_asset_id=existing_twin_asset_id,
                operator_ack=operator_ack,
                mark_for_prompt_context=mark_for_prompt_context,
            )
        except TwinChaseAnalysisFeedComposeError as e:
            raise ReadingHighlightFloatTwinFeedComposeError(str(e)) from e
        notes.extend(twin_feed.notes)
    else:
        notes.append("twin_feed skipped — include_twin_feed=false")

    twin_ok = (not include_twin) or (
        twin_feed is not None and twin_feed.feed_ready
    )
    pack_ready = surface.surface_ready and twin_ok
    if not surface.surface_ready:
        notes.append("pack_ready=false — surface tray/launch not ready")
    elif not twin_ok:
        notes.append("pack_ready=false — twin feed not ready")
    else:
        notes.append(
            "pack_ready=true — highlight float+twin intent only; still pure"
        )

    if (
        surface.live_dispatched is not False
        or surface.merge_executed is not False
        or surface.pack_dispatched is not False
    ):
        raise ReadingHighlightFloatTwinFeedComposeError(
            "invariant: surface honesty flags must remain false"
        )
    if twin_feed is not None and (
        twin_feed.twin_written is not False
        or twin_feed.record_persisted is not False
        or twin_feed.live_dispatch_authorized is not False
    ):
        raise ReadingHighlightFloatTwinFeedComposeError(
            "invariant: twin_feed honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "merge_executed=false",
            "pack_dispatched=false",
            "twin_written=false",
            "record_persisted=false",
        )
    )

    return ReadingHighlightFloatTwinFeedCompose(
        session_id=session,
        surface=surface,
        twin_feed=twin_feed,
        pack_ready=pack_ready,
        live_dispatched=False,
        merge_executed=False,
        pack_dispatched=False,
        twin_written=False,
        record_persisted=False,
        notes=tuple(notes),
        authority="reading_highlight_float_twin_feed_compose_advisory",
    )


def format_reading_highlight_float_twin_feed_summary(
    c: ReadingHighlightFloatTwinFeedCompose,
) -> str:
    feed = c.twin_feed.feed_ready if c.twin_feed is not None else "n/a"
    return (
        f"pack_ready={c.pack_ready} · surface_ready={c.surface.surface_ready} · "
        f"feed_ready={feed} · "
        f"live_dispatched=false · merge_executed=false · pack_dispatched=false · "
        f"twin_written=false · record_persisted=false"
    )


__all__ = [
    "ReadingHighlightFloatTwinFeedCompose",
    "ReadingHighlightFloatTwinFeedComposeError",
    "compose_reading_highlight_float_twin_feed",
    "format_reading_highlight_float_twin_feed_summary",
]
