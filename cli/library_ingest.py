"""``antiek library ingest`` CLI (M8).

Two modes:

  antiek library ingest <url> --user <user_id>
  antiek library ingest --batch <file_of_urls.txt> --user <user_id>

Batch mode reads URLs line-by-line (blank lines + ``#`` comments
skipped) and ingests sequentially. Progress is one line per URL to
stdout; final summary printed at the end.

Exit code 0 on full success; non-zero with a count of failures on
partial / total failure. The exit code is meant to be usable by
shell scripts and CI.

Usage as a module: ``python -m cli.library_ingest <url> --user uid``.
The ``antiek`` console_script entry point in pyproject.toml is the
production-facing surface; this module is also directly runnable for
operator scripts.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)


def _read_url_file(path: str) -> list[str]:
    """One URL per line; ``#`` comments + blank lines skipped."""
    urls: list[str] = []
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    return urls


def _ingest_one(
    url: str,
    *,
    user_id: str,
    investigation_id: str,
    dry_run: bool,
    db_path: Optional[str],
) -> tuple[bool, str]:
    """Returns (succeeded, document_id_or_error)."""
    from services.ingestion import pipeline as pipeline_mod
    from services.ingestion import content_type as ct_mod

    if dry_run:
        # In dry-run we don't actually fetch. We still run detection
        # against the URL pattern (cheap, offline) so the user sees
        # what route the pipeline *would* take.
        det = ct_mod.detect(url, do_head=False)
        # Synthesize a job for compatibility with test harness.
        from services.ingestion import jobs as jobs_mod
        job = jobs_mod.create_job(
            url=url, user_id=user_id,
            investigation_id=investigation_id,
            metadata={"dry_run": True, "detected": det.content_type},
            db_path=db_path,
        )
        jobs_mod.update_status(
            job.job_id, status="succeeded",
            content_type=det.content_type,
            document_id=f"doc-dryrun-{det.content_type}",
            db_path=db_path,
        )
        return (True, f"doc-dryrun-{det.content_type}")

    result = pipeline_mod.ingest(
        url=url, user_id=user_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    if result.status == "succeeded" and result.document_id:
        return (True, result.document_id)
    return (False, result.error or "unknown")


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point. Returns exit code."""
    parser = argparse.ArgumentParser(
        prog="antiek library ingest",
        description="Ingest one or more URLs into the universal library.",
    )
    parser.add_argument(
        "url", nargs="?",
        help="URL to ingest (omit when using --batch).",
    )
    parser.add_argument(
        "--user", required=True,
        help="user_id to attribute the ingest to.",
    )
    parser.add_argument(
        "--investigation", default="__operator__",
        help="Investigation id scope (default: __operator__).",
    )
    parser.add_argument(
        "--batch",
        help="Path to a file with one URL per line.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip the actual fetch + extract; print what would happen.",
    )
    parser.add_argument(
        "--db-path",
        help="Override the DuckDB path (default: substrate default).",
    )
    args = parser.parse_args(argv)

    if not args.url and not args.batch:
        parser.error("provide a URL or --batch")
    if args.url and args.batch:
        parser.error("provide URL or --batch, not both")

    urls: list[str] = [args.url] if args.url else _read_url_file(args.batch)
    if not urls:
        print("no URLs to ingest", file=sys.stderr)
        return 2

    succeeded = 0
    failed: list[tuple[str, str]] = []
    for i, url in enumerate(urls, start=1):
        prefix = f"[{i}/{len(urls)}]"
        try:
            ok, doc_or_err = _ingest_one(
                url, user_id=args.user,
                investigation_id=args.investigation,
                dry_run=args.dry_run,
                db_path=args.db_path,
            )
        except Exception as exc:  # noqa: BLE001
            failed.append((url, f"crash:{exc!r}"))
            print(f"{prefix} FAIL {url}: crash {exc!r}", file=sys.stderr)
            continue
        if ok:
            succeeded += 1
            print(f"{prefix} OK   {url} → {doc_or_err}")
        else:
            failed.append((url, doc_or_err))
            print(f"{prefix} FAIL {url}: {doc_or_err}", file=sys.stderr)

    print()
    print(f"summary: {succeeded} succeeded, {len(failed)} failed of {len(urls)} URLs")
    if failed:
        for url, err in failed:
            print(f"  FAIL {url}: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
