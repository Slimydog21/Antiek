"""Twin-note → depth-graph promote + search/context assembly.

Product residual (o): recorded twin insights/questions become depth-graph
nodes via the sanctioned ``promote_insight`` / ``promote_question`` single-
writer surface, then participate in research search/context packs.

Design (hard-to-vary):

* **Compose, don't reimplement.** Graph identity, content addressing, and
  DuckDB writes stay in ``substrate.graph.insight_question``. This module
  only maps twin notes → promote_* kwargs and assembles context units.
* **No second graph writer.** Callers may inject promote hooks for offline
  tests; production default calls the real promote_* APIs (which own
  ``runtime/db_lock``).
* **Idempotent.** Re-promoting the same twin text returns the same content-
  addressed graph node id (promote_* contract).
* **Twin store stays free of DuckDB.** Promotion is orchestration outside
  the EngagementStore protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, Sequence

from .store import EngagementStore
from .twin import TwinKind, TwinNote, list_twin_notes

ViewFormat = Literal["html"]


class PromoteInsightFn(Protocol):
    def __call__(
        self,
        *,
        text: str,
        investigation_id: str,
        source_document_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        embedding_provider: Any = None,
        con: Any = None,
        **kwargs: Any,
    ) -> str: ...


class PromoteQuestionFn(Protocol):
    def __call__(
        self,
        *,
        text: str,
        investigation_id: str,
        source_document_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        embedding_provider: Any = None,
        con: Any = None,
        **kwargs: Any,
    ) -> str: ...


@dataclass(frozen=True)
class TwinPromoteResult:
    """One twin note promoted into a depth-graph insight/question node."""

    twin_note_id: str
    graph_node_id: str
    kind: TwinKind
    text: str
    canonical_text: str
    asset_id: str
    investigation_id: str
    view_format: ViewFormat = "html"

    def to_dict(self) -> dict[str, Any]:
        return {
            "twin_note_id": self.twin_note_id,
            "graph_node_id": self.graph_node_id,
            "kind": self.kind,
            "text": self.text,
            "canonical_text": self.canonical_text,
            "asset_id": self.asset_id,
            "investigation_id": self.investigation_id,
            "view_format": self.view_format,
            "source": "twin_promote",
        }


@dataclass(frozen=True)
class TwinContextUnit:
    """Search/context-pack unit derived from a promoted twin note.

    Stable identity is the graph node id (content-addressed). Twin note id
    and parent asset id ride as provenance so research assembly can cite
    the twin substrate.
    """

    unit_id: str
    twin_note_id: str
    kind: TwinKind
    text: str
    canonical_text: str
    asset_id: str
    investigation_id: str
    source: Literal["twin_promote"] = "twin_promote"
    view_format: ViewFormat = "html"

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "twin_note_id": self.twin_note_id,
            "kind": self.kind,
            "text": self.text,
            "canonical_text": self.canonical_text,
            "asset_id": self.asset_id,
            "investigation_id": self.investigation_id,
            "source": self.source,
            "view_format": self.view_format,
        }


@dataclass(frozen=True)
class TwinPromoteContextResult:
    """Promote all twins for an asset, then assemble search/context units."""

    promoted: tuple[TwinPromoteResult, ...]
    context_units: tuple[TwinContextUnit, ...]
    query: str | None = None
    view_format: ViewFormat = "html"

    def to_dict(self) -> dict[str, Any]:
        return {
            "promoted": [p.to_dict() for p in self.promoted],
            "context_units": [u.to_dict() for u in self.context_units],
            "query": self.query,
            "view_format": self.view_format,
        }


def _canonical_text(text: str) -> str:
    """Match insight_question.canonical_text without importing graph at module load."""
    return " ".join(text.lower().split())


def _default_promote_insight() -> PromoteInsightFn:
    from substrate.graph.insight_question import promote_insight

    return promote_insight


def _default_promote_question() -> PromoteQuestionFn:
    from substrate.graph.insight_question import promote_question

    return promote_question


def expected_graph_node_id(kind: TwinKind, text: str) -> str:
    """Content-addressed graph id for twin text (same as promote_* identity)."""
    from substrate.graph.insight_question import insight_node_id, question_node_id

    if kind == "insight":
        return insight_node_id(text)
    if kind == "question":
        return question_node_id(text)
    raise ValueError(f"unknown twin kind: {kind!r}")


def promote_twin_note(
    note: TwinNote,
    *,
    investigation_id: str | None = None,
    source_document_id: str | None = None,
    promote_insight_fn: PromoteInsightFn | None = None,
    promote_question_fn: PromoteQuestionFn | None = None,
    embedding_provider: Any = None,
    con: Any = None,
    extra_metadata: dict[str, Any] | None = None,
) -> TwinPromoteResult:
    """Promote one twin note into a depth-graph insight or question node.

    Returns a stable ``graph_node_id`` (content-addressed). Re-promotion of
    the same text is idempotent under the promote_* contract.
    """
    if not note.text or not note.text.strip():
        raise ValueError("twin note text is required")
    inv = (
        (investigation_id or note.investigation_id or f"twin_{note.asset_id}").strip()
    )
    if not inv:
        raise ValueError("investigation_id is required")

    meta: dict[str, Any] = {
        "origin": "twin_note",
        "twin_note_id": note.note_id,
        "twin_asset_id": note.asset_id,
        "twin_kind": note.kind,
    }
    if note.source_spawn_id:
        meta["source_spawn_id"] = note.source_spawn_id
    if extra_metadata:
        meta.update(extra_metadata)

    doc_id = source_document_id or note.asset_id
    canon = _canonical_text(note.text)

    if note.kind == "insight":
        fn = promote_insight_fn or _default_promote_insight()
        nid = fn(
            text=note.text,
            investigation_id=inv,
            source_document_id=doc_id,
            metadata=meta,
            embedding_provider=embedding_provider,
            con=con,
        )
    elif note.kind == "question":
        fn = promote_question_fn or _default_promote_question()
        nid = fn(
            text=note.text,
            investigation_id=inv,
            source_document_id=doc_id,
            metadata=meta,
            embedding_provider=embedding_provider,
            con=con,
        )
    else:
        raise ValueError(f"unknown twin kind: {note.kind!r}")

    if not nid or not str(nid).strip():
        raise RuntimeError("promote_* returned empty graph node id")

    return TwinPromoteResult(
        twin_note_id=note.note_id,
        graph_node_id=str(nid),
        kind=note.kind,
        text=note.text,
        canonical_text=canon,
        asset_id=note.asset_id,
        investigation_id=inv,
        view_format="html",
    )


def promote_twin_notes_for_asset(
    asset_id: str,
    *,
    store: EngagementStore,
    investigation_id: str | None = None,
    source_document_id: str | None = None,
    promote_insight_fn: PromoteInsightFn | None = None,
    promote_question_fn: PromoteQuestionFn | None = None,
    embedding_provider: Any = None,
    con: Any = None,
    kinds: Sequence[TwinKind] | None = None,
    note_ids: Sequence[str] | None = None,
) -> list[TwinPromoteResult]:
    """Promote all (or filtered) twin notes for a parent asset.

    Residual (mq): optional ``kinds`` filter (insight | question).
    Residual (mx): optional ``note_ids`` multi-select — exact twin note ids.
    When both set, notes must match kind AND note_id (intersection).
    """
    if not asset_id or not asset_id.strip():
        raise ValueError("asset_id is required")
    notes = list_twin_notes(asset_id, store=store)
    if kinds is not None:
        allowed = set(kinds)
        notes = [n for n in notes if n.kind in allowed]
    # Residual (mx): multi-select by exact twin note_id.
    if note_ids is not None:
        wanted = {str(i).strip() for i in note_ids if str(i).strip()}
        if wanted:
            notes = [n for n in notes if n.note_id in wanted]
        else:
            notes = []
    out: list[TwinPromoteResult] = []
    for note in notes:
        out.append(
            promote_twin_note(
                note,
                investigation_id=investigation_id,
                source_document_id=source_document_id or asset_id.strip(),
                promote_insight_fn=promote_insight_fn,
                promote_question_fn=promote_question_fn,
                embedding_provider=embedding_provider,
                con=con,
            )
        )
    return out


def result_to_context_unit(result: TwinPromoteResult) -> TwinContextUnit:
    return TwinContextUnit(
        unit_id=result.graph_node_id,
        twin_note_id=result.twin_note_id,
        kind=result.kind,
        text=result.text,
        canonical_text=result.canonical_text,
        asset_id=result.asset_id,
        investigation_id=result.investigation_id,
        source="twin_promote",
        view_format=result.view_format,
    )


def search_twin_context(
    units: Sequence[TwinContextUnit],
    *,
    query: str | None = None,
    asset_id: str | None = None,
    kind: TwinKind | None = None,
) -> list[TwinContextUnit]:
    """Filter twin-derived context units for research search/context assembly.

    Pure function: substring match on text/canonical_text (case-insensitive).
    Empty/None query returns all units that pass asset/kind filters.
    """
    q = (query or "").strip().lower()
    out: list[TwinContextUnit] = []
    for u in units:
        if asset_id is not None and u.asset_id != asset_id:
            continue
        if kind is not None and u.kind != kind:
            continue
        if q:
            hay = f"{u.text} {u.canonical_text}".lower()
            if q not in hay:
                continue
        out.append(u)
    return out


def promote_and_context_for_asset(
    asset_id: str,
    *,
    store: EngagementStore,
    query: str | None = None,
    investigation_id: str | None = None,
    source_document_id: str | None = None,
    promote_insight_fn: PromoteInsightFn | None = None,
    promote_question_fn: PromoteQuestionFn | None = None,
    embedding_provider: Any = None,
    con: Any = None,
    kinds: Sequence[TwinKind] | None = None,
    note_ids: Sequence[str] | None = None,
) -> TwinPromoteContextResult:
    """Product entry: twin notes → promote_* → search/context units.

    Drive twice on the same twin fixture: graph_node_id / unit_id stay stable
    (content-addressed promote_* identity).
    Residual (mx): optional note_ids multi-select.
    """
    promoted = promote_twin_notes_for_asset(
        asset_id,
        store=store,
        investigation_id=investigation_id,
        source_document_id=source_document_id,
        promote_insight_fn=promote_insight_fn,
        promote_question_fn=promote_question_fn,
        embedding_provider=embedding_provider,
        con=con,
        kinds=kinds,
        note_ids=note_ids,
    )
    units = [result_to_context_unit(p) for p in promoted]
    filtered = search_twin_context(units, query=query, asset_id=asset_id.strip())
    return TwinPromoteContextResult(
        promoted=tuple(promoted),
        context_units=tuple(filtered),
        query=query,
        view_format="html",
    )


def depth_graph_honesty_fields(
    promoted: Sequence[dict[str, Any]] | Sequence[Any],
    context_units: Sequence[dict[str, Any]] | Sequence[Any],
) -> dict[str, Any]:
    """Compute content-addressed depth-graph honesty fields (residual ajt/ajo).

    Pure: no I/O. ``unit_id`` is expected to equal ``graph_node_id`` for
    recursive note-taker promote→context identity. Never invents edges.
    """
    graph_node_ids: list[str] = []
    for p in promoted or ():
        if not isinstance(p, dict):
            continue
        gid = str(p.get("graph_node_id") or "").strip()
        if gid:
            graph_node_ids.append(gid)
    unique_graph = list(dict.fromkeys(graph_node_ids))
    unit_ids: list[str] = []
    for u in context_units or ():
        if not isinstance(u, dict):
            continue
        uid = str(u.get("unit_id") or "").strip()
        if uid:
            unit_ids.append(uid)
    unique_units = list(dict.fromkeys(unit_ids))
    content_addressed_alignment = bool(unique_graph) and set(unique_graph) == set(
        unique_units
    )
    return {
        "graph_node_ids": unique_graph,
        "unique_graph_node_count": len(unique_graph),
        "unique_unit_id_count": len(unique_units),
        "content_addressed_alignment": content_addressed_alignment,
    }


def twin_promote_context_payload(
    asset_id: str,
    *,
    store: EngagementStore,
    query: str | None = None,
    investigation_id: str | None = None,
    source_document_id: str | None = None,
    promote_insight_fn: PromoteInsightFn | None = None,
    promote_question_fn: PromoteQuestionFn | None = None,
    include_html: bool = True,
    kinds: Sequence[TwinKind] | None = None,
    note_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Settings/workstation product shape for twin promote → context.

    Calls shipped ``promote_and_context_for_asset``. Does not invent twin notes.
    Empty twins → zero promoted units + honest notes (not an error).

    Residual (mq): optional ``kinds`` filter (insight | question) for selective
    promote — recursive note-taker merge of one twin class into context.
    Residual (mx): optional ``note_ids`` multi-select for per-note promote.
    Residual (ajo/ajn): depth-graph honesty fields (graph_node_ids · unit≡node).
    """
    if not asset_id or not str(asset_id).strip():
        raise ValueError("asset_id is required")
    # Normalize kinds: only closed twin kinds; empty → treat as all.
    kinds_norm: tuple[TwinKind, ...] | None = None
    if kinds is not None:
        allowed: list[TwinKind] = []
        for k in kinds:
            raw = str(k or "").strip().lower()
            if raw in ("insight", "question") and raw not in allowed:
                allowed.append(raw)  # type: ignore[arg-type]
        kinds_norm = tuple(allowed) if allowed else None
    # Residual (mx): normalize note_ids (strip empties; preserve order unique).
    note_ids_norm: tuple[str, ...] | None = None
    if note_ids is not None:
        seen: set[str] = set()
        ordered: list[str] = []
        for i in note_ids:
            tok = str(i or "").strip()
            if not tok or tok in seen:
                continue
            seen.add(tok)
            ordered.append(tok)
        note_ids_norm = tuple(ordered)
    result = promote_and_context_for_asset(
        asset_id.strip(),
        store=store,
        query=query,
        investigation_id=investigation_id,
        source_document_id=source_document_id,
        promote_insight_fn=promote_insight_fn,
        promote_question_fn=promote_question_fn,
        kinds=kinds_norm,
        note_ids=note_ids_norm,
    )
    raw = result.to_dict()
    # Residual (ajo/ajt): content-addressed depth-graph honesty (pure helper).
    depth = depth_graph_honesty_fields(raw["promoted"], raw["context_units"])
    unique_graph = depth["graph_node_ids"]
    content_addressed_alignment = depth["content_addressed_alignment"]
    payload: dict[str, Any] = {
        "asset_id": asset_id.strip(),
        "promoted_count": len(result.promoted),
        "context_unit_count": len(result.context_units),
        "promoted": raw["promoted"],
        "context_units": raw["context_units"],
        "query": query,
        "kinds": list(kinds_norm) if kinds_norm is not None else ["insight", "question"],
        "note_ids": list(note_ids_norm) if note_ids_norm is not None else [],
        "graph_node_ids": unique_graph,
        "unique_graph_node_count": depth["unique_graph_node_count"],
        "unique_unit_id_count": depth["unique_unit_id_count"],
        "content_addressed_alignment": content_addressed_alignment,
        "view_format": "html",
        "product_panel": "twin_promote_context",
        "source": "engagement_spine.twin_promote",
        "notes": [],
    }
    if not result.promoted:
        if note_ids_norm is not None and note_ids_norm:
            payload["notes"] = [
                "No matching twin notes for selected note_ids — check selection "
                "or record insights/questions first."
            ]
        else:
            payload["notes"] = [
                "No twin notes to promote — record insights/questions first "
                "(recursive note-taker substrate is empty)."
            ]
    else:
        payload["notes"] = [
            "Twins promoted into content-addressed context units for research prompts.",
            "Re-promote is idempotent (same graph_node_id / unit_id for same text).",
            (
                f"Depth-graph honesty: unique_nodes={len(unique_graph)} · "
                f"unit≡node={str(content_addressed_alignment).lower()}"
            ),
        ]
    if include_html:
        payload["html"] = twin_context_html(
            result.context_units,
            document_id=f"twin-promote-{asset_id.strip()}",
            title=f"Twin promote context · {asset_id.strip()}",
            unique_graph_node_count=len(unique_graph),
            content_addressed_alignment=content_addressed_alignment,
        )
    return payload


