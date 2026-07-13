"""One-shot multimedia spend authorization composed with ``BudgetLedger``.

This module does not know how to call a provider. It authenticates the exact
operator-approved call and makes the shared reserve-before-spend ledger the
only path to invoking an injected callback.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from runtime.db_lock import FlockWriteCoordinator
from substrate.midnight_oil.budget_ledger import BudgetLedger, RemainingBalance

MAX_CENTS = 9_223_372_036_854_775_807
RECEIPT_VERSION = 1
ASYNC_RECEIPT_VERSION = 2
MAX_AUTHORIZATION_LIFETIME = timedelta(hours=24)
_ROUTE_POLICIES = frozenset({"cheapest", "balanced", "highest_quality"})
T = TypeVar("T")


class ExecutionAuthorizationIntegrityError(RuntimeError):
    """The authorization is invalid, tampered, or bound to another call."""


class ExecutionAuthorizationConsumed(RuntimeError):
    """The one-shot authorization was already claimed by an execution attempt."""


class ExecutionAuthorizationRevoked(RuntimeError):
    """The operator revoked this authorization before execution claimed it."""


@dataclass(frozen=True)
class MultimediaExecutionAuthorization:
    version: int
    authorization_id: str
    request_id: str
    operator_id: str
    asset_id: str
    revision_id: str
    provider: str
    route_policy: str
    approved_ceiling_cents: int
    issued_at: str
    expires_at: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> MultimediaExecutionAuthorization:
        try:
            return cls(
                version=value["version"],
                authorization_id=value["authorization_id"],
                request_id=value["request_id"],
                operator_id=value["operator_id"],
                asset_id=value["asset_id"],
                revision_id=value["revision_id"],
                provider=value["provider"],
                route_policy=value["route_policy"],
                approved_ceiling_cents=value["approved_ceiling_cents"],
                issued_at=value["issued_at"],
                expires_at=value["expires_at"],
                signature=value["signature"],
            )
        except (KeyError, TypeError) as exc:
            raise ExecutionAuthorizationIntegrityError(
                "malformed multimedia execution authorization"
            ) from exc


@dataclass(frozen=True)
class MultimediaExecutionAuthorizationV2:
    """Signed authority for one exact asynchronous provider submission."""

    version: int
    authorization_id: str
    request_id: str
    operator_id: str
    asset_id: str
    revision_id: str
    provider: str
    route_policy: str
    model: str
    endpoint_capability: str
    catalog_version: str
    catalog_digest: str
    quote_id: str
    quote_expires_at: str
    recovery_authority_id: str
    recovery_verification_key_digest: str
    approved_ceiling_microdollars: int
    request_body_digest: str
    issued_at: str
    expires_at: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> MultimediaExecutionAuthorizationV2:
        try:
            return cls(**{field: value[field] for field in cls.__dataclass_fields__})
        except (KeyError, TypeError) as exc:
            raise ExecutionAuthorizationIntegrityError(
                "malformed asynchronous multimedia execution authorization"
            ) from exc


@dataclass(frozen=True)
class MultimediaExecutionRevocation:
    authorization_id: str
    operator_id: str
    revoked_at: str


def issue_execution_authorization(
    *,
    signing_key: bytes,
    request_id: str,
    operator_id: str,
    asset_id: str,
    revision_id: str,
    provider: str,
    route_policy: str,
    approved_ceiling_cents: int,
    issued_at: datetime,
    expires_at: datetime,
) -> MultimediaExecutionAuthorization:
    """Issue a deterministic receipt for one exact operator-approved call."""
    _validate_key(signing_key)
    canonical_request_id = _identifier("request_id", request_id)
    canonical_operator_id = _identifier("operator_id", operator_id)
    canonical_asset_id = _identifier("asset_id", asset_id)
    canonical_revision_id = _identifier("revision_id", revision_id)
    canonical_provider = _identifier("provider", provider)
    canonical_route_policy = _route_policy(route_policy)
    canonical_ceiling = _cents(approved_ceiling_cents)
    canonical_issued_at = _utc_timestamp(issued_at)
    canonical_expires_at = _utc_timestamp(expires_at)
    issued = _parse_timestamp(canonical_issued_at)
    expires = _parse_timestamp(canonical_expires_at)
    if expires <= issued or expires - issued > MAX_AUTHORIZATION_LIFETIME:
        raise ValueError("authorization lifetime must be positive and no more than 24 hours")
    fields: dict[str, Any] = {
        "version": RECEIPT_VERSION,
        "request_id": canonical_request_id,
        "operator_id": canonical_operator_id,
        "asset_id": canonical_asset_id,
        "revision_id": canonical_revision_id,
        "provider": canonical_provider,
        "route_policy": canonical_route_policy,
        "approved_ceiling_cents": canonical_ceiling,
        "issued_at": canonical_issued_at,
        "expires_at": canonical_expires_at,
    }
    authorization_id = "mmauth_" + hashlib.sha256(_canonical(fields)).hexdigest()
    signed = {**fields, "authorization_id": authorization_id}
    return MultimediaExecutionAuthorization(
        version=RECEIPT_VERSION,
        authorization_id=authorization_id,
        request_id=canonical_request_id,
        operator_id=canonical_operator_id,
        asset_id=canonical_asset_id,
        revision_id=canonical_revision_id,
        provider=canonical_provider,
        route_policy=canonical_route_policy,
        approved_ceiling_cents=canonical_ceiling,
        issued_at=canonical_issued_at,
        expires_at=canonical_expires_at,
        signature=hmac.new(signing_key, _canonical(signed), hashlib.sha256).hexdigest(),
    )


def issue_async_execution_authorization(
    *,
    signing_key: bytes,
    request_id: str,
    operator_id: str,
    asset_id: str,
    revision_id: str,
    provider: str,
    route_policy: str,
    model: str,
    endpoint_capability: str,
    catalog_version: str,
    catalog_digest: str,
    quote_id: str,
    quote_expires_at: datetime,
    recovery_authority_id: str,
    recovery_verification_key_digest: str,
    approved_ceiling_microdollars: int,
    request_body_digest: str,
    issued_at: datetime,
    expires_at: datetime,
) -> MultimediaExecutionAuthorizationV2:
    """Issue v2 authority bound to a frozen quote, catalog, and request body."""
    _validate_key(signing_key)
    canonical_issued_at = _utc_timestamp(issued_at)
    canonical_expires_at = _utc_timestamp(expires_at)
    canonical_quote_expires_at = _utc_timestamp(quote_expires_at)
    issued = _parse_timestamp(canonical_issued_at)
    expires = _parse_timestamp(canonical_expires_at)
    quote_expires = _parse_timestamp(canonical_quote_expires_at)
    if expires <= issued or expires - issued > MAX_AUTHORIZATION_LIFETIME:
        raise ValueError("authorization lifetime must be positive and no more than 24 hours")
    if quote_expires <= issued or quote_expires > expires:
        raise ValueError("quote must expire after issuance and no later than authorization")
    fields: dict[str, Any] = {
        "version": ASYNC_RECEIPT_VERSION,
        "request_id": _identifier("request_id", request_id),
        "operator_id": _identifier("operator_id", operator_id),
        "asset_id": _identifier("asset_id", asset_id),
        "revision_id": _identifier("revision_id", revision_id),
        "provider": _identifier("provider", provider),
        "route_policy": _route_policy(route_policy),
        "model": _identifier("model", model),
        "endpoint_capability": _identifier("endpoint_capability", endpoint_capability),
        "catalog_version": _identifier("catalog_version", catalog_version),
        "catalog_digest": _sha256_digest("catalog_digest", catalog_digest),
        "quote_id": _identifier("quote_id", quote_id),
        "quote_expires_at": canonical_quote_expires_at,
        "recovery_authority_id": _identifier("recovery_authority_id", recovery_authority_id),
        "recovery_verification_key_digest": _sha256_digest(
            "recovery_verification_key_digest", recovery_verification_key_digest
        ),
        "approved_ceiling_microdollars": _microdollars(approved_ceiling_microdollars),
        "request_body_digest": _sha256_digest("request_body_digest", request_body_digest),
        "issued_at": canonical_issued_at,
        "expires_at": canonical_expires_at,
    }
    authorization_id = "mmauth2_" + hashlib.sha256(_canonical(fields)).hexdigest()
    signed = {**fields, "authorization_id": authorization_id}
    return MultimediaExecutionAuthorizationV2(
        authorization_id=authorization_id,
        signature=hmac.new(signing_key, _canonical(signed), hashlib.sha256).hexdigest(),
        **fields,
    )


def verify_async_execution_authorization(
    authorization: MultimediaExecutionAuthorizationV2,
    *,
    signing_key: bytes,
    operator_id: str,
    asset_id: str,
    revision_id: str,
    provider: str,
    route_policy: str,
    model: str,
    endpoint_capability: str,
    catalog_version: str,
    catalog_digest: str,
    quote_id: str,
    recovery_authority_id: str,
    recovery_verification_key_digest: str,
    approved_ceiling_microdollars: int,
    request_body_digest: str,
    now: datetime,
) -> None:
    """Verify v2 authority and every execution-time binding."""
    _validate_key(signing_key)
    if (
        isinstance(authorization.version, bool)
        or authorization.version != ASYNC_RECEIPT_VERSION
        or not isinstance(authorization.authorization_id, str)
        or not isinstance(authorization.signature, str)
    ):
        raise ExecutionAuthorizationIntegrityError("malformed asynchronous authorization")
    try:
        expected = issue_async_execution_authorization(
            signing_key=signing_key,
            request_id=authorization.request_id,
            operator_id=authorization.operator_id,
            asset_id=authorization.asset_id,
            revision_id=authorization.revision_id,
            provider=authorization.provider,
            route_policy=authorization.route_policy,
            model=authorization.model,
            endpoint_capability=authorization.endpoint_capability,
            catalog_version=authorization.catalog_version,
            catalog_digest=authorization.catalog_digest,
            quote_id=authorization.quote_id,
            quote_expires_at=_parse_timestamp(authorization.quote_expires_at),
            recovery_authority_id=authorization.recovery_authority_id,
            recovery_verification_key_digest=(authorization.recovery_verification_key_digest),
            approved_ceiling_microdollars=(authorization.approved_ceiling_microdollars),
            request_body_digest=authorization.request_body_digest,
            issued_at=_parse_timestamp(authorization.issued_at),
            expires_at=_parse_timestamp(authorization.expires_at),
        )
    except (TypeError, ValueError) as exc:
        raise ExecutionAuthorizationIntegrityError("malformed asynchronous authorization") from exc
    if not hmac.compare_digest(authorization.authorization_id, expected.authorization_id):
        raise ExecutionAuthorizationIntegrityError("authorization identity mismatch")
    if not hmac.compare_digest(authorization.signature, expected.signature):
        raise ExecutionAuthorizationIntegrityError("authorization signature mismatch")
    checked_at = _parse_timestamp(_utc_timestamp(now))
    if checked_at < _parse_timestamp(expected.issued_at):
        raise ExecutionAuthorizationIntegrityError("authorization is not active yet")
    if checked_at >= _parse_timestamp(expected.expires_at):
        raise ExecutionAuthorizationIntegrityError("authorization has expired")
    if checked_at >= _parse_timestamp(expected.quote_expires_at):
        raise ExecutionAuthorizationIntegrityError("authorization quote has expired")
    try:
        bindings: dict[str, tuple[object, object]] = {
            "operator_id": (authorization.operator_id, _identifier("operator_id", operator_id)),
            "asset_id": (authorization.asset_id, _identifier("asset_id", asset_id)),
            "revision_id": (
                authorization.revision_id,
                _identifier("revision_id", revision_id),
            ),
            "provider": (authorization.provider, _identifier("provider", provider)),
            "route_policy": (authorization.route_policy, _route_policy(route_policy)),
            "model": (authorization.model, _identifier("model", model)),
            "endpoint_capability": (
                authorization.endpoint_capability,
                _identifier("endpoint_capability", endpoint_capability),
            ),
            "catalog_version": (
                authorization.catalog_version,
                _identifier("catalog_version", catalog_version),
            ),
            "catalog_digest": (
                authorization.catalog_digest,
                _sha256_digest("catalog_digest", catalog_digest),
            ),
            "quote_id": (authorization.quote_id, _identifier("quote_id", quote_id)),
            "recovery_authority_id": (
                authorization.recovery_authority_id,
                _identifier("recovery_authority_id", recovery_authority_id),
            ),
            "recovery_verification_key_digest": (
                authorization.recovery_verification_key_digest,
                _sha256_digest(
                    "recovery_verification_key_digest",
                    recovery_verification_key_digest,
                ),
            ),
            "approved_ceiling_microdollars": (
                authorization.approved_ceiling_microdollars,
                _microdollars(approved_ceiling_microdollars),
            ),
            "request_body_digest": (
                authorization.request_body_digest,
                _sha256_digest("request_body_digest", request_body_digest),
            ),
        }
    except ValueError as exc:
        raise ExecutionAuthorizationIntegrityError("malformed requested binding") from exc
    for name, (actual, requested) in bindings.items():
        if isinstance(actual, str) and isinstance(requested, str):
            matches = hmac.compare_digest(actual, requested)
        else:
            matches = actual == requested
        if not matches:
            raise ExecutionAuthorizationIntegrityError(f"authorization {name} mismatch")


def verify_execution_authorization(
    authorization: MultimediaExecutionAuthorization,
    *,
    signing_key: bytes,
    operator_id: str,
    asset_id: str,
    revision_id: str,
    provider: str,
    route_policy: str,
    now: datetime,
) -> None:
    """Fail closed unless the receipt is authentic and bound to this call."""
    _validate_key(signing_key)
    if (
        isinstance(authorization.version, bool)
        or not isinstance(authorization.version, int)
        or not isinstance(authorization.authorization_id, str)
        or not isinstance(authorization.signature, str)
    ):
        raise ExecutionAuthorizationIntegrityError("malformed authorization")
    try:
        expected = issue_execution_authorization(
            signing_key=signing_key,
            request_id=authorization.request_id,
            operator_id=authorization.operator_id,
            asset_id=authorization.asset_id,
            revision_id=authorization.revision_id,
            provider=authorization.provider,
            route_policy=authorization.route_policy,
            approved_ceiling_cents=authorization.approved_ceiling_cents,
            issued_at=_parse_timestamp(authorization.issued_at),
            expires_at=_parse_timestamp(authorization.expires_at),
        )
    except (TypeError, ValueError) as exc:
        raise ExecutionAuthorizationIntegrityError("malformed authorization") from exc
    if authorization.version != RECEIPT_VERSION or not hmac.compare_digest(
        authorization.authorization_id, expected.authorization_id
    ):
        raise ExecutionAuthorizationIntegrityError("authorization identity mismatch")
    if not hmac.compare_digest(authorization.signature, expected.signature):
        raise ExecutionAuthorizationIntegrityError("authorization signature mismatch")
    if (
        authorization.issued_at != expected.issued_at
        or authorization.expires_at != expected.expires_at
    ):
        raise ExecutionAuthorizationIntegrityError("authorization timestamp encoding mismatch")

    checked_at = _parse_timestamp(_utc_timestamp(now))
    if checked_at < _parse_timestamp(expected.issued_at):
        raise ExecutionAuthorizationIntegrityError("authorization is not active yet")
    if checked_at >= _parse_timestamp(expected.expires_at):
        raise ExecutionAuthorizationIntegrityError("authorization has expired")

    try:
        bindings = {
            "operator_id": (authorization.operator_id, _identifier("operator_id", operator_id)),
            "asset_id": (authorization.asset_id, _identifier("asset_id", asset_id)),
            "revision_id": (authorization.revision_id, _identifier("revision_id", revision_id)),
            "provider": (authorization.provider, _identifier("provider", provider)),
            "route_policy": (authorization.route_policy, _route_policy(route_policy)),
        }
    except ValueError as exc:
        raise ExecutionAuthorizationIntegrityError("malformed requested binding") from exc
    for name, (actual, requested) in bindings.items():
        if not hmac.compare_digest(actual, requested):
            raise ExecutionAuthorizationIntegrityError(f"authorization {name} mismatch")


def execute_authorized_call(  # noqa: UP047 - package supports Python 3.11.
    authorization: MultimediaExecutionAuthorization,
    *,
    signing_key: bytes,
    db_path: str,
    operator_id: str,
    asset_id: str,
    revision_id: str,
    provider: str,
    route_policy: str,
    projected_max_cents: int,
    now: datetime,
    call: Callable[[], tuple[T, int]],
) -> tuple[T, RemainingBalance]:
    """Reserve the complete authorized band, then invoke exactly one call.

    The full ceiling is held, rather than merely the current estimate, so a
    concurrent or replayed invocation cannot dispatch while the first is in
    flight. On success the role and run are terminally released. PR #720's
    ledger conservatively charges the full hold when the callback outcome is
    unknown.
    """
    verify_execution_authorization(
        authorization,
        signing_key=signing_key,
        operator_id=operator_id,
        asset_id=asset_id,
        revision_id=revision_id,
        provider=provider,
        route_policy=route_policy,
        now=now,
    )
    projected = _cents(projected_max_cents)
    if projected != authorization.approved_ceiling_cents:
        raise ExecutionAuthorizationIntegrityError(
            "projected maximum must equal the authorized one-shot ceiling"
        )

    run_id = authorization.authorization_id
    role = f"multimedia:{authorization.provider}"
    if not isinstance(db_path, str) or not db_path.strip():
        raise ValueError("db_path is required")
    _claim_authorization(db_path, authorization)
    ledger = BudgetLedger(db_path)
    ledger.ensure_schema()
    ledger.reserve(
        run_id,
        authorization.approved_ceiling_cents,
        role_budgets={role: authorization.approved_ceiling_cents},
    )

    def checked_call() -> tuple[T, int]:
        output = call()
        if not isinstance(output, tuple) or len(output) != 2:
            raise ValueError("provider callback must return (result, actual_cents)")
        result, actual_cents = output
        return result, _actual_cents(actual_cents)

    result, _ = ledger.guarded_call(
        run_id, role, projected, checked_call, on_call_error="conservative",
    )
    ledger.release_role(run_id, role)
    balance = ledger.release(run_id)
    _settle_authorization(db_path, authorization.authorization_id, balance.spent_cents)
    return result, balance


_AUTHORIZATION_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_execution_authorization_claims (
    authorization_id TEXT PRIMARY KEY,
    signature TEXT NOT NULL,
    status TEXT NOT NULL,
    actual_cents BIGINT,
    claimed_at TIMESTAMP NOT NULL,
    settled_at TIMESTAMP
)
"""

