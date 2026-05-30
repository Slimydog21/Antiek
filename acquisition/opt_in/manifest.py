"""Catalog-manifest format + grant validation for the §9.10 opt-in lane.

A publisher fills a versioned JSON manifest: their identity (a STABLE
publisher id + display name + legal contact), and per work an entry with
content-stable identifiers (ISBN / DOI), title/author, the body source, and —
the load-bearing field — a GRANT statement (explicit, dated authorization to
serve, with a scope).

Why a grant statement and not a ``servable: true`` boolean (rigor #2): a
boolean is a claim with no recorded provenance — it leaves no ``license_basis``
the SPR-10 audit can read months later in front of counsel, and it cannot
express scope or withdrawal. §9.0 demands a positively-established, RECORDED
basis. The grant statement IS that basis. So this module rejects any boolean
shortcut: servability is decided by validating the grant, never by trusting a
flag.

This module is PURE — it parses + validates, it performs NO I/O against the
substrate and reaches NO source. ``intake.py`` consumes its output and drives
the (network-free in tests) ingest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Optional, Sequence

# The manifest schema version. Bump on a breaking field change so a stored
# manifest records which schema it was authored against (defensibility).
MANIFEST_SCHEMA_VERSION = "opt_in/1"

# Grant scopes this validator understands. A grant whose ``scope`` is not one
# of these is treated as out-of-scope -> the work gates (deny-by-default: an
# unrecognised scope is "we couldn't tell it covers this work").
#   full_catalog  — the grant covers every work in this manifest.
#   per_work      — the grant covers exactly the work it is attached to.
GRANT_SCOPES: frozenset[str] = frozenset({"full_catalog", "per_work"})


@dataclass(frozen=True)
class PublisherIdentity:
    """Who is granting. ``publisher_id`` is the STABLE identity holder
    resolution keys on (never the mutable ``display_name``): the same
    publisher across submissions resolves to ONE ip_holder."""

    publisher_id: str
    display_name: str
    legal_contact_email: Optional[str] = None


@dataclass(frozen=True)
class ManifestEntry:
    """One work in the catalog.

    ``isbn`` / ``doi`` are the content-stable identifiers idempotency keys on
    (never title+author). ``body_path`` OR ``body_text`` carries the work's
    body — the source the servable full text is read from. ``grant`` is the
    per-work grant override; when absent the manifest-level grant (if any)
    applies. Validation (``validate_grant``) decides whether the grant is
    valid FOR THIS WORK; an invalid/absent grant gates the work.
    """

    title: str
    author: Optional[str] = None
    isbn: Optional[str] = None
    doi: Optional[str] = None
    body_path: Optional[str] = None
    body_text: Optional[str] = None
    grant: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class Manifest:
    """A parsed catalog manifest.

    ``catalog_grant`` is an optional manifest-level grant covering the whole
    catalog (scope ``full_catalog``); a per-work ``entry.grant`` overrides it.
    ``schema_version`` is recorded so the audit knows which schema produced a
    row.
    """

    schema_version: str
    publisher: PublisherIdentity
    entries: tuple[ManifestEntry, ...]
    catalog_grant: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class GrantValidation:
    """The verdict for one entry's effective grant.

    ``valid`` is True ONLY when a grant is present, parseable, in-scope for the
    work, and not withdrawn/expired. ``grant`` is the resolved grant mapping
    (per-work override or the catalog grant). ``reason`` explains a rejection
    (intellectual honesty: a gated work records exactly WHY it failed).
    ``grant_text`` is the verbatim authorization statement to record as the
    license_basis seed when valid."""

    valid: bool
    reason: str
    grant: Optional[Mapping[str, Any]] = None
    grant_text: Optional[str] = None
    rights_holder: Optional[str] = None


def _coerce_grant(value: Any) -> Optional[Mapping[str, Any]]:
    """Accept a grant only as a mapping. A bare ``True`` boolean is REJECTED
    here (returns None) — rigor #2: a boolean is not a recorded basis."""
    if isinstance(value, Mapping):
        return value
    return None


def _parse_grant_date(value: Any) -> Optional[date]:
    """Parse an ISO ``YYYY-MM-DD`` (or full ISO datetime) date, or None when
    absent/unparseable. An unparseable expiry is treated as 'no expiry stated'
    by the caller — but a MALFORMED required field (granted_at) gates."""
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if "T" in raw or " " in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _effective_grant(
    entry: ManifestEntry, catalog_grant: Optional[Mapping[str, Any]]
) -> Optional[Mapping[str, Any]]:
    """The grant that applies to ``entry``: a per-work grant overrides the
    catalog grant. A per-work grant scoped ``per_work`` covers exactly this
    work; a ``full_catalog``-scoped catalog grant covers every work."""
    per_work = _coerce_grant(entry.grant)
    if per_work is not None:
        return per_work
    return _coerce_grant(catalog_grant)


