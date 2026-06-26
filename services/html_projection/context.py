"""Render context (HPRJ SPR-02 / M2).

``RenderContext`` is the bag of inputs the renderer needs BEYOND the
doc-model itself: provenance for the footer, and the substrate ref
resolver for M6 tombstone semantics.

DETERMINISM CONTRACT: the renderer is pure and offline. That means the
context MUST NOT carry wall-clock time, randomness, network handles, or
mutable global state. Every field here is either (a) a value derived
from substrate state (timestamps that are DATA, not wall-clock) or
(b) a pure callable. The determinism tests (M5) prove the renderer
produces byte-identical output for the same (doc_model, ctx); if a
future field introduces variance, those tests go red.

REF RESOLUTION (M6): doc-models reference substrate content by ``ref_id``
(see ``substrate/notebooks/tiptap_codec.py`` ``_extract_ref_id``). The
renderer resolves a ref LIVE at render time — it never denormalises
substrate content into the doc-model. A ref that resolves returns its
payload; a ref that is MISSING or DELETED returns a ``Tombstone``. The
renderer renders the SAME tombstone the live notebook surface shows
(``substrate/notebooks/__init__.py`` docstring: "This claim was deleted
on YYYY-MM-DD; prior text was..."). A missing/deleted ref is never a
crash, never a silent drop.

The ref resolver is a PROTOCOL, not a concrete substrate call, so the
renderer stays decoupled from the substrate (pure + offline + testable
without a DuckDB connection). Tests inject a dict-backed resolver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol


@dataclass(frozen=True)
class Tombstone:
    """The render-time tombstone for a deleted/missing substrate ref.

    Mirrors the live notebook surface's tombstone contract
    (``substrate/notebooks/__init__.py`` lines 20-21): "This <kind> was
    deleted on YYYY-MM-DD; prior text was...". A tombstone is rendered
    by the renderer's tombstone partial and is byte-stable for the same
    inputs.

    Attributes
    ----------
    kind:
        Human label for the referenced object type ("claim", "note",
        "region", etc.). Surfaces in the tombstone label.
    deleted_at:
        ISO-8601 string from substrate state (the deletion event time),
        or ``None`` when the ref was never found (missing, not deleted).
        This is DATA from the substrate, never wall-clock.
    prior_text:
        The text the ref pointed to before deletion, if the substrate
        retained it. ``None`` when unavailable.
    ref_id:
        The ref_id that failed to resolve. Surfaces so the reader can
        locate the dangling reference.
    """

    kind: str
    deleted_at: Optional[str]
    prior_text: Optional[str]
    ref_id: str


@dataclass(frozen=True)
class ResolvedRef:
    """A successfully resolved substrate reference.

    ``payload`` is the live substrate state for the ref (a claim's text,
    a note's body, a region's passage, etc.). The renderer does not
    prescribe its shape — each partial knows its own ref's payload.
    ``kind`` is the object-type label (matches ``Tombstone.kind``).
    """

    kind: str
    payload: dict[str, Any]


class RefResolver(Protocol):
    """Protocol for resolving a substrate ``ref_id`` at render time.

    Implementations MUST be pure with respect to wall-clock: a deleted
    ref's ``deleted_at`` comes from substrate state (a stored event
    time), not from ``datetime.now``. Implementations MUST NOT raise for
    a missing/deleted ref — they return a ``Tombstone`` instead. The only
    acceptable raise is for a programmer error (wrong type passed), which
    is a bug, not a render-time condition.

    The ``block_type`` argument lets a resolver disambiguate ref_id
    namespaces (a ``claim_id`` and a ``note_id`` could collide as bare
    strings; the block type names the namespace).
    """

    def __call__(
        self, ref_id: str, block_type: str
    ) -> ResolvedRef | Tombstone: ...


@dataclass(frozen=True)
class RenderContext:
    """Inputs to ``render`` beyond the doc-model.

    All fields are deterministic by construction. The renderer does not
    read wall-clock; timestamps here are substrate-derived DATA.

    Attributes
    ----------
    resolver:
        Resolves substrate refs at render time. ``None`` means no
        substrate is attached (e.g. rendering a container offline) —
        every ref-bearing block renders its tombstone with
        ``deleted_at=None`` (missing, not deleted). This is the honest
        behavior: without a resolver, refs cannot be verified live, so
        the surface says so rather than inventing content.
    provenance:
        Footer provenance fields. All optional; the footer renders with
        whatever is present. ``rendered_at`` is a substrate-derived
        timestamp (e.g. the doc's ``updated_at``), NOT wall-clock — the
        caller is responsible for passing a stored value. If absent, the
        footer omits the timestamp line (deterministic: same ctx → same
        bytes).
    schema_version:
        The data-island schema version stamped into the embedded
        doc-model. Defaults to ``"1"`` (the version this sprint ships).
    """

    resolver: Optional[RefResolver] = None
    provenance: "Provenance" = field(default_factory=lambda: Provenance())
    schema_version: str = "1"


@dataclass(frozen=True)
class Provenance:
    """Footer provenance. Every field optional; footer renders what's
    present. None of these are wall-clock — they are stored substrate
    values the caller supplies.

    The footer text is built by the renderer from these fields; the
    field set is closed so the footer is byte-stable for a given ctx.
    """

    document_id: Optional[str] = None
    notebook_id: Optional[str] = None
    title: Optional[str] = None
    content_class: Optional[str] = None
    schema_version: Optional[str] = None
    creator_user_id: Optional[str] = None
    rendered_at: Optional[str] = None
    signature_valid: Optional[bool] = None


# ── Convenience resolver implementations for tests ──


class DictRefResolver:
    """A dict-backed ``RefResolver`` for tests and offline renders.

    ``refs`` maps ``(block_type, ref_id)`` → ``ResolvedRef``. Any ref not
    in the map returns a ``Tombstone(kind=block_type, deleted_at=None,
    prior_text=None, ref_id=ref_id)`` — the "missing, not deleted" case.
    For the "deleted" case, put a ``Tombstone`` value in the map.

    Deterministic: dict lookup is order-independent; the same map + the
    same ref yields the same result.
    """

    def __init__(
        self,
        refs: dict[tuple[str, str], ResolvedRef | Tombstone] | None = None,
    ) -> None:
        self._refs: dict[tuple[str, str], ResolvedRef | Tombstone] = dict(
            refs or {}
        )

    def __call__(
        self, ref_id: str, block_type: str
    ) -> ResolvedRef | Tombstone:
        found = self._refs.get((block_type, ref_id))
        if found is not None:
            return found
        return Tombstone(
            kind=_kind_label(block_type),
            deleted_at=None,
            prior_text=None,
            ref_id=ref_id,
        )


def _kind_label(block_type: str) -> str:
    """Human label for a block type's referenced object."""
    return {
        "claim_card": "claim",
        "region_embed": "region",
        "note": "note",
        "question_card": "question",
        "cross_doc_link": "document",
        "chat_exchange": "exchange",
        "master_md_section": "synthesis",
        "image": "image",
    }.get(block_type, block_type)


__all__ = [
    "DictRefResolver",
    "Provenance",
    "RefResolver",
    "RenderContext",
    "ResolvedRef",
    "Tombstone",
]
