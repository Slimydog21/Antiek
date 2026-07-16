"""Inert Cycle-35 envelope binding CoreV4 to an ordered ReceiptV7 roster."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_output_policy_v4 import _CONTRACT_DOMAINS
from .private_provider_capability_v4 import PrivateProviderProcessingCapabilityV4
from .private_provider_receipt_v7 import (
    OwnerPrivatePublicationSourceReceiptV7,
    verify_owner_private_source_receipt_v7,
)
from .private_provider_request_core_v4 import (
    PreparedOwnerPrivateRequestCoreV4,
    owner_private_request_core_v4_sha256,
    verify_owner_private_request_core_v4,
)

_ENVELOPE_V4_DOMAIN = _CONTRACT_DOMAINS["envelope_v4"].encode("utf-8")
_HEX64 = r"^[0-9a-f]{64}$"


def _canonical_json(value: object) -> bytes:
    if isinstance(value, bytes):
        value = value.hex()
    elif isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        value = {key: _canonical_value(item) for key, item in value.items()}
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _canonical_value(value: object) -> object:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    return value


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]


class OwnerPrivateReceiptV7RosterMember(_Closed):
    ordinal: int = Field(ge=1, le=8)
    receipt_id: str = Field(pattern=r"^opsr7_[0-9a-f]{24}$")
    receipt_sha256: str = Field(pattern=_HEX64)


class PreparedOwnerPrivateEnvelopeV4(_Closed):
    schema_version: Literal[4] = 4
    envelope_id: str = Field(pattern=r"^openv4_[0-9a-f]{24}$")
    envelope_sha256: str = Field(pattern=_HEX64)
    request_core: PreparedOwnerPrivateRequestCoreV4 = Field(repr=False)
    request_core_v4_sha256: str = Field(pattern=_HEX64)
    receipt_v7_roster: tuple[OwnerPrivateReceiptV7RosterMember, ...] = Field(
        max_length=8, repr=False
    )
    output_policy_v4_sha256: str = Field(pattern=_HEX64)
    capability_id: str = Field(pattern=r"^ppcap4_[0-9a-f]{24}$")
    capability_v4_sha256: str = Field(pattern=_HEX64)
    provider_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    model_id: str = Field(pattern=r"^[A-Za-z0-9._:/-]{1,256}$")
    route_key: str = Field(min_length=3, max_length=385)
    api_mode: Literal["responses_no_store", "messages_no_store"]
    processing_region: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    output_schema: Literal[
        "midnight-oil.gather-output/v1",
        "midnight-oil.planner-output/v1",
        "midnight-oil.synthesizer-output/v1",
        "midnight-oil.verifier-output/v1",
    ]
    provider_request_sha256: str = Field(pattern=_HEX64)
    provider_request_bytes_count: int = Field(ge=1, le=10_000_000)
    provider_scoped_idempotency_sha256: str = Field(pattern=_HEX64)
    projected_max_cents: int = Field(ge=1, le=1_000_000_000)
    max_output_bytes: int = Field(ge=1, le=1_000_000)
    synthetic_fixture_eligibility_only: Literal[True] = True
    live_migration_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> PreparedOwnerPrivateEnvelopeV4:
        core = self.request_core
        roster = self.receipt_v7_roster
        direct = (
            self.request_core_v4_sha256,
            self.output_policy_v4_sha256,
            self.capability_id,
            self.capability_v4_sha256,
            self.provider_id,
            self.model_id,
            self.route_key,
            self.api_mode,
            self.processing_region,
            self.output_schema,
            self.provider_request_sha256,
            self.provider_request_bytes_count,
            self.provider_scoped_idempotency_sha256,
            self.projected_max_cents,
            self.max_output_bytes,
        )
        expected = (
            core.request_core_sha256,
            core.output_policy_v4_sha256,
            core.capability_id,
            core.capability_v4_sha256,
            core.provider_id,
            core.model_id,
            core.route_key,
            core.api_mode,
            core.processing_region,
            core.output_schema,
            core.provider_request_sha256,
            core.provider_request_bytes_count,
            core.provider_scoped_idempotency_sha256,
            core.projected_max_cents,
            core.max_output_bytes,
        )
        ordinals = tuple(member.ordinal for member in roster)
        digest = prepared_owner_private_envelope_v4_sha256(self)
        if (
            direct != expected
            or owner_private_request_core_v4_sha256(core) != core.request_core_sha256
            or ordinals != tuple(range(1, len(roster) + 1))
            or len({member.receipt_id for member in roster}) != len(roster)
            or len({member.receipt_sha256 for member in roster}) != len(roster)
            or (core.router_role == "planner") != (len(roster) == 0)
            or len(roster) != len(core.source_receipt_pairs)
            or not hmac.compare_digest(self.envelope_sha256, digest)
            or self.envelope_id != "openv4_" + digest[:24]
        ):
            raise ValueError("owner-private prepared envelope v4 conflicts")
        return self


def _envelope_material(
    envelope: PreparedOwnerPrivateEnvelopeV4 | Mapping[str, object],
) -> dict[str, object]:
    raw = envelope.model_dump(mode="python") if isinstance(envelope, BaseModel) else dict(envelope)
    core = raw.get("request_core")
    if type(core) is dict:
        if any(
            type(core.get(field)) is not bytes
            for field in (
                "account_scope_blind_id",
                "project_scope_blind_id",
                "provider_request_bytes",
            )
        ):
            raise ValueError("owner-private prepared envelope v4 material is unavailable")
    elif type(core) is not PreparedOwnerPrivateRequestCoreV4:
        raise ValueError("owner-private prepared envelope v4 material is unavailable")
    return {
        key: value for key, value in raw.items() if key not in {"envelope_id", "envelope_sha256"}
    }


def prepared_owner_private_envelope_v4_sha256(
    envelope: PreparedOwnerPrivateEnvelopeV4 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _ENVELOPE_V4_DOMAIN + _canonical_json(_envelope_material(envelope))
    ).hexdigest()


def verify_prepared_owner_private_envelope_v4(
    envelope: PreparedOwnerPrivateEnvelopeV4,
    *,
    receipts: Sequence[OwnerPrivatePublicationSourceReceiptV7],
    capability: PrivateProviderProcessingCapabilityV4,
    capability_verification_keys: Mapping[str, bytes],
) -> None:
    try:
        if (
            type(envelope) is not PreparedOwnerPrivateEnvelopeV4
            or type(receipts) not in (tuple, list)
            or len(receipts) > 8
        ):
            raise ValueError
        validated = PreparedOwnerPrivateEnvelopeV4.model_validate(
            envelope.model_dump(mode="python")
        )
        rows = tuple(receipts)
        verify_owner_private_request_core_v4(
            validated.request_core,
            capability=capability,
            capability_verification_keys=capability_verification_keys,
        )
        if len(rows) != len(validated.receipt_v7_roster):
            raise ValueError
        for ordinal, (member, receipt) in enumerate(
            zip(validated.receipt_v7_roster, rows, strict=True), start=1
        ):
            verify_owner_private_source_receipt_v7(
                receipt,
                core=validated.request_core,
                capability=capability,
                capability_verification_keys=capability_verification_keys,
            )
            if (
                member.ordinal != ordinal
                or receipt.private_source_ordinal != ordinal
                or member.receipt_id != receipt.receipt_id
                or member.receipt_sha256 != receipt.receipt_sha256
            ):
                raise ValueError
    except Exception:
        raise ValueError("owner-private prepared envelope v4 is unavailable") from None


def build_prepared_owner_private_envelope_v4(
    *,
    request_core: PreparedOwnerPrivateRequestCoreV4,
    receipts: Sequence[OwnerPrivatePublicationSourceReceiptV7],
    capability: PrivateProviderProcessingCapabilityV4,
    capability_verification_keys: Mapping[str, bytes],
) -> PreparedOwnerPrivateEnvelopeV4:
    try:
        if type(receipts) not in (tuple, list) or len(receipts) > 8:
            raise ValueError
        verify_owner_private_request_core_v4(
            request_core,
            capability=capability,
            capability_verification_keys=capability_verification_keys,
        )
        rows = tuple(receipts)
        roster = tuple(
            {
                "ordinal": ordinal,
                "receipt_id": receipt.receipt_id,
                "receipt_sha256": receipt.receipt_sha256,
            }
            for ordinal, receipt in enumerate(rows, start=1)
        )
        core = request_core
        material: dict[str, object] = {
            "schema_version": 4,
            "request_core": core,
            "request_core_v4_sha256": core.request_core_sha256,
            "receipt_v7_roster": roster,
            "output_policy_v4_sha256": core.output_policy_v4_sha256,
            "capability_id": core.capability_id,
            "capability_v4_sha256": core.capability_v4_sha256,
            "provider_id": core.provider_id,
            "model_id": core.model_id,
            "route_key": core.route_key,
            "api_mode": core.api_mode,
            "processing_region": core.processing_region,
            "output_schema": core.output_schema,
            "provider_request_sha256": core.provider_request_sha256,
            "provider_request_bytes_count": core.provider_request_bytes_count,
            "provider_scoped_idempotency_sha256": core.provider_scoped_idempotency_sha256,
            "projected_max_cents": core.projected_max_cents,
            "max_output_bytes": core.max_output_bytes,
            "synthetic_fixture_eligibility_only": True,
            "live_migration_verified": False,
            "user_accounting_effect": False,
            "transport_reachable": False,
            "confers_execution_authority": False,
            "confers_checkpoint_authority": False,
            "confers_sink_authority": False,
            "confers_transition_authority": False,
            "production_consumer_enabled": False,
        }
        digest = prepared_owner_private_envelope_v4_sha256(material)
        envelope = PreparedOwnerPrivateEnvelopeV4.model_validate(
            {**material, "envelope_id": "openv4_" + digest[:24], "envelope_sha256": digest}
        )
        verify_prepared_owner_private_envelope_v4(
            envelope,
            receipts=rows,
            capability=capability,
            capability_verification_keys=capability_verification_keys,
        )
        return envelope
    except Exception:
        raise ValueError("owner-private prepared envelope v4 is unavailable") from None


__all__ = [
    "OwnerPrivateReceiptV7RosterMember",
    "PreparedOwnerPrivateEnvelopeV4",
    "build_prepared_owner_private_envelope_v4",
    "prepared_owner_private_envelope_v4_sha256",
    "verify_prepared_owner_private_envelope_v4",
]
