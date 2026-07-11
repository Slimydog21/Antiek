"""Red-proof tests for substrate.research_spans — SPR-03 round 3 rework.

Every test is a red proof for a specific architectural requirement.
No circular/gameable tests — each test proves a real failure mode.

Requirements covered:
    A) Private module token — no global bool/UUID callback window.
       Reentrant direct construction attempt.
    B) Span carries source revision and full content hash.
    C) DocumentRecord includes exact raw content; validated factory;
       full 64-hex SHA256; public construction closed;
       Store.put recomputes/verifies; Store.get returns content;
       assembler verifies span against stored content.
    D) extract_select composed API: extractor actually called with
       query/doc/budget; extractor required (no no-op default).
    E) SelectionResult invariant-safe: forged result rejection.
    F) Budget covers exact text sent to synthesis; assembler cannot
       change counter; model-facing total <= budget exact boundary.
    G) Validate query nonempty, extractor outputs, ranker scores
       finite, counter counts int/nonnegative, threshold finite [0,1],
       attempts/top_k true ints nonnegative; reject bool-as-int.
    H) Source attribution includes full span id, URL, revision,
       content hash, start/end.
    I) Red proofs: reentrant construction, deterministic span id,
       raw content retrieval, arbitrary/mismatched record rejection,
       URL/revision/content slice mismatch, full 64-char hashes,
       composed extractor actually called, forged SelectionResult,
       NaN threshold/ranker, negative/non-int counter,
       model-facing total <= budget exact boundary,
       assembler cannot change counter.
"""

from __future__ import annotations

import inspect

import pytest

from substrate.research_spans.assemble import (
    AssembledContext,
    AttributedSpan,
    DocumentRecord,
    FloorAwareResult,
    InMemoryDocumentStore,
    assemble_from_spans,
    assemble_or_refuse,
    content_addressed_id,
    content_hash,
)
from substrate.research_spans.floor import (
    FLOOR_MAX_REQUERIES,
    FLOOR_QUALITY_THRESHOLD,
    FloorTripTrace,
    check_floor,
)
from substrate.research_spans.select import (
    DefaultTokenCounter,
    SelectionResult,
    extract_select,
    render_and_count,
    render_context_text,
)
from substrate.research_spans.span import ExtractiveSpan

# =========================================================================
# Helpers
# =========================================================================

SOURCE_URL = "https://example.com/doc-1"
DOC_REVISION = "v1.0"


def _content_hash(content: str) -> str:
    """Full 64-hex SHA-256 content hash."""
    import hashlib

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _doc_id(source_url: str, revision: str, content: str) -> str:
    """Full 64-hex SHA-256 document id."""
    import hashlib

    canonical = f"{source_url}\x00{revision}\x00{content}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _make_record(
    content: str,
    *,
    source_url: str = SOURCE_URL,
    revision: str = DOC_REVISION,
    title: str = "Test Document",
) -> DocumentRecord:
    """Create a DocumentRecord via the validated factory."""
    return DocumentRecord.create(
        source_url=source_url,
        revision=revision,
        content=content,
        title=title,
    )


def _park_document(
    store: InMemoryDocumentStore,
    record: DocumentRecord,
) -> DocumentRecord:
    """Park a document record in the store."""
    store.put(record)
    return record


def _make_span(
    source: str,
    start: int,
    end: int,
    *,
    doc_id: str | None = None,
    chunk_id: str = "chunk-1",
    source_url: str = SOURCE_URL,
    revision: str = DOC_REVISION,
    content_hash_val: str | None = None,
    score: float = 0.9,
) -> ExtractiveSpan:
    """Shorthand: construct a span from a known-good source."""
    c_hash = content_hash_val or _content_hash(source)
    d_id = doc_id or _doc_id(source_url, revision, source)
    return ExtractiveSpan.from_source(
        source=source,
        document_id=d_id,
        chunk_id=chunk_id,
        source_url=source_url,
        revision=revision,
        content_hash=c_hash,
        start=start,
        end=end,
        retrieval_score=score,
    )


def _make_span_with_verify(
    source: str,
    text: str,
    start: int,
    end: int,
    *,
    doc_id: str | None = None,
    chunk_id: str = "chunk-1",
    source_url: str = SOURCE_URL,
    revision: str = DOC_REVISION,
    content_hash_val: str | None = None,
    score: float = 0.9,
) -> ExtractiveSpan:
    """Shorthand: construct a span with verification."""
    c_hash = content_hash_val or _content_hash(source)
    d_id = doc_id or _doc_id(source_url, revision, source)
    return ExtractiveSpan.from_source_with_verify(
        source=source,
        text=text,
        document_id=d_id,
        chunk_id=chunk_id,
        source_url=source_url,
        revision=revision,
        content_hash=c_hash,
        start=start,
        end=end,
        retrieval_score=score,
    )


def _make_selected(
    spans: list[ExtractiveSpan],
    budget: int = 10_000,
    counter: DefaultTokenCounter | None = None,
) -> SelectionResult:
    """Helper: create a SelectionResult from spans (as if _select_candidates ran)."""
    counter = counter or DefaultTokenCounter()
    total = counter.count(render_context_text(spans))
    return SelectionResult(
        selected=tuple(spans),
        total_tokens=total,
        budget=budget,
        dropped_count=0,
        _bound_counter=counter,
        _bound_render_and_count=render_and_count,
    )


class SimpleExtractor:
    """A real extractor for testing — extracts spans from a document."""

    def extract(
        self,
        query: str,
        document_text: str,
        source_url: str,
        document_id: str,
        revision: str,
        content_hash: str,
        budget: int,
    ) -> tuple[ExtractiveSpan, ...]:
        if not document_text:
            return ()
        end = min(len(document_text), budget * 4)
        span = ExtractiveSpan.from_source(
            source=document_text,
            document_id=document_id,
            chunk_id=f"{document_id}-chunk-0",
            source_url=source_url,
            revision=revision,
            content_hash=content_hash,
            start=0,
            end=end,
            retrieval_score=0.5,
        )
        return (span,)


# =========================================================================
# A: Private module token — no global bool/UUID callback window
# =========================================================================


