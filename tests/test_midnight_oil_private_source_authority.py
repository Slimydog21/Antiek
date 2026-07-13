from __future__ import annotations

import ast
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import substrate.midnight_oil.private_source_authority as authority
from substrate.midnight_oil.private_provider_dispatch import (
    OwnerPrivatePublicationSourceReceiptV4,
    owner_private_source_receipt_v4_sha256,
)
from substrate.midnight_oil.private_provider_envelope_v2 import (
    PreparedOwnerPrivateEnvelopeV2,
    prepared_owner_private_envelope_v2_sha256,
)
from substrate.midnight_oil.private_provider_receipt_v5 import (
    OwnerPrivatePublicationSourceReceiptV5,
    owner_private_source_receipt_v5_sha256,
)
from substrate.midnight_oil.private_source_authority import (
    OWNER_PRIVATE_SOURCE_VAULT_CONTRACT_V1_SHA256,
    PRIVATE_SOURCE_AUTHORITY_MODULE_SOURCE_SHA256,
    OwnerPrivateEncryptedSourceBundleV1,
    OwnerPrivateSourceBundleV1Rejected,
    OwnerPrivateSourceVaultContractV1,
    SourceCreationAnchorV1,
    SourceCreationAnchorV1Rejected,
    build_owner_private_source_vault_contract_v1,
    owner_private_encrypted_source_bundle_v1_sha256,
    parse_source_creation_anchor_v1_json,
    private_source_authority_module_source_sha256,
    require_private_source_authority_module_source,
    source_creation_anchor_v1_sha256,
    validate_owner_private_encrypted_source_bundle_v1,
    verify_source_creation_anchor_v1,
)
from tests.support.owner_private_source_authority_v1 import (
    ANCHOR_KEY_ID,
    ANCHOR_PRIVATE_KEY,
    ANCHOR_SIGNATURE_DOMAIN,
    creation_anchor,
    encrypted_source_bundle,
    owner_private_source_authority_case,
    sign_digest,
)
from tests.support.owner_private_v2 import (
    owner_private_v2_case,
    owner_private_v2_multi_case,
    owner_private_v2_planner_case,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "substrate/midnight_oil/private_source_authority.py"
MODULE_NAME = "substrate.midnight_oil.private_source_authority"


def _resign_anchor(raw: dict[str, Any]) -> SourceCreationAnchorV1:
    raw.pop("anchor_id", None)
    raw.pop("anchor_sha256", None)
    raw.pop("signature_ed25519", None)
    digest = source_creation_anchor_v1_sha256(raw)
    return SourceCreationAnchorV1.model_validate(
        {
            **raw,
            "anchor_id": "opsca1_" + digest[:24],
            "anchor_sha256": digest,
            "signature_ed25519": sign_digest(
                ANCHOR_SIGNATURE_DOMAIN, digest, private_key=ANCHOR_PRIVATE_KEY
            ),
        }
    )


def _rebundle(raw: dict[str, Any]) -> OwnerPrivateEncryptedSourceBundleV1:
    raw.pop("bundle_id", None)
    raw.pop("bundle_sha256", None)
    digest = owner_private_encrypted_source_bundle_v1_sha256(raw)
    return OwnerPrivateEncryptedSourceBundleV1.model_validate(
        {**raw, "bundle_id": "opsb1_" + digest[:24], "bundle_sha256": digest}
    )


def _valid_shared_lineage_substitution(
    bundle: OwnerPrivateEncryptedSourceBundleV1, field: str
) -> OwnerPrivateEncryptedSourceBundleV1:
    receipt_raw = bundle.receipt_v5_roster[0].model_dump(mode="python")
    replacements: dict[str, object] = {
        "provider_id": "other-provider",
        "model_id": "other-model",
        "route_key": "other:route",
        "api_mode": (
            "messages_no_store"
            if receipt_raw["source_authority_v4"]["api_mode"] == "responses_no_store"
            else "responses_no_store"
        ),
        "processing_region": "other-region",
        "max_output_bytes": 499_999,
        "source_byte_start": 99,
        "source_byte_end": 140,
        "source_representation_bytes": 138,
    }
    replacement = replacements.get(field, "0" * 64)
    direct_and_nested = {
        "swarm_plan_sha256",
        "stage_plan_sha256",
        "route_plan_sha256",
        "publication_manifest_sha256",
    }
    nested_only = {
        "provider_id",
        "model_id",
        "route_key",
        "api_mode",
        "processing_region",
        "endpoint_origin_sha256",
        "account_project_scope_sha256",
        "adapter_contract_sha256",
        "dispatch_config_sha256",
        "max_output_bytes",
        "source_byte_start",
        "source_byte_end",
        "source_representation_bytes",
    }
    if field in direct_and_nested | nested_only | {"source_evidence_v1_request_sha256"}:
        v4_raw = dict(receipt_raw["source_authority_v4"])
        v4_field = (
            "provider_request_sha256" if field == "source_evidence_v1_request_sha256" else field
        )
        v4_raw[v4_field] = replacement
        v4_raw.pop("receipt_id")
        v4_raw.pop("receipt_sha256")
        v4_digest = owner_private_source_receipt_v4_sha256(v4_raw)
        v4 = OwnerPrivatePublicationSourceReceiptV4.model_validate(
            {
                **v4_raw,
                "receipt_id": "opsr4_" + v4_digest[:24],
                "receipt_sha256": v4_digest,
            }
        )
        receipt_raw["source_authority_v4"] = v4.model_dump(mode="python")
        receipt_raw["source_authority_v4_sha256"] = v4.receipt_sha256
    if field in direct_and_nested | {
        "provider_capability_v2_sha256",
        "source_evidence_v1_request_sha256",
    }:
        receipt_raw[field] = replacement
    receipt_raw.pop("receipt_id")
    receipt_raw.pop("receipt_sha256")
    receipt_digest = owner_private_source_receipt_v5_sha256(receipt_raw)
    receipt = OwnerPrivatePublicationSourceReceiptV5.model_validate(
        {
            **receipt_raw,
            "receipt_id": "opsr5_" + receipt_digest[:24],
            "receipt_sha256": receipt_digest,
        }
    )
    envelope_raw = bundle.envelope_v2.model_dump(mode="python")
    envelope_raw["receipt_v5_roster"][0]["receipt_id"] = receipt.receipt_id
    envelope_raw["receipt_v5_roster"][0]["receipt_sha256"] = receipt.receipt_sha256
    envelope_raw.pop("envelope_id")
    envelope_raw.pop("envelope_sha256")
    envelope_digest = prepared_owner_private_envelope_v2_sha256(envelope_raw)
    envelope = PreparedOwnerPrivateEnvelopeV2.model_validate(
        {
            **envelope_raw,
            "envelope_id": "openv2_" + envelope_digest[:24],
            "envelope_sha256": envelope_digest,
        }
    )
    anchor_raw = bundle.creation_anchors[0].model_dump(mode="python")
    anchor_raw["envelope_v2_sha256"] = envelope.envelope_sha256
    anchor_raw["source_receipt_v5"] = receipt.model_dump(mode="python")
    anchor_raw["source_receipt_v5_sha256"] = receipt.receipt_sha256
    anchor = _resign_anchor(anchor_raw)
    bundle_raw = bundle.model_dump(mode="python")
    bundle_raw["envelope_v2"] = envelope.model_dump(mode="python")
    bundle_raw["receipt_v5_roster"] = (receipt.model_dump(mode="python"),)
    bundle_raw["creation_anchors"] = (anchor.model_dump(mode="python"),)
    return _rebundle(bundle_raw)


def test_anchor_exact_identity_signature_domains_and_nonconferral() -> None:
    case = owner_private_source_authority_case()
    anchor = creation_anchor(case.predecessor, 1)
    assert authority._SOURCE_CREATION_ANCHOR_DOMAIN == (
        b"antiek.midnight-oil.owner-private-source-creation-anchor.v1\x00"
    )
    assert authority._SOURCE_CREATION_SIGNATURE_DOMAIN == ANCHOR_SIGNATURE_DOMAIN
    assert anchor.anchor_sha256 == source_creation_anchor_v1_sha256(anchor)
    assert anchor.anchor_id == "opsca1_" + anchor.anchor_sha256[:24]
    assert anchor.source_receipt_v5_sha256 == anchor.source_receipt_v5.receipt_sha256
    assert anchor.private_source_ordinal == anchor.source_receipt_v5.private_source_ordinal
    verify_source_creation_anchor_v1(anchor, verification_keys=case.anchor_verification_keys)
    for field in (
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ):
        assert getattr(anchor, field) is False
    assert repr(anchor) == "SourceCreationAnchorV1(redacted=True)"


@pytest.mark.parametrize(
    "field",
    (
        "source_receipt_v5_sha256",
        "anchor_sha256",
    ),
)
def test_anchor_identity_mutations_reject_at_construction(field: str) -> None:
    raw = creation_anchor(owner_private_v2_case(), 1).model_dump(mode="python")
    raw[field] = "0" * 64
    with pytest.raises((ValidationError, ValueError)):
        SourceCreationAnchorV1.model_validate(raw)


@pytest.mark.parametrize(
    "field",
    (
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ),
)
def test_anchor_authority_mutations_reject(field: str) -> None:
    raw = creation_anchor(owner_private_v2_case(), 1).model_dump(mode="python")
    raw[field] = True
    with pytest.raises(ValidationError):
        SourceCreationAnchorV1.model_validate(raw)


@pytest.mark.parametrize("shape", ("signature", "domain", "key", "subclass"))
def test_anchor_verifier_rejects_cryptographic_substitution_opaquely(shape: str) -> None:
    case = owner_private_source_authority_case()
    anchor = creation_anchor(case.predecessor, 1)
    keys = case.anchor_verification_keys
    candidate: SourceCreationAnchorV1 = anchor
    if shape == "signature":
        candidate = anchor.model_copy(update={"signature_ed25519": "0" * 128})
    elif shape == "domain":
        candidate = anchor.model_copy(
            update={
                "signature_ed25519": sign_digest(
                    b"wrong.anchor.domain\x00",
                    anchor.anchor_sha256,
                    private_key=ANCHOR_PRIVATE_KEY,
                )
            }
        )
    elif shape == "key":
        keys = {ANCHOR_KEY_ID: bytes(range(32))}
    else:

        class AnchorSubclass(SourceCreationAnchorV1):
            pass

        candidate = AnchorSubclass.model_validate(anchor.model_dump(mode="python"))
    with pytest.raises(SourceCreationAnchorV1Rejected) as raised:
        verify_source_creation_anchor_v1(candidate, verification_keys=keys)
    assert str(raised.value) == "owner-private source creation anchor rejected"
    assert raised.value.__cause__ is None
    assert anchor.anchor_sha256 not in repr(raised.value)


@pytest.mark.parametrize("mutation", ("nested_receipt_hash", "ordinal", "authority"))
def test_anchor_verifier_reparses_model_copy_bypass(mutation: str) -> None:
    case = owner_private_source_authority_case()
    anchor = creation_anchor(case.predecessor, 1)
    updates: dict[str, object] = {}
    if mutation == "nested_receipt_hash":
        forged_receipt = anchor.source_receipt_v5.model_copy(update={"receipt_sha256": "0" * 64})
        updates.update(
            source_receipt_v5=forged_receipt,
            source_receipt_v5_sha256="0" * 64,
        )
    elif mutation == "ordinal":
        updates["private_source_ordinal"] = 2
    else:
        updates["confers_execution_authority"] = True
    forged = anchor.model_copy(update=updates)
    digest = source_creation_anchor_v1_sha256(forged)
    forged = forged.model_copy(
        update={
            "anchor_id": "opsca1_" + digest[:24],
            "anchor_sha256": digest,
            "signature_ed25519": sign_digest(
                ANCHOR_SIGNATURE_DOMAIN, digest, private_key=ANCHOR_PRIVATE_KEY
            ),
        }
    )
    with pytest.raises(SourceCreationAnchorV1Rejected):
        verify_source_creation_anchor_v1(forged, verification_keys=case.anchor_verification_keys)


def test_anchor_verifier_closes_malicious_key_mapping_opaquely() -> None:
    class MaliciousKeys(Mapping[str, bytes]):
        def __getitem__(self, key: str) -> bytes:
            raise RuntimeError("mapping-secret-must-not-escape")

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 0

    anchor = creation_anchor(owner_private_v2_case(), 1)
    with pytest.raises(SourceCreationAnchorV1Rejected) as raised:
        verify_source_creation_anchor_v1(anchor, verification_keys=MaliciousKeys())
    assert raised.value.__cause__ is None
    assert "mapping-secret" not in str(raised.value)


def test_anchor_parser_round_trip_duplicate_key_bound_and_opaque_error() -> None:
    anchor = creation_anchor(owner_private_v2_case(), 1)
    assert parse_source_creation_anchor_v1_json(anchor.model_dump_json().encode()) == anchor
    duplicate = b'{"schema_version":1,"schema_version":1}'
    for raw in (duplicate, b"{}", b"x" * 1_000_001):
        with pytest.raises(SourceCreationAnchorV1Rejected) as raised:
            parse_source_creation_anchor_v1_json(raw)
        assert raised.value.__cause__ is None
        assert raw[:32].decode("utf-8", errors="ignore") not in str(raised.value)


def test_single_source_bundle_complete_exact_joins_and_validation() -> None:
    case = owner_private_source_authority_case()
    bundle = encrypted_source_bundle(case.predecessor)
    assert bundle.bundle_sha256 == owner_private_encrypted_source_bundle_v1_sha256(bundle)
    assert bundle.bundle_id == "opsb1_" + bundle.bundle_sha256[:24]
    assert bundle.envelope_v2.request_core == bundle.request_core_v2
    assert bundle.receipt_v5_roster == case.predecessor.receipts
    assert len(bundle.exact_sources) == len(bundle.creation_anchors) == 1
    for source in bundle.exact_sources:
        for field in (
            "confers_execution_authority",
            "confers_checkpoint_authority",
            "confers_sink_authority",
            "confers_transition_authority",
            "production_consumer_enabled",
        ):
            assert getattr(source, field) is False
    assert bundle.private_input_commitment_sha256 == (
        case.predecessor.receipts[0].private_input_commitment_sha256
    )
    validate_owner_private_encrypted_source_bundle_v1(
        bundle, anchor_verification_keys=case.anchor_verification_keys
    )
    assert repr(bundle) == "OwnerPrivateEncryptedSourceBundleV1(redacted=True)"


def test_multi_source_bundle_preserves_order_and_exact_pairing() -> None:
    case = owner_private_v2_multi_case()
    bundle = encrypted_source_bundle(case)
    assert tuple(row.ordinal for row in bundle.exact_sources) == (1, 2)
    assert tuple(row.private_source_ordinal for row in bundle.receipt_v5_roster) == (1, 2)
    assert tuple(row.private_source_ordinal for row in bundle.creation_anchors) == (1, 2)
    validate_owner_private_encrypted_source_bundle_v1(
        bundle,
        anchor_verification_keys={
            ANCHOR_KEY_ID: owner_private_source_authority_case().anchor_verification_keys[
                ANCHOR_KEY_ID
            ]
        },
    )


def test_planner_bundle_is_exactly_empty_and_nonconferring() -> None:
    bundle = encrypted_source_bundle(owner_private_v2_planner_case())
    assert bundle.receipt_v5_roster == ()
    assert bundle.exact_sources == ()
    assert bundle.creation_anchors == ()
    assert bundle.private_input_commitment_sha256 is None
    assert bundle.private_input_bytes == 0
    validate_owner_private_encrypted_source_bundle_v1(bundle, anchor_verification_keys={})


@pytest.mark.parametrize(
    "mutation",
    (
        "receipt_order",
        "source_order",
        "anchor_order",
        "source_digest",
        "source_bytes",
        "commitment",
        "total_bytes",
        "required_until",
    ),
)
def test_bundle_member_roster_commitment_and_horizon_mutations_reject(
    mutation: str,
) -> None:
    raw = encrypted_source_bundle(owner_private_v2_multi_case()).model_dump(mode="python")
    if mutation == "receipt_order":
        raw["receipt_v5_roster"] = tuple(reversed(raw["receipt_v5_roster"]))
    elif mutation == "source_order":
        raw["exact_sources"] = tuple(reversed(raw["exact_sources"]))
    elif mutation == "anchor_order":
        raw["creation_anchors"] = tuple(reversed(raw["creation_anchors"]))
    elif mutation == "source_digest":
        raw["exact_sources"][0]["exact_source_sha256"] = "0" * 64
    elif mutation == "source_bytes":
        raw["exact_sources"][0]["exact_source_bytes"] += 1
    elif mutation == "commitment":
        raw["private_input_commitment_sha256"] = "0" * 64
    elif mutation == "total_bytes":
        raw["private_input_bytes"] += 1
    else:
        raw["required_until_ms"] -= 1
    with pytest.raises((ValidationError, ValueError)):
        _rebundle(raw)


@pytest.mark.parametrize(
    "field",
    (
        "envelope_v2_sha256",
        "request_core_v2_sha256",
        "private_source_ordinal",
        "exact_source_sha256",
        "exact_source_bytes",
    ),
)
def test_validly_resigned_anchor_predecessor_substitution_rejects_bundle(
    field: str,
) -> None:
    raw = encrypted_source_bundle().model_dump(mode="python")
    anchor_raw = dict(raw["creation_anchors"][0])
    if field.endswith("sha256"):
        anchor_raw[field] = "0" * 64
    else:
        anchor_raw[field] += 1
    with pytest.raises((ValidationError, ValueError)):
        raw["creation_anchors"] = (_resign_anchor(anchor_raw).model_dump(mode="python"),)
        _rebundle(raw)


def test_anchor_issued_after_bundle_creation_or_required_horizon_rejects() -> None:
    predecessor = owner_private_v2_case()
    for issued_at_ms in (2_001, predecessor.core.required_until_ms + 1):
        raw = encrypted_source_bundle(predecessor).model_dump(mode="python")
        raw["creation_anchors"] = (
            creation_anchor(predecessor, 1, issued_at_ms=issued_at_ms).model_dump(mode="python"),
        )
        with pytest.raises((ValidationError, ValueError)):
            _rebundle(raw)


@pytest.mark.parametrize(
    "field",
    (
        "swarm_plan_sha256",
        "stage_plan_sha256",
        "route_plan_sha256",
        "publication_manifest_sha256",
        "provider_capability_v2_sha256",
        "source_evidence_v1_request_sha256",
        "provider_id",
        "model_id",
        "route_key",
        "api_mode",
        "processing_region",
        "endpoint_origin_sha256",
        "account_project_scope_sha256",
        "adapter_contract_sha256",
        "dispatch_config_sha256",
        "max_output_bytes",
        "source_byte_start",
        "source_byte_end",
        "source_representation_bytes",
    ),
)
def test_valid_rehashed_receipt_lineage_substitution_against_core_rejects(
    field: str,
) -> None:
    with pytest.raises((ValidationError, ValueError)):
        _valid_shared_lineage_substitution(encrypted_source_bundle(), field)


def test_bundle_validator_rechecks_external_anchor_signature() -> None:
    bundle = encrypted_source_bundle()
    forged_anchor = bundle.creation_anchors[0].model_copy(update={"signature_ed25519": "0" * 128})
    forged = bundle.model_copy(update={"creation_anchors": (forged_anchor,)})
    with pytest.raises(OwnerPrivateSourceBundleV1Rejected) as raised:
        validate_owner_private_encrypted_source_bundle_v1(
            forged,
            anchor_verification_keys=(
                owner_private_source_authority_case().anchor_verification_keys
            ),
        )
    assert raised.value.__cause__ is None
    assert "0" * 64 not in str(raised.value)


def test_vault_contract_exact_aes_aad_and_closed_authority() -> None:
    contract = build_owner_private_source_vault_contract_v1()
    assert authority._SOURCE_AEAD_DOMAIN == (
        b"antiek.midnight-oil.owner-private-source-aead.v1\x00"
    )
    assert contract.contract_sha256 == OWNER_PRIVATE_SOURCE_VAULT_CONTRACT_V1_SHA256
    assert contract.aead_suite == "aes-256-gcm"
    assert (contract.key_bytes, contract.nonce_bytes, contract.tag_bytes) == (32, 12, 16)
    assert contract.aad_fields == (
        "schema_version",
        "opaque_source_bundle_id",
        "owner_path_discriminator",
        "categorical_state",
        "aead_suite",
        "key_version",
        "nonce_length",
        "ciphertext_schema",
        "ciphertext_type",
        "ciphertext_length",
        "row_revision",
    )
    forbidden = {
        "owner_id",
        "owner_scope_sha256",
        "receipt_id",
        "receipt_sha256",
        "source_sha256",
        "private_input_commitment_sha256",
        "operation_id",
        "job_id",
        "stage_key",
    }
    assert forbidden.isdisjoint(contract.aad_fields)
    assert contract.generic_decrypt is False
    for field in (
        "confers_execution_authority",
        "confers_checkpoint_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ):
        assert getattr(contract, field) is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("aad_fields", ("receipt_sha256",)),
        ("generic_decrypt", True),
        ("confers_execution_authority", True),
        ("confers_checkpoint_authority", True),
        ("confers_sink_authority", True),
        ("confers_transition_authority", True),
        ("production_consumer_enabled", True),
    ),
)
def test_vault_contract_aad_or_authority_mutations_reject(field: str, value: object) -> None:
    raw = build_owner_private_source_vault_contract_v1().model_dump(mode="python")
    raw[field] = value
    with pytest.raises((ValidationError, ValueError)):
        OwnerPrivateSourceVaultContractV1.model_validate(raw)


