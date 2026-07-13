from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from substrate.engagement_spine.store import InMemoryEngagementStore
from substrate.midnight_oil.substack_authorization import (
    MAX_SUBSTACK_AUTHORIZATION_LIFETIME_MS,
    SUBSTACK_PRIVATE_USE_POLICY_SHA256,
    SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
    SubstackExcerptReceipt,
    SubstackUseAuthorization,
    canonical_substack_post,
    create_substack_excerpt_receipt,
    owner_scope_sha256,
    parse_substack_authorization_json,
    require_active_stored_substack_authorization,
    require_active_stored_substack_excerpt,
    revoke_substack_authorization,
    signed_substack_authorization,
    store_substack_authorization,
    store_substack_excerpt_receipt,
    substack_excerpt_receipt_sha256,
    verify_substack_authorization,
)

_KEY = b"substack-authorization-test-key!"
_OWNER = "alice"
_EXTERNAL_ID = "antiek.substack.com/p/knowledge-graphs"
_REF_ID = "sref_" + hashlib.sha256(f"substack:substack:{_EXTERNAL_ID}".encode()).hexdigest()[:16]


def _authorization(
    *,
    selection_text: str = "A useful highlighted claim.",
    source_start: int = 100,
    source_bytes: int = 10_000,
    **changes: Any,
) -> SubstackUseAuthorization:
    encoded = selection_text.encode("utf-8")
    material: dict[str, object] = {
        "schema_version": 1,
        "authorization_id": "sua_" + "1" * 24,
        "owner_scope_sha256": owner_scope_sha256(_OWNER),
        "collective_unit_id": "cunit_" + "a" * 24,
        "collective_preview_sha256": "2" * 64,
        "ref_id": _REF_ID,
        "canonical_url": f"https://{_EXTERNAL_ID}",
        "external_id": _EXTERNAL_ID,
        "origin": "owner_selected_excerpt_v1",
        "use_scope": "owner_private_model_context",
        "owner_affirms_provider_processing": True,
        "provider_processing_scope": "requires_compatible_provider_capability",
        "provider_constraints_id": "antiek-substack-provider-constraints-v1",
        "provider_constraints_sha256": SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
        "redistribution_authorized": False,
        "training_authorized": False,
        "publication_authorized": False,
        "one_excerpt_only": True,
        "max_excerpt_bytes": 8_192,
        "representation_evidence": "owner_attestation_unverified",
        "source_representation_sha256": "5" * 64,
        "source_representation_bytes": source_bytes,
        "source_byte_start": source_start,
        "source_byte_end": source_start + len(encoded),
        "excerpt_sha256": hashlib.sha256(encoded).hexdigest(),
        "excerpt_bytes": len(encoded),
        "partial_excerpt_affirmed": True,
        "rights_policy_id": "antiek-substack-private-use-v1",
        "rights_policy_sha256": SUBSTACK_PRIVATE_USE_POLICY_SHA256,
        "issued_at_ms": 1_000,
        "not_before_ms": 1_000,
        "expires_at_ms": 20_000,
        "nonce": "4" * 32,
    }
    material.update(changes)
    return signed_substack_authorization(material, key_id="substack-test-key", signing_key=_KEY)


def _receipt(
    authorization: SubstackUseAuthorization | None = None,
    *,
    text: str = "A useful highlighted claim.",
    start: int = 100,
) -> SubstackExcerptReceipt:
    return create_substack_excerpt_receipt(
        authorization or _authorization(selection_text=text, source_start=start),
        verification_keys={"substack-test-key": _KEY},
        owner_id=_OWNER,
        now_ms=2_000,
        source_representation_sha256="5" * 64,
        source_representation_bytes=10_000,
        source_byte_start=start,
        text=text,
    )


def test_signed_authorization_and_content_addressed_unicode_receipt() -> None:
    authorization = _authorization(selection_text="Café → graph")
    verify_substack_authorization(
        authorization,
        verification_keys={"substack-test-key": _KEY},
        owner_id=_OWNER,
        now_ms=2_000,
        collective_unit_id="cunit_" + "a" * 24,
        collective_preview_sha256="2" * 64,
        ref_id=_REF_ID,
    )
    receipt = _receipt(authorization, text="Café → graph")
    assert receipt.excerpt_bytes == len("Café → graph".encode())
    assert receipt.source_byte_end - receipt.source_byte_start == receipt.excerpt_bytes
    assert receipt.receipt_id == "suer_" + receipt.receipt_sha256[:24]
    assert receipt.content_class == "personal_reading"
    assert receipt.rights_tier == "not_applicable"
    with pytest.raises(ValueError, match="signed commitment"):
        _receipt(authorization, text="A second selection")


