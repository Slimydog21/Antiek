"""Twin-side notes: insights and questions for every information asset.

The recursive note-taker vision: every asset has a twin substrate of
insights and questions that can be merged, referenced, and searched.
This module is the pure write/read path. Depth-graph promotion and
search/context assembly live in ``twin_promote`` (composes
``insight_question.promote_*`` without coupling the store to DuckDB).
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .store import EngagementStore

TwinKind = Literal["insight", "question"]


@dataclass(frozen=True)
class TwinNote:
    note_id: str
    asset_id: str
    kind: TwinKind
    text: str
    source_spawn_id: str | None = None
    investigation_id: str | None = None
    owner_id: str = "__operator__"


def _note_id(
    asset_id: str, kind: TwinKind, text: str, owner_id: str = "__operator__"
) -> str:
    canon = " ".join(text.strip().lower().split())
    owner_scope = "" if owner_id == "__operator__" else f"owner:{owner_id}:"
    digest = hashlib.sha256(
        f"{owner_scope}{asset_id}:{kind}:{canon}".encode()
    ).hexdigest()[:16]
    return f"twin_{digest}"


def record_twin_insight(
    asset_id: str,
    text: str,
    *,
    store: EngagementStore,
    source_spawn_id: str | None = None,
    investigation_id: str | None = None,
    owner_id: str = "__operator__",
) -> TwinNote:
    return _record(
        asset_id,
        text,
        kind="insight",
        store=store,
        source_spawn_id=source_spawn_id,
        investigation_id=investigation_id,
        owner_id=owner_id,
    )


def record_twin_question(
    asset_id: str,
    text: str,
    *,
    store: EngagementStore,
    source_spawn_id: str | None = None,
    investigation_id: str | None = None,
    owner_id: str = "__operator__",
) -> TwinNote:
    return _record(
        asset_id,
        text,
        kind="question",
        store=store,
        source_spawn_id=source_spawn_id,
        investigation_id=investigation_id,
        owner_id=owner_id,
    )


def _record(
    asset_id: str,
    text: str,
    *,
    kind: TwinKind,
    store: EngagementStore,
    source_spawn_id: str | None,
    investigation_id: str | None,
    owner_id: str,
) -> TwinNote:
    if not asset_id or not asset_id.strip():
        raise ValueError("asset_id is required")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("text is required")
    note = TwinNote(
        note_id=_note_id(asset_id.strip(), kind, cleaned, owner_id),
        asset_id=asset_id.strip(),
        kind=kind,
        text=cleaned,
        source_spawn_id=source_spawn_id,
        investigation_id=investigation_id,
        owner_id=owner_id,
    )
    store.put_twin(_to_row(note))
    return note


def list_twin_notes(
    asset_id: str, *, store: EngagementStore, owner_id: str = "__operator__"
) -> list[TwinNote]:
    return [_from_row(r) for r in store.list_twins(asset_id, owner_id)]


def twins_product_payload(
    asset_id: str,
    *,
    store: EngagementStore,
    include_html: bool = False,
    spawn_id: str | None = None,
    owner_id: str = "__operator__",
) -> dict[str, Any]:
    """Product entry: list twin notes for an asset (HTML-capable).

    Residual (le): optional ``spawn_id`` scopes reserved research_tier onto
    the list payload + HTML (parity seed la / research-context kk).
    """
    if not asset_id or not str(asset_id).strip():
        raise ValueError("asset_id is required")
    notes = list_twin_notes(asset_id, store=store, owner_id=owner_id)
    insights = [n for n in notes if n.kind == "insight"]
    questions = [n for n in notes if n.kind == "question"]
    research_tier = None
    sid = (spawn_id or "").strip() or None
    if sid:
        from substrate.dispatch.research_tier import normalize_research_tier

        row = store.get_spawn(sid) or {}
        research_tier = normalize_research_tier(row.get("research_tier"))
    payload: dict[str, Any] = {
        "asset_id": asset_id.strip(),
        "note_count": len(notes),
        "insight_count": len(insights),
        "question_count": len(questions),
        "notes": [_to_row(n) for n in notes],
        "view_format": "html",
        "product_panel": "twin_notes",
        "source": "engagement_spine.twin",
        "notes_meta": [],
        "spawn_id": sid,
        "research_tier": research_tier,
    }
    # Avoid key collision with note list: use `messages` for operator notes.
    payload["messages"] = (
        ["No twin notes yet — record insights/questions as the recursive note-taker."]
        if not notes
        else ["Twin substrate is the recursive note-taker for this asset."]
    )
    if include_html:
        payload["html"] = project_twins_html(payload)
    return payload


def record_twin_product(
    asset_id: str,
    *,
    store: EngagementStore,
    kind: TwinKind,
    text: str,
    source_spawn_id: str | None = None,
    investigation_id: str | None = None,
    include_html: bool = False,
) -> dict[str, Any]:
    """Product entry: record one twin note then return full twin payload."""
    if kind == "insight":
        record_twin_insight(
            asset_id,
            text,
            store=store,
            source_spawn_id=source_spawn_id,
            investigation_id=investigation_id,
        )
    elif kind == "question":
        record_twin_question(
            asset_id,
            text,
            store=store,
            source_spawn_id=source_spawn_id,
            investigation_id=investigation_id,
        )
    else:
        raise ValueError(f"invalid twin kind: {kind!r}")
    return twins_product_payload(asset_id, store=store, include_html=include_html)


# Residual (bz): optional live note_taker for twin seed — default OFF.
# Env ANTIEK_TWIN_SEED_LIVE + process inject both required (no silent LLM).
ANTIEK_TWIN_SEED_LIVE_ENV = "ANTIEK_TWIN_SEED_LIVE"

# (title, body_text) -> sequence of (kind, text) pairs; kinds insight|question
TwinSeedLiveFn = Callable[[str, str], Sequence[tuple[str, str]]]
_twin_seed_live_fn: TwinSeedLiveFn | None = None


def configure_twin_seed_live(fn: TwinSeedLiveFn | None) -> None:
    """Install or clear process-local live note_taker for twin seed."""
    global _twin_seed_live_fn
    _twin_seed_live_fn = fn


def clear_twin_seed_live() -> None:
    configure_twin_seed_live(None)


def twin_seed_live_enabled() -> bool:
    raw = (os.environ.get(ANTIEK_TWIN_SEED_LIVE_ENV) or "").strip().lower()
    return raw not in ("", "0", "false", "off", "no", "disabled")


def twin_seed_live_fn_installed() -> bool:
    """Residual (hs): True when a process-local live note_taker seed fn is set."""
    return _twin_seed_live_fn is not None


def seed_twins_for_asset(
    asset_id: str,
    *,
    store: EngagementStore,
    title: str,
    body_text: str = "",
    source_spawn_id: str | None = None,
    include_html: bool = False,
    force_offline: bool = False,
    live_fn: TwinSeedLiveFn | None = None,
) -> dict[str, Any]:
    """Recursive note-taker seed: insight + question twins for an asset.

    Residual (bu)/(bz). Idempotent when twins already exist.
    Default: offline identity stubs. Live note_taker only when:
      1. ``ANTIEK_TWIN_SEED_LIVE`` is on, AND
      2. ``live_fn`` passed or ``configure_twin_seed_live`` installed, AND
      3. not ``force_offline``
    """
    aid = (asset_id or "").strip()
    if not aid:
        raise ValueError("asset_id is required")
    existing = list_twin_notes(aid, store=store)
    if existing:
        payload = twins_product_payload(aid, store=store, include_html=include_html)
        payload["seeded"] = False
        payload["seed_skipped"] = "twins_already_present"
        payload["live_seed"] = False
        # Residual (la): still surface spawn research_tier when scoped.
        sid = (source_spawn_id or "").strip() or None
        if sid:
            from substrate.dispatch.research_tier import normalize_research_tier

            row = store.get_spawn(sid) or {}
            payload["source_spawn_id"] = sid
            payload["research_tier"] = normalize_research_tier(
                row.get("research_tier")
            )
        else:
            payload["research_tier"] = None
        return payload

    t = (title or "").strip() or aid
    body_preview = (body_text or "").strip().replace("\n", " ")
    if len(body_preview) > 160:
        body_preview = body_preview[:157] + "…"

    used_live = False
    pairs: list[tuple[str, str]] = []
    candidate = live_fn if live_fn is not None else _twin_seed_live_fn
    if (
        not force_offline
        and twin_seed_live_enabled()
        and candidate is not None
    ):
        try:
            raw_pairs = candidate(t, body_text or "")
            for kind, text in raw_pairs:
                k = (kind or "").strip().lower()
                tx = (text or "").strip()
                if k in ("insight", "question") and tx:
                    pairs.append((k, tx))
            if pairs:
                used_live = True
        except Exception:
            pairs = []
            used_live = False

    if not pairs:
        insight = f"Asset identity: {t}."
        if body_preview:
            insight += f" Opening: {body_preview}"
        question = f"What claims in “{t}” should be wrestled or cited next?"
        pairs = [("insight", insight), ("question", question)]

    for kind, text in pairs:
        if kind == "insight":
            record_twin_insight(
                aid, text, store=store, source_spawn_id=source_spawn_id
            )
        else:
            record_twin_question(
                aid, text, store=store, source_spawn_id=source_spawn_id
            )

    payload = twins_product_payload(aid, store=store, include_html=False)
    payload["seeded"] = True
    payload["seed_skipped"] = None
    payload["live_seed"] = used_live
    payload["seed_source"] = (
        "engagement_spine.twin.seed_twins_for_asset.live"
        if used_live
        else "engagement_spine.twin.seed_twins_for_asset"
    )
    # Residual (la): surface reserved spawn research_tier when seed scoped.
    research_tier = None
    sid = (source_spawn_id or "").strip() or None
    if sid:
        from substrate.dispatch.research_tier import normalize_research_tier

        row = store.get_spawn(sid) or {}
        research_tier = normalize_research_tier(row.get("research_tier"))
        payload["source_spawn_id"] = sid
    payload["research_tier"] = research_tier
    payload["messages"] = list(payload.get("messages") or []) + [
        (
            "Live note_taker twin seed (env + injector)."
            if used_live
            else "Offline twin seed (insight + question) — recursive note-taker substrate."
        ),
        f"Live env {ANTIEK_TWIN_SEED_LIVE_ENV}="
        f"{'on' if twin_seed_live_enabled() else 'off (default)'}.",
    ]
    if include_html:
        payload["html"] = project_twins_html(payload)
    return payload


def project_twins_html(payload: dict[str, Any]) -> str:
    """HTML-first twin document view (never PDF)."""
    from .project import project_to_html

    asset_id = str(payload.get("asset_id") or "")
    tier = payload.get("research_tier")
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Twin notes"}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Asset {asset_id} · insights={payload.get('insight_count')} · "
                        f"questions={payload.get('question_count')}"
                        + (f" · tier={tier}" if tier else "")
                        + " · view: HTML"
                    ),
                }
            ],
        },
    ]
    for row in payload.get("notes") or []:
        if not isinstance(row, dict):
            continue
        label = "Insight" if row.get("kind") == "insight" else "Question"
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": f"{label}: {row.get('text') or ''}"}
                ],
            }
        )
    if len(blocks) == 2:
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "(empty twin substrate — LLM note-taker has not written yet)",
                    }
                ],
            }
        )
    html = project_to_html(
        {"type": "doc", "content": blocks},
        document_id=f"twin-{asset_id}",
        creator="engagement_spine.twin",
    )
    if html.lstrip().lower().startswith("%pdf"):
        raise RuntimeError("PDF is not a valid twin view surface")
    return html


def _to_row(note: TwinNote) -> dict[str, Any]:
    return {
        "note_id": note.note_id,
        "asset_id": note.asset_id,
        "kind": note.kind,
        "text": note.text,
        "source_spawn_id": note.source_spawn_id,
        "investigation_id": note.investigation_id,
        "owner_id": note.owner_id,
    }


def _from_row(row: dict[str, Any]) -> TwinNote:
    return TwinNote(
        note_id=row["note_id"],
        asset_id=row["asset_id"],
        kind=row["kind"],
        text=row["text"],
        source_spawn_id=row.get("source_spawn_id"),
        investigation_id=row.get("investigation_id"),
        owner_id=str(row.get("owner_id") or "__operator__"),
    )
