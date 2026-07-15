"""Immutable cost evidence for direct, exact-revision provider executions."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from runtime.db_lock import connect_read
from substrate.multimedia.provider_execution import (
    ProviderExecutionIntegrityError,
    ProviderExecutionStatus,
    provider_execution_record_from_row,
)

_IDENTIFIER_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-")
_MAX_CENTS = (1 << 63) - 1


class MultimediaShipCostEvidenceUnavailable(RuntimeError):
    """No complete, supported direct-provider accounting closure exists."""

    code = "evidence_unavailable"


class MultimediaShipCostEvidenceConflict(MultimediaShipCostEvidenceUnavailable):
    """Persisted accounting rows contradict the supported closure contract."""

    code = "evidence_conflict"


class _SnapshotModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class MultimediaShipCostExecutionV1(_SnapshotModel):
    execution_id: str
    authorization_id: str
    provider: str
    model: str
    route_policy: str
    capability: str
    catalog_version: str
    catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_status: Literal["succeeded"] = "succeeded"
    charged_cents: int = Field(ge=0, le=_MAX_CENTS)
    settled_at: str


class MultimediaShipCostSnapshotV1(_SnapshotModel):
    schema_version: Literal["antiek.multimedia-ship-cost-snapshot.v1"] = (
        "antiek.multimedia-ship-cost-snapshot.v1"
    )
    evidence_id: str = Field(pattern=r"^mmscost_[0-9a-f]{64}$")
    owner_identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset_id: str
    revision_id: str
    generated_at_cutoff: str
    basis: Literal["direct_settled_provider_executions"] = "direct_settled_provider_executions"
    executions: tuple[MultimediaShipCostExecutionV1, ...]
    charged_cents: int = Field(ge=0, le=_MAX_CENTS)
    snapshot_mac: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_multimedia_ship_cost_snapshot(
    *,
    db_path: str,
    signing_key: bytes,
    snapshot_key: bytes,
    owner_id: str,
    asset_id: str,
    revision_id: str,
    now: datetime,
) -> MultimediaShipCostSnapshotV1:
    """Discover and freeze all direct executions for one exact revision."""
    owner = _owner_identity(owner_id)
    asset = _identity("asset_id", asset_id)
    revision = _identity("revision_id", revision_id)
    cutoff = _timestamp(now)
    _key(signing_key, "signing_key")
    _key(snapshot_key, "snapshot_key")
    try:
        with connect_read(str(db_path)) as connection:
            connection.execute("BEGIN TRANSACTION")
            rows = connection.execute(
                "SELECT * FROM multimedia_provider_executions "
                "WHERE operator_id=? AND asset_id=? AND revision_id=? ORDER BY execution_id",
                [owner, asset, revision],
            ).fetchall()
            if not rows:
                raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
            evidence_rows = tuple(
                _execution_evidence(
                    connection,
                    row=tuple(row),
                    signing_key=signing_key,
                    owner_id=owner,
                    asset_id=asset,
                    revision_id=revision,
                    cutoff=cutoff,
                )
                for row in rows
            )
            connection.execute("COMMIT")
    except MultimediaShipCostEvidenceUnavailable:
        raise
    except Exception as exc:
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable") from exc
    ids = tuple(row.execution_id for row in evidence_rows)
    if len(ids) != len(set(ids)):
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
    total = sum(row.charged_cents for row in evidence_rows)
    if total > _MAX_CENTS:
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
    owner_digest = hashlib.sha256(owner.encode()).hexdigest()
    unsigned = {
        "schema_version": "antiek.multimedia-ship-cost-snapshot.v1",
        "owner_identity_digest": owner_digest,
        "asset_id": asset,
        "revision_id": revision,
        "generated_at_cutoff": cutoff,
        "basis": "direct_settled_provider_executions",
        "executions": tuple(row.model_dump(mode="json") for row in evidence_rows),
        "charged_cents": total,
    }
    evidence_id = "mmscost_" + hashlib.sha256(_canonical(unsigned)).hexdigest()
    signed = {"evidence_id": evidence_id, **unsigned}
    snapshot_mac = hmac.new(snapshot_key, _canonical(signed), hashlib.sha256).hexdigest()
    return MultimediaShipCostSnapshotV1(
        evidence_id=evidence_id,
        owner_identity_digest=owner_digest,
        asset_id=asset,
        revision_id=revision,
        generated_at_cutoff=cutoff,
        executions=evidence_rows,
        charged_cents=total,
        snapshot_mac=snapshot_mac,
    )


def verify_multimedia_ship_cost_snapshot(
    snapshot: MultimediaShipCostSnapshotV1,
    *,
    snapshot_key: bytes,
    owner_id: str,
    asset_id: str,
    revision_id: str,
) -> None:
    """Verify the immutable evidence and its requested identity bindings."""
    _key(snapshot_key, "snapshot_key")
    owner = _owner_identity(owner_id)
    asset = _identity("asset_id", asset_id)
    revision = _identity("revision_id", revision_id)
    payload = snapshot.model_dump(mode="json", exclude={"snapshot_mac"})
    unsigned = dict(payload)
    unsigned.pop("evidence_id")
    expected_id = "mmscost_" + hashlib.sha256(_canonical(unsigned)).hexdigest()
    expected_mac = hmac.new(snapshot_key, _canonical(payload), hashlib.sha256).hexdigest()
    ids = tuple(row.execution_id for row in snapshot.executions)
    expected_total = sum(row.charged_cents for row in snapshot.executions)
    if (
        not snapshot.executions
        or ids != tuple(sorted(ids))
        or len(ids) != len(set(ids))
        or expected_total > _MAX_CENTS
        or snapshot.charged_cents != expected_total
        or snapshot.owner_identity_digest != hashlib.sha256(owner.encode()).hexdigest()
        or snapshot.asset_id != asset
        or snapshot.revision_id != revision
        or not hmac.compare_digest(snapshot.evidence_id, expected_id)
        or not hmac.compare_digest(snapshot.snapshot_mac, expected_mac)
    ):
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
    _timestamp(datetime.fromisoformat(snapshot.generated_at_cutoff.replace("Z", "+00:00")))


def validate_settled_execution(
    connection: Any,
    *,
    execution_id: str,
    signing_key: bytes,
    owner_id: str,
    asset_id: str,
    revision_id: str,
    cutoff: str,
) -> MultimediaShipCostExecutionV1:
    """Validate one exact execution through MAC, settlement, and accounting closure.

    This is the bounded exact-execution helper reused by production_cost_closure
    so settlement accounting is not duplicated.
    """
    row = connection.execute(
        "SELECT * FROM multimedia_provider_executions WHERE execution_id=?",
        [execution_id],
    ).fetchone()
    if row is None:
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
    return _execution_evidence(
        connection,
        row=tuple(row),
        signing_key=signing_key,
        owner_id=owner_id,
        asset_id=asset_id,
        revision_id=revision_id,
        cutoff=cutoff,
    )


def _execution_evidence(
    connection: Any,
    *,
    row: tuple[object, ...],
    signing_key: bytes,
    owner_id: str,
    asset_id: str,
    revision_id: str,
    cutoff: str,
) -> MultimediaShipCostExecutionV1:
    try:
        record = provider_execution_record_from_row(row, signing_key=signing_key)
    except ProviderExecutionIntegrityError as exc:
        raise MultimediaShipCostEvidenceConflict("evidence_conflict") from exc
    if (
        record.operator_id != owner_id
        or record.asset_id != asset_id
        or record.revision_id != revision_id
        or record.status is not ProviderExecutionStatus.SUCCEEDED
    ):
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    return _validate_execution_accounting(
        connection,
        record=record,
        authorization_signature=row[2],
        cutoff=cutoff,
    )


def _validate_execution_accounting(
    connection: Any,
    *,
    record: Any,
    authorization_signature: object,
    cutoff: str,
) -> MultimediaShipCostExecutionV1:
    """Validate claim, hold, and reservation accounting for one execution."""
    claim_rows = connection.execute(
        "SELECT signature,status,actual_cents,settled_at FROM "
        "multimedia_execution_authorization_claims WHERE authorization_id=?",
        [record.authorization_id],
    ).fetchall()
    hold_rows = connection.execute(
        "SELECT projected_max_cents,state FROM midnight_oil_call_holds WHERE run_id=?",
        [record.authorization_id],
    ).fetchall()
    reservation_rows = connection.execute(
        "SELECT ceiling_cents,spent_cents,held_cents,freed_cents,status FROM "
        "midnight_oil_reservations WHERE run_id=?",
        [record.authorization_id],
    ).fetchall()
    if len(claim_rows) != 1 or len(hold_rows) != 1 or len(reservation_rows) != 1:
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    signature, claim_status, cents, settled_at = claim_rows[0]
    projected, hold_state = hold_rows[0]
    ceiling, spent, held, freed, reservation_status = reservation_rows[0]
    expected_ceiling = (record.approved_ceiling_microdollars + 9_999) // 10_000
    if isinstance(cents, bool) or not isinstance(cents, int) or not 0 <= cents <= _MAX_CENTS:
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    settled = _db_timestamp(settled_at)
    updated = _db_timestamp(record.updated_at)
    if (
        signature != authorization_signature
        or claim_status != "settled"
        or hold_state != "settled"
        or reservation_status != "exhausted"
        or projected != expected_ceiling
        or ceiling != expected_ceiling
        or spent != cents
        or held != 0
        or freed != expected_ceiling - cents
        or settled > cutoff
        or updated > cutoff
    ):
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    return MultimediaShipCostExecutionV1(
        execution_id=record.execution_id,
        authorization_id=record.authorization_id,
        provider=record.provider,
        model=record.model,
        route_policy=record.route_policy,
        capability=record.endpoint_capability,
        catalog_version=record.catalog_version,
        catalog_digest=record.catalog_digest,
        charged_cents=cents,
        settled_at=settled,
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")


def _key(value: bytes, name: str) -> None:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError(f"{name} must contain at least 32 bytes")


def _identity(name: str, value: str, *, max_bytes: int = 128) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValueError(f"{name} is invalid")
    encoded = value.encode("utf-8")
    if len(encoded) > max_bytes or any(char not in _IDENTIFIER_CHARS for char in value):
        raise ValueError(f"{name} is invalid")
    return value


def _owner_identity(value: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValueError("owner_id is invalid")
    encoded = value.encode("utf-8")
    if len(encoded) > 512 or any(byte < 32 or byte == 127 for byte in encoded):
        raise ValueError("owner_id is invalid")
    return value


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("snapshot time must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _db_timestamp(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
    else:
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
    return _timestamp(parsed)


__all__ = [
    "MultimediaShipCostEvidenceConflict",
    "MultimediaShipCostEvidenceUnavailable",
    "MultimediaShipCostExecutionV1",
    "MultimediaShipCostSnapshotV1",
    "build_multimedia_ship_cost_snapshot",
    "validate_settled_execution",
    "verify_multimedia_ship_cost_snapshot",
]
