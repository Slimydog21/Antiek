"""M1 tests — encrypted-at-rest BYOK credential store + redacting SecretStr.

All offline + deterministic: a test-injected 32-byte key (no key file daemon, no
OS keychain), a temp artifact path, zero network. The byte-level no-plaintext
assertion is the load-bearing one (rigor #3: "never logged" is a byte assertion,
not a vibe)."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import nacl.secret  # noqa: E402
import pytest  # noqa: E402

from runtime.byok.secret_str import SecretStr  # noqa: E402
from runtime.byok.store import (  # noqa: E402
    CredentialIntegrityError,
    list_credentials,
    load_credential,
    store_credential,
)

_TEST_KEY = b"0" * nacl.secret.SecretBox.KEY_SIZE  # 32 bytes, test-injected
_SECRET = "AAAAxxxx-super-secret-x-bearer-token-1234567890"


def test_secret_str_redacts():
    s = SecretStr("abc")
    assert str(s) != "abc"
    assert repr(s) != "abc"
    assert f"{s}" != "abc"
    assert "abc" not in str(s)
    assert str(s) == "<SecretStr ***>"
    # the real value is reachable only via the explicit accessor
    assert s.reveal() == "abc"
    # equality compares the underlying secret (so round-trips can be asserted)
    assert s == "abc"
    assert s == SecretStr("abc")


def test_store_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        artifact = os.path.join(tmp, "credentials.enc")
        cred_id = store_credential(
            "@dhh", _SECRET, pipeline_kind="general_feed",
            artifact_path=artifact, key_bytes=_TEST_KEY,
        )
        assert cred_id.startswith("cred-x-")
        loaded = load_credential(
            cred_id, artifact_path=artifact, key_bytes=_TEST_KEY,
        )
        assert isinstance(loaded, SecretStr)
        assert loaded.reveal() == _SECRET


def test_raw_artifact_has_no_plaintext_secret():
    with tempfile.TemporaryDirectory() as tmp:
        artifact = os.path.join(tmp, "credentials.enc")
        store_credential(
            "dhh", _SECRET, artifact_path=artifact, key_bytes=_TEST_KEY,
        )
        with open(artifact, "rb") as fh:
            raw = fh.read()
        # the plaintext key substring MUST NOT appear in the at-rest artifact
        assert _SECRET.encode("utf-8") not in raw
        # and the artifact must still carry the non-secret metadata + ciphertext
        text = raw.decode("utf-8")
        assert "ciphertext_hex" in text
        assert "dhh" in text  # the non-secret handle is fine to store


def test_list_credentials_carries_metadata_not_key():
    with tempfile.TemporaryDirectory() as tmp:
        artifact = os.path.join(tmp, "credentials.enc")
        store_credential(
            "dhh", _SECRET, pipeline_kind="general_feed",
            artifact_path=artifact, key_bytes=_TEST_KEY,
        )
        store_credential(
            "patio11", "another-secret-token-zzz",
            artifact_path=artifact, key_bytes=_TEST_KEY,
        )
        metas = list_credentials(artifact_path=artifact)
        assert len(metas) == 2
        handles = {m.account_handle for m in metas}
        assert handles == {"dhh", "patio11"}
        # the metadata objects never expose a plaintext key field
        for m in metas:
            assert _SECRET not in repr(m)


def test_load_unknown_cred_raises():
    with tempfile.TemporaryDirectory() as tmp:
        artifact = os.path.join(tmp, "credentials.enc")
        with pytest.raises(KeyError):
            load_credential("cred-x-nope", artifact_path=artifact, key_bytes=_TEST_KEY)


def test_ciphertext_cannot_be_substituted_between_bound_credentials():
    with tempfile.TemporaryDirectory() as tmp:
        artifact = os.path.join(tmp, "credentials.enc")
        first = store_credential(
            "first",
            "first-secret",
            pipeline_kind="user_model_provider",
            artifact_path=artifact,
            key_bytes=_TEST_KEY,
        )
        second = store_credential(
            "second",
            "second-secret",
            pipeline_kind="user_model_provider",
            artifact_path=artifact,
            key_bytes=_TEST_KEY,
        )
        data = json.loads(Path(artifact).read_text(encoding="utf-8"))
        data[first]["ciphertext_hex"] = data[second]["ciphertext_hex"]
        Path(artifact).write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(CredentialIntegrityError):
            load_credential(first, artifact_path=artifact, key_bytes=_TEST_KEY)


def test_legacy_unbound_credential_remains_readable_for_non_routing_consumers():
    with tempfile.TemporaryDirectory() as tmp:
        artifact = Path(tmp) / "credentials.enc"
        cred_id = "cred-x-legacy"
        sealed = nacl.secret.SecretBox(_TEST_KEY).encrypt(_SECRET.encode("utf-8"))
        artifact.write_text(
            json.dumps(
                {
                    cred_id: {
                        "cred_id": cred_id,
                        "account_handle": "legacy",
                        "pipeline_kind": "general_feed",
                        "ciphertext_hex": bytes(sealed).hex(),
                    }
                }
            ),
            encoding="utf-8",
        )

        loaded = load_credential(
            cred_id,
            artifact_path=str(artifact),
            key_bytes=_TEST_KEY,
        )
        assert loaded.reveal() == _SECRET
        assert list_credentials(artifact_path=str(artifact))[0].binding_version == 1


def test_concurrent_stores_preserve_every_ciphertext_and_valid_json():
    with tempfile.TemporaryDirectory() as tmp:
        artifact = Path(tmp) / "credentials.enc"

        def store(index: int) -> tuple[str, str]:
            secret = f"secret-{index}"
            return (
                store_credential(
                    f"account-{index}",
                    secret,
                    pipeline_kind="user_model_provider",
                    artifact_path=str(artifact),
                    key_bytes=_TEST_KEY,
                ),
                secret,
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            stored = list(pool.map(store, range(24)))

        assert len(json.loads(artifact.read_text(encoding="utf-8"))) == 24
        assert len(list_credentials(artifact_path=str(artifact))) == 24
        for cred_id, secret in stored:
            assert load_credential(
                cred_id,
                artifact_path=str(artifact),
                key_bytes=_TEST_KEY,
            ).reveal() == secret


def test_existing_master_key_permissions_are_repaired_before_read():
    with tempfile.TemporaryDirectory() as tmp:
        artifact = Path(tmp) / "credentials.enc"
        key_file = Path(tmp) / "master.key"
        cred_id = store_credential(
            "mode-check",
            _SECRET,
            artifact_path=str(artifact),
            key_file=str(key_file),
        )
        key_file.chmod(0o644)

        assert load_credential(
            cred_id,
            artifact_path=str(artifact),
            key_file=str(key_file),
        ).reveal() == _SECRET
        assert stat.S_IMODE(key_file.stat().st_mode) == 0o600


def test_master_key_symlink_is_rejected_without_touching_target():
    with tempfile.TemporaryDirectory() as tmp:
        artifact = Path(tmp) / "credentials.enc"
        target = Path(tmp) / "target.key"
        target.write_bytes(_TEST_KEY)
        key_file = Path(tmp) / "master.key"
        key_file.symlink_to(target)

        with pytest.raises(ValueError, match="regular file"):
            store_credential(
                "symlink-check",
                _SECRET,
                artifact_path=str(artifact),
                key_file=str(key_file),
            )
        assert target.read_bytes() == _TEST_KEY
