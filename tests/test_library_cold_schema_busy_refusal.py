"""Real private Library contention and post-release catalogue controls."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator

import httpx
import pytest
from test_library_account_admission import page, seed_book
from test_operational_account_isolation import account_api as account_api
from test_reader_cold_schema_busy_refusal import (
    PrivateReader,
    _external_writer,
    _record,
    _release,
)
from test_reader_cold_schema_busy_refusal import private_reader as private_reader

from runtime import db_lock
from substrate.graph import schema


@pytest.fixture
def private_library(private_reader: PrivateReader) -> Iterator[PrivateReader]:
    reader = private_reader
    bob = reader.bob.get("/auth/me").json()["user_id"]
    with db_lock.connect_write(
        reader.db,
        purpose="test/library-cold-seed",
        keepalive_s=0,
    ) as con:
        seed_book(con, "second-public", bob, "public_domain", order=1)
        seed_book(con, "bob-private", bob, "user_owned", order=2)
        seed_book(con, "unknown-private", "unresolved-library-owner", None, order=3)
    db_lock.flush_warm_writers(reader.db)
    yield reader


@pytest.mark.parametrize("filter", ("all", "servable", "gated"))
def test_cold_catalogue_busy_refuses_without_writer_and_recovers(
    private_library: PrivateReader,
    filter: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = private_library
    schema._INITIALIZED_PATHS.discard(reader.db)
    writes: list[str] = []
    errors: list[str] = []
    real_write = schema.connect_write
    real_read = schema.connect_read

    def observed_write(*args, **kwargs):
        writes.append(kwargs["purpose"])
        return real_write(*args, **kwargs)

    def observed_read(*args, **kwargs):
        try:
            return real_read(*args, **kwargs)
        except db_lock.ReadLockTimeout as exc:
            errors.append(type(exc).__name__)
            raise

    monkeypatch.setattr(schema, "connect_write", observed_write)
    monkeypatch.setattr(schema, "connect_read", observed_read)
    with _external_writer(reader.db) as holder:

        async def exercise() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=reader.app),
                base_url="http://testserver",
                cookies=reader.alice.cookies,
            ) as client:
                started = time.monotonic()
                pending = asyncio.create_task(client.get("/library", params={"filter": filter}))
                try:
                    response = await asyncio.wait_for(asyncio.shield(pending), 6)
                    elapsed = time.monotonic() - started
                    _record(
                        "cold_library_busy",
                        filter=filter,
                        status=response.status_code,
                        elapsed_s=elapsed,
                        typed_errors=errors,
                        schema_writer_attempts=writes,
                    )
                    assert response.status_code == 503
                    assert response.headers["Retry-After"] == "2"
                    assert response.json() == {
                        "detail": "database read is temporarily unavailable; retry shortly",
                    }
                    assert errors == ["ReadLockTimeout"]
                    assert writes == []
                    assert 1.8 <= elapsed < 6
                    assert reader.db not in response.text and "PRIVATE" not in response.text
                    assert reader.db not in schema._INITIALIZED_PATHS
                    assert holder.poll() is None
                except TimeoutError:
                    _record(
                        "cold_library_request_deadline",
                        filter=filter,
                        elapsed_s=time.monotonic() - started,
                        typed_errors=errors,
                        schema_writer_attempts=writes,
                    )
                    raise
                finally:
                    await asyncio.to_thread(_release, holder)
                    await asyncio.wait_for(pending, 10)

        asyncio.run(exercise())
    assert holder.returncode == 0

    # Real stored rows recover after direct writer retirement, with the same
    # public/stored-owner filtering before totals and pagination.
    recovered = page(reader.alice, filter="all", page_size=200)
    works = {work["document_id"]: work for work in recovered["works"]}
    assert recovered["total"] == 3
    assert set(works) == {
        "cold-reader-public",
        "second-public",
        "cold-reader-owned",
    }
    metadata = reader.alice.get("/books/cold-reader-taken-down")
    assert metadata.status_code == 200
    assert metadata.json()["taken_down"] is True
    assert metadata.json()["servable_full_text"] is False
    assert works["cold-reader-owned"]["servable_full_text"] is False
    servable = page(reader.alice, filter="servable")
    assert servable["total"] == 2
    assert {work["document_id"] for work in servable["works"]} == {
        "cold-reader-public",
        "second-public",
    }
    gated = page(reader.alice, filter="gated")
    assert gated["total"] == 1
    assert {work["document_id"] for work in gated["works"]} == {
        "cold-reader-owned",
    }
    searched = page(reader.alice, search="TITLE SECOND", page_size=1)
    assert searched["total"] == 1
    assert searched["works"][0]["document_id"] == "second-public"
    pages = [page(reader.alice, page=number, page_size=2) for number in (1, 2)]
    ids = [{work["document_id"] for work in result["works"]} for result in pages]
    assert all(result["total"] == 3 for result in pages)
    assert ids[0].isdisjoint(ids[1]) and ids[0] | ids[1] == set(works)
    bob = page(reader.bob, filter="all")
    assert bob["total"] == 3
    assert {work["document_id"] for work in bob["works"]} == {
        "cold-reader-public",
        "second-public",
        "bob-private",
    }
    assert "SYNTHETIC PRIVATE TEST BOOK BODY" not in str(recovered)
    assert writes == []
    _record(
        "cold_library_recovered",
        filter=filter,
        status=200,
        alice_total=recovered["total"],
        bob_total=bob["total"],
        schema_writer_attempts=writes,
        holder_exit=holder.returncode,
    )
