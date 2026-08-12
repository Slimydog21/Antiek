"""Document-to-canonical-HTML ingestion pipeline (Antiek doc→HTML S-D2H).

Converts documents to sanitized canonical HTML for the Antiek reader surface.
Uses the anydoc CLI for conversion with docling as fallback for scanned PDFs.

CRITICAL: Storage goes ONLY through store_reader_html, which sanitizes INSIDE
the write and stamps SANITIZER_VERSION in the same INSERT. Never store raw
client HTML as trusted.

Fair-use gate: acquisition from known non-fair-use sources (libgen,
annas-archive, z-library domain list) is REFUSED with a clear error.
This is a hard compliance requirement (Bartz v. Anthropic / Hachette v.
Internet Archive).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from acquisition.snapshot.reader_html import markdown_to_safe_html
from runtime.db_lock import connect_write
from substrate.books.html_sanitizer import sanitize_book_html, strip_trust_markers
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.ops import insert_document
from substrate.memory import write_memory_item
from substrate.reader_html.store import store_reader_html

logger = logging.getLogger(__name__)

# Resolve anydoc and docling CLI paths at import time.
# Tests monkeypatch these; production resolves from env or which.
ANYDOC_BIN: str = os.environ.get(
    "ANYDOC_BIN",
    shutil.which("anydoc") or "anydoc",
)
DOCLING_BIN: str = os.environ.get(
    "DOCLING_BIN",
    shutil.which("docling") or "docling",
)

# Conversion limits
CONVERSION_TIMEOUT_SECONDS = 30.0
MAX_CONVERTED_MARKDOWN_BYTES = 16 * 1024 * 1024

# Fair-use blocked domains — known non-fair-use sources.
# Acquisition from these is REFUSED (Bartz v. Anthropic / Hachette v. IA).
BLOCKED_DOMAINS: frozenset[str] = frozenset({
    "libgen.is",
    "libgen.rs",
    "libgen.li",
    "libgen.me",
    "libgen.org",
    "libgen.io",
    "annas-archive.org",
    "annas-archive.cc",
    "annas-archive.se",
    "z-lib.org",
    "zlib.org",
    "z-lib.is",
    "z-lib.cc",
    "singlelogin.re",
    "singlelogin.site",
    "1lib.sk",
    "1lib.domains",
    "b-ok.cc",
    "b-ok.org",
    "bookfi.net",
    "book4you.org",
    "book4you.se",
})


class FairUseError(ValueError):
    """Raised when a source violates fair-use compliance requirements.

    This is a HARD compliance gate — not a soft warning. Acquisition from
    known non-fair-use sources is refused unconditionally.
    """


class ConversionError(RuntimeError):
    """Raised when document conversion fails (both anydoc and docling)."""


def _resolve_bin(env_key: str, fallback: str) -> str:
    """Resolve a CLI binary path from env or PATH."""
    return os.environ.get(env_key, shutil.which(fallback) or fallback)


def convert_to_markdown(
    asset_path: str | Path,
    *,
    fmt: str | None = None,
    timeout: float = CONVERSION_TIMEOUT_SECONDS,
    max_output_bytes: int = MAX_CONVERTED_MARKDOWN_BYTES,
) -> str:
    """Convert a document to GitHub-Flavored Markdown using anydoc CLI.

    Falls back to docling when anydoc exits non-zero (e.g. scanned PDFs).

    Args:
        asset_path: Path to the document file.
        fmt: Optional format override for anydoc (--format flag).
        timeout: Subprocess timeout in seconds.
        max_output_bytes: Maximum output size in bytes.

    Returns:
        GFM markdown string.

    Raises:
        ConversionError: If both anydoc and docling fail.
        FileNotFoundError: If asset_path does not exist.
    """
    path = Path(asset_path)
    if not path.exists():
        raise FileNotFoundError(f"asset not found: {path}")

    # Try anydoc first
    md = _run_anydoc(path, fmt=fmt, timeout=timeout, max_output=max_output_bytes)
    if md is not None:
        return md

    # Fallback to docling
    md = _run_docling(path, timeout=timeout, max_output=max_output_bytes)
    if md is not None:
        return md

    raise ConversionError(
        f"conversion failed for {path.name}: both anydoc and docling failed"
    )


def _run_anydoc(
    path: Path,
    *,
    fmt: str | None,
    timeout: float,
    max_output: int,
) -> str | None:
    """Run anydoc CLI. Returns markdown on success, None on failure."""
    cmd = [ANYDOC_BIN, str(path)]
    if fmt:
        cmd.extend(["--format", fmt])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            logger.debug(
                "anydoc exited %d for %s: %s",
                result.returncode,
                path.name,
                result.stderr[:500],
            )
            return None
        output = result.stdout
        if len(output.encode("utf-8")) > max_output:
            output = output.encode("utf-8")[:max_output].decode("utf-8", errors="ignore")
        return output
    except subprocess.TimeoutExpired:
        logger.warning("anydoc timed out after %.1fs for %s", timeout, path.name)
        return None
    except FileNotFoundError:
        logger.warning("anydoc binary not found: %s", ANYDOC_BIN)
        return None


def _run_docling(
    path: Path,
    *,
    timeout: float,
    max_output: int,
) -> str | None:
    """Run docling CLI as fallback. Returns markdown on success, None on failure."""
    cmd = [DOCLING_BIN, "--to", "md", str(path)]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            logger.debug(
                "docling exited %d for %s: %s",
                result.returncode,
                path.name,
                result.stderr[:500],
            )
            return None
        output = result.stdout
        if len(output.encode("utf-8")) > max_output:
            output = output.encode("utf-8")[:max_output].decode("utf-8", errors="ignore")
        return output
    except subprocess.TimeoutExpired:
        logger.warning("docling timed out after %.1fs for %s", timeout, path.name)
        return None
    except FileNotFoundError:
        logger.warning("docling binary not found: %s", DOCLING_BIN)
        return None


def _extract_domain(source_uri: str) -> str | None:
    """Extract the domain from a source URI. Returns None for non-URL sources."""
    try:
        parts = urlsplit(source_uri)
        if parts.scheme in ("http", "https") and parts.hostname:
            return parts.hostname.lower()
    except Exception:
        pass
    return None


def _check_fair_use(provenance: dict[str, Any]) -> None:
    """Enforce the fair-use gate.

    Raises FairUseError when:
    - fair_use_class is not set
    - fair_use_class is not one of: public, licensed, personal
    - source_url matches a blocked domain

    This is a HARD compliance gate — not a soft warning.
    """
    fair_use_class = provenance.get("fair_use_class")
    if fair_use_class is None:
        raise FairUseError(
            "provenance.fair_use_class must be set "
            "(public|licensed|personal)"
        )
    if fair_use_class not in ("public", "licensed", "personal"):
        raise FairUseError(
            f"invalid fair_use_class: {fair_use_class!r} "
            "(must be public|licensed|personal)"
        )

    source_url = provenance.get("source_url", "")
    if isinstance(source_url, str) and source_url:
        domain = _extract_domain(source_url)
        if domain is not None:
            # Check the domain and all parent domains
            parts = domain.split(".")
            for i in range(len(parts)):
                check = ".".join(parts[i:])
                if check in BLOCKED_DOMAINS:
                    raise FairUseError(
                        f"acquisition from {domain} is refused: "
                        f"source matches blocked domain {check} "
                        f"(fair-use compliance)"
                    )


def _doc_id_for_asset(source_uri: str, file_bytes: bytes) -> str:
    """Stable Antiek doc id for an asset: ``doc-asset-<sha256(uri+bytes)[:16]>``.

    Content-addressed: same URI + same bytes → same id (idempotent re-ingest).
    """
    content = f"{source_uri}|".encode() + file_bytes
    digest = hashlib.sha256(content).hexdigest()[:16]
    return f"doc-asset-{digest}"


def ingest_asset(
    *,
    source_uri: str,
    bytes_path: str | Path,
    kind: str,
    provenance: dict[str, Any],
    owner_user_id: str = "__operator__",
) -> dict[str, Any]:
    """Ingest a document asset into the Antiek reader as canonical HTML.

    Pipeline:
    1. Validate source (http(s) URL, uploaded file, or local path)
    2. Check fair-use gate
    3. Convert to markdown (anydoc → docling fallback)
    4. Render canonical HTML (markdown_to_safe_html → sanitize_book_html)
    5. Insert document + store HTML sidecar
    6. Write memory item (best-effort)

    Args:
        source_uri: The source URI (URL, file path, or identifier).
        bytes_path: Path to the document bytes on disk.
        kind: Document kind (pdf, docx, epub, etc).
        provenance: Provenance dict with at least fair_use_class.
            Required keys: fair_use_class (public|licensed|personal).
            Optional keys: source_url, license_note.
        owner_user_id: The owner user ID for memory writes.

    Returns:
        Dict with document_id, reader_html_url, provenance.

    Raises:
        FairUseError: If the source violates fair-use compliance.
        ConversionError: If document conversion fails.
        FileNotFoundError: If bytes_path does not exist.
    """
    path = Path(bytes_path)
    if not path.exists():
        raise FileNotFoundError(f"asset not found: {path}")

    # Enrich provenance with timestamps
    provenance = dict(provenance)  # copy
    provenance.setdefault("original_format", kind)
    provenance.setdefault("source_url", source_uri)
    provenance.setdefault("fetched_at", datetime.now(UTC).isoformat())

    # Fair-use gate — HARD refusal
    _check_fair_use(provenance)

    # Read file bytes for doc_id generation
    file_bytes = path.read_bytes()
    document_id = _doc_id_for_asset(source_uri, file_bytes)

    # Convert to markdown
    md = convert_to_markdown(path, fmt=kind)

    # Render canonical HTML
    # markdown_to_safe_html is escape-first (safe input to the sanitizer)
    safe_html = markdown_to_safe_html(md)
    # sanitize_book_html applies the allowlist sanitizer (the trust floor)
    sanitized_html = sanitize_book_html(safe_html)

    # Build metadata (server-controlled only; strip trust markers)
    metadata = strip_trust_markers({
        "source": "doc_ingest",
        "asset_kind": kind,
        "source_uri": source_uri,
        "provenance": {
            "fair_use_class": provenance["fair_use_class"],
            "source_url": provenance.get("source_url", source_uri),
            "license_note": provenance.get("license_note"),
            "fetched_at": provenance["fetched_at"],
        },
    })

    # Source kind for the sidecar
    source_kind = f"doc_{kind}"

    # DB path
    db_path = default_db_path()
    ensure_initialized(db_path)

    # Write document + sidecar
    with connect_write(db_path, purpose="doc-to-html/ingest") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="doc_asset",
            source_uri=source_uri,
            title=None,
            author=None,
            published_at=None,
            investigation_id=None,
            raw_text=md,
            metadata=metadata,
            content_class=provenance["fair_use_class"],
            on_conflict="ignore",
        )
        store_reader_html(
            con,
            document_id=document_id,
            main_html=sanitized_html,
            source_kind=source_kind,
            source_url=source_uri,
        )

    # Memory hook — best-effort
    try:
        with connect_write(db_path, purpose="doc-to-html/memory") as con:
            write_memory_item(
                con,
                owner_user_id=owner_user_id,
                subject=f"document:{document_id}",
                predicate="ingested_as",
                object=json.dumps({
                    "document_id": document_id,
                    "kind": kind,
                    "source_uri": source_uri,
                    "fair_use_class": provenance["fair_use_class"],
                }),
                provenance={
                    "source": "doc_ingest",
                    "document_id": document_id,
                    "source_tier": 2,
                },
                valid_from=datetime.now(UTC),
            )
    except Exception:
        logger.warning(
            "memory hook failed for %s (non-fatal)", document_id,
            exc_info=True,
        )

    return {
        "document_id": document_id,
        "reader_html_url": f"/sources/{document_id}/reader-html",
        "provenance": {
            "original_format": kind,
            "source_url": provenance.get("source_url", source_uri),
            "fetched_at": provenance["fetched_at"],
            "fair_use_class": provenance["fair_use_class"],
            "license_note": provenance.get("license_note"),
        },
    }


__all__ = [
    "ANYDOC_BIN",
    "BLOCKED_DOMAINS",
    "CONVERSION_TIMEOUT_SECONDS",
    "ConversionError",
    "DOCLING_BIN",
    "FairUseError",
    "MAX_CONVERTED_MARKDOWN_BYTES",
    "convert_to_markdown",
    "ingest_asset",
]
