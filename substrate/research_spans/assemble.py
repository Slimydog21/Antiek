"""Synthesis boundary assembler — spans only, no raw-document smuggling.

The assembler builds the synthesis input from ``ExtractiveSpan``
instances **only**.  It is the type-level boundary (doctrine I-2):
the synthesis model sees verbatim, attributed, budgeted extractive
spans — not raw documents, not arbitrary strings, not duck-typed dicts.

Raw documents are parked by content-addressed id for provenance; they
never appear in the assembled context text.

Adjacent attribution shape (SPR-04 compatibility):
    Each span's rendered output carries attribution metadata **adjacent**
    to the verbatim text.  The shape includes full provenance::

        [source: {document_id} | url: {source_url} | rev: {revision} |
         hash: {content_hash} | chunk: {chunk_id} | score: {score:.3f}]
        {verbatim text}

    The full 64-char content hash, URL, revision, and stable span_id
    are mechanically bindable by SPR-04's citation binder.

Content-addressed document parking (REJECT fix #5):
    Document ids are derived from canonical content + source URL +
    revision via full SHA-256 hash.  ``DocumentRecord`` is created
    via the validated factory ``DocumentRecord.create()``; direct
    ``DocumentRecord(...)`` construction is rejected.  The store
    recomputes and verifies on put.  ``Store.get`` returns content.

AttributedSpan (REJECT fix #6):
    Preserves stable ``span_id``, ``document_id``, ``source_url``,
    ``revision``, ``content_hash``, ``start``, ``end``, exact ``text``,
    and ``retrieval_score`` so SPR-04 can mechanically bind offsets.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .floor import FloorTripTrace, InsufficientSources, Requery
from .select import (
    DefaultTokenCounter,
    SelectionResult,
    TokenCounter,
    render_context_text,
    render_span_text,
)
from .span import ExtractiveSpan

# ---------------------------------------------------------------------------
# Content-addressed document record (REJECT fix #5)
# ---------------------------------------------------------------------------


def _compute_document_id(source_url: str, revision: str, content: str) -> str:
    """Compute deterministic full 64-hex SHA-256 document id.

    The id is ``sha256(source_url + revision + content)`` — full 64 hex
    chars, not truncated.  Same inputs always produce the same id.
    """
    canonical = f"{source_url}\x00{revision}\x00{content}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compute_content_hash(content: str) -> str:
    """Compute full 64-hex SHA-256 content hash."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def content_addressed_id(source_url: str, revision: str, content: str) -> str:
    """Derive a stable, collision-safe document id.

    The id is ``sha256(source_url + revision + content)`` — full 64 hex
    chars (256 bits).  This is idempotent: the same inputs always
    produce the same id.
    """
    return _compute_document_id(source_url, revision, content)


def content_hash(content: str) -> str:
    """Compute a full 64-hex SHA-256 content hash for integrity verification."""
    return _compute_content_hash(content)


# DocumentRecord construction sentinel (private, constant reference).
_DOCUMENT_RECORD_TOKEN = object()