@pytest.mark.parametrize(
    ("url", "external_id"),
    [
        ("http://antiek.substack.com/p/post", "antiek.substack.com/p/post"),
        ("https://substack.com/p/post", "substack.com/p/post"),
        ("https://a.b.substack.com/p/post", "a.b.substack.com/p/post"),
        ("https://antiek.substack.com/", "antiek.substack.com/"),
        ("https://antiek.substack.com/p/post/", "antiek.substack.com/p/post/"),
        ("https://antiek.substack.com/p/Post", "antiek.substack.com/p/Post"),
        ("https://antiek.substack.com/p/post?q=1", "antiek.substack.com/p/post"),
        ("https://antiek.substack.com:444/p/post", "antiek.substack.com/p/post"),
        ("https://user@antiek.substack.com/p/post", "antiek.substack.com/p/post"),
        ("https://example.com/p/post", "example.com/p/post"),
    ],
)
def test_post_identity_rejects_generic_or_ambiguous_urls(url: str, external_id: str) -> None:
    with pytest.raises(ValueError, match="Substack"):
        canonical_substack_post(url, external_id)


def test_signature_tamper_unknown_key_owner_and_bindings_fail_closed() -> None:
    authorization = _authorization()
    raw = authorization.model_dump(mode="json")
    raw["signature_sha256"] = "0" * 64
    tampered = SubstackUseAuthorization.model_validate(raw)
    with pytest.raises(ValueError, match="signature"):
        verify_substack_authorization(
            tampered,
            verification_keys={"substack-test-key": _KEY},
            owner_id=_OWNER,
            now_ms=2_000,
        )
    with pytest.raises(ValueError, match="unknown"):
        verify_substack_authorization(
            authorization, verification_keys={}, owner_id=_OWNER, now_ms=2_000
        )
    with pytest.raises(ValueError, match="unavailable"):
        verify_substack_authorization(
            authorization,
            verification_keys={"substack-test-key": _KEY},
            owner_id="mallory",
            now_ms=2_000,
        )
    for binding in (
        {"collective_unit_id": "other"},
        {"collective_preview_sha256": "9" * 64},
        {"ref_id": "sref_" + "9" * 16},
    ):
        with pytest.raises(ValueError, match="binding"):
            verify_substack_authorization(
                authorization,
                verification_keys={"substack-test-key": _KEY},
                owner_id=_OWNER,
                now_ms=2_000,
                **binding,
            )


def test_hash_tamper_unknown_fields_and_noncanonical_ref_fail_closed() -> None:
    raw = _authorization().model_dump(mode="json")
    raw["max_excerpt_bytes"] = 7_000
    with pytest.raises(ValidationError, match="hash conflicts"):
        SubstackUseAuthorization.model_validate(raw)
    raw = _authorization().model_dump(mode="json")
    raw["ambient_fetch"] = True
    with pytest.raises(ValidationError, match="Extra inputs"):
        SubstackUseAuthorization.model_validate(raw)
    with pytest.raises(ValidationError, match="ref id conflicts"):
        _authorization(ref_id="sref_" + "f" * 16)


def test_serialized_authorization_rejects_duplicate_json_keys() -> None:
    payload = _authorization().model_dump_json().encode()
    duplicate = payload.replace(
        b'"owner_scope_sha256":',
        b'"owner_scope_sha256":"' + b"0" * 64 + b'","owner_scope_sha256":',
        1,
    )
    with pytest.raises(ValueError, match="duplicate JSON keys"):
        parse_substack_authorization_json(duplicate)
    assert parse_substack_authorization_json(payload) == _authorization()


