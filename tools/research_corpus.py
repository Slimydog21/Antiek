#!/usr/bin/env python3
"""Search and fetch across explicitly mounted durable research corpora."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

_REPO = str(Path(__file__).resolve().parent.parent)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.core_cache import CoreSnapshotError  # noqa: E402
from acquisition.openalex_cache import OpenAlexSnapshotError  # noqa: E402
from acquisition.research_corpus_mounts import (  # noqa: E402
    MountConfigurationError,
    load_research_corpus_mounts,
)
from acquisition.s2_cache import S2SnapshotError  # noqa: E402
from substrate.corpus_contract import (  # noqa: E402
    CorpusContractError,
    CorpusDocument,
    CorpusMiss,
)
from substrate.corpus_federation import FederatedCorpus  # noqa: E402

EXIT_OK, EXIT_CONFIGURATION, EXIT_CACHE, EXIT_MISS = 0, 3, 5, 6
_CACHE_ERRORS = (
    CoreSnapshotError,
    OpenAlexSnapshotError,
    S2SnapshotError,
    CorpusContractError,
    OSError,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-corpus",
        description="Search/fetch explicit durable corpus mounts without network.",
    )
    parser.add_argument(
        "--mount",
        action="append",
        required=True,
        metavar="KIND=PATH",
        help="repeatable mount: s2=PATH, openalex=PATH, or core=PATH",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=50)
    fetch = commands.add_parser("fetch")
    fetch.add_argument("qualified_id")
    return parser


def _emit(stream: TextIO, payload: Mapping[str, object]) -> None:
    stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "search":
            if type(args.query) is not str or not args.query.strip() or args.query != args.query.strip() or "\n" in args.query or "\r" in args.query:
                _emit(sys.stderr, {"error": "invalid_query"})
                return EXIT_CONFIGURATION
            if type(args.limit) is not int or isinstance(args.limit, bool) or not 1 <= args.limit <= 300:
                _emit(sys.stderr, {"allowed": "1..300", "error": "invalid_limit"})
                return EXIT_CONFIGURATION
        elif type(args.qualified_id) is not str or ":" not in args.qualified_id or not all(args.qualified_id.split(":", 1)):
            _emit(sys.stderr, {"error": "invalid_qualified_id"})
            return EXIT_CONFIGURATION
        try:
            federation = FederatedCorpus(load_research_corpus_mounts(args.mount))
        except MountConfigurationError:
            _emit(sys.stderr, {"error": "invalid_mount_configuration"})
            return EXIT_CONFIGURATION
        if args.command == "search":
            hits = federation.search(args.query)[: args.limit]
            _emit(sys.stdout, {"count": len(hits), "hits": [{"id": hit.id, "score": hit.score, "snippet": hit.snippet} for hit in hits]})
            return EXIT_OK
        result = federation.fetch(args.qualified_id)
        if type(result) is CorpusMiss:
            _emit(sys.stderr, {"error": "work_not_found", "reason": result.reason, "work_id": result.id})
            return EXIT_MISS
        if type(result) is not CorpusDocument:
            raise CorpusContractError("federated fetch returned unsupported result")
        _emit(sys.stdout, {"content": result.content, "license_class": result.provenance.license_class, "origin_ref": result.provenance.origin_ref, "retrieved_at": result.provenance.retrieved_at.isoformat(), "source_kind": result.provenance.source_kind, "work_id": args.qualified_id})
        return EXIT_OK
    except _CACHE_ERRORS:
        _emit(sys.stderr, {"error": "cache_contract_failed"})
        return EXIT_CACHE


if __name__ == "__main__":
    raise SystemExit(main())