_REVOCATION_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_execution_authorization_revocations (
    authorization_id TEXT PRIMARY KEY,
    operator_id TEXT NOT NULL,
    signature TEXT NOT NULL,
    revoked_at TEXT NOT NULL
)
"""

_ASYNC_REVOCATION_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_async_execution_authorization_revocations (
    authorization_id TEXT PRIMARY KEY,
    operator_id TEXT NOT NULL,
    authorization_signature TEXT NOT NULL,
    revoked_at TEXT NOT NULL,
    revocation_mac TEXT NOT NULL
)
"""


def _claim_authorization(
    db_path: str,
    authorization: MultimediaExecutionAuthorization,
) -> None:
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.execution_authorization.claim") as ctx:
        ctx.execute(_AUTHORIZATION_DDL)
        ctx.execute(_REVOCATION_DDL)
        ctx.execute("BEGIN TRANSACTION")
        try:
            revoked = ctx.execute(
                "SELECT 1 FROM multimedia_execution_authorization_revocations "
                "WHERE authorization_id = ?",
                [authorization.authorization_id],
            ).fetchone()
            if revoked is not None:
                raise ExecutionAuthorizationRevoked(
                    f"authorization {authorization.authorization_id} was revoked"
                )
            inserted = ctx.execute(
                "INSERT INTO multimedia_execution_authorization_claims "
                "(authorization_id, signature, status, actual_cents, claimed_at, settled_at) "
                "VALUES (?, ?, 'claimed', NULL, CURRENT_TIMESTAMP, NULL) "
                "ON CONFLICT DO NOTHING RETURNING authorization_id",
                [authorization.authorization_id, authorization.signature],
            ).fetchone()
            if inserted is None:
                raise ExecutionAuthorizationConsumed(
                    f"authorization {authorization.authorization_id} was already consumed"
                )
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")


