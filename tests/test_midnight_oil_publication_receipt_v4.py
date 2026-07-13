from __future__ import annotations

import pytest
from pydantic import ValidationError

from substrate.midnight_oil.private_provider_dispatch import (
    OwnerPrivatePublicationSourceReceiptV4,
)
from tests.test_midnight_oil_private_dispatch_boundary import _prepare


def test_owner_private_source_receipt_v4_literal_golden_vector() -> None:
    prepared, _composition = _prepare()
    receipt = prepared.source_receipts[0]
    assert receipt.receipt_id == "opsr4_bd488b95c5756aff06ae2a63"
    assert receipt.receipt_sha256 == (
        "bd488b95c5756aff06ae2a63e4cb803a3d8b5030c72512cec563f7e4a46beba1"
    )
    assert prepared.provider_request_sha256 == (
        "b2e1f64e637ee269512c204ee1ed0335b3b77e477485c8e0d6b5185e2c4b097e"
    )


@pytest.mark.parametrize(
    "field",
    (
        "operation_id",
        "job_id",
        "execution_id",
        "stage_key",
        "router_role",
        "publication_manifest_sha256",
        "provider_request_sha256",
        "private_input_commitment_sha256",
        "required_until_ms",
        "private_source_ordinal",
        "overlay_sha256",
        "authorization_sha256",
        "source_receipt_sha256",
        "excerpt_sha256",
        "provider_capability_sha256",
        "route_key",
        "api_mode",
        "processing_region",
        "endpoint_origin_sha256",
        "account_project_scope_sha256",
        "adapter_contract_sha256",
        "dispatch_config_sha256",
        "output_policy_sha256",
        "max_output_bytes",
        "content_class",
        "rights_tier",
        "rights_use",
    ),
)
def test_every_v4_identity_mutation_rejects(field: str) -> None:
    prepared, _composition = _prepare()
    raw = prepared.source_receipts[0].model_dump(mode="python")
    original = raw[field]
    raw[field] = "0" * 64 if isinstance(original, str) and len(original) == 64 else "changed"
    with pytest.raises((ValidationError, ValueError)):
        OwnerPrivatePublicationSourceReceiptV4.model_validate(raw)
