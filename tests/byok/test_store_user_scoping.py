from __future__ import annotations

import hashlib
import json
from pathlib import Path

import nacl.secret
import pytest

from runtime.byok.store import (
    CredentialIntegrityError,
    delete_credential,
    list_credentials,
    load_credential,
    store_credential,
)

_KEY = b"u" * nacl.secret.SecretBox.KEY_SIZE


def test_v2_ownerless_credential_remains_readable(tmp_path: Path) -> None:
    artifact = tmp_path / "credentials.enc"
    cred_id = "cred-x-v2-legacy"
    identity = json.dumps(
        {
            "account_handle": "legacy-model",
            "cred_id": cred_id,
            "pipeline_kind": "model_provider",
            "version": 2,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    bound_key = hashlib.blake2b(
        identity,
        key=_KEY,
        digest_size=nacl.secret.SecretBox.KEY_SIZE,
        person=b"antiek-byok-v2",
    ).digest()
    sealed = nacl.secret.SecretBox(bound_key).encrypt(b"legacy-v2-secret")
    artifact.write_text(
        json.dumps(
            {
                cred_id: {
                    "cred_id": cred_id,
                    "account_handle": "legacy-model",
                    "pipeline_kind": "model_provider",
                    "binding_version": 2,
                    "ciphertext_hex": bytes(sealed).hex(),
                }
            }
        ),
        encoding="utf-8",
    )

    assert (
        load_credential(
            cred_id,
            artifact_path=str(artifact),
            key_bytes=_KEY,
        ).reveal()
        == "legacy-v2-secret"
    )
    metadata = list_credentials(artifact_path=str(artifact))[0]
    assert metadata.binding_version == 2
    assert metadata.owner_user_id is None


def test_credentials_are_owner_bound_and_delete_is_exact(tmp_path: Path) -> None:
    artifact = str(tmp_path / "credentials.enc")
    first = store_credential(
        "shared-model",
        "first-user-secret",
        pipeline_kind="model_provider",
        owner_user_id="user-a",
        artifact_path=artifact,
        key_bytes=_KEY,
    )
    second = store_credential(
        "shared-model",
        "second-user-secret",
        pipeline_kind="model_provider",
        owner_user_id="user-b",
        artifact_path=artifact,
        key_bytes=_KEY,
    )

    metadata = {item.cred_id: item for item in list_credentials(artifact_path=artifact)}
    assert metadata[first].owner_user_id == "user-a"
    assert metadata[second].owner_user_id == "user-b"
    assert metadata[first].binding_version == 3
    assert load_credential(first, artifact_path=artifact, key_bytes=_KEY).reveal() == (
        "first-user-secret"
    )

    raw = json.loads(Path(artifact).read_text(encoding="utf-8"))
    raw[first]["owner_user_id"] = "user-b"
    Path(artifact).write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CredentialIntegrityError):
        load_credential(first, artifact_path=artifact, key_bytes=_KEY)

    assert delete_credential(first, artifact_path=artifact) is True
    assert delete_credential(first, artifact_path=artifact) is False
    assert [item.cred_id for item in list_credentials(artifact_path=artifact)] == [second]
    assert load_credential(second, artifact_path=artifact, key_bytes=_KEY).reveal() == (
        "second-user-secret"
    )
