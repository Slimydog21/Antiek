"""Hermetic tests for free-copy preflight routes — no live PD network."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from acquisition.books.lookup import FreeCopyFound, NotFreelyAvailable, SourceOutcome
from interfaces.research.api.book_free_copy_routes import (
    project_free_copy_result,
    register_book_free_copy_routes,
    set_free_copy_search_fn,
)


@dataclass
class _FakeCandidate:
    title: str = "Walden"


def _found() -> FreeCopyFound:
    return FreeCopyFound(
        source="gutenberg",
        candidate_ref=_FakeCandidate(),  # type: ignore[arg-type]
        rights_basis="copyright=false",
        retrieved_at="2026-07-11T00:00:00+00:00",
    )


def _not_found() -> NotFreelyAvailable:
    return NotFreelyAvailable(
        title="Unknown Book",
        author="Anon",
        outcomes=(
            SourceOutcome(
                source="gutenberg",
                found=False,
                query="Unknown Book",
                timestamp="2026-07-11T00:00:00+00:00",
                error=None,
            ),
        ),
        checked_at="2026-07-11T00:00:00+00:00",
    )


def test_project_found_withholds_candidate() -> None:
    body = project_free_copy_result(
        _found(),
        requested_title="Walden",
        requested_author="Thoreau",
    )
    assert body["freely_available"] is True
    assert body["source"] == "gutenberg"
    assert body["candidate_ref_withheld"] is True
    assert "candidate_ref" not in body
    assert body["candidate_kind"] == "_FakeCandidate"


def test_project_not_found_outcomes_honest() -> None:
    body = project_free_copy_result(
        _not_found(),
        requested_title="Unknown Book",
        requested_author="Anon",
    )
    assert body["freely_available"] is False
    assert body["source"] is None
    assert len(body["outcomes"]) == 1
    assert body["outcomes"][0]["found"] is False


def test_http_preflight_found_via_injectable() -> None:
    set_free_copy_search_fn(lambda title, author=None, **kw: _found())
    try:
        app = FastAPI()
        register_book_free_copy_routes(app)
        client = TestClient(app)
        r = client.post(
            "/books/free-copy/preflight",
            json={"title": "Walden", "author": "Thoreau"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["freely_available"] is True
        assert body["source"] == "gutenberg"
        assert body["candidate_ref_withheld"] is True
    finally:
        set_free_copy_search_fn(None)


def test_http_preflight_not_found_via_injectable() -> None:
    set_free_copy_search_fn(lambda title, author=None, **kw: _not_found())
    try:
        app = FastAPI()
        register_book_free_copy_routes(app)
        client = TestClient(app)
        r = client.post(
            "/books/free-copy/preflight",
            json={"title": "Unknown Book", "author": "Anon"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["freely_available"] is False
        assert body["outcomes"][0]["source"] == "gutenberg"
    finally:
        set_free_copy_search_fn(None)


def test_http_blank_title_rejected() -> None:
    set_free_copy_search_fn(lambda *a, **k: _found())
    try:
        app = FastAPI()
        register_book_free_copy_routes(app)
        client = TestClient(app)
        # pydantic min_length=1 catches empty string at validation
        r = client.post("/books/free-copy/preflight", json={"title": "   "})
        # strip happens after pydantic; whitespace-only may pass min_length then 400
        assert r.status_code in (400, 422)
    finally:
        set_free_copy_search_fn(None)


def test_http_empty_sources_rejected() -> None:
    set_free_copy_search_fn(lambda *a, **k: _found())
    try:
        app = FastAPI()
        register_book_free_copy_routes(app)
        client = TestClient(app)
        r = client.post(
            "/books/free-copy/preflight",
            json={"title": "Walden", "sources": ["  ", ""]},
        )
        assert r.status_code == 400
    finally:
        set_free_copy_search_fn(None)


def test_http_search_exception_is_502_not_200() -> None:
    def boom(*a, **k):  # noqa: ANN001
        raise RuntimeError("network exploded")

    set_free_copy_search_fn(boom)
    try:
        app = FastAPI()
        register_book_free_copy_routes(app)
        client = TestClient(app)
        r = client.post("/books/free-copy/preflight", json={"title": "Walden"})
        assert r.status_code == 502
        assert "freely_available" not in r.json() or r.json().get("freely_available") is not True
    finally:
        set_free_copy_search_fn(None)


def test_http_typeerror_is_single_call_502() -> None:
    """Internal TypeError must not retry (duplicate work) and must stay 502."""
    calls: list[tuple[object, ...]] = []

    def boom(title, author=None, *, sources=()):  # noqa: ANN001
        calls.append((title, author, sources))
        raise TypeError("internal contract break")

    set_free_copy_search_fn(boom)
    try:
        app = FastAPI()
        register_book_free_copy_routes(app)
        client = TestClient(app)
        r = client.post("/books/free-copy/preflight", json={"title": "Walden"})
        assert r.status_code == 502
        assert len(calls) == 1
        body = r.json()
        assert body.get("freely_available") is not True
    finally:
        set_free_copy_search_fn(None)