def validate_grant(
    entry: ManifestEntry,
    *,
    catalog_grant: Optional[Mapping[str, Any]] = None,
    today: Optional[date] = None,
) -> GrantValidation:
    """Decide whether ``entry`` carries a VALID serving grant.

    Deny-by-default: every failure mode below lands the work GATED, never
    servable and never dropped. The grant is the ONLY thing that can flip a
    work servable — no other manifest field does.

    A grant is valid iff ALL hold:
      - it is present (a mapping; a bare boolean is not a grant) and not empty;
      - it carries a non-empty ``statement`` (the verbatim authorization text
        recorded as the license_basis) and a ``granted_at`` date;
      - its ``scope`` is recognised AND covers this work (``per_work`` covers
        the work it is attached to; ``full_catalog`` covers every work);
      - it is not flagged ``withdrawn`` and not past its ``expires_at``.
    """
    today = today or datetime.now(timezone.utc).date()
    grant = _effective_grant(entry, catalog_grant)

    if grant is None:
        return GrantValidation(
            valid=False,
            reason="no grant present (absent or non-mapping) -> gated by default",
        )
    if not grant:
        return GrantValidation(valid=False, reason="empty grant -> gated by default")

    rights_holder = grant.get("rights_holder") or grant.get("rights_holder_name")
    rights_holder = str(rights_holder).strip() if rights_holder else None

    statement = grant.get("statement")
    statement = statement.strip() if isinstance(statement, str) else ""
    if not statement:
        return GrantValidation(
            valid=False,
            reason="grant has no authorization statement -> gated (no basis to record)",
            rights_holder=rights_holder,
        )

    if grant.get("withdrawn") is True:
        return GrantValidation(
            valid=False,
            reason="grant flagged withdrawn -> gated (servability revoked)",
            grant=grant,
            rights_holder=rights_holder,
        )

    granted_at = _parse_grant_date(grant.get("granted_at"))
    if granted_at is None:
        return GrantValidation(
            valid=False,
            reason="grant missing/malformed granted_at date -> gated (undated)",
            grant=grant,
            rights_holder=rights_holder,
        )

    expires_at = _parse_grant_date(grant.get("expires_at"))
    if expires_at is not None and expires_at < today:
        return GrantValidation(
            valid=False,
            reason=f"grant expired at {expires_at.isoformat()} -> gated",
            grant=grant,
            rights_holder=rights_holder,
        )

    scope = grant.get("scope")
    scope = scope.strip() if isinstance(scope, str) else ""
    if scope not in GRANT_SCOPES:
        return GrantValidation(
            valid=False,
            reason=(
                f"grant scope {scope!r} unrecognised (expected one of "
                f"{sorted(GRANT_SCOPES)}) -> gated; a vague scope is not "
                "stretched into a serving right"
            ),
            grant=grant,
            rights_holder=rights_holder,
        )
    # A per-work grant that came from the catalog level (not attached to this
    # entry) does NOT cover an arbitrary work — only a full_catalog scope does.
    if scope == "per_work" and _coerce_grant(entry.grant) is None:
        return GrantValidation(
            valid=False,
            reason=(
                "catalog-level grant scoped per_work does not cover this work "
                "-> gated (out of scope)"
            ),
            grant=grant,
            rights_holder=rights_holder,
        )

    return GrantValidation(
        valid=True,
        reason=f"valid {scope} grant granted_at={granted_at.isoformat()}",
        grant=grant,
        grant_text=statement,
        rights_holder=rights_holder,
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_manifest(data: Mapping[str, Any]) -> Manifest:
    """Parse a manifest mapping into a :class:`Manifest`.

    Validates the structural shape (a recognised schema version, a publisher
    block with a stable id, a non-empty works list). Does NOT validate grants
    here — grant validation is per-work and happens at intake so a single bad
    grant gates ONE work instead of rejecting the whole manifest.
    """
    version = data.get("schema_version")
    if version != MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported manifest schema_version {version!r}; this intake "
            f"speaks {MANIFEST_SCHEMA_VERSION!r}"
        )

    pub = data.get("publisher")
    if not isinstance(pub, Mapping):
        raise ValueError("manifest 'publisher' block is required")
    publisher_id = pub.get("publisher_id")
    if not publisher_id or not str(publisher_id).strip():
        raise ValueError(
            "publisher.publisher_id is required (the STABLE identity holder "
            "resolution keys on — never the display name)"
        )
    display_name = pub.get("display_name") or str(publisher_id)
    publisher = PublisherIdentity(
        publisher_id=str(publisher_id).strip(),
        display_name=str(display_name).strip(),
        legal_contact_email=(
            str(pub["legal_contact_email"]).strip()
            if pub.get("legal_contact_email")
            else None
        ),
    )

    raw_works = data.get("works")
    if not isinstance(raw_works, Sequence) or not raw_works:
        raise ValueError("manifest 'works' must be a non-empty list")

    entries: list[ManifestEntry] = []
    for i, raw in enumerate(raw_works):
        if not isinstance(raw, Mapping):
            raise ValueError(f"works[{i}] must be an object")
        title = raw.get("title")
        if not title or not str(title).strip():
            raise ValueError(f"works[{i}].title is required")
        entries.append(
            ManifestEntry(
                title=str(title).strip(),
                author=(str(raw["author"]).strip() if raw.get("author") else None),
                isbn=(str(raw["isbn"]).strip() if raw.get("isbn") else None),
                doi=(str(raw["doi"]).strip() if raw.get("doi") else None),
                body_path=(
                    str(raw["body_path"]).strip() if raw.get("body_path") else None
                ),
                body_text=(raw["body_text"] if isinstance(raw.get("body_text"), str) else None),
                grant=_coerce_grant(raw.get("grant")),
            )
        )

    return Manifest(
        schema_version=version,
        publisher=publisher,
        entries=tuple(entries),
        catalog_grant=_coerce_grant(data.get("catalog_grant")),
    )


def load_manifest(path: str) -> Manifest:
    """Read + parse a manifest JSON file from ``path``."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, Mapping):
        raise ValueError("manifest root must be a JSON object")
    return parse_manifest(data)
