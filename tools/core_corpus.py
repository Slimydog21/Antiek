#!/usr/bin/env python3
"""Operator CLI for durable CORE scholarly metadata search."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO, cast

import httpx

_REPO = str(Path(__file__).resolve().parent.parent)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.core_cache import (  # noqa: E402
    CachedCoreSearch,
    CoreCorpusAdapter,
    CoreSnapshotError,
    CoreSnapshotStore,
    SearchWorks,
)
from acquisition.papers._pipeline import PaperRecord  # noqa: E402
from acquisition.papers.core import DEFAULT_BASE_URL, search_works  # noqa: E402
from substrate.corpus_contract import (  # noqa: E402
    CorpusContractError,
    CorpusDocument,
    CorpusMiss,
)
from substrate.source_throttle import SourceBanned, SourceThrottle  # noqa: E402

EXIT_OK, EXIT_CONFIGURATION, EXIT_PROVIDER, EXIT_CACHE, EXIT_MISS = 0, 3, 4, 5, 6
_API_KEY = re.compile(r"\S{8,512}\Z")
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
_PROVIDER_ERRORS = (SourceBanned, httpx.HTTPError, RuntimeError, ValueError)
_CACHE_ERRORS = (CoreSnapshotError, CorpusContractError, OSError)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="core-corpus",
        description="Persist one governed CORE search, then search/fetch it offline.",
    )
    parser.add_argument("--cache-dir", type=Path, default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync-search", help="Make one confirmed live search and persist it.")
    sync.add_argument("query")
    sync.add_argument("--max-records", type=int, default=25)
    sync.add_argument("--yes", action="store_true")
    search = commands.add_parser("search", help="Search persisted works without network.")
    search.add_argument("query")
    fetch = commands.add_parser("fetch", help="Fetch one persisted metadata record without network.")
    fetch.add_argument("work_id")
    return parser


def _emit(stream: TextIO, payload: Mapping[str, object]) -> None:
    stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _cache_dir(args: argparse.Namespace, environ: Mapping[str, str]) -> Path:
    if args.cache_dir is not None:
        return cast(Path, args.cache_dir)
    home = Path(environ.get("ANTIEK_HOME", str(Path.home() / ".antiek")))
    return home / "caches" / "core"


def _live_search(api_key: str, store: CoreSnapshotStore) -> tuple[httpx.Client, SearchWorks]:
    # CORE documents batch search at one request per ten seconds. Persist the
    # spacing and ban sentinel beside the private snapshot across CLI restarts.
    throttle = SourceThrottle(
        state_path=str(store.cache_dir / "throttle.json"),
        min_interval_overrides={"core": 10.0},
    )

    def bound(response: httpx.Response) -> None:
        response.read()
        throttle.note_response("core", response.status_code, response.headers)
        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise RuntimeError("CORE response exceeds local bound")

    client = httpx.Client(
        timeout=httpx.Timeout(20.0),
        follow_redirects=False,
        event_hooks={"response": [bound]},
    )

    def search(query: str, limit: int) -> list[PaperRecord]:
        return search_works(
            query=query,
            limit=limit,
            api_key=api_key,
            client=client,
            base_url=DEFAULT_BASE_URL,
            throttle=throttle,
        )

    return client, search


def _sync(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    store: CoreSnapshotStore,
    search: SearchWorks | None,
) -> int:
    if not args.yes:
        _emit(sys.stderr, {"error": "live_request_not_confirmed", "next": "rerun with --yes"})
        return EXIT_CONFIGURATION
    key = environ.get("ANTIEK_CORE_API_KEY", "")
    if not _API_KEY.fullmatch(key):
        _emit(sys.stderr, {"error": "missing_or_invalid_core_api_key"})
        return EXIT_CONFIGURATION
    if type(args.max_records) is not int or isinstance(args.max_records, bool) or not 1 <= args.max_records <= 100:
        _emit(sys.stderr, {"error": "invalid_max_records", "allowed": "1..100"})
        return EXIT_CONFIGURATION
    client: httpx.Client | None = None
    if search is None:
        client, search = _live_search(key, store)
    try:
        records = CachedCoreSearch(search, store).sync(args.query, max_records=args.max_records)
    except CoreSnapshotError:
        raise
    except _PROVIDER_ERRORS:
        _emit(sys.stderr, {"error": "provider_request_failed"})
        return EXIT_PROVIDER
    finally:
        if client is not None:
            client.close()
    _emit(sys.stdout, {"count": len(records), "status": "persisted", "work_ids": [item["id"] for item in records]})
    return EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    search: SearchWorks | None = None,
) -> int:
    args = _parser().parse_args(argv)
    env = os.environ if environ is None else environ
    try:
        store = CoreSnapshotStore(_cache_dir(args, env))
        if args.command == "sync-search":
            return _sync(args, env, store, search)
        adapter = CoreCorpusAdapter(store.load())
        if args.command == "search":
            hits = adapter.search(args.query)
            _emit(sys.stdout, {"count": len(hits), "hits": [{"id": hit.id, "score": hit.score, "snippet": hit.snippet} for hit in hits]})
            return EXIT_OK
        result = adapter.fetch(args.work_id)
        if type(result) is CorpusMiss:
            _emit(sys.stderr, {"error": "work_not_found", "work_id": result.id})
            return EXIT_MISS
        if type(result) is not CorpusDocument:
            raise CorpusContractError("fetch returned an unsupported result")
        _emit(sys.stdout, {"content": result.content, "license_class": result.provenance.license_class, "retrieved_at": result.provenance.retrieved_at.isoformat(), "source_kind": result.provenance.source_kind, "work_id": result.provenance.origin_ref})
        return EXIT_OK
    except _CACHE_ERRORS:
        _emit(sys.stderr, {"error": "cache_contract_failed"})
        return EXIT_CACHE


if __name__ == "__main__":
    raise SystemExit(main())
