#!/usr/bin/env python3
"""license_library — license the operator's books in one command (D3).

The flywheel compounds only over SERVABLE knowledge. A freshly ingested
third-party book lands with ``content_class = NULL`` (deny-by-default,
master-spec §9.0) — it is invisible to retrieval and to knowledge reuse
until the operator asserts a rights basis. This CLI is that assertion:
it flips the unlicensed documents to a licensed ``content_class``
(``user_owned`` by default — the owner has rights to their own library)
via the ONLY sanctioned mutator,
``substrate.graph.ops.update_document_gate_columns``, under the
single-writer ``connect_write`` lock.

D3 = "license the library". Proven unblocked: the real adapter path uses
``connect_write`` autocommit, so existing chunked books CAN be re-licensed
(an earlier FK failure was a test-only artifact of an explicit BEGIN).

Safety posture
--------------
- ``--dry-run`` is the DEFAULT. It reports the exact plan (which docs,
  which class) and writes NOTHING. The operator passes ``--apply`` to
  mutate, against the real store only when ready.
- Idempotent: a document already carrying the target ``content_class`` is
  skipped (reported, not re-written).
- Single-writer: every mutation rides ``connect_write(purpose=...)`` so the
  §single-writer invariant and the gate-column index drop/recreate dance
  are honored exactly as ingest does.
- Real corpus: the operator's real store (``--db-path`` default) is only
  touched with ``--apply``. Verify on a scratch copy first (see --help).

Usage::

    # Plan only (no writes):
    python -m tools.license_library --db-path /path/to/research_graph.duckdb

    # Apply against a SCRATCH copy to verify:
    cp ~/.antiek/research_graph.duckdb /tmp/scratch.duckdb
    python -m tools.license_library --db-path /tmp/scratch.duckdb --apply

    # Apply against the REAL store (operator action):
    python -m tools.license_library --apply
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from runtime.db_lock import connect_write
from substrate.graph.ops import update_document_gate_columns

DEFAULT_DB_PATH = "/Users/slimydog/.antiek/research_graph.duckdb"
DEFAULT_CONTENT_CLASS = "user_owned"
DEFAULT_PURPOSE = "d3:license_library"


def discover_unlicensed(
    db_path: str,
    *,
    target_class: str,
    source_tier: int | None,
    document_id: str | None,
) -> list[tuple[str, str | None]]:
    """Return ``(document_id, current_content_class)`` for documents that are
    NOT yet at ``target_class``. Read-only. Filters by ``source_tier`` and/or
    ``document_id`` when given; otherwise every document below target."""
    from runtime.db_lock import connect_read

    where = ["(content_class IS NULL OR content_class <> ?)"]
    params: list[object] = [target_class]
    if source_tier is not None:
        where.append("source_tier = ?")
        params.append(source_tier)
    if document_id is not None:
        where.append("document_id = ?")
        params.append(document_id)
    con = connect_read(db_path)
    try:
        rows = con.execute(
            "SELECT document_id, content_class FROM documents "
            f"WHERE {' AND '.join(where)} ORDER BY document_id",
            params,
        ).fetchall()
    finally:
        con.close()
    return [(str(r[0]), None if r[1] is None else str(r[1])) for r in rows]


def license_documents(
    db_path: str,
    doc_ids: Sequence[str],
    *,
    content_class: str,
    ip_holder_id: str | None,
    purpose: str,
    apply: bool,
) -> list[tuple[str, str, str]]:
    """License each ``doc_id`` to ``content_class`` under one write lock.
    Returns ``(document_id, status, detail)`` triples where status is one of
    ``licensed`` / ``skipped`` / ``planned`` (dry-run)."""
    if not doc_ids:
        return []
    if not apply:
        return [(d, "planned", f"-> {content_class}") for d in doc_ids]
    results: list[tuple[str, str, str]] = []
    with connect_write(db_path, purpose=purpose) as con:
        for d in doc_ids:
            current = con.execute(
                "SELECT content_class FROM documents WHERE document_id = ?",
                [d],
            ).fetchone()
            if current and current[0] == content_class:
                results.append((d, "skipped", f"already {content_class}"))
                continue
            update_document_gate_columns(
                con,
                d,
                content_class=content_class,
                set_content_class=True,
                ip_holder_id=ip_holder_id,
                set_ip_holder_id=ip_holder_id is not None,
            )
            after = con.execute(
                "SELECT content_class FROM documents WHERE document_id = ?",
                [d],
            ).fetchone()
            results.append(
                (d, "licensed", f"{current[0] if current else None} -> {after[0] if after else '?'}")
            )
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="license_library",
        description="License the operator's books (flip content_class NULL -> user_owned) "
        "via the single-writer path. DRY-RUN by default.",
    )
    p.add_argument(
        "--db-path", default=DEFAULT_DB_PATH,
        help=f"path to the research_graph DuckDB (default: {DEFAULT_DB_PATH})",
    )
    p.add_argument(
        "--apply", action="store_true",
        help="MUTATE the store. Without it, only the plan is printed.",
    )
    p.add_argument(
        "--content-class", default=DEFAULT_CONTENT_CLASS,
        help=f"target content_class (default: {DEFAULT_CONTENT_CLASS})",
    )
    p.add_argument(
        "--ip-holder", default=None,
        help="optional ip_holder_id to stamp on each licensed document",
    )
    p.add_argument(
        "--source-tier", type=int, default=None,
        help="restrict to documents with this source_tier (default: all unlicensed)",
    )
    p.add_argument(
        "--document-id", default=None,
        help="restrict to a single document_id",
    )
    p.add_argument(
        "--purpose", default=DEFAULT_PURPOSE,
        help=f"write-lock purpose tag (default: {DEFAULT_PURPOSE})",
    )
    args = p.parse_args(argv)

    targets = discover_unlicensed(
        args.db_path,
        target_class=args.content_class,
        source_tier=args.source_tier,
        document_id=args.document_id,
    )
    if not targets:
        print(f"no documents below content_class={args.content_class!r} "
              f"(nothing to license).")
        return 0

    mode = "APPLY" if args.apply else "DRY-RUN (no writes)"
    print(f"== license_library [{mode}] ==")
    print(f"db_path={args.db_path} target_class={args.content_class} "
          f"source_tier={args.source_tier} document_id={args.document_id}")
    print(f"{len(targets)} document(s) below target:")
    for did, cur in targets:
        print(f"  {did}  (content_class={cur!r})")

    results = license_documents(
        args.db_path,
        [d for d, _ in targets],
        content_class=args.content_class,
        ip_holder_id=args.ip_holder,
        purpose=args.purpose,
        apply=args.apply,
    )
    if args.apply:
        print("\nresults:")
        for did, status, detail in results:
            print(f"  {status:<8} {did}  {detail}")
        licensed = sum(1 for _, s, _ in results if s == "licensed")
        print(f"\nlicensed {licensed} document(s) -> content_class={args.content_class!r}")
    else:
        print(f"\n(dry-run) would license {len(results)} document(s). "
              f"Re-run with --apply to mutate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