def test_validity_interval_horizon_and_strict_policy_boole() -> None:
    authorization = _authorization()
    for now_ms in (999, 20_000):
        with pytest.raises(ValueError, match="not active"):
            verify_substack_authorization(
                authorization,
                verification_keys={"substack-test-key": _KEY},
                owner_id=_OWNER,
                now_ms=now_ms,
            )
    with pytest.raises(ValidationError, match="lifetime"):
        _authorization(expires_at_ms=1_000 + MAX_SUBSTACK_AUTHORIZATION_LIFETIME_MS + 1)
    with pytest.raises(ValueError, match="required horizon"):
        verify_substack_authorization(
            authorization,
            verification_keys={"substack-test-key": _KEY},
            owner_id=_OWNER,
            now_ms=2_000,
            required_until_ms=20_000,
        )
    with pytest.raises(ValueError, match="now_ms is invalid"):
        verify_substack_authorization(
            authorization,
            verification_keys={"substack-test-key": _KEY},
            owner_id=_OWNER,
            now_ms=True,
        )
    with pytest.raises(ValidationError):
        _authorization(owner_affirms_provider_processing=1)
    with pytest.raises(ValidationError):
        _authorization(redistribution_authorized=True)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "decomposed cafe\u0301",
        "bad\rline",
        "nul\x00byte",
        "zero\u200bwidth",
        "<p>markup</p>",
        "<script>x</script>",
        "![tracker](https://example.com/pixel)",
        "![tracker](//evil.example/pixel)",
        "![tracker](<https://evil.example/pixel>)",
        "![tracker][x]\n[x]: https://evil.example/pixel",
    ],
)
def test_receipt_rejects_empty_noncanonical_control_and_active_markup(text: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        _receipt(text=text)


def test_receipt_rejects_oversize_and_range_or_content_tamper() -> None:
    with pytest.raises(ValidationError, match="commitment conflicts"):
        _authorization(selection_text="x" * 257, max_excerpt_bytes=256)
    receipt = _receipt()
    for field, value in (
        ("source_byte_end", receipt.source_byte_end + 1),
        ("text", receipt.text + "x"),
        ("receipt_id", "suer_" + "0" * 24),
    ):
        raw = receipt.model_dump(mode="json")
        raw[field] = value
        with pytest.raises(ValidationError):
            SubstackExcerptReceipt.model_validate(raw)
    with pytest.raises(ValidationError, match="commitment conflicts"):
        _authorization(selection_text="complete", source_start=0, source_bytes=8)


def test_owner_private_store_is_idempotent_and_revocation_is_live() -> None:
    store = InMemoryEngagementStore()
    authorization = _authorization()
    first = store_substack_authorization(
        store,
        owner_id=_OWNER,
        authorization=authorization,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_000,
    )
    second = store_substack_authorization(
        store,
        owner_id=_OWNER,
        authorization=authorization,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_000,
    )
    assert first == second
    assert (
        require_active_stored_substack_authorization(
            store,
            owner_id=_OWNER,
            authorization_id=authorization.authorization_id,
            expected_authorization_sha256=authorization.authorization_sha256,
            verification_keys={"substack-test-key": _KEY},
            now_ms=2_000,
        )
        == authorization
    )
    revoked = revoke_substack_authorization(
        store,
        owner_id=_OWNER,
        authorization_id=authorization.authorization_id,
        expected_authorization_sha256=authorization.authorization_sha256,
        clock_ms=lambda: 3_000,
    )
    assert revoked["state"] == "revoked"
    with pytest.raises(ValueError, match="unavailable"):
        require_active_stored_substack_authorization(
            store,
            owner_id=_OWNER,
            authorization_id=authorization.authorization_id,
            expected_authorization_sha256=authorization.authorization_sha256,
            verification_keys={"substack-test-key": _KEY},
            now_ms=3_001,
        )
    replayed = revoke_substack_authorization(
        store,
        owner_id=_OWNER,
        authorization_id=authorization.authorization_id,
        expected_authorization_sha256=authorization.authorization_sha256,
        clock_ms=lambda: 3_001,
    )
    assert replayed == revoked


def test_receipt_store_is_owner_scoped_and_immutable() -> None:
    store = InMemoryEngagementStore()
    authorization = _authorization()
    store_substack_authorization(
        store,
        owner_id=_OWNER,
        authorization=authorization,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_000,
    )
    receipt = _receipt(authorization)
    store_args = {
        "owner_id": _OWNER,
        "receipt": receipt,
        "authorization_id": authorization.authorization_id,
        "verification_keys": {"substack-test-key": _KEY},
        "now_ms": 2_001,
    }
    first = store_substack_excerpt_receipt(store, **store_args)
    second = store_substack_excerpt_receipt(store, **store_args)
    assert first == second
    later_receipt = create_substack_excerpt_receipt(
        authorization,
        verification_keys={"substack-test-key": _KEY},
        owner_id=_OWNER,
        now_ms=2_002,
        source_representation_sha256=authorization.source_representation_sha256,
        source_representation_bytes=authorization.source_representation_bytes,
        source_byte_start=authorization.source_byte_start,
        text="A useful highlighted claim.",
    )
    assert later_receipt == receipt
    assert (
        store_substack_excerpt_receipt(
            store,
            **{**store_args, "receipt": later_receipt, "now_ms": 2_002},
        )
        == first
    )
    active, loaded = require_active_stored_substack_excerpt(
        store,
        owner_id=_OWNER,
        authorization_id=authorization.authorization_id,
        expected_authorization_sha256=authorization.authorization_sha256,
        receipt_id=receipt.receipt_id,
        expected_receipt_sha256=receipt.receipt_sha256,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_001,
    )
    assert (active, loaded) == (authorization, receipt)
    revoke_substack_authorization(
        store,
        owner_id=_OWNER,
        authorization_id=authorization.authorization_id,
        expected_authorization_sha256=authorization.authorization_sha256,
        clock_ms=lambda: 3_000,
    )
    with pytest.raises(ValueError, match="authorization is unavailable"):
        require_active_stored_substack_excerpt(
            store,
            owner_id=_OWNER,
            authorization_id=authorization.authorization_id,
            expected_authorization_sha256=authorization.authorization_sha256,
            receipt_id=receipt.receipt_id,
            expected_receipt_sha256=receipt.receipt_sha256,
            verification_keys={"substack-test-key": _KEY},
            now_ms=3_001,
        )
    with pytest.raises(ValueError, match="unavailable"):
        store_substack_excerpt_receipt(
            store,
            **{**store_args, "owner_id": "mallory", "now_ms": 3_001},
        )


def test_receipt_cannot_be_stored_without_live_durable_authority() -> None:
    authorization = _authorization()
    receipt = _receipt(authorization)
    with pytest.raises(ValueError, match="authorization is unavailable"):
        store_substack_excerpt_receipt(
            InMemoryEngagementStore(),
            owner_id=_OWNER,
            receipt=receipt,
            authorization_id=authorization.authorization_id,
            verification_keys={"substack-test-key": _KEY},
            now_ms=2_000,
        )


def test_crash_after_one_receipt_claim_repairs_with_fresh_runtime() -> None:
    store = InMemoryEngagementStore()
    authorization = _authorization()
    store_substack_authorization(
        store,
        owner_id=_OWNER,
        authorization=authorization,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_000,
    )
    first = _receipt(authorization)

    original_mutate = store.mutate_owned_document
    auth_logical_id = "suauth_" + authorization.authorization_id.removeprefix("sua_")
    armed = True

    def faulting_mutate(logical_id: str, owner_id: str, mutation: Any) -> dict[str, Any]:
        nonlocal armed
        result = original_mutate(logical_id, owner_id, mutation)
        if armed and logical_id == auth_logical_id:
            armed = False
            raise RuntimeError("simulated crash after authorization CAS")
        return result

    store.mutate_owned_document = faulting_mutate  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="simulated crash"):
        store_substack_excerpt_receipt(
            store,
            owner_id=_OWNER,
            receipt=first,
            authorization_id=authorization.authorization_id,
            verification_keys={"substack-test-key": _KEY},
            now_ms=2_000,
        )
    store.mutate_owned_document = original_mutate  # type: ignore[method-assign]
    repaired = create_substack_excerpt_receipt(
        authorization,
        verification_keys={"substack-test-key": _KEY},
        owner_id=_OWNER,
        now_ms=2_500,
        source_representation_sha256=authorization.source_representation_sha256,
        source_representation_bytes=authorization.source_representation_bytes,
        source_byte_start=authorization.source_byte_start,
        text="A useful highlighted claim.",
    )
    assert repaired == first
    store_substack_excerpt_receipt(
        store,
        owner_id=_OWNER,
        receipt=repaired,
        authorization_id=authorization.authorization_id,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_500,
    )
    _, loaded = require_active_stored_substack_excerpt(
        store,
        owner_id=_OWNER,
        authorization_id=authorization.authorization_id,
        expected_authorization_sha256=authorization.authorization_sha256,
        receipt_id=repaired.receipt_id,
        expected_receipt_sha256=repaired.receipt_sha256,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_501,
    )
    assert loaded == repaired