class DocumentRecord:
    """A raw document record with content-addressed id and exact content.

    ``document_id`` is derived from
    ``sha256(source_url + revision + content)`` — full 64 hex chars.
    ``source_url`` is the canonical URL of the document.
    ``revision`` is the caller's revision identifier.
    ``content_hash`` is ``sha256(content)`` — full 64 hex chars.
    ``content`` is the exact raw content of the document.
    ``title`` is the document's title (not faked from id).
    ``ip_holder_id`` is the IP holder identifier (may be None).
    ``source_tier`` is the source quality tier.

    Direct ``DocumentRecord(...)`` construction is **rejected**.
    Use ``DocumentRecord.create()`` to construct.
    """

    document_id: str
    source_url: str
    revision: str
    content_hash: str
    content: str
    title: str
    ip_holder_id: str | None
    source_tier: int

    __slots__ = (
        "document_id", "source_url", "revision", "content_hash",
        "content", "title", "ip_holder_id", "source_tier",
    )

    def __new__(cls, *args: Any, **kwargs: Any) -> DocumentRecord:
        if not args or args[0] is not _DOCUMENT_RECORD_TOKEN:
            raise TypeError(
                "DocumentRecord cannot be constructed directly — "
                "use DocumentRecord.create() to construct"
            )
        return super().__new__(cls)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("DocumentRecord cannot be subclassed")

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("DocumentRecord is frozen")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("DocumentRecord is frozen")

    def _validate(self) -> None:
        """Recompute and verify hashes; refuse mismatch."""
        expected_doc_id = _compute_document_id(
            self.source_url, self.revision, self.content
        )
        if self.document_id != expected_doc_id:
            raise ValueError(
                f"document_id mismatch: expected {expected_doc_id!r}, "
                f"got {self.document_id!r}"
            )
        expected_content_hash = _compute_content_hash(self.content)
        if self.content_hash != expected_content_hash:
            raise ValueError(
                f"content_hash mismatch: expected {expected_content_hash!r}, "
                f"got {self.content_hash!r}"
            )
        if not self.source_url:
            raise ValueError("source_url must be non-empty")
        if not self.revision:
            raise ValueError("revision must be non-empty")
        if not self.content:
            raise ValueError("content must be non-empty")
        if not self.title:
            raise ValueError("title must be non-empty")
        if len(self.document_id) != 64:
            raise ValueError(
                f"document_id must be 64 hex chars, got {len(self.document_id)}"
            )
        if len(self.content_hash) != 64:
            raise ValueError(
                f"content_hash must be 64 hex chars, got {len(self.content_hash)}"
            )

    @classmethod
    def create(
        cls,
        *,
        source_url: str,
        revision: str,
        content: str,
        title: str,
        ip_holder_id: str | None = None,
        source_tier: int = 3,
    ) -> DocumentRecord:
        """Validated factory: compute document_id and content_hash from inputs.

        Computes full 64-hex SHA-256 hashes.  Validates all inputs.
        Identical inputs always produce the same record.
        """
        if not isinstance(source_url, str):
            raise TypeError(
                f"source_url must be str, got {type(source_url).__name__}"
            )
        if not isinstance(revision, str):
            raise TypeError(
                f"revision must be str, got {type(revision).__name__}"
            )
        if not isinstance(content, str):
            raise TypeError(
                f"content must be str, got {type(content).__name__}"
            )
        if not isinstance(title, str):
            raise TypeError(f"title must be str, got {type(title).__name__}")
        if not source_url:
            raise ValueError("source_url must be non-empty")
        if not revision:
            raise ValueError("revision must be non-empty")
        if not content:
            raise ValueError("content must be non-empty")
        if not title:
            raise ValueError("title must be non-empty")

        doc_id = _compute_document_id(source_url, revision, content)
        c_hash = _compute_content_hash(content)

        obj = cls.__new__(cls, _DOCUMENT_RECORD_TOKEN)
        sa = object.__setattr__
        sa(obj, "document_id", doc_id)
        sa(obj, "source_url", source_url)
        sa(obj, "revision", revision)
        sa(obj, "content_hash", c_hash)
        sa(obj, "content", content)
        sa(obj, "title", title)
        sa(obj, "ip_holder_id", ip_holder_id)
        sa(obj, "source_tier", source_tier)
        obj._validate()
        return obj

    def verify_content(self) -> None:
        """Recompute and verify document_id and content_hash from stored content.

        Raises ValueError if hashes don't match.
        """
        expected_doc_id = _compute_document_id(
            self.source_url, self.revision, self.content
        )
        if self.document_id != expected_doc_id:
            raise ValueError(
                f"document_id mismatch on verify: expected {expected_doc_id!r}, "
                f"got {self.document_id!r}"
            )
        expected_content_hash = _compute_content_hash(self.content)
        if self.content_hash != expected_content_hash:
            raise ValueError(
                f"content_hash mismatch on verify: expected {expected_content_hash!r}, "
                f"got {self.content_hash!r}"
            )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DocumentRecord):
            return NotImplemented
        return (
            self.document_id == other.document_id
            and self.source_url == other.source_url
            and self.revision == other.revision
            and self.content_hash == other.content_hash
            and self.content == other.content
            and self.title == other.title
            and self.ip_holder_id == other.ip_holder_id
            and self.source_tier == other.source_tier
        )

    def __hash__(self) -> int:
        return hash((
            self.document_id, self.source_url, self.revision,
            self.content_hash, self.title,
        ))

    def __repr__(self) -> str:
        return (
            f"DocumentRecord(doc_id={self.document_id[:12]}…, "
            f"url={self.source_url!r}, rev={self.revision!r})"
        )


# ---------------------------------------------------------------------------
# Document store protocol (REJECT fix #5)
# ---------------------------------------------------------------------------


@runtime_checkable
class DocumentStore(Protocol):
    """Collision-safe idempotent document store.

    ``put`` stores a document record.  If a record with the same
    ``document_id`` already exists, the store verifies consistency:
    the stored record must match the new one (same source_url,
    revision, content_hash, content).  If they conflict, ``put``
    raises ``ValueError``.

    ``get`` retrieves a record by ``document_id``.  Returns ``None``
    if not found.  The returned record carries the exact raw content.

    ``contains`` checks if a record exists.
    """

    def put(self, record: DocumentRecord) -> None: ...
    def get(self, document_id: str) -> DocumentRecord | None: ...
    def contains(self, document_id: str) -> bool: ...


