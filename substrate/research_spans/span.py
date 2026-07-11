"""ExtractiveSpan — verbatim extractive span with provenance.

A span is a verbatim slice of a source document, carrying character offsets
into that document and a retrieval score.  Construction **verifies**
``text == source[start:end]``; direct ``ExtractiveSpan(...)`` construction
is mechanically impossible — the private module token pattern ensures
only the factory method can construct instances.

Slicing convention (SPR-04 binding):
    Offsets are **Python ``str`` indices** — counting Unicode code points,
    not UTF-8 bytes.  ``source[start:end]`` uses the same ``__getitem__``
    semantics as the Python runtime.

Span id:
    ``span_id`` is a deterministic full 64-hex SHA-256 hash derived from
    ``document_id + source_url + revision + start + end + text``.
    Identical inputs always produce the same id.  No UUIDs, no arbitrary ids.

Provenance:
    ``document_id`` is the caller's stable identifier for the source
    document.  ``source_url`` is the canonical URL.  ``revision`` is
    the caller's revision identifier.  ``content_hash`` is the full
    SHA-256 content hash of the source document.  Both ``document_id``
    and ``content_hash`` are full 64-char hex strings.  ``chunk_id``
    is the retriever's own id.  All are non-empty strings.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any


class ExtractiveSpan:
    """A verbatim extractive span.

    Direct construction (``ExtractiveSpan(...)``) is **mechanically
    impossible**.  ``__new__`` rejects it via the private module token
    pattern.  The only public constructors are :meth:`from_source` and
    :meth:`from_source_with_verify`.

    No global mutable authorization — the construction token is a
    private module-level sentinel passed positionally to ``__new__``.

    Frozen: ``__setattr__`` and ``__delattr__`` raise after construction.
    """

    span_id: str
    text: str
    document_id: str
    chunk_id: str
    source_url: str
    revision: str
    content_hash: str
    start: int
    end: int
    retrieval_score: float

    __slots__ = (
        "span_id", "text", "document_id", "chunk_id",
        "source_url", "revision", "content_hash",
        "start", "end", "retrieval_score",
    )

    def __new__(cls, *args: Any, **kwargs: Any) -> ExtractiveSpan:
        if not args or args[0] is not _CONSTRUCTION_TOKEN:
            raise TypeError(
                "ExtractiveSpan cannot be constructed directly — "
                "use ExtractiveSpan.from_source() or "
                "use ExtractiveSpan.from_source_with_verify()"
            )
        return super().__new__(cls)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError(
            "ExtractiveSpan cannot be subclassed — "
            "use ExtractiveSpan.from_source() to construct"
        )

    # -- Frozen semantics ---------------------------------------------------

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("ExtractiveSpan is frozen")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("ExtractiveSpan is frozen")

    # -- Validation (called by factory after setting fields) -----------------

    def _validate(self, source: str | None = None) -> None:
        """Validate all fields.  Called by factory methods.

        If ``source`` is provided, also checks that text matches
        source[start:end].
        """
        # Type checks.
        if not isinstance(self.span_id, str):
            raise TypeError(f"span_id must be str, got {type(self.span_id).__name__}")
        if not isinstance(self.text, str):
            raise TypeError(f"text must be str, got {type(self.text).__name__}")
        if not isinstance(self.document_id, str):
            raise TypeError(f"document_id must be str, got {type(self.document_id).__name__}")
        if not isinstance(self.chunk_id, str):
            raise TypeError(f"chunk_id must be str, got {type(self.chunk_id).__name__}")
        if not isinstance(self.source_url, str):
            raise TypeError(f"source_url must be str, got {type(self.source_url).__name__}")
        if not isinstance(self.revision, str):
            raise TypeError(f"revision must be str, got {type(self.revision).__name__}")
        if not isinstance(self.content_hash, str):
            raise TypeError(f"content_hash must be str, got {type(self.content_hash).__name__}")
        if not isinstance(self.retrieval_score, (int, float)):
            raise TypeError(
                f"retrieval_score must be int or float, "
                f"got {type(self.retrieval_score).__name__}"
            )

        # Non-empty checks.
        if not self.document_id:
            raise ValueError("document_id must be non-empty")
        if not self.chunk_id:
            raise ValueError("chunk_id must be non-empty")
        if not self.source_url:
            raise ValueError("source_url must be non-empty")
        if not self.revision:
            raise ValueError("revision must be non-empty")
        if not self.content_hash:
            raise ValueError("content_hash must be non-empty")
        if not self.text:
            raise ValueError("text must be non-empty")

        # Score validation: finite and in [0, 1].
        score = float(self.retrieval_score)
        if math.isnan(score):
            raise ValueError("retrieval_score must not be NaN")
        if math.isinf(score):
            raise ValueError("retrieval_score must not be infinite")
        if score < 0.0:
            raise ValueError(f"retrieval_score must be >= 0, got {score}")
        if score > 1.0:
            raise ValueError(f"retrieval_score must be <= 1, got {score}")

        # Range validation.
        if not isinstance(self.start, int):
            raise TypeError(f"start must be int, got {type(self.start).__name__}")
        if not isinstance(self.end, int):
            raise TypeError(f"end must be int, got {type(self.end).__name__}")
        if self.start < 0:
            raise ValueError(f"start must be >= 0, got {self.start}")
        if self.end < 0:
            raise ValueError(f"end must be >= 0, got {self.end}")
        if self.start > self.end:
            raise ValueError(f"start ({self.start}) > end ({self.end})")
        if self.end - self.start != len(self.text):
            raise ValueError(
                f"span text length ({len(self.text)}) does not match "
                f"end - start ({self.end - self.start})"
            )

        # Source verbatim check.
        if source is not None:
            if self.end > len(source):
                raise ValueError(
                    f"end ({self.end}) exceeds source length ({len(source)})"
                )
            expected = source[self.start : self.end]
            if self.text != expected:
                raise ValueError(
                    "span text does not match source[start:end] — "
                    "paraphrased, offset-shifted, or normalization-mismatched "
                    "text cannot be constructed"
                )

        # Hash length: full 64-char hex (SHA-256).
        if len(self.span_id) != 64:
            raise ValueError(f"span_id must be 64 hex chars, got {len(self.span_id)}")
        if len(self.content_hash) != 64:
            raise ValueError(
                f"content_hash must be 64 hex chars, got {len(self.content_hash)}"
            )
        expected_span_id = self._compute_span_id(
            self.document_id,
            self.source_url,
            self.revision,
            self.start,
            self.end,
            self.text,
        )
        if self.span_id != expected_span_id:
            raise ValueError(
                f"span_id mismatch: expected {expected_span_id!r}, got {self.span_id!r}"
            )

    # -- Deterministic span id -----------------------------------------------

    @staticmethod
    def _compute_span_id(
        document_id: str,
        source_url: str,
        revision: str,
        start: int,
        end: int,
        text: str,
    ) -> str:
        """Compute deterministic full 64-hex SHA-256 span id.

        Derived from document_id + source_url + revision + start + end + text.
        Identical inputs always produce the same id.
        """
        canonical = (
            f"{document_id}\x00{source_url}\x00{revision}"
            f"\x00{start}\x00{end}\x00{text}"
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # -- Shared validation ---------------------------------------------------

    @staticmethod
    def _validate_and_slice(
        source: str,
        start: int,
        end: int,
        document_id: str,
        chunk_id: str,
        source_url: str,
        retrieval_score: float,
    ) -> str:
        """Validate all inputs and return the verbatim slice."""
        if not isinstance(source, str):
            raise TypeError(f"source must be str, got {type(source).__name__}")
        if not isinstance(document_id, str):
            raise TypeError(f"document_id must be str, got {type(document_id).__name__}")
        if not isinstance(chunk_id, str):
            raise TypeError(f"chunk_id must be str, got {type(chunk_id).__name__}")
        if not isinstance(source_url, str):
            raise TypeError(f"source_url must be str, got {type(source_url).__name__}")
        if not isinstance(retrieval_score, (int, float)):
            raise TypeError(
                f"retrieval_score must be int or float, "
                f"got {type(retrieval_score).__name__}"
            )

        if not document_id:
            raise ValueError("document_id must be non-empty")
        if not chunk_id:
            raise ValueError("chunk_id must be non-empty")
        if not source_url:
            raise ValueError("source_url must be non-empty")
        if not source:
            raise ValueError("source must be non-empty")

        score = float(retrieval_score)
        if math.isnan(score):
            raise ValueError("retrieval_score must not be NaN")
        if math.isinf(score):
            raise ValueError("retrieval_score must not be infinite")
        if score < 0.0:
            raise ValueError(f"retrieval_score must be >= 0, got {score}")
        if score > 1.0:
            raise ValueError(f"retrieval_score must be <= 1, got {score}")

        if not isinstance(start, int):
            raise TypeError(f"start must be int, got {type(start).__name__}")
        if not isinstance(end, int):
            raise TypeError(f"end must be int, got {type(end).__name__}")
        if start < 0:
            raise ValueError(f"start must be >= 0, got {start}")
        if end < 0:
            raise ValueError(f"end must be >= 0, got {end}")
        if start > end:
            raise ValueError(f"start ({start}) > end ({end})")
        if end > len(source):
            raise ValueError(f"end ({end}) exceeds source length ({len(source)})")

        verbatim = source[start:end]
        if not verbatim:
            raise ValueError(f"span must be non-empty (start={start}, end={end})")
        return verbatim

    # -- Internal construction helper -----------------------------------------

    @classmethod
    def _construct(
        cls,
        *,
        span_id: str,
        text: str,
        document_id: str,
        chunk_id: str,
        source_url: str,
        revision: str,
        content_hash: str,
        start: int,
        end: int,
        retrieval_score: float,
        source: str | None = None,
    ) -> ExtractiveSpan:
        """Internal construction: bypass __init__, set fields, validate."""
        obj = cls.__new__(cls, _CONSTRUCTION_TOKEN)
        # Use object.__setattr__ to set frozen fields.
        sa = object.__setattr__
        sa(obj, "span_id", span_id)
        sa(obj, "text", text)
        sa(obj, "document_id", document_id)
        sa(obj, "chunk_id", chunk_id)
        sa(obj, "source_url", source_url)
        sa(obj, "revision", revision)
        sa(obj, "content_hash", content_hash)
        sa(obj, "start", start)
        sa(obj, "end", end)
        sa(obj, "retrieval_score", float(retrieval_score))
        obj._validate(source=source)
        return obj

    # -- Factory constructors ------------------------------------------------

    @classmethod
    def from_source(
        cls,
        *,
        source: str,
        document_id: str,
        chunk_id: str,
        source_url: str,
        revision: str,
        content_hash: str,
        start: int,
        end: int,
        retrieval_score: float,
    ) -> ExtractiveSpan:
        """Construct a span from a source document.

        The stored text is ``source[start:end]`` — the verbatim slice.
        Validates ids are non-empty, source is non-empty, span is
        non-empty, score is finite and in [0, 1], offsets are in range,
        and hash lengths are full 64 hex chars.

        ``span_id`` is a deterministic full SHA-256 hash derived from
        document_id + source_url + revision + start + end + text.
        Identical inputs always produce the same id.
        """
        verbatim = cls._validate_and_slice(
            source, start, end, document_id, chunk_id, source_url,
            retrieval_score,
        )

        if not isinstance(revision, str) or not revision:
            raise ValueError("revision must be a non-empty string")
        if not isinstance(content_hash, str) or len(content_hash) != 64:
            raise ValueError("content_hash must be a 64-char hex string")

        span_id = cls._compute_span_id(
            document_id, source_url, revision, start, end, verbatim
        )

        return cls._construct(
            span_id=span_id,
            text=verbatim,
            document_id=document_id,
            chunk_id=chunk_id,
            source_url=source_url,
            revision=revision,
            content_hash=content_hash,
            start=start,
            end=end,
            retrieval_score=float(retrieval_score),
            source=source,
        )

    @classmethod
    def from_source_with_verify(
        cls,
        *,
        source: str,
        text: str,
        document_id: str,
        chunk_id: str,
        source_url: str,
        revision: str,
        content_hash: str,
        start: int,
        end: int,
        retrieval_score: float,
    ) -> ExtractiveSpan:
        """Construct a span **and** verify ``text == source[start:end]``.

        ``span_id`` is a deterministic full SHA-256 hash derived from
        document_id + source_url + revision + start + end + text.
        Identical inputs always produce the same id.
        """
        if not isinstance(text, str):
            raise TypeError(f"text must be str, got {type(text).__name__}")

        verbatim = cls._validate_and_slice(
            source, start, end, document_id, chunk_id, source_url,
            retrieval_score,
        )

        if text != verbatim:
            raise ValueError(
                "span text does not match source[start:end] — "
                "paraphrased, offset-shifted, or normalization-mismatched "
                "text cannot be constructed"
            )

        if not isinstance(revision, str) or not revision:
            raise ValueError("revision must be a non-empty string")
        if not isinstance(content_hash, str) or len(content_hash) != 64:
            raise ValueError("content_hash must be a 64-char hex string")

        span_id = cls._compute_span_id(
            document_id, source_url, revision, start, end, verbatim
        )

        return cls._construct(
            span_id=span_id,
            text=verbatim,
            document_id=document_id,
            chunk_id=chunk_id,
            source_url=source_url,
            revision=revision,
            content_hash=content_hash,
            start=start,
            end=end,
            retrieval_score=float(retrieval_score),
            source=source,
        )

    # -- Convenience ----------------------------------------------------------

    @property
    def char_length(self) -> int:
        """Character (code-point) length of the span."""
        return self.end - self.start

    @property
    def source_ref(self) -> str:
        """Full source reference: url@revision#content_hash."""
        return f"{self.source_url}@{self.revision}#{self.content_hash}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ExtractiveSpan):
            return NotImplemented
        return (
            self.span_id == other.span_id
            and self.text == other.text
            and self.document_id == other.document_id
            and self.chunk_id == other.chunk_id
            and self.source_url == other.source_url
            and self.revision == other.revision
            and self.content_hash == other.content_hash
            and self.start == other.start
            and self.end == other.end
            and self.retrieval_score == other.retrieval_score
        )

    def __hash__(self) -> int:
        return hash((
            self.span_id, self.text, self.document_id, self.chunk_id,
            self.source_url, self.revision, self.content_hash,
            self.start, self.end, self.retrieval_score,
        ))

    def __repr__(self) -> str:
        preview = self.text[:40] + ("…" if len(self.text) > 40 else "")
        return (
            f"ExtractiveSpan(doc={self.document_id[:12]}…, "
            f"chunk={self.chunk_id!r}, "
            f"[{self.start}:{self.end}], "
            f"score={self.retrieval_score:.4f}, "
            f"text={preview!r})"
        )


# Private module-level construction sentinel.
# Only the factory methods pass this via _construct.
# No global mutable bool — the token is a constant reference.
_CONSTRUCTION_TOKEN = object()