def test_final_reader_barrier_observes_concurrent_revocation() -> None:
    store = InMemoryEngagementStore()
    authorization = _authorization()
    store_substack_authorization(
        store,
        owner_id=_OWNER,
        authorization=authorization,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_000,
    )
    receipt = _receipt(authorization)
    store_substack_excerpt_receipt(
        store,
        owner_id=_OWNER,
        receipt=receipt,
        authorization_id=authorization.authorization_id,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_000,
    )
    original_mutate = store.mutate_owned_document
    auth_logical_id = "suauth_" + authorization.authorization_id.removeprefix("sua_")
    raced = False

    def racing_mutate(logical_id: str, owner_id: str, mutation: Any) -> dict[str, Any]:
        nonlocal raced
        if logical_id == auth_logical_id and not raced:
            raced = True

            def revoke(current: dict[str, Any] | None) -> dict[str, Any]:
                assert current is not None
                return {**current, "state": "revoked", "revoked_at_ms": 2_001}

            original_mutate(logical_id, owner_id, revoke)
        return original_mutate(logical_id, owner_id, mutation)

    store.mutate_owned_document = racing_mutate  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="authorization is unavailable"):
        require_active_stored_substack_excerpt(
            store,
            owner_id=_OWNER,
            authorization_id=authorization.authorization_id,
            expected_authorization_sha256=authorization.authorization_sha256,
            receipt_id=receipt.receipt_id,
            expected_receipt_sha256=receipt.receipt_sha256,
            verification_keys={"substack-test-key": _KEY},
            now_ms=2_002,
        )


