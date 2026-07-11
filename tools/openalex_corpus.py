#!/usr/bin/env python3
"""Operator CLI for durable OpenAlex sync, search, and fetch."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, TextIO, cast

import httpx

from acquisition.corpus_bridge import from_openalex
from acquisition.openalex import OpenAlexClient, RateLimitExceeded
from acquisition.openalex_cache import (
    CachedOpenAlexSearch,
    OpenAlexSnapshotError,
    OpenAlexSnapshotStore,
)
from substrate.corpus_contract import CorpusContractError, CorpusDocument, CorpusMiss

EXIT_OK, EXIT_CONFIGURATION, EXIT_PROVIDER, EXIT_CACHE, EXIT_MISS = 0, 3, 4, 5, 6
_MAILTO = re.compile(r"[^\s@]{1,128}@[^\s@]{1,128}\Z")
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
_PROVIDER_ERRORS = (RateLimitExceeded, httpx.HTTPError, RuntimeError, ValueError)
_CACHE_ERRORS = (OpenAlexSnapshotError, CorpusContractError, OSError)


class ResponseLike(Protocol):
    status_code: int

    def json(self) -> dict[str, object]: ...


Get = Callable[[str], ResponseLike]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openalex-corpus",
        description="Persist governed OpenAlex search, then search/fetch it offline.",
    )
    parser.add_argument("--cache-dir", type=Path, default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync-search", help="Make a confirmed live search and persist it.")
    sync.add_argument("query")
    sync.add_argument("--max-records", type=int, default=25)
    sync.add_argument("--yes", action="store_true")
    search = commands.add_parser("search", help="Search persisted works without network.")
    search.add_argument("query")
    fetch = commands.add_parser("fetch", help="Fetch one persisted work without network.")
    fetch.add_argument("work_id")
    return parser


def _emit(stream: TextIO, payload: Mapping[str, object]) -> None:
    stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _cache_dir(args: argparse.Namespace, environ: Mapping[str, str]) -> Path:
    if args.cache_dir is not None:
        return cast(Path, args.cache_dir)
    home = Path(environ.get("ANTIEK_HOME", str(Path.home() / ".antiek")))
    return home / "caches" / "openalex"


def _http_get() -> tuple[httpx.Client, Get]:
    client = httpx.Client(timeout=httpx.Timeout(20.0), follow_redirects=False)

    def get(url: str) -> ResponseLike:
        response = client.get(url)
        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise RuntimeError("OpenAlex response exceeds local bound")
        return response

    return client, get


def _sync(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    store: OpenAlexSnapshotStore,
    get: Get | None,
) -> int:
    if not args.yes:
        _emit(sys.stderr, {"error": "live_request_not_confirmed", "next": "rerun with --yes"})
        return EXIT_CONFIGURATION
    mailto = environ.get("OPENALEX_MAILTO", "")
    if not _MAILTO.fullmatch(mailto):
        _emit(sys.stderr, {"error": "missing_or_invalid_openalex_mailto"})
        return EXIT_CONFIGURATION
    if (
        type(args.max_records) is not int
        or isinstance(args.max_records, bool)
        or not 1 <= args.max_records <= 100
    ):
        _emit(sys.stderr, {"error": "invalid_max_records", "allowed": "1..100"})
        return EXIT_CONFIGURATION
    client: httpx.Client | None = None
    if get is None:
        client, get = _http_get()
    try:
        source = OpenAlexClient(
            get=get,
            mailto=mailto,
            cache_dir=store.cache_dir / "raw-nonauthoritative",
        )
        records = CachedOpenAlexSearch(source, store).sync(args.query, max_records=args.max_records)
    except OpenAlexSnapshotError:
        raise
    except _PROVIDER_ERRORS:
        _emit(sys.stderr, {"error": "provider_request_failed"})
        return EXIT_PROVIDER
    finally:
        if client is not None:
            client.close()
    _emit(
        sys.stdout,
        {
            "count": len(records),
            "status": "persisted",
            "work_ids": [item["id"] for item in records],
        },
    )
    return EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    get: Get | None = None,
) -> int:
    args = _parser().parse_args(argv)
    env = os.environ if environ is None else environ
    try:
        store = OpenAlexSnapshotStore(_cache_dir(args, env))
        if args.command == "sync-search":
            return _sync(args, env, store, get)
        adapter = from_openalex(store.load())
        if args.command == "search":
            hits = adapter.search(args.query)
            _emit(
                sys.stdout,
                {
                    "count": len(hits),
                    "hits": [
                        {"id": hit.id, "score": hit.score, "snippet": hit.snippet} for hit in hits
                    ],
                },
            )
            return EXIT_OK
        result = adapter.fetch(args.work_id)
        if type(result) is CorpusMiss:
            _emit(sys.stderr, {"error": "work_not_found", "work_id": result.id})
            return EXIT_MISS
        if type(result) is not CorpusDocument:
            raise CorpusContractError("fetch returned an unsupported result")
        _emit(
            sys.stdout,
            {
                "content": result.content,
                "license_class": result.provenance.license_class,
                "retrieved_at": result.provenance.retrieved_at.isoformat(),
                "source_kind": result.provenance.source_kind,
                "work_id": result.provenance.origin_ref,
            },
        )
        return EXIT_OK
    except _CACHE_ERRORS:
        _emit(sys.stderr, {"error": "cache_contract_failed"})
        return EXIT_CACHE


if __name__ == "__main__":
    raise SystemExit(main())