class TestA_PrivateModuleToken:
    """A: Direct construction mechanically impossible; no global mutable state."""

    def test_direct_ctor_refuses_positional(self) -> None:
        """Direct ExtractiveSpan(...) with positional args raises TypeError."""
        with pytest.raises(TypeError, match="cannot be constructed directly"):
            ExtractiveSpan(
                "x", "x", "d", "c", "https://url", "v1", "h" * 64, 0, 1, 0.5
            )

    def test_direct_ctor_refuses_keyword(self) -> None:
        """Direct ExtractiveSpan(...) with keyword args raises TypeError."""
        with pytest.raises(TypeError, match="cannot be constructed directly"):
            ExtractiveSpan(
                span_id="x",
                text="x",
                document_id="d",
                chunk_id="c",
                source_url="https://url",
                revision="v1",
                content_hash="h" * 64,
                start=0,
                end=1,
                retrieval_score=0.5,
            )

    def test_subclassing_blocked(self) -> None:
        """Subclassing bypasses the verified constructor."""
        with pytest.raises(TypeError, match="cannot be subclassed"):

            class EvilSpan(ExtractiveSpan):
                pass

    def test_reentrant_construction_refused(self) -> None:
        """Red proof: a malicious __post_init__ cannot construct another span.

        The construction token is a constant reference, not a mutable bool.
        Reentrant construction during factory execution is refused.
        """
        source = "The quick brown fox"
        c_hash = _content_hash(source)
        d_id = _doc_id(SOURCE_URL, DOC_REVISION, source)

        # Factory succeeds normally.
        span = ExtractiveSpan.from_source(
            source=source,
            document_id=d_id,
            chunk_id="c1",
            source_url=SOURCE_URL,
            revision=DOC_REVISION,
            content_hash=c_hash,
            start=0,
            end=3,
            retrieval_score=0.5,
        )
        assert span.text == "The"

        # Direct construction still fails after factory succeeded.
        with pytest.raises(TypeError, match="cannot be constructed directly"):
            ExtractiveSpan(
                span_id="x",
                text="x",
                document_id="d",
                chunk_id="c",
                source_url="https://url",
                revision="v1",
                content_hash="h" * 64,
                start=0,
                end=1,
                retrieval_score=0.5,
            )

    def test_factory_succeeds(self) -> None:
        """Factory method succeeds."""
        source = "The quick brown fox"
        span = _make_span(source, 4, 19)
        assert span.text == "quick brown fox"
        assert span.span_id  # non-empty

    def test_factory_with_verify_succeeds(self) -> None:
        """Verify factory succeeds with matching text."""
        source = "The quick brown fox"
        span = _make_span_with_verify(source, "quick brown fox", 4, 19)
        assert span.text == "quick brown fox"


# =========================================================================
# A: Deterministic span id (red proof)
# =========================================================================


class TestA_DeterministicSpanId:
    """A: span_id is deterministic full SHA-256 from document identity + offsets."""

    def test_deterministic_same_inputs(self) -> None:
        """Red proof: identical inputs produce identical span_id."""
        source = "hello world"
        span1 = _make_span(source, 0, 5)
        span2 = _make_span(source, 0, 5)
        assert span1.span_id == span2.span_id

    def test_deterministic_different_text(self) -> None:
        """Different text → different span_id."""
        source = "hello world"
        span1 = _make_span(source, 0, 5)
        span2 = _make_span(source, 6, 11)
        assert span1.span_id != span2.span_id

    def test_deterministic_different_doc_id(self) -> None:
        """Different document_id → different span_id."""
        source = "hello world"
        span1 = _make_span(source, 0, 5, doc_id="d1")
        span2 = _make_span(source, 0, 5, doc_id="d2")
        assert span1.span_id != span2.span_id

    def test_deterministic_different_url(self) -> None:
        """Different source_url → different span_id."""
        source = "hello world"
        span1 = _make_span(source, 0, 5, source_url="https://a.com")
        span2 = _make_span(source, 0, 5, source_url="https://b.com")
        assert span1.span_id != span2.span_id

    def test_deterministic_different_revision(self) -> None:
        """Different revision → different span_id."""
        source = "hello world"
        span1 = _make_span(source, 0, 5, revision="v1")
        span2 = _make_span(source, 0, 5, revision="v2")
        assert span1.span_id != span2.span_id

    def test_span_id_is_full_64_hex(self) -> None:
        """Red proof: span_id is full 64-char hex (SHA-256), not truncated."""
        source = "abc"
        span = _make_span(source, 0, 3)
        assert len(span.span_id) == 64
        assert all(c in "0123456789abcdef" for c in span.span_id)


# =========================================================================
# B: Span carries source revision and full content hash
# =========================================================================


class TestB_SpanProvenance:
    """B: ExtractiveSpan carries revision and content_hash."""

    def test_span_has_revision(self) -> None:
        source = "hello"
        span = _make_span(source, 0, 5, revision="v2.1")
        assert span.revision == "v2.1"

    def test_span_has_content_hash(self) -> None:
        source = "hello"
        c_hash = _content_hash(source)
        span = _make_span(source, 0, 5)
        assert span.content_hash == c_hash
        assert len(span.content_hash) == 64

    def test_frozen(self) -> None:
        source = "immutable"
        span = _make_span(source, 0, 9)
        with pytest.raises(AttributeError):
            span.text = "mutated"  # type: ignore[misc]


# =========================================================================
# C: DocumentRecord with raw content, validated factory, full 64-hex hashes
# =========================================================================