def test_store_rejects_rehashed_receipt_with_unbound_timestamp() -> None:
    store = InMemoryEngagementStore()
    authorization = _authorization()
    store_substack_authorization(
        store,
        owner_id=_OWNER,
        authorization=authorization,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_000,
    )
    raw = _receipt(authorization).model_dump(mode="json")
    raw["injected_at_ms"] = authorization.expires_at_ms + 1
    digest = substack_excerpt_receipt_sha256(raw)
    raw.update(receipt_sha256=digest, receipt_id="suer_" + digest[:24])
    forged = SubstackExcerptReceipt.model_validate(raw)
    with pytest.raises(ValueError, match="binding conflicts"):
        store_substack_excerpt_receipt(
            store,
            owner_id=_OWNER,
            receipt=forged,
            authorization_id=authorization.authorization_id,
            verification_keys={"substack-test-key": _KEY},
            now_ms=2_001,
        )


def test_durable_inner_authorization_and_receipt_substitution_fail_closed() -> None:
    store = InMemoryEngagementStore()
    authorization = _authorization()
    store_substack_authorization(
        store,
        owner_id=_OWNER,
        authorization=authorization,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_000,
    )
    logical_auth = "suauth_" + authorization.authorization_id.removeprefix("sua_")
    other = _authorization(authorization_id="sua_" + "6" * 24, nonce="7" * 32)

    def replace_inner_auth(current: dict[str, Any] | None) -> dict[str, Any]:
        assert current is not None
        return {**current, "authorization": other.model_dump(mode="json")}

    store.mutate_owned_document(logical_auth, _OWNER, replace_inner_auth)
    with pytest.raises(ValueError, match="durable binding conflicts"):
        require_active_stored_substack_authorization(
            store,
            owner_id=_OWNER,
            authorization_id=authorization.authorization_id,
            expected_authorization_sha256=authorization.authorization_sha256,
            verification_keys={"substack-test-key": _KEY},
            now_ms=2_001,
        )

    clean_store = InMemoryEngagementStore()
    store_substack_authorization(
        clean_store,
        owner_id=_OWNER,
        authorization=authorization,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_000,
    )
    receipt = _receipt(authorization)
    store_substack_excerpt_receipt(
        clean_store,
        owner_id=_OWNER,
        receipt=receipt,
        authorization_id=authorization.authorization_id,
        verification_keys={"substack-test-key": _KEY},
        now_ms=2_000,
    )
    other_raw = receipt.model_dump(mode="json")
    other_raw["injected_at_ms"] = authorization.not_before_ms + 1
    other_digest = substack_excerpt_receipt_sha256(other_raw)
    other_raw["receipt_sha256"] = other_digest
    other_raw["receipt_id"] = "suer_" + other_digest[:24]
    other_receipt = SubstackExcerptReceipt.model_validate(other_raw)
    logical_receipt = "suexcerpt_" + receipt.receipt_id.removeprefix("suer_")

    def replace_inner_receipt(current: dict[str, Any] | None) -> dict[str, Any]:
        assert current is not None
        return {**current, "receipt": other_receipt.model_dump(mode="json")}

    clean_store.mutate_owned_document(logical_receipt, _OWNER, replace_inner_receipt)
    with pytest.raises(ValueError, match="durable binding conflicts"):
        require_active_stored_substack_excerpt(
            clean_store,
            owner_id=_OWNER,
            authorization_id=authorization.authorization_id,
            expected_authorization_sha256=authorization.authorization_sha256,
            receipt_id=receipt.receipt_id,
            expected_receipt_sha256=receipt.receipt_sha256,
            verification_keys={"substack-test-key": _KEY},
            now_ms=2_002,
        )


def test_authorization_module_has_no_network_or_credential_seam() -> None:
    path = Path(__file__).parents[1] / "substrate/midnight_oil/substack_authorization.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imports.isdisjoint({"httpx", "requests", "urllib3", "socket"})
    source = path.read_text(encoding="utf-8").lower()
    assert "cookie" not in source
    assert "fetch_callback" not in source
