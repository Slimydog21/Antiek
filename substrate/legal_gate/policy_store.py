"""Durable, cited legal-policy revisions and deterministic snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

import duckdb

from runtime.db_lock import LockedConnection
from substrate.investigation_streams import resolve_investigation_stream
from substrate.investigation_tenancy import InvestigationAuthority

MatcherKind = Literal["domain", "corpus", "author", "title", "content_sha256"]
Decision = Literal["allow", "deny", "revoke"]
ScopeKind = Literal["global", "account"]
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class LegalPolicyDenied(RuntimeError):
    pass


_AUTHORITY_TOKEN = object()
_GLOBAL_CAPABILITY_TOKEN = object()


@dataclass(frozen=True, init=False)
class LegalPolicyAuthority:
    account_digest: str | None
    global_capability_fingerprint: str | None
    global_issuer_id: str | None
    _token: object

    def __init__(
        self,
        *,
        account_digest: str | None,
        global_capability_fingerprint: str | None,
        global_issuer_id: str | None,
        _token: object,
    ) -> None:
        if _token is not _AUTHORITY_TOKEN:
            raise LegalPolicyDenied("legal-policy authority must be minted")
        object.__setattr__(self, "account_digest", account_digest)
        object.__setattr__(self, "global_capability_fingerprint", global_capability_fingerprint)
        object.__setattr__(self, "global_issuer_id", global_issuer_id)
        object.__setattr__(self, "_token", _token)


@dataclass(frozen=True, init=False)
class GlobalPolicyAdminCapability:
    issuer_id: str
    ratification_fingerprint: str
    _token: object

    def __init__(self, *, issuer_id: str, ratification_fingerprint: str, _token: object) -> None:
        if _token is not _GLOBAL_CAPABILITY_TOKEN:
            raise LegalPolicyDenied("global policy capability must be installed")
        object.__setattr__(self, "issuer_id", issuer_id)
        object.__setattr__(self, "ratification_fingerprint", ratification_fingerprint)
        object.__setattr__(self, "_token", _token)


@dataclass(frozen=True)
class PolicySnapshot:
    snapshot_sha256: str
    active_events: tuple[dict[str, str | None], ...]


@dataclass(frozen=True)
class PolicyVerdict:
    decision: Literal["allow", "deny", "no_decision"]
    snapshot_sha256: str
    matched_event_ids: tuple[str, ...]
    reason_code: str | None


def account_policy_authority(authority: InvestigationAuthority) -> LegalPolicyAuthority:
    resolve_investigation_stream(authority)
    fingerprint = hashlib.sha256(
        f"account\0{authority.key_id}\0{authority.account_digest}".encode()
    ).hexdigest()
    return LegalPolicyAuthority(
        account_digest=authority.account_digest,
        global_capability_fingerprint=fingerprint,
        global_issuer_id=None,
        _token=_AUTHORITY_TOKEN,
    )


def load_global_policy_admin_capability() -> GlobalPolicyAdminCapability:
    """Load an operator-installed capability; request data cannot mint it."""
    if os.environ.get("ANTIEK_LEGAL_POLICY_ADMIN_ENABLED") != "1":
        raise LegalPolicyDenied("global policy administration is not installed")
    issuer = _canonical_text(os.environ.get("ANTIEK_LEGAL_POLICY_ISSUER_ID", ""), field="issuer_id")
    digest = os.environ.get("ANTIEK_LEGAL_POLICY_RATIFICATION_SHA256", "")
    digest = digest.removeprefix("sha256:").strip().lower()
    if not _HEX_64.fullmatch(digest):
        raise ValueError("ratification_sha256 must be a full SHA-256 digest")
    fingerprint = hashlib.sha256(f"{issuer}\0{digest}".encode()).hexdigest()
    return GlobalPolicyAdminCapability(
        issuer_id=issuer,
        ratification_fingerprint=fingerprint,
        _token=_GLOBAL_CAPABILITY_TOKEN,
    )


def global_policy_authority(
    capability: GlobalPolicyAdminCapability,
) -> LegalPolicyAuthority:
    if (
        not isinstance(capability, GlobalPolicyAdminCapability)
        or capability._token is not _GLOBAL_CAPABILITY_TOKEN
    ):
        raise LegalPolicyDenied("global legal-policy administration denied")
    return LegalPolicyAuthority(
        account_digest=None,
        global_capability_fingerprint=capability.ratification_fingerprint,
        global_issuer_id=capability.issuer_id,
        _token=_AUTHORITY_TOKEN,
    )


def _canonical_text(value: str, *, field: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if not normalized or len(normalized) > 500:
        raise ValueError(f"{field} must be a bounded non-empty string")
    return normalized


def normalize_matcher(kind: MatcherKind, value: str) -> str:
    canonical = _canonical_text(value, field="matcher_value")
    if kind == "domain":
        candidate = canonical if "://" in canonical else f"https://{canonical}"
        parsed = urlsplit(candidate)
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or not parsed.hostname:
            raise ValueError("domain matcher must be a host only")
        return parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    if kind == "content_sha256":
        digest = canonical.removeprefix("sha256:").lower()
        if not _HEX_64.fullmatch(digest):
            raise ValueError("content_sha256 matcher must be a full SHA-256 digest")
        return digest
    return canonical.casefold()


def append_policy_event(
    con: LockedConnection,
    authority: LegalPolicyAuthority,
    *,
    scope_kind: ScopeKind,
    matcher_kind: MatcherKind,
    matcher_value: str,
    decision: Decision,
    citation_ref: str,
    issuer_id: str,
    reason_code: str,
    effective_at: datetime,
    expires_at: datetime | None = None,
    supersedes_event_id: str | None = None,
) -> str:
    if not isinstance(con, LockedConnection):
        raise TypeError("legal-policy writes require a LockedConnection")
    if scope_kind == "global":
        if authority.global_capability_fingerprint is None or authority.account_digest is not None:
            raise LegalPolicyDenied("global legal-policy administration denied")
        if decision == "allow":
            raise ValueError("global allow entries are forbidden")
        if issuer_id != authority.global_issuer_id:
            raise LegalPolicyDenied("global policy issuer does not match installed authority")
        account_digest = ""
        active_lease = con.execute(
            "SELECT lease_id FROM legal_policy_dispatch_leases "
            "LIMIT 1"
        ).fetchone()
    else:
        if authority.account_digest is None:
            raise LegalPolicyDenied("account legal-policy administration denied")
        account_digest = authority.account_digest
        active_lease = con.execute(
            "SELECT lease_id FROM legal_policy_dispatch_leases "
            "WHERE account_digest = ? LIMIT 1",
            [account_digest],
        ).fetchone()
    if active_lease is not None:
        raise LegalPolicyDenied("legal-policy change conflicts with active provider dispatch")
    if decision == "revoke" and not supersedes_event_id:
        raise ValueError("revocation must identify the superseded event")
    if decision == "revoke" and expires_at is not None:
        raise ValueError("revocation cannot expire")
    if effective_at.tzinfo is None:
        raise ValueError("effective_at must be timezone-aware")
    if expires_at is not None and (expires_at.tzinfo is None or expires_at <= effective_at):
        raise ValueError("expires_at must be timezone-aware and after effective_at")
    row = {
        "scope_kind": scope_kind,
        "account_digest": account_digest,
        "matcher_kind": matcher_kind,
        "matcher_value": normalize_matcher(matcher_kind, matcher_value),
        "decision": decision,
        "citation_ref": _canonical_text(citation_ref, field="citation_ref"),
        "issuer_id": _canonical_text(issuer_id, field="issuer_id"),
        "reason_code": _canonical_text(reason_code, field="reason_code"),
        "effective_at": effective_at.astimezone(UTC).isoformat(),
        "expires_at": None if expires_at is None else expires_at.astimezone(UTC).isoformat(),
        "supersedes_event_id": supersedes_event_id,
        "capability_fingerprint": authority.global_capability_fingerprint or "",
    }
    encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    event_id = f"lpe-{fingerprint[:32]}"
    existing = con.execute(
        "SELECT event_fingerprint FROM legal_policy_events WHERE event_id = ?", [event_id]
    ).fetchone()
    if existing is not None:
        if existing == (fingerprint,):
            return event_id
        raise LegalPolicyDenied("legal-policy event identity collision")
    if supersedes_event_id is not None:
        prior = con.execute(
            "SELECT scope_kind, account_digest, matcher_kind, matcher_value, decision, "
            "effective_at "
            "FROM legal_policy_events WHERE event_id = ?",
            [supersedes_event_id],
        ).fetchone()
        expected_allow = (
            scope_kind,
            account_digest,
            matcher_kind,
            row["matcher_value"],
            "allow",
        )
        expected_deny = (
            scope_kind,
            account_digest,
            matcher_kind,
            row["matcher_value"],
            "deny",
        )
        if prior is None or prior[:5] not in {expected_allow, expected_deny}:
            raise LegalPolicyDenied("superseded policy event does not match authority")
        if prior[5].replace(tzinfo=UTC) >= effective_at.astimezone(UTC):
            raise LegalPolicyDenied("revocation must become effective after its target")
    con.execute(
        "INSERT INTO legal_policy_events "
        "(event_id, scope_kind, account_digest, matcher_kind, matcher_value, decision, "
        "citation_ref, issuer_id, reason_code, effective_at, expires_at, "
        "supersedes_event_id, capability_fingerprint, event_fingerprint) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [event_id, *row.values(), fingerprint],
    )
    return event_id


def policy_snapshot(
    con: duckdb.DuckDBPyConnection | LockedConnection,
    authority: LegalPolicyAuthority,
    *,
    at: datetime,
) -> PolicySnapshot:
    if not isinstance(authority, LegalPolicyAuthority) or authority._token is not _AUTHORITY_TOKEN:
        raise LegalPolicyDenied("legal-policy snapshot authority denied")
    if at.tzinfo is None:
        raise ValueError("snapshot time must be timezone-aware")
    account_digest = authority.account_digest or ""
    all_rows = con.execute(
        "SELECT event_id, scope_kind, account_digest, matcher_kind, matcher_value, "
        "decision, citation_ref, issuer_id, reason_code, effective_at, expires_at, "
        "supersedes_event_id, capability_fingerprint, event_fingerprint "
        "FROM legal_policy_events "
        "WHERE scope_kind = 'global' OR account_digest = ? "
        "ORDER BY effective_at, event_id",
        [account_digest],
    ).fetchall()
    installed_global: GlobalPolicyAdminCapability | None = None
    if any(row[1] == "global" for row in all_rows):
        try:
            installed_global = load_global_policy_admin_capability()
        except (LegalPolicyDenied, ValueError) as exc:
            raise LegalPolicyDenied("global legal-policy verification is not installed") from exc
    for row in all_rows:
        canonical = {
            "scope_kind": str(row[1]),
            "account_digest": str(row[2]),
            "matcher_kind": str(row[3]),
            "matcher_value": str(row[4]),
            "decision": str(row[5]),
            "citation_ref": str(row[6]),
            "issuer_id": str(row[7]),
            "reason_code": str(row[8]),
            "effective_at": row[9].replace(tzinfo=UTC).isoformat(),
            "expires_at": None if row[10] is None else row[10].replace(tzinfo=UTC).isoformat(),
            "supersedes_event_id": None if row[11] is None else str(row[11]),
            "capability_fingerprint": str(row[12]),
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if hashlib.sha256(encoded.encode()).hexdigest() != row[13]:
            raise LegalPolicyDenied("legal-policy event failed integrity validation")
        if row[1] == "global" and (
            installed_global is None
            or row[7] != installed_global.issuer_id
            or row[12] != installed_global.ratification_fingerprint
        ):
            raise LegalPolicyDenied("global legal-policy event failed authority validation")
        if row[1] == "account" and row[12] != authority.global_capability_fingerprint:
            raise LegalPolicyDenied("account legal-policy event failed authority validation")
    snapshot_at = at.astimezone(UTC).replace(tzinfo=None)
    rows = [
        row
        for row in all_rows
        if row[9] <= snapshot_at and (row[10] is None or row[10] > snapshot_at)
    ]
    by_id = {str(row[0]): row for row in rows}
    revoked: set[str] = set()
    for row in rows:
        if row[5] != "revoke":
            continue
        prior = by_id.get(str(row[11]))
        if (
            prior is None
            or prior[5] not in {"allow", "deny"}
            or prior[1:5] != row[1:5]
            or prior[9] >= row[9]
        ):
            raise LegalPolicyDenied("legal-policy revocation authority is invalid")
        revoked.add(str(prior[0]))
    active = []
    for row in rows:
        if row[5] == "revoke" or row[0] in revoked:
            continue
        active.append(
            {
                "event_id": str(row[0]),
                "scope_kind": str(row[1]),
                "account_digest": str(row[2]),
                "matcher_kind": str(row[3]),
                "matcher_value": str(row[4]),
                "decision": str(row[5]),
                "citation_ref": str(row[6]),
                "issuer_id": str(row[7]),
                "reason_code": str(row[8]),
                "effective_at": row[9].replace(tzinfo=UTC).isoformat(),
                "expires_at": None if row[10] is None else row[10].replace(tzinfo=UTC).isoformat(),
            }
        )
    active.sort(
        key=lambda item: (
            item["scope_kind"] != "global",
            item["matcher_kind"],
            item["matcher_value"],
            item["event_id"],
        )
    )
    encoded = json.dumps(active, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return PolicySnapshot(hashlib.sha256(encoded.encode()).hexdigest(), tuple(active))


def evaluate_document(
    snapshot: PolicySnapshot,
    *,
    url: str = "",
    author: str = "",
    title: str = "",
    source_corpus: str = "",
    content_sha256: str = "",
) -> PolicyVerdict:
    """Apply global-deny, account-deny, account-allow precedence."""
    host = (urlsplit(url).hostname or "").encode("idna").decode("ascii").lower().rstrip(".")

    def normalized_candidate(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).strip().split()).casefold()

    values = {
        "domain": host,
        "corpus": normalized_candidate(source_corpus),
        "author": normalized_candidate(author),
        "title": normalized_candidate(title),
        "content_sha256": content_sha256.removeprefix("sha256:").strip().lower(),
    }

    def matches(event: dict[str, str | None]) -> bool:
        kind = str(event["matcher_kind"])
        matcher = str(event["matcher_value"])
        candidate = values[kind]
        if kind == "domain":
            return bool(candidate) and (candidate == matcher or candidate.endswith(f".{matcher}"))
        if kind in {"author", "title"}:
            return bool(candidate) and matcher in candidate
        return bool(candidate) and candidate == matcher

    groups = (
        ("global", "deny"),
        ("account", "deny"),
        ("account", "allow"),
    )
    for scope, decision in groups:
        matched = tuple(
            event
            for event in snapshot.active_events
            if event["scope_kind"] == scope and event["decision"] == decision and matches(event)
        )
        if matched:
            return PolicyVerdict(
                decision=decision,
                snapshot_sha256=snapshot.snapshot_sha256,
                matched_event_ids=tuple(str(event["event_id"]) for event in matched),
                reason_code=str(matched[0]["reason_code"]),
            )
    return PolicyVerdict("no_decision", snapshot.snapshot_sha256, (), None)