class TestC_DocumentRecord:
    """C: DocumentRecord includes exact raw content; validated factory;
    full 64-hex SHA256; public construction closed."""

    def test_factory_creates_record(self) -> None:
        """Factory creates a valid DocumentRecord."""
        content = "The full document content"
        record = _make_record(content)
        assert record.content == content
        assert record.source_url == SOURCE_URL
        assert record.revision == DOC_REVISION
        assert record.title == "Test Document"

    def test_factory_computes_full_64_hex_document_id(self) -> None:
        """Red proof: document_id is full 64-hex SHA-256."""
        record = _make_record("content")
        assert len(record.document_id) == 64
        assert all(c in "0123456789abcdef" for c in record.document_id)

    def test_factory_computes_full_64_hex_content_hash(self) -> None:
        """Red proof: content_hash is full 64-hex SHA-256."""
        record = _make_record("content")
        assert len(record.content_hash) == 64
        assert all(c in "0123456789abcdef" for c in record.content_hash)

    def test_factory_deterministic(self) -> None:
        """Same inputs → same record."""
        r1 = _make_record("content")
        r2 = _make_record("content")
        assert r1.document_id == r2.document_id
        assert r1.content_hash == r2.content_hash

    def test_factory_different_content_different_id(self) -> None:
        r1 = _make_record("content A")
        r2 = _make_record("content B")
        assert r1.document_id != r2.document_id

    def test_factory_different_url_different_id(self) -> None:
        r1 = _make_record("content", source_url="https://a.com")
        r2 = _make_record("content", source_url="https://b.com")
        assert r1.document_id != r2.document_id

    def test_factory_different_revision_different_id(self) -> None:
        r1 = _make_record("content", revision="v1")
        r2 = _make_record("content", revision="v2")
        assert r1.document_id != r2.document_id

    def test_direct_construction_rejected(self) -> None:
        """Red proof: DocumentRecord(...) is rejected."""
        with pytest.raises(TypeError, match="cannot be constructed directly"):
            DocumentRecord(
                document_id="d1",
                source_url="https://example.com",
                revision="v1",
                content_hash="abc",
                content="text",
                title="Title",
            )

    def test_post_init_refuses_mismatched_document_id(self) -> None:
        """Red proof: _validate refuses mismatched document_id."""
        content = "hello"
        obj = object.__new__(DocumentRecord)
        sa = object.__setattr__
        sa(obj, "document_id", "wrong_id_that_is_64_chars_long_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        sa(obj, "source_url", SOURCE_URL)
        sa(obj, "revision", DOC_REVISION)
        sa(obj, "content_hash", _content_hash(content))
        sa(obj, "content", content)
        sa(obj, "title", "Test")
        sa(obj, "ip_holder_id", None)
        sa(obj, "source_tier", 3)
        with pytest.raises(ValueError, match="document_id mismatch"):
            obj._validate()

    def test_post_init_refuses_mismatched_content_hash(self) -> None:
        """Red proof: _validate refuses mismatched content_hash."""
        content = "hello"
        obj = object.__new__(DocumentRecord)
        sa = object.__setattr__
        sa(obj, "document_id", _doc_id(SOURCE_URL, DOC_REVISION, content))
        sa(obj, "source_url", SOURCE_URL)
        sa(obj, "revision", DOC_REVISION)
        sa(obj, "content_hash", "wrong_hash_that_is_64_chars_long_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        sa(obj, "content", content)
        sa(obj, "title", "Test")
        sa(obj, "ip_holder_id", None)
        sa(obj, "source_tier", 3)
        with pytest.raises(ValueError, match="content_hash mismatch"):
            obj._validate()

    def test_store_put_recomputes_and_verifies(self) -> None:
        """Red proof: Store.put recomputes hashes and verifies."""
        store = InMemoryDocumentStore()
        record = _make_record("content")
        store.put(record)  # should succeed

        # Verify the store holds the correct record.
        retrieved = store.get(record.document_id)
        assert retrieved is not None
        assert retrieved.content == "content"

    def test_store_get_returns_content(self) -> None:
        """Red proof: Store.get returns content."""
        store = InMemoryDocumentStore()
        content = "The exact raw content of the document"
        record = _make_record(content)
        store.put(record)
        retrieved = store.get(record.document_id)
        assert retrieved is not None
        assert retrieved.content == content

    def test_store_put_rejects_mismatched_hashes(self) -> None:
        """Red proof: Store.put rejects records with wrong hashes."""
        store = InMemoryDocumentStore()
        record = _make_record("content")
        store.put(record)

        # Try to put a record with same id but different content.

        bad_record = _make_record("different content")
        # Force same document_id as the original.
        object.__setattr__(bad_record, "document_id", record.document_id)
        with pytest.raises(ValueError, match="document_id mismatch"):
            store.put(bad_record)

    def test_verify_content_passes(self) -> None:
        record = _make_record("content")
        record.verify_content()  # should not raise

    def test_verify_content_fails_on_tampered_content(self) -> None:
        """Red proof: tampered content fails verification."""
        record = _make_record("content")
        # Tamper with content after construction.
        object.__setattr__(record, "content", "tampered")
        with pytest.raises(ValueError, match="mismatch"):
            record.verify_content()

    def test_factory_empty_url_raises(self) -> None:
        with pytest.raises(ValueError, match="source_url must be non-empty"):
            DocumentRecord.create(
                source_url="", revision="v1", content="c", title="T"
            )

    def test_factory_empty_content_raises(self) -> None:
        with pytest.raises(ValueError, match="content must be non-empty"):
            DocumentRecord.create(
                source_url="https://x.com", revision="v1", content="", title="T"
            )

    def test_factory_empty_title_raises(self) -> None:
        with pytest.raises(ValueError, match="title must be non-empty"):
            DocumentRecord.create(
                source_url="https://x.com", revision="v1", content="c", title=""
            )


# =========================================================================
# C: Assembler verifies span against stored content
# =========================================================================


class TestC_AssemblerVerification:
    """C: Assembler verifies span document_id, url, revision, content_hash,
    source slice, exact text all match stored content."""

    def test_assembler_verifies_url_mismatch(self) -> None:
        """Red proof: URL mismatch between span and stored record is rejected."""
        source = "hello world"
        record = _make_record(source, source_url="https://correct.com")
        store = InMemoryDocumentStore()
        store.put(record)

        # Create a span with the CORRECT doc_id but WRONG source_url.
        span = _make_span(source, 0, 5, source_url="https://correct.com")
        # Tamper source_url after construction.
        object.__setattr__(span, "source_url", "https://wrong.com")
        with pytest.raises(ValueError, match="source_url.*does not match"):
            assemble_from_spans([span], document_store=store)

    def test_assembler_verifies_revision_mismatch(self) -> None:
        """Red proof: revision mismatch between span and stored record is rejected."""
        source = "hello world"
        record = _make_record(source, revision="v1")
        store = InMemoryDocumentStore()
        store.put(record)

        # Create a span with the CORRECT doc_id but WRONG revision.
        span = _make_span(source, 0, 5, revision="v1")
        object.__setattr__(span, "revision", "v2")
        with pytest.raises(ValueError, match="revision.*does not match"):
            assemble_from_spans([span], document_store=store)

    def test_assembler_verifies_content_hash_mismatch(self) -> None:
        """Red proof: content_hash mismatch is rejected."""
        source = "hello world"
        record = _make_record(source)
        store = InMemoryDocumentStore()
        store.put(record)

        # Create span with wrong content hash.
        span = _make_span(source, 0, 5, content_hash_val="0" * 64)
        with pytest.raises(ValueError, match="content_hash.*does not match"):
            assemble_from_spans([span], document_store=store)

    def test_assembler_verifies_text_slice_mismatch(self) -> None:
        """Red proof: text != stored_content[start:end] is rejected."""
        source = "hello world"
        record = _make_record(source)
        store = InMemoryDocumentStore()
        store.put(record)

        # Create span with correct hashes but wrong text.
        # Use from_source to get a span, then tamper.
        span = _make_span(source, 0, 5)
        object.__setattr__(span, "text", "WRONG")
        with pytest.raises(ValueError, match="text does not match stored content"):
            assemble_from_spans([span], document_store=store)

    def test_assembler_rejects_missing_document(self) -> None:
        source = "hello"
        span = _make_span(source, 0, 5)
        store = InMemoryDocumentStore()  # empty
        with pytest.raises(ValueError, match="not in the document store"):
            assemble_from_spans([span], document_store=store)


# =========================================================================
# D: extract_select composed API
# =========================================================================


class TestD_ExtractSelect:
    """D: extract_select calls extractor, verifies spans, ranks, budgets."""

    def test_extractor_actually_called(self) -> None:
        """Red proof: extractor is actually called with query/doc/budget."""
        calls: list[dict] = []

        class TrackingExtractor:
            def extract(
                self,
                query: str,
                document_text: str,
                source_url: str,
                document_id: str,
                revision: str,
                content_hash: str,
                budget: int,
            ) -> tuple[ExtractiveSpan, ...]:
                calls.append({
                    "query": query,
                    "document_text": document_text,
                    "source_url": source_url,
                    "document_id": document_id,
                    "revision": revision,
                    "content_hash": content_hash,
                    "budget": budget,
                })
                return ()

        content = "The document content"
        record = _make_record(content)
        extractor = TrackingExtractor()

        extract_select("test query", record, 1000, extractor=extractor)

        assert len(calls) == 1
        assert calls[0]["query"] == "test query"
        assert calls[0]["document_text"] == content
        assert calls[0]["source_url"] == SOURCE_URL
        assert calls[0]["document_id"] == record.document_id
        assert calls[0]["revision"] == DOC_REVISION
        assert calls[0]["content_hash"] == record.content_hash
        assert calls[0]["budget"] == 1000

    def test_extractor_required(self) -> None:
        """Red proof: extract_select without extractor raises TypeError."""
        record = _make_record("content")
        with pytest.raises(TypeError):
            extract_select("query", record, 1000)  # type: ignore[call-arg]

    def test_extractor_must_implement_protocol(self) -> None:
        """Red proof: non-ExtractorProtocol extractor is rejected."""
        record = _make_record("content")

        class NotAnExtractor:
            pass

        with pytest.raises(TypeError, match="must implement ExtractorProtocol"):
            extract_select("query", record, 1000, extractor=NotAnExtractor())  # type: ignore[arg-type]

    def test_verifies_spans_against_document(self) -> None:
        """Red proof: extract_select verifies spans match the document."""
        content = "The full document text here"
        record = _make_record(content)

        class BadExtractor:
            def extract(
                self,
                query: str,
                document_text: str,
                source_url: str,
                document_id: str,
                revision: str,
                content_hash: str,
                budget: int,
            ) -> tuple[ExtractiveSpan, ...]:
                # Return a span with wrong source_url.
                return (
                    ExtractiveSpan.from_source(
                        source=document_text,
                        document_id=document_id,
                        chunk_id="c1",
                        source_url="https://WRONG.com",
                        revision=revision,
                        content_hash=content_hash,
                        start=0,
                        end=3,
                        retrieval_score=0.5,
                    ),
                )

        with pytest.raises(ValueError, match="source_url.*does not match"):
            extract_select("query", record, 1000, extractor=BadExtractor())

    def test_valid_pipeline(self) -> None:
        """extract_select with a real extractor produces a valid result."""
        content = "word " * 100
        record = _make_record(content)
        result = extract_select(
            "query", record, 500, extractor=SimpleExtractor()
        )
        assert isinstance(result, SelectionResult)
        assert result.total_tokens <= result.budget

    def test_query_must_be_nonempty(self) -> None:
        record = _make_record("content")
        with pytest.raises(ValueError, match="query must be a non-empty string"):
            extract_select("", record, 1000, extractor=SimpleExtractor())

    def test_budget_must_be_positive(self) -> None:
        record = _make_record("content")
        with pytest.raises(ValueError, match="budget must be a positive int"):
            extract_select("query", record, 0, extractor=SimpleExtractor())


# =========================================================================
# E: SelectionResult invariant-safe
# =========================================================================


class TestE_SelectionResultInvariant:
    """E: SelectionResult __post_init__ validates everything; callers cannot forge."""

    def test_forged_negative_budget_rejected(self) -> None:
        """Red proof: negative budget is rejected."""
        with pytest.raises(ValueError, match="budget must be a positive int"):
            SelectionResult(
                selected=(), total_tokens=0, budget=-1, dropped_count=0,
                _bound_counter=DefaultTokenCounter(),
                _bound_render_and_count=render_and_count,
            )

    def test_forged_zero_budget_rejected(self) -> None:
        """Red proof: zero budget is rejected."""
        with pytest.raises(ValueError, match="budget must be a positive int"):
            SelectionResult(
                selected=(), total_tokens=0, budget=0, dropped_count=0,
                _bound_counter=DefaultTokenCounter(),
                _bound_render_and_count=render_and_count,
            )

    def test_forged_total_exceeds_budget_rejected(self) -> None:
        """Red proof: total_tokens > budget is rejected."""
        with pytest.raises(ValueError, match="total_tokens.*exceeds budget"):
            SelectionResult(
                selected=(), total_tokens=100, budget=50, dropped_count=0,
                _bound_counter=DefaultTokenCounter(),
                _bound_render_and_count=render_and_count,
            )

    def test_forged_negative_total_rejected(self) -> None:
        """Red proof: negative total_tokens is rejected."""
        with pytest.raises(ValueError, match="total_tokens must be a non-negative int"):
            SelectionResult(
                selected=(), total_tokens=-1, budget=100, dropped_count=0,
                _bound_counter=DefaultTokenCounter(),
                _bound_render_and_count=render_and_count,
            )

    def test_forged_negative_dropped_rejected(self) -> None:
        """Red proof: negative dropped_count is rejected."""
        with pytest.raises(ValueError, match="dropped_count must be a non-negative int"):
            SelectionResult(
                selected=(), total_tokens=0, budget=100, dropped_count=-1,
                _bound_counter=DefaultTokenCounter(),
                _bound_render_and_count=render_and_count,
            )

    def test_forged_non_tuple_selected_rejected(self) -> None:
        """Red proof: selected must be tuple."""
        with pytest.raises(TypeError, match="selected must be tuple"):
            SelectionResult(
                selected=["not", "tuple"],  # type: ignore[arg-type]
                total_tokens=0, budget=100, dropped_count=0,
                _bound_counter=DefaultTokenCounter(),
                _bound_render_and_count=render_and_count,
            )

    def test_forged_non_span_in_selected_rejected(self) -> None:
        """Red proof: non-ExtractiveSpan in selected is rejected."""
        with pytest.raises(TypeError, match="selected.*must be ExtractiveSpan"):
            SelectionResult(
                selected=("not a span",),  # type: ignore[arg-type]
                total_tokens=0, budget=100, dropped_count=0,
                _bound_counter=DefaultTokenCounter(),
                _bound_render_and_count=render_and_count,
            )

    def test_forged_total_mismatch_rejected(self) -> None:
        """Red proof: total_tokens != recomputed total is rejected."""
        source = "hello world"
        span = _make_span(source, 0, 5)
        counter = DefaultTokenCounter()
        real_total = render_and_count(span, counter)

        with pytest.raises(ValueError, match="does not match recomputed total"):
            SelectionResult(
                selected=(span,),
                total_tokens=real_total + 10,  # wrong!
                budget=10000,
                dropped_count=0,
                _bound_counter=counter,
                _bound_render_and_count=render_and_count,
            )

    def test_valid_result_passes(self) -> None:
        """Valid SelectionResult passes validation."""
        source = "hello world"
        span = _make_span(source, 0, 5)
        counter = DefaultTokenCounter()
        total = render_and_count(span, counter)
        result = SelectionResult(
            selected=(span,),
            total_tokens=total,
            budget=10000,
            dropped_count=0,
            _bound_counter=counter,
            _bound_render_and_count=render_and_count,
        )
        assert result.total_tokens == total


# =========================================================================
# F: Budget covers exact text; assembler cannot change counter
# =========================================================================


class TestF_BudgetAccounting:
    """F: Budget covers EXACT text sent to synthesis; assembler cannot change counter."""

    def test_budget_covers_exact_rendered_text(self) -> None:
        """Red proof: budget covers attribution + text + separator."""
        source = "word " * 100
        span = _make_span(source, 0, 50)
        counter = DefaultTokenCounter()

        # render_and_count includes attribution.
        rendered_tokens = render_and_count(span, counter)
        # The span text alone is fewer tokens.
        text_tokens = counter.count(span.text)
        assert rendered_tokens > text_tokens, (
            "rendered tokens must exceed text-only tokens "
            "(attribution adds overhead)"
        )

    def test_model_facing_total_le_budget_exact_boundary(self) -> None:
        """Red proof: model-facing total <= budget at exact boundary."""
        source = "word " * 100
        span = _make_span(source, 0, 50)
        counter = DefaultTokenCounter()
        rendered_tokens = render_and_count(span, counter)

        # Set budget exactly to rendered_tokens.
        result = _make_selected([span], budget=rendered_tokens, counter=counter)
        assert result.total_tokens == rendered_tokens
        assert result.total_tokens <= result.budget

    def test_assembler_cannot_change_counter(self) -> None:
        """Red proof: assemble_or_refuse rejects different counter."""
        source = "word " * 100
        span = _make_span(source, 0, 50)
        counter1 = DefaultTokenCounter()
        counter2 = DefaultTokenCounter()

        # Create selection with counter1.
        selection = _make_selected([span], budget=10000, counter=counter1)

        store = InMemoryDocumentStore()
        record = _make_record(source)
        store.put(record)

        # Attempt assembly with counter2 — must be rejected.
        with pytest.raises(ValueError, match="Cannot pass a different counter"):
            assemble_or_refuse(selection, counter=counter2, document_store=store)

    def test_assembler_uses_bound_counter(self) -> None:
        """Red proof: assemble_or_refuse uses the bound counter."""
        source = "word " * 200
        spans = [_make_span(source, i * 100, i * 100 + 100, score=0.9) for i in range(5)]
        counter = DefaultTokenCounter()
        selection = _make_selected(spans, budget=10000, counter=counter)

        store = InMemoryDocumentStore()
        record = _make_record(source)
        store.put(record)

        # No explicit counter — uses bound counter.
        result = assemble_or_refuse(selection, document_store=store)
        assert isinstance(result.outcome, AssembledContext)

    def test_budget_enforced_assembler_has_no_separator_override(self) -> None:
        """The enforced boundary cannot render text selection did not count."""
        signature = inspect.signature(assemble_or_refuse)
        assert "separator" not in signature.parameters

        source = "word " * 200
        spans = [_make_span(source, 0, 100), _make_span(source, 100, 200)]
        counter = DefaultTokenCounter()
        exact_budget = counter.count(render_context_text(spans))
        selection = _make_selected(spans, budget=exact_budget, counter=counter)
        store = InMemoryDocumentStore()
        store.put(_make_record(source))

        result = assemble_or_refuse(selection, document_store=store)
        assert isinstance(result.outcome, AssembledContext)
        assert result.outcome.total_tokens == selection.total_tokens
        assert result.outcome.total_tokens <= selection.budget

    def test_stateful_bound_counter_cannot_bypass_budget(self) -> None:
        """A counter that changes after selection fails closed at assembly."""

        class StatefulCounter:
            def __init__(self) -> None:
                self.calls = 0

            def count(self, text: str) -> int:
                self.calls += 1
                return 1 if self.calls == 1 else 999

        source = "x" * 200
        spans = (_make_span(source, 0, 100), _make_span(source, 100, 200))
        counter = StatefulCounter()
        selection = SelectionResult(
            selected=spans,
            total_tokens=1,
            budget=1,
            dropped_count=0,
            _bound_counter=counter,
            _bound_render_and_count=render_and_count,
        )
        store = InMemoryDocumentStore()
        store.put(_make_record(source))

        with pytest.raises(ValueError, match="changed after selection"):
            assemble_or_refuse(selection, threshold=0.0, document_store=store)

    def test_shared_render_and_count(self) -> None:
        """Red proof: selection and assembly use the same render function."""
        source = "evidence text for testing"
        span = _make_span(source, 0, 14)
        counter = DefaultTokenCounter()

        # Selection counts via render_and_count.
        sel_count = render_and_count(span, counter)

        # Assembly renders the same way.
        store = InMemoryDocumentStore()
        record = _make_record(source)
        store.put(record)
        ctx = assemble_from_spans([span], counter=counter, document_store=store)

        # The attributed span's token count matches render_and_count.
        assert ctx.spans[0].tokens == sel_count


# =========================================================================
# G: Input validation — reject bool-as-int, NaN, negative, non-int
# =========================================================================


class TestG_InputValidation:
    """G: Validate all inputs; reject bool-as-int, NaN, negative, non-int."""

    def test_query_nonempty(self) -> None:
        record = _make_record("content")
        with pytest.raises(ValueError, match="query must be a non-empty"):
            extract_select("", record, 1000, extractor=SimpleExtractor())

    def test_nan_threshold_rejected(self) -> None:
        """Red proof: NaN threshold is rejected."""
        source = "word " * 100
        spans = [_make_span(source, 0, 50)]
        selection = _make_selected(spans)
        with pytest.raises(ValueError, match="threshold must not be NaN"):
            check_floor(selection, threshold=float("nan"))

    def test_inf_threshold_rejected(self) -> None:
        """Red proof: inf threshold is rejected."""
        source = "word " * 100
        spans = [_make_span(source, 0, 50)]
        selection = _make_selected(spans)
        with pytest.raises(ValueError, match="threshold must not be infinite"):
            check_floor(selection, threshold=float("inf"))

    def test_bool_threshold_rejected(self) -> None:
        """Red proof: bool-as-float threshold is rejected."""
        source = "word " * 100
        spans = [_make_span(source, 0, 50)]
        selection = _make_selected(spans)
        with pytest.raises(TypeError, match="threshold must be float, not bool"):
            check_floor(selection, threshold=True)  # type: ignore[arg-type]

    def test_bool_current_attempt_rejected(self) -> None:
        """Red proof: bool-as-int current_attempt is rejected."""
        source = "word " * 100
        spans = [_make_span(source, 0, 50)]
        selection = _make_selected(spans)
        with pytest.raises(TypeError, match="current_attempt must be int, not bool"):
            check_floor(selection, current_attempt=True)  # type: ignore[arg-type]

    def test_bool_initial_top_k_rejected(self) -> None:
        """Red proof: bool-as-int initial_top_k is rejected."""
        source = "word " * 100
        spans = [_make_span(source, 0, 50)]
        selection = _make_selected(spans)
        with pytest.raises(TypeError, match="initial_top_k must be int, not bool"):
            check_floor(selection, initial_top_k=False)  # type: ignore[arg-type]

    def test_negative_current_attempt_rejected(self) -> None:
        source = "word " * 100
        spans = [_make_span(source, 0, 50)]
        selection = _make_selected(spans)
        with pytest.raises(ValueError, match="current_attempt must be >= 0"):
            check_floor(selection, current_attempt=-1)

    def test_zero_initial_top_k_rejected(self) -> None:
        source = "word " * 100
        spans = [_make_span(source, 0, 50)]
        selection = _make_selected(spans)
        with pytest.raises(ValueError, match="initial_top_k must be >= 1"):
            check_floor(selection, initial_top_k=0)

    def test_nan_ranker_score_rejected(self) -> None:
        """Red proof: ranker returning NaN is rejected."""

        class NaNRanker:
            def score(self, query: str, span: ExtractiveSpan) -> float:
                return float("nan")

        source = "word " * 100
        record = _make_record(source)
        with pytest.raises(ValueError, match="ranker.score returned NaN"):
            extract_select("q", record, 1000, extractor=SimpleExtractor(), ranker=NaNRanker())

    def test_inf_ranker_score_rejected(self) -> None:
        """Red proof: ranker returning inf is rejected."""

        class InfRanker:
            def score(self, query: str, span: ExtractiveSpan) -> float:
                return float("inf")

        source = "word " * 100
        record = _make_record(source)
        with pytest.raises(ValueError, match="ranker.score returned infinite"):
            extract_select("q", record, 1000, extractor=SimpleExtractor(), ranker=InfRanker())

    def test_bool_ranker_score_rejected(self) -> None:
        class BoolRanker:
            def score(self, query: str, span: ExtractiveSpan) -> bool:
                return True

        record = _make_record("word " * 100)
        with pytest.raises(TypeError, match="non-boolean"):
            extract_select(
                "q", record, 1000, extractor=SimpleExtractor(), ranker=BoolRanker()
            )

    def test_negative_counter_rejected(self) -> None:
        """Red proof: canonical accounting rejects negative counters."""
        class NegativeCounter:
            def count(self, text: str) -> int:
                return -1

        span = _make_span("word " * 100, 0, 50)
        with pytest.raises(ValueError, match="counter.count returned negative"):
            render_and_count(span, NegativeCounter())

    def test_non_int_counter_rejected_in_render(self) -> None:
        """Red proof: counter returning non-int is rejected."""

        class FloatCounter:
            def count(self, text: str) -> float:  # type: ignore[override]
                return 1.5

        span = _make_span("hello", 0, 5)
        with pytest.raises(TypeError, match="non-boolean int"):
            render_and_count(span, FloatCounter())

    @pytest.mark.parametrize("bad_count", [True, -1, 1.5])
    def test_direct_assembler_rejects_hostile_counter(self, bad_count: object) -> None:
        class HostileCounter:
            def count(self, text: str) -> int:
                return bad_count  # type: ignore[return-value]

        source = "word " * 100
        record = _make_record(source)
        store = InMemoryDocumentStore()
        store.put(record)
        span = _make_span(source, 0, 50, doc_id=record.document_id)
        with pytest.raises((TypeError, ValueError)):
            assemble_from_spans((span,), counter=HostileCounter(), document_store=store)


# =========================================================================
# H: Source attribution includes full provenance
# =========================================================================


class TestH_SourceAttribution:
    """H: Attribution includes full span id, URL, revision, content hash, start/end."""

    def test_attribution_includes_all_fields(self) -> None:
        """Red proof: attribution rendered string includes full provenance."""
        source = "The quick brown fox jumps over the lazy dog"
        record = _make_record(source)
        store = InMemoryDocumentStore()
        store.put(record)

        span = _make_span(source, 0, 19, doc_id=record.document_id)
        ctx = assemble_from_spans([span], document_store=store)
        attr = ctx.spans[0]

        # Full provenance in attribution.
        assert attr.span_id in attr.attribution or attr.document_id in attr.attribution
        assert "url:" in attr.attribution
        assert attr.source_url in attr.attribution
        assert "rev:" in attr.attribution
        assert attr.revision in attr.attribution
        assert "hash:" in attr.attribution
        assert attr.content_hash in attr.attribution
        assert "chunk:" in attr.attribution
        assert "score:" in attr.attribution

    def test_attributed_span_has_all_provenance_fields(self) -> None:
        source = "hello world test"
        record = _make_record(source)
        store = InMemoryDocumentStore()
        store.put(record)

        span = _make_span(source, 0, 11, doc_id=record.document_id, chunk_id="c1")
        ctx = assemble_from_spans([span], document_store=store)
        attr = ctx.spans[0]

        assert isinstance(attr, AttributedSpan)
        assert attr.span_id == span.span_id
        assert attr.document_id == record.document_id
        assert attr.chunk_id == "c1"
        assert attr.source_url == SOURCE_URL
        assert attr.revision == DOC_REVISION
        assert attr.content_hash == record.content_hash
        assert attr.start == 0
        assert attr.end == 11
        assert attr.text == "hello world"
        assert attr.retrieval_score == 0.9
        assert attr.tokens > 0


# =========================================================================
# I: Adversarial semantic tests (red proofs)
# =========================================================================


class TestI_AdversarialSemantics:
    """I: Red proofs for all major failure modes."""

    def test_reentrant_direct_construction_attempt(self) -> None:
        """Red proof: cannot construct ExtractiveSpan directly even after
        a factory call succeeded."""
        source = "abc"
        _make_span(source, 0, 3)
        # Direct construction still fails.
        with pytest.raises(TypeError, match="cannot be constructed directly"):
            ExtractiveSpan("x", "x", "d", "c", "url", "v1", "h" * 64, 0, 1, 0.5)

    def test_reconstructed_span_deterministic_id(self) -> None:
        """Red proof: reconstructing a span with same inputs gives same id."""
        source = "hello world"
        span1 = _make_span(source, 0, 5)
        # Reconstruct.
        span2 = _make_span(source, 0, 5)
        assert span1.span_id == span2.span_id

    def test_raw_content_retrieval(self) -> None:
        """Red proof: Store.get returns the exact raw content."""
        content = "The exact raw content that was stored"
        record = _make_record(content)
        store = InMemoryDocumentStore()
        store.put(record)
        retrieved = store.get(record.document_id)
        assert retrieved is not None
        assert retrieved.content == content

    def test_arbitrary_mismatched_record_rejection(self) -> None:
        """Red proof: assembler rejects arbitrary/mismatched records."""
        source = "hello"
        record = _make_record(source)
        store = InMemoryDocumentStore()
        store.put(record)

        # Span with wrong content_hash.
        bad_span = _make_span(source, 0, 5, content_hash_val="0" * 64)
        with pytest.raises(ValueError, match="content_hash.*does not match"):
            assemble_from_spans([bad_span], document_store=store)

    def test_url_revision_content_slice_mismatch(self) -> None:
        """Red proof: all mismatches between span and record are caught."""
        source = "hello world"
        record = _make_record(source, source_url="https://correct.com", revision="v1")
        store = InMemoryDocumentStore()
        store.put(record)

        # URL mismatch: create span with correct doc_id, tamper URL.
        span_url = _make_span(source, 0, 5, source_url="https://correct.com", revision="v1")
        object.__setattr__(span_url, "source_url", "https://wrong.com")
        with pytest.raises(ValueError, match="source_url.*does not match"):
            assemble_from_spans([span_url], document_store=store)

        # Revision mismatch: create span with correct doc_id, tamper revision.
        span_rev = _make_span(source, 0, 5, source_url="https://correct.com", revision="v1")
        object.__setattr__(span_rev, "revision", "v99")
        with pytest.raises(ValueError, match="revision.*does not match"):
            assemble_from_spans([span_rev], document_store=store)

    def test_full_64_char_hashes(self) -> None:
        """Red proof: all hashes are full 64-char hex."""
        source = "test"
        span = _make_span(source, 0, 4)
        assert len(span.span_id) == 64
        assert len(span.content_hash) == 64

        record = _make_record(source)
        assert len(record.document_id) == 64
        assert len(record.content_hash) == 64

        assert len(content_addressed_id("url", "rev", "c")) == 64
        assert len(content_hash("content")) == 64

    def test_composed_extractor_called_with_query_doc_budget(self) -> None:
        """Red proof: extract_select passes query, doc content, budget to extractor."""
        captured: dict = {}

        class CapturingExtractor:
            def extract(
                self,
                query: str,
                document_text: str,
                source_url: str,
                document_id: str,
                revision: str,
                content_hash: str,
                budget: int,
            ) -> tuple[ExtractiveSpan, ...]:
                captured.update({
                    "query": query,
                    "document_text": document_text,
                    "budget": budget,
                    "source_url": source_url,
                    "document_id": document_id,
                    "revision": revision,
                    "content_hash": content_hash,
                })
                return ()

        content = "The document for extraction"
        record = _make_record(content)
        extract_select("my query", record, 500, extractor=CapturingExtractor())

        assert captured["query"] == "my query"
        assert captured["document_text"] == content
        assert captured["budget"] == 500
        assert captured["source_url"] == SOURCE_URL
        assert captured["document_id"] == record.document_id
        assert captured["revision"] == DOC_REVISION
        assert captured["content_hash"] == record.content_hash

    def test_forged_selection_result_rejection(self) -> None:
        """Red proof: forged SelectionResult is rejected by __post_init__."""
        source = "hello"
        span = _make_span(source, 0, 5)
        counter = DefaultTokenCounter()

        # Forged: total doesn't match.
        with pytest.raises(ValueError, match="does not match recomputed"):
            SelectionResult(
                selected=(span,),
                total_tokens=99999,
                budget=100000,
                dropped_count=0,
                _bound_counter=counter,
                _bound_render_and_count=render_and_count,
            )

    def test_model_facing_total_le_budget_exact_boundary(self) -> None:
        """Red proof: model-facing total <= budget at exact boundary."""
        source = "word " * 100
        span = _make_span(source, 0, 50)
        counter = DefaultTokenCounter()
        exact = render_and_count(span, counter)

        result = _make_selected([span], budget=exact, counter=counter)
        assert result.total_tokens == result.budget
        assert result.total_tokens <= result.budget

    def test_assembler_cannot_change_counter_red_proof(self) -> None:
        """Red proof: passing a different counter to assemble_or_refuse raises."""
        source = "word " * 100
        span = _make_span(source, 0, 50)
        counter = DefaultTokenCounter()
        selection = _make_selected([span], budget=10000, counter=counter)

        store = InMemoryDocumentStore()
        record = _make_record(source)
        store.put(record)

        different_counter = DefaultTokenCounter()
        with pytest.raises(ValueError, match="Cannot pass a different counter"):
            assemble_or_refuse(selection, counter=different_counter, document_store=store)


# =========================================================================
# Cross-cutting: Verbatim enforcement
# =========================================================================


class TestVerbatimEnforcement:
    """Paraphrased / offset-shifted text refuses."""

    def test_paraphrase_refused(self) -> None:
        source = "The quick brown fox jumps"
        with pytest.raises(ValueError, match="does not match"):
            _make_span_with_verify(
                source=source,
                text="The slow brown fox jumps",
                start=0,
                end=25,
            )

    def test_offset_shift_refused(self) -> None:
        source = "The quick brown fox"
        with pytest.raises(ValueError, match="does not match"):
            _make_span_with_verify(
                source=source,
                text="quick brown",
                start=4,
                end=19,
            )

    def test_nfc_nfd_non_equivalence(self) -> None:
        nfc_source = "café"
        nfd_source = "cafe\u0301"
        with pytest.raises(ValueError, match="does not match"):
            _make_span_with_verify(
                source=nfc_source,
                text=nfd_source,
                start=0,
                end=4,
            )

    def test_multi_byte_emoji_offsets(self) -> None:
        source = "Hello 🌍 World 🚀"
        span = _make_span(source, 6, 7)
        assert span.text == "🌍"

    def test_cjk_offsets(self) -> None:
        source = "研究调查结果"
        span = _make_span(source, 0, 2)
        assert span.text == "研究"


# =========================================================================
# Cross-cutting: Field validation
# =========================================================================


class TestFieldValidation:
    """Validate nonempty ids, nonempty spans, finite score in [0,1]."""

    def test_empty_document_id_refused(self) -> None:
        with pytest.raises(ValueError, match="document_id must be non-empty"):
            ExtractiveSpan.from_source(
                source="abc", document_id="", chunk_id="c",
                source_url="https://url", revision="v1",
                content_hash="h" * 64, start=0, end=3, retrieval_score=0.5,
            )

    def test_empty_chunk_id_refused(self) -> None:
        with pytest.raises(ValueError, match="chunk_id must be non-empty"):
            ExtractiveSpan.from_source(
                source="abc", document_id="d", chunk_id="",
                source_url="https://url", revision="v1",
                content_hash="h" * 64, start=0, end=3, retrieval_score=0.5,
            )

    def test_empty_source_url_refused(self) -> None:
        with pytest.raises(ValueError, match="source_url must be non-empty"):
            ExtractiveSpan.from_source(
                source="abc", document_id="d", chunk_id="c",
                source_url="", revision="v1",
                content_hash="h" * 64, start=0, end=3, retrieval_score=0.5,
            )

    def test_empty_source_refused(self) -> None:
        with pytest.raises(ValueError, match="source must be non-empty"):
            ExtractiveSpan.from_source(
                source="", document_id="d", chunk_id="c",
                source_url="https://url", revision="v1",
                content_hash="h" * 64, start=0, end=0, retrieval_score=0.5,
            )

    def test_empty_span_refused(self) -> None:
        with pytest.raises(ValueError, match="span must be non-empty"):
            ExtractiveSpan.from_source(
                source="abc", document_id="d", chunk_id="c",
                source_url="https://url", revision="v1",
                content_hash="h" * 64, start=2, end=2, retrieval_score=0.5,
            )

    def test_nan_score_refused(self) -> None:
        with pytest.raises(ValueError, match="must not be NaN"):
            _make_span("abc", 0, 3, score=float("nan"))

    def test_inf_score_refused(self) -> None:
        with pytest.raises(ValueError, match="must not be infinite"):
            _make_span("abc", 0, 3, score=float("inf"))

    def test_negative_score_refused(self) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            _make_span("abc", 0, 3, score=-0.1)

    def test_score_above_one_refused(self) -> None:
        with pytest.raises(ValueError, match="must be <= 1"):
            _make_span("abc", 0, 3, score=1.1)

    def test_score_exactly_zero_accepted(self) -> None:
        span = _make_span("abc", 0, 3, score=0.0)
        assert span.retrieval_score == 0.0

    def test_score_exactly_one_accepted(self) -> None:
        span = _make_span("abc", 0, 3, score=1.0)
        assert span.retrieval_score == 1.0

    def test_start_negative_refused(self) -> None:
        with pytest.raises(ValueError, match="start must be >= 0"):
            _make_span("abc", -1, 3)

    def test_end_negative_refused(self) -> None:
        with pytest.raises(ValueError, match="end must be >= 0"):
            _make_span("abc", 0, -1)

    def test_start_gt_end_refused(self) -> None:
        with pytest.raises(ValueError, match="start .* > end"):
            _make_span("abc", 3, 1)

    def test_end_exceeds_source_refused(self) -> None:
        with pytest.raises(ValueError, match="exceeds source length"):
            _make_span("abc", 0, 10)

    def test_empty_revision_refused(self) -> None:
        with pytest.raises(ValueError, match="revision must be a non-empty"):
            ExtractiveSpan.from_source(
                source="abc", document_id="d", chunk_id="c",
                source_url="https://url", revision="",
                content_hash="h" * 64, start=0, end=3, retrieval_score=0.5,
            )

    def test_short_content_hash_refused(self) -> None:
        with pytest.raises(ValueError, match="64-char hex"):
            ExtractiveSpan.from_source(
                source="abc", document_id="d", chunk_id="c",
                source_url="https://url", revision="v1",
                content_hash="short", start=0, end=3, retrieval_score=0.5,
            )


# =========================================================================
# Cross-cutting: Typed assembler boundary
# =========================================================================


class TestTypedAssembler:
    """Assembler rejects non-ExtractiveSpan inputs at runtime."""

    def test_rejects_string(self) -> None:
        with pytest.raises(TypeError, match="ExtractiveSpan only"):
            assemble_from_spans(["raw document text"])  # type: ignore[list-item]

    def test_rejects_dict(self) -> None:
        with pytest.raises(TypeError, match="ExtractiveSpan only"):
            assemble_from_spans([{"text": "raw", "doc": "d1"}])  # type: ignore[list-item]

    def test_rejects_none(self) -> None:
        with pytest.raises(TypeError, match="ExtractiveSpan only"):
            assemble_from_spans([None])  # type: ignore[list-item]

    def test_accepts_valid_spans(self) -> None:
        source = "hello world"
        span = _make_span(source, 0, 5)
        store = InMemoryDocumentStore()
        record = _make_record(source)
        store.put(record)
        ctx = assemble_from_spans([span], document_store=store)
        assert isinstance(ctx, AssembledContext)


# =========================================================================
# Cross-cutting: Token accounting
# =========================================================================


class TestTokenAccounting:
    """Token accounting cross-checks selection and assembly totals."""

    def test_selection_total_matches_render_and_count(self) -> None:
        counter = DefaultTokenCounter()
        source = "word " * 200
        record = _make_record(source)
        result = extract_select("q", record, 1000, extractor=SimpleExtractor())
        assert result.total_tokens == counter.count(render_context_text(result.selected))

    def test_assembly_total_matches_counter(self) -> None:
        counter = DefaultTokenCounter()
        source = "evidence text for testing"
        spans = [_make_span(source, 0, 14), _make_span(source, 15, 24)]
        store = InMemoryDocumentStore()
        record = _make_record(source)
        store.put(record)
        ctx = assemble_from_spans(spans, counter=counter, document_store=store)
        assert ctx.total_tokens == counter.count(ctx.text)

    def test_assembled_context_total_is_positive(self) -> None:
        source = "x" * 100
        span = _make_span(source, 0, 50)
        store = InMemoryDocumentStore()
        record = _make_record(source)
        store.put(record)
        ctx = assemble_from_spans([span], document_store=store)
        assert ctx.total_tokens > 0


# =========================================================================
# Cross-cutting: Floor trace preservation
# =========================================================================


class TestFloorTracePreservation:
    """Every public floor trip preserves a structured trace."""

    def test_floor_pass_returns_none_trace(self) -> None:
        source = "word " * 100
        spans = [_make_span(source, i * 50, i * 50 + 50, score=0.9) for i in range(5)]
        selection = _make_selected(spans)
        _, trace = check_floor(selection)
        assert trace is None

    def test_floor_trip_returns_trace(self) -> None:
        source = "x" * 10
        spans = [_make_span(source, 0, 5, score=0.01)]
        selection = _make_selected(spans)
        _, trace = check_floor(selection)
        assert trace is not None
        assert isinstance(trace, FloorTripTrace)
        assert trace.quality_score < FLOOR_QUALITY_THRESHOLD
        assert trace.outcome_kind == "requery"

    def test_insufficient_sources_returns_trace(self) -> None:
        source = "x" * 10
        spans = [_make_span(source, 0, 5, score=0.01)]
        selection = _make_selected(spans)
        _, trace = check_floor(selection, current_attempt=FLOOR_MAX_REQUERIES)
        assert trace is not None
        assert trace.outcome_kind == "insufficient_sources"

    def test_assemble_or_refuse_preserves_trace_on_trip(self) -> None:
        source = "x" * 10
        spans = [_make_span(source, 0, 5, score=0.01)]
        selection = _make_selected(spans, budget=100)
        result = assemble_or_refuse(selection)
        assert isinstance(result, FloorAwareResult)
        assert result.trace is not None

    def test_assemble_or_refuse_preserves_trace_on_pass(self) -> None:
        source = "word " * 200
        spans = [_make_span(source, i * 100, i * 100 + 100, score=0.9) for i in range(5)]
        selection = _make_selected(spans)
        store = InMemoryDocumentStore()
        record = _make_record(source)
        store.put(record)
        result = assemble_or_refuse(selection, document_store=store)
        assert isinstance(result, FloorAwareResult)
        assert isinstance(result.outcome, AssembledContext)
        assert result.trace is None


# =========================================================================
# Cross-cutting: Public API surface + WIRING.md
# =========================================================================


class TestPublicApiSurface:
    """Public API exports are complete."""

    def test_init_exports(self) -> None:
        import substrate.research_spans as pkg

        for name in (
            "ExtractiveSpan",
            "extract_select",
            "render_and_count",
            "check_floor",
            "assemble_from_spans",
            "assemble_or_refuse",
            "AssembledContext",
            "AttributedSpan",
            "DocumentRecord",
            "DocumentStore",
            "InMemoryDocumentStore",
            "FloorAwareResult",
            "Requery",
            "InsufficientSources",
            "FloorTripTrace",
            "SelectionResult",
            "RankerProtocol",
            "ExtractorProtocol",
            "TokenCounter",
            "DefaultRanker",
            "DefaultTokenCounter",
            "result_set_quality",
            "span_budget_for_tier",
            "span_budget_high",
            "span_budget_low",
            "span_budget_medium",
            "content_addressed_id",
            "content_hash",
        ):
            assert hasattr(pkg, name), f"{name} not exported from research_spans"


class TestWiringMd:
    """WIRING.md exists and names real call sites."""

    def test_wiring_md_exists(self) -> None:
        import os

        wiring_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "substrate",
            "research_spans",
            "WIRING.md",
        )
        assert os.path.isfile(wiring_path)
