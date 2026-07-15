"""Per-title free-copy search over the existing PD book connectors.

Given a title (and optional author), searches the already-built public-domain
sources to determine whether a freely-available copy exists before any
purchase-intent path is considered.  The operator's intent: "I am okay with
buying a digital book if there is no pdf online" — this module answers the
"is there a pdf online?" question by querying the existing connectors in
priority order.

Sources with per-title query surfaces (searched):

  * **Project Gutenberg** via Gutendex — ``search`` parameter queries title
    text; results filtered to explicit PD (``copyright=false``) by the
    existing ``gutenberg_candidates`` machinery.
  * **Internet Archive** — ``advancedsearch`` full-text search constrained to
    ``possible-copyright-status:(NOT_IN_COPYRIGHT)`` + per-item layer-2
    rights re-check via ``item_candidate``.

Sources WITHOUT per-title query surfaces (excluded, not faked):

  * **Standard Ebooks** — OPDS feed only (full catalogue dump); no per-title
    search endpoint.  Would require fetching the entire feed and filtering.
  * **Wikisource** — MediaWiki category listing; no title search via the
    connector's current surface.
  * **HathiTrust** — Bibliographic API requires known record IDs; no title
    search.
  * **Library of Congress** — collection listing; no per-title search.

Every HTTP byte flows through the existing ``SourceClient`` /
``ThrottledFetcher`` + SPR-03 throttle machinery.  ZERO new HTTP clients.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Protocol

from .pd_connector_base import BookCandidate, FetchError, classify_and_ingest
from .pd_connector_base import IngestOutcome as PdIngestOutcome
from .public_domain import PublicDomainWork

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FreeCopyFound:
    """A freely-available copy was located at a PD source.

    ``candidate_ref`` is the connector-native object (``PublicDomainWork``
    for Gutenberg, ``BookCandidate`` for Internet Archive / Wave-2) — the
    ingest path expects its own type.  ``rights_basis`` names the source
    field / rights signal that established PD status.
    """

    source: str
    candidate_ref: PublicDomainWork | BookCandidate
    rights_basis: str
    retrieved_at: str  # ISO-8601 UTC


@dataclass(frozen=True)
class SourceOutcome:
    """Per-source search result — present in ``NotFreelyAvailable.outcomes``.

    ``found=False`` may mean zero results, zero PD results, or a connector
    error (recorded in ``error``).  ``query`` is the human-readable
    description of what was sent to the source.
    """

    source: str
    found: bool
    query: str
    timestamp: str  # ISO-8601 UTC
    error: str | None = None


@dataclass(frozen=True)
class NotFreelyAvailable:
    """No freely-available copy located across the searched sources.

    ``outcomes`` carries one honest entry per source attempted, so the
    operator can see exactly what was queried and what came back.  This is a
    RECOMMENDATION record — it does NOT mint purchase intents.
    """

    title: str
    author: str | None
    outcomes: tuple[SourceOutcome, ...]
    checked_at: str  # ISO-8601 UTC


# ---------------------------------------------------------------------------
# Fetcher protocol
# ---------------------------------------------------------------------------


class _FetcherProto(Protocol):
    """Minimal fetcher surface accepted by :func:`search_free_copy`.

    Satisfied by ``FakeFetcher`` in tests and by :class:`SourceClientFetcher`
    in production (which routes Gutendex / archive.org requests through the
    existing ``SourceClient`` / ``ThrottledFetcher`` + SPR-03 throttle).
    """

    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    def get_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> bytes: ...


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def search_free_copy(
    title: str,
    author: str | None = None,
    *,
    sources: tuple[str, ...] = ("gutenberg", "internet_archive"),
    fetcher: _FetcherProto | None = None,
) -> FreeCopyFound | NotFreelyAvailable:
    """Search for a freely-available copy of *title* across PD sources.

    Returns :class:`FreeCopyFound` on the first positive hit, or
    :class:`NotFreelyAvailable` with honest per-source outcomes when nothing
    is located.  Each source is searched via its existing connector machinery
    (Gutendex title search, IA advancedsearch + per-item re-check); errors in
    one source are recorded and the sweep continues.

    ``fetcher`` is injectable for tests (``FakeFetcher``); when ``None`` a
    production :class:`SourceClientFetcher` is created internally.
    """
    title = _validated_query_text(title, field="title", max_length=500)
    if author is not None:
        author = _validated_query_text(author, field="author", max_length=300)

    if fetcher is None:
        fetcher = SourceClientFetcher()

    now = _dt.datetime.now(_dt.UTC).isoformat()
    outcomes: list[SourceOutcome] = []

    for source in sources:
        try:
            if source == "gutenberg":
                result = _search_gutenberg(title, author, fetcher)
            elif source == "internet_archive":
                result = _search_ia(title, author, fetcher)
            else:
                outcomes.append(SourceOutcome(
                    source=source, found=False,
                    query=f"(unsupported source {source!r})",
                    timestamp=_dt.datetime.now(_dt.UTC).isoformat(),
                ))
                continue

            if isinstance(result, FreeCopyFound):
                return result
            outcomes.append(result)
        except Exception as exc:
            outcomes.append(SourceOutcome(
                source=source, found=False,
                query=title,
                timestamp=_dt.datetime.now(_dt.UTC).isoformat(),
                error=str(exc),
            ))

    return NotFreelyAvailable(
        title=title,
        author=author,
        outcomes=tuple(outcomes),
        checked_at=now,
    )


# ---------------------------------------------------------------------------
# Per-source searchers
# ---------------------------------------------------------------------------


def _validated_query_text(value: str, *, field: str, max_length: int) -> str:
    """Normalize operator text before it reaches a connector query grammar."""
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    if len(normalized) > max_length:
        raise ValueError(f"{field} must be at most {max_length} characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise ValueError(f"{field} must not contain control characters")
    return normalized


def _ia_phrase(value: str) -> str:
    """Encode operator text as one literal Internet Archive query phrase."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _search_gutenberg(
    title: str,
    author: str | None,
    fetcher: _FetcherProto,
) -> FreeCopyFound | SourceOutcome:
    """Search Gutendex for a public-domain copy of *title*.

    Delegates to the existing ``gutenberg_candidates`` which applies the
    ``copyright=false`` PD filter and selects an ingestible format.  Returns
    the first PD hit or a ``SourceOutcome`` noting no PD results.
    """
    from .public_domain import gutenberg_candidates

    query = f"{title} {author}" if author else title
    try:
        # gutenberg_candidates is typed to concrete SourceClient (owned by
        # another lane); _FetcherProto is structurally compatible — the
        # connector calls only .get_json, which SourceClientFetcher provides —
        # so the narrow ignore stays here rather than widening their signature.
        candidates = gutenberg_candidates(
            fetcher,  # type: ignore[arg-type]
            search=query,
            limit=5,
        )
    except Exception as exc:
        raise FetchError(f"gutendex search failed: {exc}") from exc

    for c in candidates:
        if c.pd_basis is not None:
            return FreeCopyFound(
                source="gutenberg",
                candidate_ref=c,
                rights_basis=c.pd_basis,
                retrieved_at=_dt.datetime.now(_dt.UTC).isoformat(),
            )
    return SourceOutcome(
        source="gutenberg",
        found=False,
        query=query,
        timestamp=_dt.datetime.now(_dt.UTC).isoformat(),
    )