def twin_context_html(
    units: Sequence[TwinContextUnit],
    *,
    document_id: str = "twin-context",
    title: str = "Twin-derived research context",
    unique_graph_node_count: int | None = None,
    content_addressed_alignment: bool | None = None,
) -> str:
    """HTML-first human view of twin-derived context units (never PDF).

    Residual (ajo): optional depth-graph honesty strip when promote payload
    provides unique node counts and unit≡node alignment.
    """
    from .project import project_to_html

    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": title}],
        }
    ]
    # Residual (ajo): agent-readable depth-graph honesty on promote HTML.
    if unique_graph_node_count is not None or content_addressed_alignment is not None:
        align = (
            str(bool(content_addressed_alignment)).lower()
            if content_addressed_alignment is not None
            else "unknown"
        )
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Depth-graph · unique_nodes="
                            f"{unique_graph_node_count if unique_graph_node_count is not None else 'n/a'}"
                            f" · content_addressed_alignment={align}"
                            " · view: HTML · never invent graph edges"
                        ),
                    }
                ],
            }
        )
    if not units:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "(no twin-derived units)"}],
            }
        )
    for u in units:
        # Residual (ajo): stamp unit_id (content-addressed graph node) in label.
        label = f"[{u.kind}] [{u.unit_id}] {u.text}"
        blocks.append(
            {
                "type": "paragraph",
                "attrs": {
                    "data-unit-id": u.unit_id,
                    "data-twin-note-id": u.twin_note_id,
                    "data-graph-node-id": u.unit_id,
                },
                "content": [{"type": "text", "text": label}],
            }
        )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id=document_id,
        creator="twin_promote",
    )
