"""Non-conferring PolicyV3 for certified in-memory overlap evaluation only."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_output_checker_v2 import (
    PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_V2_SHA256,
    PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256,
    PRIVATE_OUTPUT_LEDGER_V2_SHA256,
    PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256,
)
from .private_output_compliance import (
    OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
    PRIVATE_OUTPUT_LIVE_ROLES_CODE_SHA256,
    PRIVATE_OUTPUT_ROLE_PARSER_SHA256,
    PRIVATE_OUTPUT_ROLE_SCHEMA_SHA256,
    PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    PRIVATE_OUTPUT_THRESHOLD_SHA256,
)
from .private_output_source_adapter_v1 import (
    PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256,
    PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256,
    PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256,
)

_POLICY_V3_DOMAIN = b"antiek.midnight-oil.owner-private-output-policy.v3\x00"
_HEX64 = r"^[0-9a-f]{64}$"


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


_POLICY_V3_MATERIAL: dict[str, object] = {
    "schema_version": 3,
    "policy_id": "antiek-owner-private-provider-output-v3",
    "predecessor_kind": "policy_v2_route_only_nonconferring_evidence",
    "predecessor_policy_v2_sha256": OWNER_PRIVATE_OUTPUT_POLICY_V2_SHA256,
    "content_class": "personal_reading",
    "certified_operation": "in_memory_owner_private_overlap_evaluation_only",
    "source_adapter_contract_sha256": PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256,
    "source_adapter_implementation_sha256": (
        PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256
    ),
    "source_adapter_source_set_sha256": PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256,
    "checker_v2_contract_sha256": PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256,
    "checker_v2_sha256": PRIVATE_OUTPUT_CHECKER_V2_SHA256,
    "checker_v2_corpus_sha256": PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256,
    "checker_v2_module_sha256": PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256,
    "checker_v2_normalizer_sha256": PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256,
    "checker_v2_ledger_sha256": PRIVATE_OUTPUT_LEDGER_V2_SHA256,
    "role_parser_sha256": PRIVATE_OUTPUT_ROLE_PARSER_SHA256,
    "role_schema_sha256": PRIVATE_OUTPUT_ROLE_SCHEMA_SHA256,
    "live_roles_code_sha256": PRIVATE_OUTPUT_LIVE_ROLES_CODE_SHA256,
    "source_extractor_sha256": PRIVATE_OUTPUT_SOURCE_EXTRACTOR_SHA256,
    "threshold_sha256": PRIVATE_OUTPUT_THRESHOLD_SHA256,
    "durable_current_resolution_required": True,
    "authorized_sinks": (),
    "unknown_sink": "deny",
    "declassification_authorized": False,
    "public_serving_authorized": False,
    "portable_export_authorized": False,
    "training_authorized": False,
    "checkpoint_authorized": False,
    "checker_evaluation_ready": True,
    "provider_execution_authorized": False,
    "request_core_v3_authorized": False,
    "receipt_v6_authorized": False,
    "confers_checkpoint_authority": False,
    "confers_execution_authority": False,
    "confers_sink_authority": False,
    "production_consumer_enabled": False,
}


def _policy_v3_digest(value: object) -> str:
    return hashlib.sha256(_POLICY_V3_DOMAIN + _canonical_json(value)).hexdigest()


OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256 = _policy_v3_digest(_POLICY_V3_MATERIAL)


class _Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]


class OwnerPrivateOutputPolicyV3(_Closed):
    schema_version: Literal[3] = 3
    policy_id: Literal["antiek-owner-private-provider-output-v3"] = (
        "antiek-owner-private-provider-output-v3"
    )
    predecessor_kind: Literal["policy_v2_route_only_nonconferring_evidence"] = (
        "policy_v2_route_only_nonconferring_evidence"
    )
    predecessor_policy_v2_sha256: str = Field(pattern=_HEX64)
    content_class: Literal["personal_reading"] = "personal_reading"
    certified_operation: Literal[
        "in_memory_owner_private_overlap_evaluation_only"
    ] = "in_memory_owner_private_overlap_evaluation_only"
    source_adapter_contract_sha256: str = Field(pattern=_HEX64)
    source_adapter_implementation_sha256: str = Field(pattern=_HEX64)
    source_adapter_source_set_sha256: str = Field(pattern=_HEX64)
    checker_v2_contract_sha256: str = Field(pattern=_HEX64)
    checker_v2_sha256: str = Field(pattern=_HEX64)
    checker_v2_corpus_sha256: str = Field(pattern=_HEX64)
    checker_v2_module_sha256: str = Field(pattern=_HEX64)
    checker_v2_normalizer_sha256: str = Field(pattern=_HEX64)
    checker_v2_ledger_sha256: str = Field(pattern=_HEX64)
    role_parser_sha256: str = Field(pattern=_HEX64)
    role_schema_sha256: str = Field(pattern=_HEX64)
    live_roles_code_sha256: str = Field(pattern=_HEX64)
    source_extractor_sha256: str = Field(pattern=_HEX64)
    threshold_sha256: str = Field(pattern=_HEX64)
    durable_current_resolution_required: Literal[True] = True
    authorized_sinks: tuple[()] = ()
    unknown_sink: Literal["deny"] = "deny"
    declassification_authorized: Literal[False] = False
    public_serving_authorized: Literal[False] = False
    portable_export_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    checkpoint_authorized: Literal[False] = False
    checker_evaluation_ready: Literal[True] = True
    provider_execution_authorized: Literal[False] = False
    request_core_v3_authorized: Literal[False] = False
    receipt_v6_authorized: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False
    policy_sha256: str = Field(pattern=_HEX64)

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateOutputPolicyV3:
        if (
            self.model_dump(mode="python", exclude={"policy_sha256"})
            != _POLICY_V3_MATERIAL
            or self.policy_sha256 != OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256
        ):
            raise ValueError("owner-private output policy v3 conflicts")
        return self


def owner_private_output_policy_v3_sha256(
    policy: OwnerPrivateOutputPolicyV3 | Mapping[str, object],
) -> str:
    raw = policy.model_dump(mode="json") if isinstance(policy, BaseModel) else dict(policy)
    return _policy_v3_digest({key: value for key, value in raw.items() if key != "policy_sha256"})


def build_owner_private_output_policy_v3() -> OwnerPrivateOutputPolicyV3:
    return OwnerPrivateOutputPolicyV3.model_validate(
        {**_POLICY_V3_MATERIAL, "policy_sha256": OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256}
    )


__all__ = [
    "OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256",
    "OwnerPrivateOutputPolicyV3",
    "build_owner_private_output_policy_v3",
    "owner_private_output_policy_v3_sha256",
]