class InMemoryDocumentStore:
    """Deterministic in-memory document store for tests and isolation.

    REJECT fix #5: collision-safe idempotent storage.
    Store.put recomputes and verifies hashes.
    Store.get returns content.
    """

    def __init__(self) -> None:
        self._records: dict[str, DocumentRecord] = {}

    def put(self, record: DocumentRecord) -> None:
        """Store a document record.  Recomputes and verifies hashes."""
        # Recompute and verify (never trust caller-supplied hashes).
        expected_doc_id = _compute_document_id(
            record.source_url, record.revision, record.content
        )
        expected_content_hash = _compute_content_hash(record.content)
        if record.document_id != expected_doc_id:
            raise ValueError(
                f"document_id mismatch in put: expected {expected_doc_id!r}, "
                f"got {record.document_id!r}"
            )
        if record.content_hash != expected_content_hash:
            raise ValueError(
                f"content_hash mismatch in put: expected {expected_content_hash!r}, "
                f"got {record.content_hash!r}"
            )

        existing = self._records.get(record.document_id)
        if existing is not None:
            # Verify consistency — idempotent put is fine, conflict is not.
            if (
                existing.source_url != record.source_url
                or existing.revision != record.revision
                or existing.content_hash != record.content_hash
                or existing.content != record.content
            ):
                raise ValueError(
                    f"Document id collision: {record.document_id!r} "
                    f"already exists with different metadata. "
                    f"Existing: url={existing.source_url!r}, "
                    f"rev={existing.revision!r}. "
                    f"New: url={record.source_url!r}, "
                    f"rev={record.revision!r}."
                )
            # Idempotent put — same record, no-op.
            return
        self._records[record.document_id] = record

    def get(self, document_id: str) -> DocumentRecord | None:
        """Retrieve a record by document_id.  Returns the record with content."""
        return self._records.get(document_id)

    def contains(self, document_id: str) -> bool:
        return document_id in self._records


# ---------------------------------------------------------------------------
# Attributed span (REJECT fix #6 — the shape SPR-04 binds to)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttributedSpan:
    """One span rendered with adjacent attribution.

    REJECT fix #6: preserves stable ``span_id``, ``document_id``,
    ``source_url``, ``revision``, ``content_hash``, ``start``, ``end``,
    exact ``text``, and ``retrieval_score`` so SPR-04 can mechanically
    bind offsets.  The attribution rendered string includes full stable
    span id, URL, revision, content hash, start/end so the model-facing
    context itself is mechanically bindable.
    """

    span_id: str
    text: str
    attribution: str
    document_id: str
    chunk_id: str
    source_url: str
    revision: str
    content_hash: str
    start: int
    end: int
    retrieval_score: float
    tokens: int


# ---------------------------------------------------------------------------
# Assembled context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssembledContext:
    """The synthesis input assembled from spans only.

    ``text`` is the full context string passed to the synthesis model.
    ``spans`` are the attributed spans that compose it.
    ``document_store`` is the store containing referenced document records.
    ``total_tokens`` is the token count of the assembled text.
    ``source_document_ids`` are the unique document ids referenced.
    ``floor_trace`` is the floor trip trace if the floor tripped, else None.
    """

    text: str
    spans: tuple[AttributedSpan, ...]
    document_store: DocumentStore
    total_tokens: int
    floor_trace: FloorTripTrace | None = None

    @property
    def source_document_ids(self) -> tuple[str, ...]:
        """Unique document ids in the assembled context, in order."""
        seen: set[str] = set()
        out: list[str] = []
        for s in self.spans:
            if s.document_id not in seen:
                seen.add(s.document_id)
                out.append(s.document_id)
        return tuple(out)


# ---------------------------------------------------------------------------
# Floor-aware result (REJECT fix #4 — trace preservation)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FloorAwareResult:
    """Wrapper that preserves the floor trace for any outcome.

    REJECT fix #4: no convenience API may discard the trace.
    ``assemble_or_refuse`` returns this instead of a bare union.
    """

    outcome: AssembledContext | Requery | InsufficientSources
    trace: FloorTripTrace | None


# ---------------------------------------------------------------------------
# Rendering — uses shared canonical render_and_count from select.py
# ---------------------------------------------------------------------------


