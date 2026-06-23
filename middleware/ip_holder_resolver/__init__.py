"""IP-holder resolver middleware (master-spec §9.6 + §9.10).

Hook on the document-ingestion path that populates
``documents.ip_holder_id`` from the ``ip_holders`` table using
metadata heuristics.

Resolution chain (first match wins):

  1. ISBN match — if document has an ISBN in its ``metadata.isbn``
     field, look up an ip_holder whose ``metadata.isbns`` list
     contains that ISBN.
  2. Domain match — if document's ``source_uri`` host matches an
     ip_holder's ``metadata.domains`` list.
  3. Author canonicalization — if document's ``author`` field
     exactly matches an ip_holder's ``display_name`` (case-
     insensitive).

Returns ``None`` when no match — the document's ``ip_holder_id``
stays NULL and the document is unattributable until the operator
runs the publisher dashboard (Sprint 18 §9.6) to manually link it.

The resolver is intentionally CONSERVATIVE — no fuzzy matching, no
LLM-based publisher classification. A false positive misroutes
real revenue. A false negative leaves it in escrow, which is the
safe state per the master-spec legal posture.
"""

from __future__ import annotations

import json
from typing import Any, Optional
from urllib.parse import urlparse


def _normalize_isbn(isbn: str | None) -> str | None:
    """Strip hyphens + whitespace; uppercase. Returns None for empty."""
    if not isbn:
        return None
    cleaned = "".join(c for c in isbn if c.isalnum()).upper()
    if not cleaned:
        return None
    return cleaned


def _normalize_host(uri: str | None) -> str | None:
    """Extract lowercase host from a URL; strip ``www.``."""
    if not uri:
        return None
    try:
        parsed = urlparse(uri)
    except (ValueError, AttributeError):
        return None
    host = (parsed.netloc or parsed.path or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _load_holder_metadata(con: Any) -> list[tuple[str, dict, str]]:
    """Return [(ip_holder_id, metadata_dict, display_name), ...] for
    every IP holder, parsed defensively. Empty metadata = empty dict.
    Skip rows whose metadata is unparseable rather than blowing up."""
    rows = con.execute(
        "SELECT ip_holder_id, metadata, display_name FROM ip_holders"
    ).fetchall()
    out: list[tuple[str, dict, str]] = []
    for ip_holder_id, raw, display_name in rows:
        md: dict = {}
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    md = parsed
            except (TypeError, ValueError):
                md = {}
        out.append((ip_holder_id, md, display_name or ""))
    return out


def _resolve_by_isbn(
    holders: list[tuple[str, dict, str]], target_isbn: str,
) -> str | None:
    for ip_holder_id, md, _display in holders:
        isbns = md.get("isbns") or []
        if not isinstance(isbns, list):
            continue
        for raw in isbns:
            if _normalize_isbn(str(raw)) == target_isbn:
                return ip_holder_id
    return None


def _resolve_by_host(
    holders: list[tuple[str, dict, str]], target_host: str,
) -> str | None:
    for ip_holder_id, md, _display in holders:
        domains = md.get("domains") or []
        if not isinstance(domains, list):
            continue
        for raw in domains:
            normalized = str(raw).lower().strip()
            if normalized.startswith("www."):
                normalized = normalized[4:]
            if normalized == target_host:
                return ip_holder_id
            # Subdomain match: if holder lists "example.com", also
            # match "press.example.com". Subdomains carry the parent's
            # IP-holder identity by convention.
            if target_host.endswith("." + normalized):
                return ip_holder_id
    return None


def _resolve_by_author(
    holders: list[tuple[str, dict, str]], target_author: str,
) -> str | None:
    target = target_author.strip().lower()
    if not target:
        return None
    for ip_holder_id, _md, display_name in holders:
        if display_name.strip().lower() == target:
            return ip_holder_id
    return None


def resolve_ip_holder(
    con: Any,
    *,
    source_uri: str | None = None,
    isbn: str | None = None,
    author: str | None = None,
) -> str | None:
    """Resolve a document's ip_holder_id from its metadata.

    Args:
      con: a DuckDB connection (read-only is fine).
      source_uri: document URL; matched against holder domain lists.
      isbn: book ISBN; matched against holder ISBN lists.
      author: document author; matched (case-insensitive) against
        ``ip_holders.display_name``.

    Returns the matching ip_holder_id, or None if no match. First
    match wins in the order ISBN → domain → author. Substrate stays
    conservative; ambiguous cases return None so the operator can
    resolve them via the publisher dashboard.
    """
    holders = _load_holder_metadata(con)
    if not holders:
        return None

    if isbn:
        normalized = _normalize_isbn(isbn)
        if normalized is not None:
            match = _resolve_by_isbn(holders, normalized)
            if match is not None:
                return match

    if source_uri:
        host = _normalize_host(source_uri)
        if host is not None:
            match = _resolve_by_host(holders, host)
            if match is not None:
                return match

    if author:
        match = _resolve_by_author(holders, author)
        if match is not None:
            return match

    return None


def apply_resolved_ip_holder(
    con: Any, *, document_id: str, ip_holder_id: str,
) -> None:
    """Persist a resolved ip_holder_id on a document. Idempotent: if
    the document already has an ip_holder_id, the existing value
    wins (operator-managed overrides via publisher dashboard take
    precedence over auto-resolution).
    """
    existing = con.execute(
        "SELECT ip_holder_id FROM documents WHERE document_id = ?",
        [document_id],
    ).fetchone()
    if existing is None:
        raise ValueError(
            f"document_id {document_id!r} not found in documents table"
        )
    if existing[0]:
        return  # already attributed; leave it
    con.execute(
        "UPDATE documents SET ip_holder_id = ? WHERE document_id = ?",
        [ip_holder_id, document_id],
    )


def resolve_and_apply(
    con: Any,
    *,
    document_id: str,
    source_uri: str | None = None,
    isbn: str | None = None,
    author: str | None = None,
) -> str | None:
    """Resolve + persist in one call. Returns the resolved
    ip_holder_id (or None). Skips persistence if no match (the
    document's ip_holder_id stays NULL = unattributable)."""
    resolved = resolve_ip_holder(
        con, source_uri=source_uri, isbn=isbn, author=author,
    )
    if resolved is None:
        return None
    apply_resolved_ip_holder(
        con, document_id=document_id, ip_holder_id=resolved,
    )
    return resolved


__all__ = [
    "apply_resolved_ip_holder",
    "resolve_and_apply",
    "resolve_ip_holder",
]