def _search_ia(
    title: str,
    author: str | None,
    fetcher: _FetcherProto,
) -> FreeCopyFound | SourceOutcome:
    """Search Internet Archive for a public-domain copy of *title*.

    Uses the existing ``advancedsearch`` (Layer-1 NOT_IN_COPYRIGHT query)
    then ``item_candidate`` (Layer-2 per-item rights re-check).  Returns the
    first PD hit or a ``SourceOutcome`` noting no PD results.
    """
    from . import internet_archive as ia

    query = f"title:{_ia_phrase(title)}"
    if author:
        query += f" AND creator:{_ia_phrase(author)}"
    try:
        # advancedsearch is typed to concrete ThrottledFetcher (owned lane);
        # _FetcherProto is structurally compatible (get_json only).
        identifiers = ia.advancedsearch(fetcher, query=query, limit=5)  # type: ignore[arg-type]
    except Exception as exc:
        raise FetchError(f"IA advancedsearch failed: {exc}") from exc

    for ident in identifiers:
        try:
            cand = ia.item_candidate(fetcher, ident)  # type: ignore[arg-type]  # concrete ThrottledFetcher param; _FetcherProto is structurally compatible
        except Exception:
            continue
        if cand is not None and (cand.license_uri is not None or cand.pd_signal is not None):
            return FreeCopyFound(
                source="internet_archive",
                candidate_ref=cand,
                rights_basis=cand.pd_signal or cand.license_uri or "",
                retrieved_at=_dt.datetime.now(_dt.UTC).isoformat(),
            )

    return SourceOutcome(
        source="internet_archive",
        found=False,
        query=query,
        timestamp=_dt.datetime.now(_dt.UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# Ingest handoff
# ---------------------------------------------------------------------------


def ingest_found_copy(
    found: FreeCopyFound,
    fetcher: _FetcherProto,
    *,
    investigation_id: str = "inv-library",
    db_path: str | None = None,
    embedder: Any = None,
) -> PdIngestOutcome:
    """Hand a :class:`FreeCopyFound` to the SPR-02 classify-and-ingest path.

    Only ``BookCandidate`` instances (Internet Archive / Wave-2 sources) are
    supported — the SPR-02 ``classify_and_ingest`` chokepoint expects that
    type.  Gutenberg ``PublicDomainWork`` results should be ingested via the
    existing ``tools/ingest_public_domain`` CLI.

    Raises :class:`TypeError` if ``candidate_ref`` is not a ``BookCandidate``.
    """
    candidate = found.candidate_ref
    if not isinstance(candidate, BookCandidate):
        raise TypeError(
            f"ingest_found_copy expects a BookCandidate (Wave-2 connector type); "
            f"got {type(candidate).__name__}.  Use tools/ingest_public_domain "
            "for Gutenberg PublicDomainWork results."
        )
    return classify_and_ingest(
        candidate,
        # classify_and_ingest is typed to the concrete ThrottledFetcher; the
        # _FetcherProto is structurally compatible (SourceClientFetcher wraps a
        # real ThrottledFetcher for the IA path) and pd_connector_base is owned
        # by another lane, so the narrow ignore stays here rather than widening
        # their signature.
        fetcher,  # type: ignore[arg-type]
        investigation_id=investigation_id,
        db_path=db_path,
        embedder=embedder,
    )


# ---------------------------------------------------------------------------
# Production fetcher wrapper
# ---------------------------------------------------------------------------


class SourceClientFetcher:
    """Route Gutendex / archive.org requests through the existing
    ``SourceClient`` (Gutendex throttle) and ``ThrottledFetcher`` (IA
    throttle).  Satisfies the ``_FetcherProto`` protocol so
    :func:`search_free_copy` accepts it.

    NOT a new HTTP client — it delegates to the existing per-source clients
    that carry the SPR-03 throttle + ban-sentinel machinery.
    """

    def __init__(self) -> None:
        from .pd_connector_base import ThrottledFetcher
        from .public_domain import SourceClient

        self._gutenberg = SourceClient(source="gutendex")
        self._ia = ThrottledFetcher(source="internet_archive")

    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if "gutendex.com" in url:
            return self._gutenberg.get_json(url, params=params)
        return self._ia.get_json(url, params=params)

    def get_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> bytes:
        if "gutendex.com" in url:
            return self._gutenberg.get_bytes(url)
        return self._ia.get_bytes(url, params=params)