def test_semantic_source_attestation_and_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        private_source_authority_module_source_sha256()
    ) == PRIVATE_SOURCE_AUTHORITY_MODULE_SOURCE_SHA256
    require_private_source_authority_module_source()
    original = Path.read_bytes

    def drift(path: Path) -> bytes:
        return original(path) + b"\nSOURCE_AUTHORITY_DRIFT = True\n"

    monkeypatch.setattr(Path, "read_bytes", drift)
    with pytest.raises(RuntimeError, match="implementation conflicts"):
        require_private_source_authority_module_source()


def test_production_module_has_verifier_but_no_anchor_issuer_or_aead_runtime() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    arguments = {
        argument.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
    }
    assert "Ed25519PublicKey" in imported
    assert "Ed25519PrivateKey" not in imported
    assert "AESGCM" not in imported
    assert "signing_key" not in arguments
    assert not {
        "signed_source_creation_anchor_v1",
        "build_source_creation_anchor_v1",
        "create_source_creation_anchor_v1",
        "encrypt_source_bundle_v1",
        "decrypt_source_bundle_v1",
    }.intersection(functions)


def _imports_module(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == MODULE_NAME for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == MODULE_NAME or (node.level and module == "private_source_authority"):
                return True
            if (
                node.level
                and not module
                and any(alias.name == "private_source_authority" for alias in node.names)
            ):
                return True
            if module == "substrate.midnight_oil" and any(
                alias.name == "private_source_authority" for alias in node.names
            ):
                return True
        if isinstance(node, ast.Call) and node.args:
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and argument.value == MODULE_NAME:
                return True
    return False


def test_production_consumers_packages_and_routes_quarantine_authority_module() -> None:
    excluded = {
        MODULE_PATH,
    }
    violations = [
        path.relative_to(ROOT)
        for path in ROOT.rglob("*.py")
        if path not in excluded
        and "tests" not in path.relative_to(ROOT).parts
        and not {".git", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"}.intersection(
            path.relative_to(ROOT).parts
        )
        if _imports_module(path.read_text(encoding="utf-8"))
    ]
    assert violations == []
    package = ROOT / "substrate/midnight_oil/__init__.py"
    package_text = package.read_text(encoding="utf-8") if package.is_file() else ""
    assert "private_source_authority" not in package_text
    for path in (
        ROOT / "interfaces/research/api/app.py",
        ROOT / "substrate/midnight_oil/worker_cli.py",
        ROOT / "substrate/cli/__main__.py",
    ):
        assert "private_source_authority" not in path.read_text(encoding="utf-8")


def test_quarantine_scanner_has_direct_relative_and_dynamic_teeth() -> None:
    assert _imports_module(f"import {MODULE_NAME}\n")
    assert _imports_module("from .private_source_authority import SourceCreationAnchorV1\n")
    assert _imports_module("from . import private_source_authority\n")
    assert _imports_module(
        "from substrate.midnight_oil import private_source_authority as authority\n"
    )
    assert _imports_module(f"__import__({json.dumps(MODULE_NAME)})\n")
    assert _imports_module(
        f"from importlib import import_module as load\nload({json.dumps(MODULE_NAME)})\n"
    )


def test_public_surface_is_exact_and_contains_no_creation_or_decrypt_capability() -> None:
    assert authority.__all__ == [
        "OWNER_PRIVATE_SOURCE_VAULT_CONTRACT_V1_SHA256",
        "PRIVATE_SOURCE_AUTHORITY_MODULE_SOURCE_SHA256",
        "OwnerPrivateEncryptedSourceBundleV1",
        "OwnerPrivateExactSourceV1",
        "OwnerPrivateSourceBundleV1Rejected",
        "OwnerPrivateSourceVaultContractV1",
        "SourceCreationAnchorV1",
        "SourceCreationAnchorV1Rejected",
        "build_owner_private_source_vault_contract_v1",
        "owner_private_encrypted_source_bundle_v1_sha256",
        "parse_source_creation_anchor_v1_json",
        "private_source_authority_module_source_sha256",
        "require_private_source_authority_module_source",
        "source_creation_anchor_v1_sha256",
        "validate_owner_private_encrypted_source_bundle_v1",
        "verify_source_creation_anchor_v1",
    ]
    forbidden_prefixes = ("sign_", "signed_", "issue_", "encrypt_", "decrypt_", "resolve_")
    assert not any(name.lower().startswith(forbidden_prefixes) for name in authority.__all__)
