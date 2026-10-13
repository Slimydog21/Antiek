"""Tests for BYOK-first provider key resolution (``byok_key_source``).

Exercises the real resolver logic; the BYOK store's ``list_credentials`` /
``load_credential`` are monkeypatched (no artifact / master key needed) and the
environment is controlled per test.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from runtime.byok import store as byok_store
from runtime.byok.secret_str import SecretStr
from substrate.dispatch.providers import byok_key_source as ks


def _meta(pipeline_kind: str, cred_id: str = "c1") -> byok_store.CredentialMetadata:
    return byok_store.CredentialMetadata(
        cred_id=cred_id, account_handle="operator", pipeline_kind=pipeline_kind,
        owner_user_id="__operator__", binding_version=3,
    )


@pytest.fixture(autouse=True)
def _clean_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default posture in every test: BYOT-only OFF (env fallback active) unless
    # a test opts in explicitly.
    monkeypatch.delenv("ANTIEK_BYOT_ONLY", raising=False)


def test_env_fallback_when_no_byok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(byok_store, "list_credentials", lambda **k: [])
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "env-key"


def test_byok_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        byok_store, "list_credentials", lambda **k: [_meta("provider:deepseek")]
    )
    monkeypatch.setattr(
        byok_store, "load_credential", lambda cred_id, **k: SecretStr("byok-key")
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "byok-key"


def test_byot_only_no_byok_refuses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(byok_store, "list_credentials", lambda **k: [])
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    monkeypatch.setenv("ANTIEK_BYOT_ONLY", "1")
    # Env key present but flag says BYOT-only + nothing onboarded → honest None,
    # NOT a silent spend on the env key the operator meant to retire.
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") is None


def test_byot_only_uses_byok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        byok_store, "list_credentials", lambda **k: [_meta("provider:deepseek")]
    )
    monkeypatch.setattr(
        byok_store, "load_credential", lambda cred_id, **k: SecretStr("byok-key")
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("ANTIEK_BYOT_ONLY", "true")
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "byok-key"


def test_handle_namespacing_ignores_other_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A stored credential for a DIFFERENT provider must not leak into deepseek.
    monkeypatch.setattr(
        byok_store, "list_credentials", lambda **k: [_meta("provider:anthropic")]
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "env-key"


def test_non_provider_pipeline_kinds_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An ingest/tool credential (e.g. pipeline_kind="x_ingest") is never treated
    # as a dispatch key.
    monkeypatch.setattr(
        byok_store, "list_credentials", lambda **k: [_meta("x_ingest"), _meta("deepseek")]
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    # Neither "x_ingest" nor bare "deepseek" (missing the provider: prefix) match.
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "env-key"


def test_unreadable_store_degrades_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**k):
        raise RuntimeError("no artifact / permission denied")

    monkeypatch.setattr(byok_store, "list_credentials", boom)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    # A broken store must never take down provider bootstrap.
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "env-key"


def test_undecryptable_credential_degrades_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        byok_store, "list_credentials", lambda **k: [_meta("provider:deepseek")]
    )

    def boom(cred_id, **k):
        raise ValueError("master key missing / rotated")

    monkeypatch.setattr(byok_store, "load_credential", boom)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    # Ciphertext present but undecryptable → warn + env fallback, never crash.
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "env-key"


def test_no_key_anywhere_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(byok_store, "list_credentials", lambda **k: [])
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") is None


def test_byot_only_flag_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    for truthy in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("ANTIEK_BYOT_ONLY", truthy)
        assert ks.byot_only_enabled() is True
    for falsy in ("0", "false", "no", "", "off"):
        monkeypatch.setenv("ANTIEK_BYOT_ONLY", falsy)
        assert ks.byot_only_enabled() is False


@pytest.fixture
def encrypted_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    artifact = tmp_path / "credentials.enc"
    key_file = tmp_path / "master.key"
    key_file.write_bytes(b"x" * 32)
    key_file.chmod(0o600)
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(artifact))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(key_file))
    return artifact


@pytest.mark.parametrize("owner", ["owner-alice", "owner-bob", None])
@pytest.mark.parametrize("byot_only", [False, True])
def test_account_key_never_becomes_shared_provider(
    encrypted_store: Path,
    monkeypatch: pytest.MonkeyPatch,
    owner: str | None,
    byot_only: bool,
) -> None:
    from substrate.dispatch.providers.bootstrap import _maybe_deepseek

    byok_store.store_credential_with_metadata(
        "deepseek", "personal-synthetic-key",
        pipeline_kind="provider:deepseek", owner_user_id=owner,
    )
    assert b"personal-synthetic-key" not in encrypted_store.read_bytes()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "house-synthetic-key")
    monkeypatch.setenv("ANTIEK_BYOT_ONLY", str(int(byot_only)))

    # Check both resolution and the actual bootstrap consumer. Neither may
    # turn a user's credential into a process-wide background provider.
    expected = None if byot_only else "house-synthetic-key"
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == expected
    provider = _maybe_deepseek()
    if byot_only:
        assert provider is None
    else:
        assert provider is not None
        assert provider._resolve_api_key() == "house-synthetic-key"


def test_migrated_operator_key_is_still_available_to_bootstrap(
    encrypted_store: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.byot_migrate_env_keys import run_migration

    env_file = tmp_path / "synthetic.env"
    env_file.write_text("DEEPSEEK_API_KEY=migrated-synthetic-key\n")
    result = run_migration(str(env_file))
    assert result.errors == []
    monkeypatch.setenv("ANTIEK_BYOT_ONLY", "1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "migrated-synthetic-key"


def test_operator_key_wins_regardless_of_foreign_credential_sort_order(
    encrypted_store: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    byok_store.store_credential_with_metadata(
        "deepseek", "operator-synthetic-key",
        pipeline_kind="provider:deepseek", owner_user_id="__operator__",
    )
    byok_store.store_credential_with_metadata(
        "deepseek", "foreign-synthetic-key",
        pipeline_kind="provider:deepseek", owner_user_id="owner-alice",
    )
    records = byok_store.list_credentials()
    for ordered in (records, list(reversed(records))):
        monkeypatch.setattr(byok_store, "list_credentials", lambda records=ordered: records)
        assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") == "operator-synthetic-key"


@pytest.mark.parametrize("binding_version", [1, 2, 4])
def test_unbound_or_unknown_shared_credential_is_not_decrypted(
    monkeypatch: pytest.MonkeyPatch, binding_version: int,
) -> None:
    record = replace(_meta("provider:deepseek"), binding_version=binding_version)
    monkeypatch.setattr(byok_store, "list_credentials", lambda: [record])
    monkeypatch.setenv("ANTIEK_BYOT_ONLY", "1")

    def forbidden_load(cred_id: str) -> SecretStr:
        pytest.fail("credential without authenticated owner binding was decrypted")

    monkeypatch.setattr(byok_store, "load_credential", forbidden_load)
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") is None


def test_relabeling_personal_key_as_operator_does_not_grant_shared_use(
    encrypted_store: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    meta = byok_store.store_credential_with_metadata(
        "deepseek", "personal-synthetic-key",
        pipeline_kind="provider:deepseek", owner_user_id="owner-alice",
    )
    records = json.loads(encrypted_store.read_text())
    records[meta.cred_id]["owner_user_id"] = "__operator__"
    encrypted_store.write_text(json.dumps(records))
    monkeypatch.setenv("ANTIEK_BYOT_ONLY", "1")
    assert ks.resolve_provider_key("deepseek", "DEEPSEEK_API_KEY") is None
