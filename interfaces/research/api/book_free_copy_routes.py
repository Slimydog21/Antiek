"""Registerable free-copy preflight HTTP surface (marketplace honesty).

Operator intent: search for a free PD/OA copy before any purchase intent.
Wraps ``acquisition.books.lookup.search_free_copy`` with an injectable
search function so unit tests never open live PD network sockets.

Does not perform purchase, Stripe charges, or app.py registration
(create_app mount is a separate residual while app.py is owned).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from acquisition.books.lookup import (
    FreeCopyFound,
    NotFreelyAvailable,
    SourceOutcome,
    search_free_copy,
)

book_free_copy_router = APIRouter(
    prefix="/books/free-copy",
    tags=["book-free-copy-preflight"],
)

SearchFn = Callable[..., FreeCopyFound | NotFreelyAvailable]

_SEARCH_FN: SearchFn | None = None


def set_free_copy_search_fn(fn: SearchFn | None) -> None:
    """Inject search implementation (tests); None restores production default."""
    global _SEARCH_FN
    _SEARCH_FN = fn


def _default_search(
    title: str,
    author: str | None = None,
    *,
    sources: tuple[str, ...] = ("gutenberg", "internet_archive"),
) -> FreeCopyFound | NotFreelyAvailable:
    return search_free_copy(title, author, sources=sources)


def _search() -> SearchFn:
    return _SEARCH_FN if _SEARCH_FN is not None else _default_search


class FreeCopyPreflightRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    author: str | None = Field(default=None, max_length=512)
    sources: list[str] | None = Field(
        default=None,
        description="Optional source allowlist; default gutenberg+internet_archive",
    )


def _outcome_dict(o: SourceOutcome) -> dict[str, Any]:
    return {
        "source": o.source,
        "found": bool(o.found),
        "query": o.query,
        "timestamp": o.timestamp,
        "error": o.error,
    }


def project_free_copy_result(
    result: FreeCopyFound | NotFreelyAvailable,
    *,
    requested_title: str,
    requested_author: str | None,
) -> dict[str, Any]:
    """Honest JSON projection — never invent a free hit; omit raw candidate objects."""
    if isinstance(result, FreeCopyFound):
        kind = type(result.candidate_ref).__name__
        return {
            "freely_available": True,
            "title": requested_title,
            "author": requested_author,
            "source": result.source,
            "rights_basis": result.rights_basis,
            "retrieved_at": result.retrieved_at,
            "candidate_kind": kind,
            # Opaque ref withheld — bytes/network objects must not leak via HTTP.
            "candidate_ref_withheld": True,
            "outcomes": [],
            "checked_at": result.retrieved_at,
        }
    if isinstance(result, NotFreelyAvailable):
        return {
            "freely_available": False,
            "title": result.title,
            "author": result.author,
            "source": None,
            "rights_basis": None,
            "retrieved_at": None,
            "candidate_kind": None,
            "candidate_ref_withheld": True,
            "outcomes": [_outcome_dict(o) for o in result.outcomes],
            "checked_at": result.checked_at,
        }
    raise TypeError(f"unexpected free-copy result type: {type(result)!r}")


@book_free_copy_router.post("/preflight")
def free_copy_preflight(req: FreeCopyPreflightRequest) -> dict[str, Any]:
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must be non-empty")
    author = (req.author or "").strip() or None
    sources: Sequence[str]
    if req.sources is None:
        sources = ("gutenberg", "internet_archive")
    else:
        sources = tuple(s.strip() for s in req.sources if isinstance(s, str) and s.strip())
        if not sources:
            raise HTTPException(status_code=400, detail="sources must be non-empty when provided")

    try:
        result = _search()(title, author, sources=tuple(sources))
    except TypeError:
        # Injectable may not accept sources= kw — try positional-compatible call.
        result = _search()(title, author)
    except Exception as exc:  # noqa: BLE001 — surface as 502 without leaking secrets
        raise HTTPException(
            status_code=502,
            detail=f"free-copy preflight failed: {type(exc).__name__}",
        ) from exc

    return project_free_copy_result(
        result,
        requested_title=title,
        requested_author=author,
    )


def register_book_free_copy_routes(app: FastAPI) -> None:
    app.include_router(book_free_copy_router)


__all__ = [
    "book_free_copy_router",
    "project_free_copy_result",
    "register_book_free_copy_routes",
    "set_free_copy_search_fn",
]