def revoke_execution_authorization(
    authorization: MultimediaExecutionAuthorization,
    *,
    signing_key: bytes,
    db_path: str,
    operator_id: str,
    now: datetime,
) -> MultimediaExecutionRevocation:
    """Atomically revoke unused authority; exact replay returns the first receipt."""
    issued_at = _parse_timestamp(authorization.issued_at)
    verify_execution_authorization(
        authorization,
        signing_key=signing_key,
        operator_id=operator_id,
        asset_id=authorization.asset_id,
        revision_id=authorization.revision_id,
        provider=authorization.provider,
        route_policy=authorization.route_policy,
        now=issued_at,
    )
    if not isinstance(db_path, str) or not db_path.strip():
        raise ValueError("db_path is required")
    revoked_at = _utc_timestamp(now)
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.execution_authorization.revoke") as ctx:
        ctx.execute(_AUTHORIZATION_DDL)
        ctx.execute(_REVOCATION_DDL)
        ctx.execute("BEGIN TRANSACTION")
        try:
            claimed = ctx.execute(
                "SELECT 1 FROM multimedia_execution_authorization_claims "
                "WHERE authorization_id = ?",
                [authorization.authorization_id],
            ).fetchone()
            existing = ctx.execute(
                "SELECT operator_id, signature, revoked_at "
                "FROM multimedia_execution_authorization_revocations "
                "WHERE authorization_id = ?",
                [authorization.authorization_id],
            ).fetchone()
            if claimed is not None and existing is not None:
                raise ExecutionAuthorizationIntegrityError(
                    "authorization is both consumed and revoked"
                )
            if existing is not None:
                if existing[0] != operator_id or not hmac.compare_digest(
                    existing[1], authorization.signature
                ):
                    raise ExecutionAuthorizationIntegrityError(
                        "stored revocation does not match authorization"
                    )
                result = MultimediaExecutionRevocation(
                    authorization_id=authorization.authorization_id,
                    operator_id=existing[0],
                    revoked_at=_identifier("revoked_at", existing[2]),
                )
            else:
                if claimed is not None:
                    raise ExecutionAuthorizationConsumed(
                        f"authorization {authorization.authorization_id} was already consumed"
                    )
                verify_execution_authorization(
                    authorization,
                    signing_key=signing_key,
                    operator_id=operator_id,
                    asset_id=authorization.asset_id,
                    revision_id=authorization.revision_id,
                    provider=authorization.provider,
                    route_policy=authorization.route_policy,
                    now=now,
                )
                ctx.execute(
                    "INSERT INTO multimedia_execution_authorization_revocations "
                    "(authorization_id, operator_id, signature, revoked_at) "
                    "VALUES (?, ?, ?, ?)",
                    [
                        authorization.authorization_id,
                        operator_id,
                        authorization.signature,
                        revoked_at,
                    ],
                )
                result = MultimediaExecutionRevocation(
                    authorization_id=authorization.authorization_id,
                    operator_id=operator_id,
                    revoked_at=revoked_at,
                )
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")
            return result


