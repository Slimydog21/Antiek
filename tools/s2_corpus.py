#!/usr/bin/env python3
"""Operator CLI for durable Semantic Scholar enrich, search, and fetch."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, TextIO, cast

import httpx

from acquisition.corpus_bridge import from_semantic_scholar
from acquisition.s2_cache import CachedS2Enricher, S2SnapshotError, S2SnapshotStore
from acquisition.s2_enrich import BudgetExceeded, S2Client
from substrate.corpus_contract import CorpusContractError, CorpusDocument, CorpusMiss

EXIT_OK = 0
EXIT_CONFIGURATION = 3
EXIT_PROVIDER = 4
EXIT_CACHE = 5
EXIT_MISS = 6
_MAX_BATCH = 100
_PROVIDER_ERRORS = (BudgetExceeded, httpx.HTTPError, RuntimeError, json.JSONDecodeError)
_CACHE_ERRORS = (S2SnapshotError, CorpusContractError, OSError)


class ResponseLike(Protocol):
    status_code: int

    def json(self) -> list[dict[str, object]]: ...


Post = Callable[[str, Mapping[str, str], dict[str, object]], ResponseLike]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s2-corpus",
        description="Persist Semantic Scholar enrichment, then search/fetch it offline.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Private cache directory (default: $ANTIEK_HOME/caches/semantic-scholar).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    enrich = commands.add_parser(
        "enrich", help="Make one governed live batch request and persist it."
    )
    enrich.add_argument("ids", nargs="+", help="Provider-recognized paper identifiers.")
    enrich.add_argument(
        "--yes",
        action="store_true",
        help="Explicitly authorize the live provider request.",
    )
    search = commands.add_parser("search", help="Search the persisted snapshot without network.")
    search.add_argument("query")
    fetch = commands.add_parser("fetch", help="Fetch one persisted paper without network.")
    fetch.add_argument("paper_id")
    return parser


def _cache_dir(args: argparse.Namespace, environ: Mapping[str, str]) -> Path:
    if args.cache_dir is not None:
        return cast(Path, args.cache_dir)
    home = Path(environ.get("ANTIEK_HOME", str(Path.home() / ".antiek")))
    return home / "caches" / "semantic-scholar"


def _emit(stream: TextIO, payload: Mapping[str, object]) -> None:
    stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _http_post() -> tuple[httpx.Client, Post]:
    client = httpx.Client(timeout=httpx.Timeout(20.0), follow_redirects=False)

    def post(url: str, headers: Mapping[str, str], body: dict[str, object]) -> ResponseLike:
        return client.post(url, headers=dict(headers), json=body)

    return client, post


def _enrich(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    store: S2SnapshotStore,
    post: Post | None,
) -> int:
    if not args.yes:
        _emit(
            sys.stderr,
            {
                "error": "live_request_not_confirmed",
                "next": "rerun with enrich --yes after reviewing the identifiers",
            },
        )
        return EXIT_CONFIGURATION
    api_key = environ.get("S2_API_KEY")
    if api_key is None or not api_key.strip():
        _emit(sys.stderr, {"error": "missing_s2_api_key"})
        return EXIT_CONFIGURATION
    ids = args.ids
    if len(ids) > _MAX_BATCH or len(ids) != len(set(ids)):
        _emit(
            sys.stderr,
            {"error": "invalid_batch", "max_ids": _MAX_BATCH, "unique_required": True},
        )
        return EXIT_CONFIGURATION

    client: httpx.Client | None = None
    if post is None:
        client, post = _http_post()
    try:
        governed = S2Client(post=post, api_key=api_key)
        records = CachedS2Enricher(governed, store).enrich(ids)
    except _PROVIDER_ERRORS:
        _emit(sys.stderr, {"error": "provider_request_failed"})
        return EXIT_PROVIDER
    finally:
        if client is not None:
            client.close()
    _emit(
        sys.stdout,
        {
            "cache_dir": str(_cache_dir(args, environ)),
            "count": len(records),
            "paper_ids": [record["paperId"] for record in records],
            "status": "persisted",
        },
    )
    return EXIT_OK


def _search(args: argparse.Namespace, store: S2SnapshotStore) -> int:
    adapter = from_semantic_scholar(store.load())
    hits = adapter.search(args.query)
    _emit(
        sys.stdout,
        {
            "count": len(hits),
            "hits": [{"id": hit.id, "score": hit.score, "snippet": hit.snippet} for hit in hits],
        },
    )
    return EXIT_OK


def _fetch(args: argparse.Namespace, store: S2SnapshotStore) -> int:
    result = from_semantic_scholar(store.load()).fetch(args.paper_id)
    if type(result) is CorpusMiss:
        _emit(sys.stderr, {"error": "paper_not_found", "paper_id": result.id})
        return EXIT_MISS
    assert type(result) is CorpusDocument
    _emit(
        sys.stdout,
        {
            "content": result.content,
            "id": result.provenance.origin_ref,
            "license_class": result.provenance.license_class,
            "retrieved_at": result.provenance.retrieved_at.isoformat(),
            "source_kind": result.provenance.source_kind,
        },
    )
    return EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    post: Post | None = None,
) -> int:
    args = _parser().parse_args(argv)
    env = os.environ if environ is None else environ
    try:
        store = S2SnapshotStore(_cache_dir(args, env))
        if args.command == "enrich":
            return _enrich(args, env, store, post)
        if args.command == "search":
            return _search(args, store)
        return _fetch(args, store)
    except _CACHE_ERRORS:
        _emit(sys.stderr, {"error": "cache_contract_failed"})
        return EXIT_CACHE


if __name__ == "__main__":
    raise SystemExit(main())
