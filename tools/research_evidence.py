#!/usr/bin/env python3
"""Build bounded evidence spans from explicit durable corpus mounts."""

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
from acquisition.s2_cache import S2SnapshotError  # noqa: E402
from substrate.corpus_contract import CorpusContractError  # noqa: E402
from substrate.corpus_evidence import render_chunks_block, select_evidence_spans  # noqa: E402
from substrate.corpus_federation import FederatedCorpus  # noqa: E402
from tools.research_corpus import MountConfigurationError, _mounts  # noqa: E402

EXIT_OK, EXIT_CONFIGURATION, EXIT_CACHE = 0, 3, 5
_CACHE_ERRORS = (
    CoreSnapshotError,
    OpenAlexSnapshotError,
    S2SnapshotError,
    CorpusContractError,
    OSError,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-evidence",
        description="Project offline federated corpus results into bounded evidence spans.",
    )
    parser.add_argument("--mount", action="append", required=True, metavar="KIND=PATH")
    parser.add_argument("query")
    parser.add_argument("--max-spans", type=int, default=5)
    parser.add_argument("--max-chars", type=int, default=1200)
    parser.add_argument("--format", choices=("json", "chunks"), default="json")
    return parser


def _emit(stream: TextIO, payload: Mapping[str, object]) -> None:
    stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if (
        type(args.query) is not str
        or not args.query.strip()
        or args.query != args.query.strip()
        or args.query.splitlines() != [args.query]
    ):
        _emit(sys.stderr, {"error": "invalid_query"})
        return EXIT_CONFIGURATION
    if type(args.max_spans) is not int or isinstance(args.max_spans, bool) or not 1 <= args.max_spans <= 50:
        _emit(sys.stderr, {"allowed": "1..50", "error": "invalid_max_spans"})
        return EXIT_CONFIGURATION
    if type(args.max_chars) is not int or isinstance(args.max_chars, bool) or not 200 <= args.max_chars <= 4000:
        _emit(sys.stderr, {"allowed": "200..4000", "error": "invalid_max_chars"})
        return EXIT_CONFIGURATION
    try:
        try:
            corpus = FederatedCorpus(_mounts(args.mount))
        except MountConfigurationError:
            _emit(sys.stderr, {"error": "invalid_mount_configuration"})
            return EXIT_CONFIGURATION
        spans = select_evidence_spans(
            corpus,
            args.query,
            max_spans=args.max_spans,
            max_chars=args.max_chars,
        )
        if args.format == "chunks":
            sys.stdout.write(render_chunks_block(spans) + "\n")
        else:
            _emit(
                sys.stdout,
                {
                    "count": len(spans),
                    "spans": [
                        {
                            "corpus_id": span.corpus_id,
                            "end_char": span.end_char,
                            "license_class": span.license_class,
                            "origin_ref": span.origin_ref,
                            "retrieved_at": span.retrieved_at.isoformat(),
                            "source_kind": span.source_kind,
                            "source_tier": span.source_tier,
                            "span_id": span.span_id,
                            "start_char": span.start_char,
                            "text": span.text,
                        }
                        for span in spans
                    ],
                },
            )
        return EXIT_OK
    except _CACHE_ERRORS:
        _emit(sys.stderr, {"error": "cache_contract_failed"})
        return EXIT_CACHE


if __name__ == "__main__":
    raise SystemExit(main())