def _render_attributed_span(
    span: ExtractiveSpan,
    counter: TokenCounter,
    record: DocumentRecord,
) -> AttributedSpan:
    """Render one span with adjacent attribution (SPR-04 shape).

    The attribution includes full provenance: span_id, document_id,
    URL, revision, content hash, chunk_id, score.  The model-facing
    context is mechanically bindable.
    """
    rendered = render_span_text(span)
    attribution = rendered.split("\n", 1)[0]
    tokens = counter.count(rendered)
    if isinstance(tokens, bool) or not isinstance(tokens, int):
        raise TypeError("counter.count must return a non-boolean int")
    if tokens < 0:
        raise ValueError(f"counter.count returned negative ({tokens})")
    return AttributedSpan(
        span_id=span.span_id,
        text=span.text,
        attribution=attribution,
        document_id=span.document_id,
        chunk_id=span.chunk_id,
        source_url=span.source_url,
        revision=span.revision,
        content_hash=record.content_hash,
        start=span.start,
        end=span.end,
        retrieval_score=span.retrieval_score,
        tokens=tokens,
    )


# ---------------------------------------------------------------------------
# Runtime guard: reject non-span inputs
# ---------------------------------------------------------------------------


def _validate_span(obj: Any, idx: int) -> ExtractiveSpan:
    """Runtime guard: reject anything that is not an ExtractiveSpan.

    This covers untyped callers that might smuggle in a raw document,
    a dict, a string, or an ``Any``-typed value.  The type signature
    of ``assemble_from_spans`` already enforces the boundary for typed
    callers (mypy will reject ``str`` or ``dict``); this guard is the
    safety net for dynamic / reflection-based callers.
    """
    if not isinstance(obj, ExtractiveSpan):
        raise TypeError(
            f"assemble_from_spans accepts ExtractiveSpan only — "
            f"item {idx} is {type(obj).__name__!r}, not an ExtractiveSpan. "
            f"Raw documents, dicts, strings, and Any-typed values cannot "
            f"reach the assembler."
        )
    return obj


# ---------------------------------------------------------------------------
# Document store validation — verify span against stored content
# ---------------------------------------------------------------------------


def _validate_documents(
    spans: Sequence[ExtractiveSpan],
    store: DocumentStore,
) -> dict[str, DocumentRecord]:
    """Verify all spans against stored document records.

    For each span, verifies:
    - document_id exists in the store
    - span's source_url matches stored record's source_url
    - span's revision matches stored record's revision
    - span's content_hash matches stored record's content_hash
    - span's text matches stored content[start:end]
    - span's document_id matches stored record's document_id

    REJECT fix #5: assembler must require exact source records
    and reject missing/mismatched documents.
    """
    records: dict[str, DocumentRecord] = {}
    for i, span in enumerate(spans):
        record = store.get(span.document_id)
        if record is None:
            raise ValueError(
                f"Span {i} references document {span.document_id!r} "
                f"which is not in the document store.  Park the document "
                f"before assembling."
            )
        record.verify_content()
        # Verify span matches stored record.
        if span.source_url != record.source_url:
            raise ValueError(
                f"Span {i} source_url {span.source_url!r} does not match "
                f"stored record source_url {record.source_url!r}"
            )
        if span.revision != record.revision:
            raise ValueError(
                f"Span {i} revision {span.revision!r} does not match "
                f"stored record revision {record.revision!r}"
            )
        if span.content_hash != record.content_hash:
            raise ValueError(
                f"Span {i} content_hash {span.content_hash!r} does not match "
                f"stored record content_hash {record.content_hash!r}"
            )
        if span.document_id != record.document_id:
            raise ValueError(
                f"Span {i} document_id {span.document_id!r} does not match "
                f"stored record document_id {record.document_id!r}"
            )
        # Verify span text matches stored content slice.
        stored_slice = record.content[span.start : span.end]
        if span.text != stored_slice:
            raise ValueError(
                f"Span {i} text does not match stored content[{span.start}:{span.end}]. "
                f"Expected {stored_slice!r}, got {span.text!r}"
            )
        records[span.document_id] = record
    return records


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def assemble_from_spans(
    spans: Sequence[ExtractiveSpan],
    *,
    counter: TokenCounter | None = None,
    separator: str = "\n---\n",
    document_store: DocumentStore | None = None,
    floor_trace: FloorTripTrace | None = None,
) -> AssembledContext:
    """Assemble synthesis context from spans ONLY.

    Type-level boundary: mypy rejects any call that passes a ``str``,
    ``dict``, ``Document``, or ``Any`` where ``Sequence[ExtractiveSpan]``
    is expected.  The runtime guard (``_validate_span``) covers
    untyped callers.

    REJECT fix #2: signature is ``Sequence[ExtractiveSpan]``.
    REJECT fix #5: requires document store for provenance.  Verifies
    span document_id, url, revision, content_hash, source slice, and
    exact text all match stored content.
    REJECT fix #6: AttributedSpan carries full provenance fields
    including revision and content_hash.

    Args:
        spans: The spans to assemble. Must be ``ExtractiveSpan``
            instances — the runtime guard rejects anything else.
        counter: Injectable token counter.
        separator: Separator between attributed spans in the output.
        document_store: Document store for provenance.  If None,
            an empty in-memory store is created (no documents parked).
        floor_trace: Floor trip trace to preserve (REJECT fix #4).

    Returns:
        ``AssembledContext`` with the rendered text, attributed spans,
        document store, and token count.
    """
    counter = counter or DefaultTokenCounter()
    store = document_store or InMemoryDocumentStore()

    # Validate every span (runtime guard against smuggling).
    validated = [_validate_span(s, i) for i, s in enumerate(spans)]

    # Verify all documents are in the store and span matches stored content.
    records = _validate_documents(validated, store)

    # Render each span with adjacent attribution (full provenance).
    attributed = [
        _render_attributed_span(s, counter, records[s.document_id])
        for s in validated
    ]

    # Compose the final text.
    text = render_context_text(validated, separator)
    total_tokens = counter.count(text)
    if isinstance(total_tokens, bool) or not isinstance(total_tokens, int):
        raise TypeError("counter.count must return a non-boolean int")
    if total_tokens < 0:
        raise ValueError(f"counter.count returned negative ({total_tokens})")

    return AssembledContext(
        text=text,
        spans=tuple(attributed),
        document_store=store,
        total_tokens=total_tokens,
        floor_trace=floor_trace,
    )


