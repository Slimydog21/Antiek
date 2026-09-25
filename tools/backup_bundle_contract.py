"""Reject incompatible DuckDB backup bundles before a destructive restore.

The nightly archive contains ``source_manifest.json`` beside DuckDB's Parquet
export. This check runs on the extracted archive before the recovery runbook
removes the destination DB. It does not attest archive authenticity; the
backup's upload/read-back digest and import verification serve that purpose.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from substrate.graph.schema import ARXIV_BULK_PROGRESS_COLUMNS

BUNDLE_CONTRACT_VERSION = 2
_MANIFEST_LIMIT_BYTES = 8 * 1024 * 1024


class BundleCompatibilityError(ValueError):
    """The extracted archive cannot be imported under this code contract."""


def _manifest(root: Path) -> dict[str, Any]:
    path = root / "source_manifest.json"
    try:
        if path.stat().st_size > _MANIFEST_LIMIT_BYTES:
            raise BundleCompatibilityError("source manifest exceeds size limit")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleCompatibilityError("source manifest is missing or unreadable") from exc
    if not isinstance(value, dict):
        raise BundleCompatibilityError("source manifest must be an object")
    return value


def verify_restore_bundle(root: Path, *, allow_legacy: bool = False) -> str:
    """Return the accepted contract label or raise before ``IMPORT DATABASE``.

    An unversioned pre-cursor archive needs an explicit ``allow_legacy`` choice.
    It contains no DB-backed arXiv cursor, so the next sync must bootstrap from
    a verified snapshot rather than trust an external JSON high-water file.
    """
    if not root.is_dir() or not (root / "duckdb" / "schema.sql").is_file() or not (
        root / "duckdb" / "load.sql"
    ).is_file():
        raise BundleCompatibilityError("DuckDB export is incomplete")
    manifest = _manifest(root)
    counts = manifest.get("counts")
    columns = manifest.get("columns")
    if not isinstance(counts, dict) or not isinstance(columns, list):
        raise BundleCompatibilityError("source manifest lacks table inventory")
    version = manifest.get("bundle_contract_version")
    if version is None:
        if "arxiv_bulk_progress" in counts or any(
            isinstance(row, list) and row and row[0] == "arxiv_bulk_progress"
            for row in columns
        ):
            raise BundleCompatibilityError("unversioned bundle contains a cursor table")
        if not allow_legacy:
            raise BundleCompatibilityError(
                "unversioned legacy bundle requires --allow-legacy after review"
            )
        return "legacy-unversioned"
    if type(version) is not int or version != BUNDLE_CONTRACT_VERSION:
        raise BundleCompatibilityError(f"unsupported bundle contract version: {version!r}")
    if type(counts.get("arxiv_bulk_progress")) is not int or counts[
        "arxiv_bulk_progress"
    ] < 0:
        raise BundleCompatibilityError("versioned bundle lacks arXiv progress table")

    actual: list[tuple[int, str]] = []
    for row in columns:
        if not isinstance(row, list) or len(row) != 6:
            raise BundleCompatibilityError("source manifest has malformed column inventory")
        if row[0] == "arxiv_bulk_progress":
            if type(row[2]) is not int:
                raise BundleCompatibilityError("arXiv progress column order is malformed")
            actual.append((row[2], row[1]))
    expected = [(index, name) for index, name in enumerate(ARXIV_BULK_PROGRESS_COLUMNS, 1)]
    if actual != expected:
        raise BundleCompatibilityError("arXiv progress column contract is incompatible")
    return f"v{BUNDLE_CONTRACT_VERSION}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("restore_dir", type=Path, help="extracted backup root")
    parser.add_argument(
        "--allow-legacy", action="store_true", help="accept an unversioned pre-cursor bundle"
    )
    args = parser.parse_args(argv)
    try:
        contract = verify_restore_bundle(args.restore_dir, allow_legacy=args.allow_legacy)
    except BundleCompatibilityError as exc:
        parser.exit(2, f"ABORT: backup compatibility: {exc}\n")
    print(f"backup compatibility: {contract}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