def revoke_async_execution_authorization(
    authorization: MultimediaExecutionAuthorizationV2,
    *,
    signing_key: bytes,
    db_path: str,
    operator_id: str,
    now: datetime,
) -> MultimediaExecutionRevocation:
    """Atomically revoke unused v2 authority; exact replay is stable."""
    issued_at = _parse_timestamp(authorization.issued_at)
    verify_async_execution_authorization(
        authorization,
        signing_key=signing_key,
        operator_id=operator_id,
        asset_id=authorization.asset_id,
        revision_id=authorization.revision_id,
        provider=authorization.provider,
        route_policy=authorization.route_policy,
        model=authorization.model,
        endpoint_capability=authorization.endpoint_capability,
        catalog_version=authorization.catalog_version,
        catalog_digest=authorization.catalog_digest,
        quote_id=authorization.quote_id,
        recovery_authority_id=authorization.recovery_authority_id,
        recovery_verification_key_digest=(authorization.recovery_verification_key_digest),
        approved_ceiling_microdollars=authorization.approved_ceiling_microdollars,
        request_body_digest=authorization.request_body_digest,
        now=issued_at,
    )
    if not isinstance(db_path, str) or not db_path.strip():
        raise ValueError("db_path is required")
    revoked_at = _utc_timestamp(now)
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context(
        "multimedia.execution_authorization.revoke_async"
    ) as ctx:
        ctx.execute(_AUTHORIZATION_DDL)
        ctx.execute(_ASYNC_REVOCATION_DDL)
        ctx.execute("BEGIN TRANSACTION")
        try:
            claimed = ctx.execute(
                "SELECT 1 FROM multimedia_execution_authorization_claims "
                "WHERE authorization_id = ?",
                [authorization.authorization_id],
            ).fetchone()
            if claimed is not None:
                raise ExecutionAuthorizationConsumed(
                    f"authorization {authorization.authorization_id} was already consumed"
                )
            existing = ctx.execute(
                "SELECT operator_id, authorization_signature, revoked_at, revocation_mac "
                "FROM multimedia_async_execution_authorization_revocations "
                "WHERE authorization_id = ?",
                [authorization.authorization_id],
            ).fetchone()
            if existing is not None:
                expected_mac = _async_revocation_mac(
                    signing_key,
                    authorization_id=authorization.authorization_id,
                    operator_id=str(existing[0]),
                    authorization_signature=str(existing[1]),
                    revoked_at=str(existing[2]),
                )
                if (
                    existing[0] != operator_id
                    or existing[1] != authorization.signature
                    or not isinstance(existing[3], str)
                    or not hmac.compare_digest(existing[3], expected_mac)
                ):
                    raise ExecutionAuthorizationIntegrityError(
                        "stored authorization revocation is corrupt"
                    )
                result = MultimediaExecutionRevocation(
                    authorization_id=authorization.authorization_id,
                    operator_id=str(existing[0]),
                    revoked_at=str(existing[2]),
                )
            else:
                revocation_mac = _async_revocation_mac(
                    signing_key,
                    authorization_id=authorization.authorization_id,
                    operator_id=operator_id,
                    authorization_signature=authorization.signature,
                    revoked_at=revoked_at,
                )
                ctx.execute(
                    "INSERT INTO multimedia_async_execution_authorization_revocations "
                    "(authorization_id, operator_id, authorization_signature, revoked_at, "
                    "revocation_mac) VALUES (?, ?, ?, ?, ?)",
                    [
                        authorization.authorization_id,
                        operator_id,
                        authorization.signature,
                        revoked_at,
                        revocation_mac,
                    ],
                )
                result = MultimediaExecutionRevocation(
                    authorization_id=authorization.authorization_id,
                    operator_id=operator_id,
                    revoked_at=revoked_at,
                )
        except Exception:
            ctx.execute("ROLLBACK")
            raise
        else:
            ctx.execute("COMMIT")
            return result