def assemble_or_refuse(
    selection: SelectionResult,
    *,
    counter: TokenCounter | None = None,
    threshold: float = 0.3,
    initial_top_k: int = 5,
    current_attempt: int = 0,
    document_store: DocumentStore | None = None,
) -> FloorAwareResult:
    """Assemble from a selection, or refuse if the floor trips.

    Takes a ``SelectionResult`` (from ``extract_select`` or
    ``_select_candidates``) to enforce the select-before-floor invariant
    (REJECT fix #3).

    REJECT fix #4: returns ``FloorAwareResult`` which preserves the
    floor trace for ALL outcomes (pass and trip).

    REJECT fix F: the counter used for assembly is the one bound to
    the SelectionResult, ensuring budget accounting consistency.
    If a counter is explicitly passed, it must be the same object
    as the one bound to the SelectionResult.

    Args:
        selection: The selection result from ``extract_select``.
        counter: Injectable token counter.  If provided, must be the
            same object as selection._bound_counter.  If None, uses
            the counter bound to the SelectionResult.
        threshold: Floor quality threshold.
        initial_top_k: Initial top_k for re-query suggestion.
        current_attempt: Current re-query attempt (0-indexed).
        document_store: Document store for provenance.

    Returns:
        ``FloorAwareResult`` with the outcome and trace.
    """
    from .floor import check_floor

    # Use the bound counter from SelectionResult (budget accounting
    # consistency — assembly cannot switch to a different counter).
    bound_counter = selection._bound_counter

    if counter is not None and counter is not bound_counter:
        raise ValueError(
            "Cannot pass a different counter to assemble_or_refuse — "
            "the counter is bound to the SelectionResult for budget "
            "accounting consistency"
        )

    outcome, trace = check_floor(
        selection,
        threshold=threshold,
        initial_top_k=initial_top_k,
        current_attempt=current_attempt,
    )

    if isinstance(outcome, (Requery, InsufficientSources)):
        return FloorAwareResult(outcome=outcome, trace=trace)

    # Floor passed — assemble using the bound counter and render function.
    ctx = assemble_from_spans(
        list(outcome.selected),
        counter=bound_counter,
        document_store=document_store,
        floor_trace=trace,
    )
    if ctx.total_tokens != selection.total_tokens:
        raise ValueError(
            "Assembled token total changed after selection: "
            f"selected={selection.total_tokens}, assembled={ctx.total_tokens}"
        )
    if ctx.total_tokens > selection.budget:
        raise ValueError(
            f"Assembled token total ({ctx.total_tokens}) exceeds "
            f"selection budget ({selection.budget})"
        )
    return FloorAwareResult(outcome=ctx, trace=trace)
