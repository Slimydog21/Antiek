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
) -> list[TwinPromoteResult]:
    """Promote all (or filtered-kind) twin notes for a parent asset."""
    if not asset_id or not asset_id.strip():
        raise ValueError("asset_id is required")
    notes = list_twin_notes(asset_id, store=store)
    if kinds is not None:
        allowed = set(kinds)
        notes = [n for n in notes if n.kind in allowed]
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
) -> TwinPromoteContextResult:
    """Product entry: twin notes → promote_* → search/context units.

    Drive twice on the same twin fixture: graph_node_id / unit_id stay stable
    (content-addressed promote_* identity).
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
    )
    units = [result_to_context_unit(p) for p in promoted]
    filtered = search_twin_context(units, query=query, asset_id=asset_id.strip())
    return TwinPromoteContextResult(
        promoted=tuple(promoted),
        context_units=tuple(filtered),
        query=query,
        view_format="html",
    )


def twin_context_html(
    units: Sequence[TwinContextUnit],
    *,
    document_id: str = "twin-context",
    title: str = "Twin-derived research context",
) -> str:
    """HTML-first human view of twin-derived context units (never PDF)."""
    from .project import project_to_html

    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": title}],
        }
    ]
    if not units:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "(no twin-derived units)"}],
            }
        )
    for u in units:
        label = f"[{u.kind}] {u.text}"
        blocks.append(
            {
                "type": "paragraph",
                "attrs": {
                    "data-unit-id": u.unit_id,
                    "data-twin-note-id": u.twin_note_id,
                },
                "content": [{"type": "text", "text": label}],
            }
        )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id=document_id,
        creator="twin_promote",
    )