def _async_revocation_mac(
    signing_key: bytes,
    *,
    authorization_id: str,
    operator_id: str,
    authorization_signature: str,
    revoked_at: str,
) -> str:
    canonical_revoked_at = _utc_timestamp(_parse_timestamp(revoked_at))
    if canonical_revoked_at != revoked_at:
        raise ExecutionAuthorizationIntegrityError(
            "stored authorization revocation timestamp is not canonical"
        )
    fields = {
        "authorization_id": _identifier("authorization_id", authorization_id),
        "authorization_signature": _identifier("authorization_signature", authorization_signature),
        "operator_id": _identifier("operator_id", operator_id),
        "revoked_at": canonical_revoked_at,
    }
    return hmac.new(signing_key, _canonical(fields), hashlib.sha256).hexdigest()


def verify_async_revocation_record(
    authorization: MultimediaExecutionAuthorizationV2,
    *,
    signing_key: bytes,
    operator_id: object,
    authorization_signature: object,
    revoked_at: object,
    revocation_mac: object,
) -> None:
    """Authenticate one persisted v2 revocation row against its authority."""
    if (
        not isinstance(operator_id, str)
        or not isinstance(authorization_signature, str)
        or not isinstance(revoked_at, str)
        or not isinstance(revocation_mac, str)
        or operator_id != authorization.operator_id
        or authorization_signature != authorization.signature
    ):
        raise ExecutionAuthorizationIntegrityError(
            "stored asynchronous authorization revocation is corrupt"
        )
    expected = _async_revocation_mac(
        signing_key,
        authorization_id=authorization.authorization_id,
        operator_id=operator_id,
        authorization_signature=authorization_signature,
        revoked_at=revoked_at,
    )
    if not hmac.compare_digest(revocation_mac, expected):
        raise ExecutionAuthorizationIntegrityError(
            "stored asynchronous authorization revocation is corrupt"
        )


