"""Recover reader HTML for one legacy, operator-owned URL document.

The source is retained raw text. This command never fetches the source URL.
Report output is deliberately limited to classification and a content digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Sequence
from typing import Any, cast

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.snapshot.reader_html import markdown_to_safe_html  # noqa: E402
from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.books.html_sanitizer import SANITIZER_VERSION  # noqa: E402
from substrate.books.serve_guard import (  # noqa: E402
    LinkBackMissingError,
    guard_candidate_full_text,
)
from substrate.constants import PERSONAL_READING_CONTENT_CLASS  # noqa: E402
from substrate.reader_html.store import MAX_READER_HTML_CHARS, store_reader_html  # noqa: E402
from substrate.rights import T3BodyServeError  # noqa: E402

SOURCE_KIND = "url_text_derived"
_OPERATOR = "__operator__"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
# The renderer's output is generated, never copied HTML. Its img attributes
# are quoted and escaped, so this removes every automatic remote image load.
_IMAGE_TAG = re.compile(r"<img(?:\s[^>]*)?\s*/?>", re.IGNORECASE)


def _row(con: Any, document_id: str) -> tuple[Any, ...] | None:
    return cast(tuple[Any, ...] | None, con.execute(
        """SELECT d.document_type, d.content_class, d.raw_text, d.owner_user_id,
                  d.metadata,
                  COALESCE(b.taken_down, FALSE), r.sanitizer_version, r.revision
           FROM documents d
           LEFT JOIN book_assets b ON b.document_id = d.document_id
           LEFT JOIN document_reader_html r ON r.document_id = d.document_id
           WHERE d.document_id = ?""",
        [document_id],
    ).fetchone())


def _project(raw_text: str) -> str | None:
    if len(raw_text) > MAX_READER_HTML_CHARS:
        return None
    rendered = markdown_to_safe_html(raw_text)
    rendered = _IMAGE_TAG.sub("", rendered)
    if len(rendered) > MAX_READER_HTML_CHARS:
        return None
    return rendered


def _status(document_id: str, row: tuple[Any, ...] | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "document_id": document_id,
        "status": "skipped",
        "reason": "not_found",
        "document_type": None,
        "content_class": None,
        "raw_length": None,
        "raw_sha256": None,
        "sidecar_present": False,
        "sidecar_version": None,
        "sidecar_revision": None,
    }
    if row is None:
        return result
    doc_type, content_class, raw_text, owner, metadata, taken_down, version, revision = row
    result.update(
        document_type=doc_type,
        content_class=content_class,
        raw_length=len(raw_text) if raw_text is not None else 0,
        raw_sha256=(hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
                    if raw_text is not None else None),
        sidecar_present=version is not None,
        sidecar_version=version,
        sidecar_revision=revision,
    )
    if version is not None:
        result["reason"] = "already_present"
    elif owner != _OPERATOR:
        result["reason"] = "not_single_operator_owned"
    elif doc_type != "web_article":
        result["reason"] = "wrong_document_type"
    elif content_class != PERSONAL_READING_CONTENT_CLASS:
        result["reason"] = "wrong_content_class"
    elif taken_down:
        result["reason"] = "taken_down"
    elif not raw_text or not raw_text.strip():
        result["reason"] = "empty_raw_text"
    elif _project(raw_text) is None:
        result["reason"] = "oversized_text_or_html"
    else:
        try:
            allowed = guard_candidate_full_text(
                raw_text, content_class, metadata, owner=True, taken_down=bool(taken_down)
            )
        except (T3BodyServeError, LinkBackMissingError):
            allowed = None
        if allowed is None:
            result["reason"] = "rights_refused"
        else:
            result["status"] = "eligible"
            result["reason"] = None
    return result


def run(db_path: str, document_id: str, *, apply: bool = False,
        expected_sha256: str | None = None) -> dict[str, Any]:
    """Report or atomically write one sidecar. The digest is a compare-and-swap token."""
    if apply:
        if expected_sha256 is None or _SHA256.fullmatch(expected_sha256) is None:
            raise ValueError("--apply requires a full lowercase --expected-sha256 digest")
        with connect_write(db_path, purpose="tools/backfill_url_reader_html") as con, con.transaction():
            row = _row(con, document_id)
            result = _status(document_id, row)
            if result["reason"] == "already_present":
                return result
            if result["status"] != "eligible":
                return result
            if result["raw_sha256"] != expected_sha256:
                result.update(status="skipped", reason="digest_changed")
                return result
            assert row is not None
            rendered = _project(row[2])
            assert rendered is not None
            store_reader_html(
                con, document_id=document_id, main_html=rendered,
                source_kind=SOURCE_KIND,
            )
            result.update(
                status="written", reason=None, sidecar_present=True,
                sidecar_version=SANITIZER_VERSION, sidecar_revision=1,
            )
            return result
    with connect_read(db_path) as reader:
        return _status(document_id, _row(reader, document_id))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.document_id.strip() or any(ch in args.document_id for ch in "*?%,"):
        parser.error("--document-id must be one exact identifier")
    if args.expected_sha256 and not args.apply:
        parser.error("--expected-sha256 requires --apply")
    if args.apply and (not args.expected_sha256 or not _SHA256.fullmatch(args.expected_sha256)):
        parser.error("--apply requires a full lowercase --expected-sha256 digest")
    db_path = os.path.expanduser(args.db_path)
    if not os.path.isfile(db_path):
        print(json.dumps({"status": "error", "reason": "database_not_found"}))
        return 2
    try:
        result = run(db_path, args.document_id, apply=args.apply,
                     expected_sha256=args.expected_sha256)
    except Exception:
        # DuckDB exceptions may echo SQL parameters. Never expose body or URL.
        print(json.dumps({"status": "error", "reason": "database_operation_failed"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"eligible", "written"} or result["reason"] == "already_present" else 1


if __name__ == "__main__":
    raise SystemExit(main())
