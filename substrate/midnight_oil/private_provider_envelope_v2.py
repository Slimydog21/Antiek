"""Acyclic fixture-only envelope binding one request core to receipt-v5 membership."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_provider_receipt_v5 import (
    OwnerPrivatePublicationSourceReceiptV5,
    owner_private_source_receipt_v5_sha256,
)
from .private_provider_request_core_v2 import (
    PreparedOwnerPrivateRequestCoreV2,
    owner_private_request_core_v2_sha256,
)

_ENVELOPE_DOMAIN = b"antiek.midnight-oil.owner-private-prepared-envelope.v2\x00"
_HEX64 = r"^[0-9a-f]{64}$"


class _Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]


class OwnerPrivateReceiptV5RosterMember(_Closed):
    ordinal: int = Field(ge=1, le=8)
    receipt_id: str = Field(pattern=r"^opsr5_[0-9a-f]{24}$")
    receipt_sha256: str = Field(pattern=_HEX64)


class PreparedOwnerPrivateEnvelopeV2(_Closed):
    schema_version: Literal[2] = 2
    envelope_id: str = Field(pattern=r"^openv2_[0-9a-f]{24}$")
    envelope_sha256: str = Field(pattern=_HEX64)
    request_core: PreparedOwnerPrivateRequestCoreV2 = Field(repr=False)
    request_core_v2_sha256: str = Field(pattern=_HEX64)
    receipt_v5_roster: tuple[OwnerPrivateReceiptV5RosterMember, ...] = Field(
        max_length=8, repr=False
    )
    confers_execution_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> PreparedOwnerPrivateEnvelopeV2:
        roster = self.receipt_v5_roster
        expected = tuple(range(1, len(roster) + 1))
        if (
            self.request_core_v2_sha256 != self.request_core.request_core_sha256
            or tuple(member.ordinal for member in roster) != expected
            or len({member.receipt_id for member in roster}) != len(roster)
            or len({member.receipt_sha256 for member in roster}) != len(roster)
            or (self.request_core.router_role == "planner" and roster)
            or (
                self.request_core.router_role != "planner"
                and len(roster) != len(self.request_core.private_sources)
            )
        ):
            raise ValueError("owner-private prepared envelope v2 roster conflicts")
        digest = prepared_owner_private_envelope_v2_sha256(self)
        if self.envelope_sha256 != digest or self.envelope_id != "openv2_" + digest[:24]:
            raise ValueError("owner-private prepared envelope v2 identity conflicts")
        return self


def prepared_owner_private_envelope_v2_sha256(
    envelope: PreparedOwnerPrivateEnvelopeV2 | Mapping[str, object],
) -> str:
    raw = (
        envelope.model_dump(mode="json")
        if isinstance(envelope, BaseModel)
        else dict(envelope)
    )
    request_core = raw.get("request_core")
    if isinstance(request_core, BaseModel):
        raw["request_core"] = request_core.model_dump(mode="json")
    elif isinstance(request_core, dict):
        request_core = dict(request_core)
        provider_bytes = request_core.get("provider_request_bytes")
        if isinstance(provider_bytes, bytes):
            request_core["provider_request_bytes"] = provider_bytes.decode("utf-8")
        raw["request_core"] = request_core
    material = {
        key: value
        for key, value in raw.items()
        if key not in {"envelope_id", "envelope_sha256"}
    }
    encoded = json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(_ENVELOPE_DOMAIN + encoded).hexdigest()


def build_prepared_owner_private_envelope_v2(
    *,
    request_core: PreparedOwnerPrivateRequestCoreV2,
    receipts: Sequence[OwnerPrivatePublicationSourceReceiptV5],
) -> PreparedOwnerPrivateEnvelopeV2:
    try:
        request_core = PreparedOwnerPrivateRequestCoreV2.model_validate(
            request_core.model_dump(mode="python")
        )
        rows = tuple(
            OwnerPrivatePublicationSourceReceiptV5.model_validate(
                receipt.model_dump(mode="python")
            )
            for receipt in receipts
        )
    except (ValueError, TypeError):
        raise ValueError("owner-private prepared envelope v2 authority is unavailable") from None
    if (
        owner_private_request_core_v2_sha256(request_core)
        != request_core.request_core_sha256
        or request_core.request_core_id
        != "oprc2_" + request_core.request_core_sha256[:24]
        or any(
            owner_private_source_receipt_v5_sha256(receipt)
            != receipt.receipt_sha256
            or receipt.receipt_id != "opsr5_" + receipt.receipt_sha256[:24]
            for receipt in rows
        )
    ):
        raise ValueError("owner-private prepared envelope v2 authority is unavailable")
    if len(rows) != len(request_core.private_sources):
        raise ValueError("owner-private prepared envelope v2 receipt count conflicts")
    for ordinal, (source, receipt) in enumerate(
        zip(request_core.private_sources, rows, strict=True), start=1
    ):
        if (
            source.ordinal != ordinal
            or receipt.private_source_ordinal != ordinal
            or receipt.request_core_v2_sha256 != request_core.request_core_sha256
            or receipt.owner_scope_sha256 != request_core.owner_scope_sha256
            or receipt.operation_id != request_core.operation_id
            or receipt.job_id != request_core.job_id
            or receipt.execution_id != request_core.execution_id
            or receipt.stage_key != request_core.stage_key
            or receipt.router_role != request_core.router_role
            or receipt.provider_capability_v2_sha256
            != request_core.provider_capability_v2_sha256
            or receipt.swarm_plan_sha256 != request_core.swarm_plan_sha256
            or receipt.stage_plan_sha256 != request_core.stage_plan_sha256
            or receipt.route_plan_sha256 != request_core.route_plan_sha256
            or receipt.publication_manifest_sha256
            != request_core.publication_manifest_sha256
            or receipt.required_until_ms != request_core.required_until_ms
            or receipt.output_policy_v2_sha256
            != request_core.output_policy_v2_sha256
            or receipt.checker_sha256 != request_core.checker_sha256
            or receipt.source_extractor_sha256
            != request_core.source_extractor_sha256
            or hashlib.sha256(source.text.encode("utf-8")).hexdigest()
            != receipt.source_authority_v4.excerpt_sha256
            or len(source.text.encode("utf-8"))
            != receipt.source_authority_v4.excerpt_bytes
        ):
            raise ValueError("owner-private prepared envelope v2 receipt conflicts")
    roster = tuple(
        {
            "ordinal": ordinal,
            "receipt_id": receipt.receipt_id,
            "receipt_sha256": receipt.receipt_sha256,
        }
        for ordinal, receipt in enumerate(rows, start=1)
    )
    material: dict[str, object] = {
        "schema_version": 2,
        "request_core": request_core,
        "request_core_v2_sha256": request_core.request_core_sha256,
        "receipt_v5_roster": roster,
        "confers_execution_authority": False,
        "production_consumer_enabled": False,
    }
    digest = prepared_owner_private_envelope_v2_sha256(material)
    return PreparedOwnerPrivateEnvelopeV2.model_validate(
        {**material, "envelope_id": "openv2_" + digest[:24], "envelope_sha256": digest}
    )


__all__ = [
    "OwnerPrivateReceiptV5RosterMember",
    "PreparedOwnerPrivateEnvelopeV2",
    "build_prepared_owner_private_envelope_v2",
    "prepared_owner_private_envelope_v2_sha256",
]