def _settle_authorization(db_path: str, authorization_id: str, actual_cents: int) -> None:
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.execution_authorization.settle") as ctx:
        updated = ctx.execute(
            "UPDATE multimedia_execution_authorization_claims SET "
            "status = 'settled', actual_cents = ?, settled_at = CURRENT_TIMESTAMP "
            "WHERE authorization_id = ? AND status = 'claimed' RETURNING authorization_id",
            [actual_cents, authorization_id],
        ).fetchone()
        if updated is None:
            raise ExecutionAuthorizationIntegrityError(
                "authorization claim disappeared before settlement"
            )


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _validate_key(signing_key: bytes) -> None:
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise ValueError("signing_key must contain at least 32 bytes")


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a nonempty canonical string")
    return value


def _route_policy(value: object) -> str:
    route = _identifier("route_policy", value)
    if route not in _ROUTE_POLICIES:
        raise ValueError("route_policy is not supported")
    return route


def _cents(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("cents must be an integer")
    if value <= 0 or value > MAX_CENTS:
        raise ValueError("cents must be within the positive signed-BIGINT range")
    return value


def _microdollars(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("microdollars must be an integer")
    if value <= 0 or value > MAX_CENTS:
        raise ValueError("microdollars must be within the positive signed-BIGINT range")
    return value


def _sha256_digest(name: str, value: object) -> str:
    text = _identifier(name, value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return text


def _actual_cents(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("actual_cents must be an integer")
    if value < 0 or value > MAX_CENTS:
        raise ValueError("actual_cents must be within the nonnegative signed-BIGINT range")
    return value


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("issued_at must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    text = _identifier("issued_at", value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionAuthorizationIntegrityError("invalid issued_at") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionAuthorizationIntegrityError("issued_at must be timezone-aware")
    return parsed


__all__ = [
    "ExecutionAuthorizationConsumed",
    "ExecutionAuthorizationIntegrityError",
    "ExecutionAuthorizationRevoked",
    "MAX_CENTS",
    "MAX_AUTHORIZATION_LIFETIME",
    "MultimediaExecutionAuthorization",
    "MultimediaExecutionAuthorizationV2",
    "MultimediaExecutionRevocation",
    "execute_authorized_call",
    "issue_execution_authorization",
    "issue_async_execution_authorization",
    "revoke_execution_authorization",
    "revoke_async_execution_authorization",
    "verify_execution_authorization",
    "verify_async_execution_authorization",
    "verify_async_revocation_record",
]
