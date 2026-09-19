#!/usr/bin/env python3
"""Operator CLI for durable Substack RSS sync, search, and fetch."""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, TextIO, cast
from urllib.parse import urlsplit

import httpx

from acquisition.corpus_bridge import from_substack
from acquisition.oai_pmh import BannedUntil
from acquisition.substack_cache import (
    CachedSubstackFeed,
    SubstackSnapshotError,
    SubstackSnapshotStore,
)
from acquisition.substack_feed import SubstackClient
from substrate.corpus_contract import CorpusContractError, CorpusDocument, CorpusMiss

EXIT_OK, EXIT_CONFIGURATION, EXIT_PROVIDER, EXIT_CACHE, EXIT_MISS = 0, 3, 4, 5, 6
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_PROVIDER_ERRORS = (BannedUntil, httpx.HTTPError, RuntimeError, ET.ParseError)
_CACHE_ERRORS = (SubstackSnapshotError, CorpusContractError, OSError)


class ResponseLike(Protocol):
    status_code: int
    text: str

    @property
    def headers(self) -> Mapping[str, str]: ...

    def json(self) -> object: ...


Get = Callable[[str], ResponseLike]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="substack-corpus",
        description="Persist a canonical Substack RSS feed, then search/fetch it offline.",
    )
    parser.add_argument("--cache-dir", type=Path, default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser(
        "sync-feed", help="Make one confirmed live RSS request and persist it."
    )
    sync.add_argument("publication_url")
    sync.add_argument("--yes", action="store_true")
    search = commands.add_parser("search", help="Search persisted posts without network.")
    search.add_argument("query")
    fetch = commands.add_parser(
        "fetch", help="Fetch one persisted accessible post without network."
    )
    fetch.add_argument("post_url")
    return parser


def _emit(stream: TextIO, payload: Mapping[str, object]) -> None:
    stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _cache_dir(args: argparse.Namespace, environ: Mapping[str, str]) -> Path:
    if args.cache_dir is not None:
        return cast(Path, args.cache_dir)
    home = Path(environ.get("ANTIEK_HOME", str(Path.home() / ".antiek")))
    return home / "caches" / "substack"


def _publication(value: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise SubstackSnapshotError("publication URL is invalid") from error
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or (host != "substack.com" and not host.endswith(".substack.com"))
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise SubstackSnapshotError("publication must be a canonical HTTPS substack.com host")
    return f"https://{host}", host


def _http_get() -> tuple[httpx.Client, Get]:
    client = httpx.Client(timeout=httpx.Timeout(20.0), follow_redirects=False)

    def get(url: str) -> ResponseLike:
        response = client.get(url)
        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise RuntimeError("Substack response exceeds local bound")
        return response

    return client, get


def _records_for_corpus(store: SubstackSnapshotStore) -> tuple[dict[str, object], ...]:
    return tuple(
        {key: value for key, value in item.items() if key != "publication"} for item in store.load()
    )


def _sync(args: argparse.Namespace, store: SubstackSnapshotStore, get: Get | None) -> int:
    if not args.yes:
        _emit(sys.stderr, {"error": "live_request_not_confirmed", "next": "rerun with --yes"})
        return EXIT_CONFIGURATION
    base_url, publication = _publication(args.publication_url)
    client: httpx.Client | None = None
    if get is None:
        client, get = _http_get()
    try:
        source = SubstackClient(
            base_url=base_url,
            get=get,
            sentinel_path=store.cache_dir / f"ban-{publication}.json",
        )
        records = CachedSubstackFeed(source, store, publication=publication).sync()
    except _PROVIDER_ERRORS:
        _emit(sys.stderr, {"error": "provider_request_failed"})
        return EXIT_PROVIDER
    finally:
        if client is not None:
            client.close()
    _emit(
        sys.stdout,
        {
            "accessible": sum(bool(item["accessible"]) for item in records),
            "count": len(records),
            "publication": publication,
            "status": "persisted",
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
        store = SubstackSnapshotStore(_cache_dir(args, env))
        if args.command == "sync-feed":
            return _sync(args, store, get)
        adapter = from_substack(_records_for_corpus(store))
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
        result = adapter.fetch(args.post_url)
        if type(result) is CorpusMiss:
            _emit(
                sys.stderr,
                {"error": "post_unavailable", "post_url": result.id, "reason": result.reason},
            )
            return EXIT_MISS
        assert type(result) is CorpusDocument
        _emit(
            sys.stdout,
            {
                "content": result.content,
                "license_class": result.provenance.license_class,
                "post_url": result.provenance.origin_ref,
                "retrieved_at": result.provenance.retrieved_at.isoformat(),
                "source_kind": result.provenance.source_kind,
            },
        )
        return EXIT_OK
    except _CACHE_ERRORS:
        _emit(sys.stderr, {"error": "cache_contract_failed"})
        return EXIT_CACHE


if __name__ == "__main__":
    raise SystemExit(main())
