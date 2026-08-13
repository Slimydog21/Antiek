"""Tests for ``tools.byot_migrate_env_keys``.

Uses isolated BYOK artifact + master key (no real store, no network, no OS
keychain). Follows the same ``tmp_path`` + ``key_bytes`` injection pattern as
``tests/byok/test_store_user_scoping.py``.
"""

from __future__ import annotations

from pathlib import Path

import nacl.secret
import pytest

from runtime.byok.store import (
    list_credentials,
    load_credential,
    store_credential,
)
from tools.byot_migrate_env_keys import (
    _PROVIDER_ENV_MAP,
    _existing_stored_handles,
    _parse_env_file,
    _pipeline_kind,
    run_migration,
)

_KEY = b"t" * nacl.secret.SecretBox.KEY_SIZE


# ── env-file parsing ────────────────────────────────────────────────────


def test_parse_env_file_basics(tmp_path: Path) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text(
        '# comment\n'
        'DEEPSEEK_API_KEY=sk-deep-123\n'
        'export ANTHROPIC_API_KEY="sk-ant-456"\n'
        "Z_AI_API_KEY='sk-z-789'\n"
        "\n"
        "EMPTY_KEY=\n"
        "NO_EQUALS_SIGN\n"
        "MIXED=Value=With=Equals\n",
        encoding="utf-8",
    )
    result = _parse_env_file(str(env_file))
    assert result == {
        "DEEPSEEK_API_KEY": "sk-deep-123",
        "ANTHROPIC_API_KEY": "sk-ant-456",
        "Z_AI_API_KEY": "sk-z-789",
        "MIXED": "Value=With=Equals",
    }


def test_parse_env_file_not_found() -> None:
    with pytest.raises(FileNotFoundError, match="env file not found"):
        _parse_env_file("/nonexistent/path/secrets.env")


def test_parse_env_file_empty(tmp_path: Path) -> None:
    env_file = tmp_path / "empty.env"
    env_file.write_text("# just comments\n\n", encoding="utf-8")
    assert _parse_env_file(str(env_file)) == {}


# ── dry-run ─────────────────────────────────────────────────────────────


def test_dry_run_no_writes(tmp_path: Path) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=sk-dry\nHERMES_API_KEY=sk-hermes\n",
        encoding="utf-8",
    )
    result = run_migration(str(env_file), dry_run=True)
    assert len(result.stored) == 2
    assert result.skipped_missing == [ev for ev, _ in _PROVIDER_ENV_MAP if ev not in (
        "DEEPSEEK_API_KEY", "HERMES_API_KEY",
    )]
    # No artifact should have been created
    assert len(result.errors) == 0


# ── full migration ──────────────────────────────────────────────────────


def test_full_migration_stores_all_keys(tmp_path: Path) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=sk-deep-real\n"
        "ANTHROPIC_API_KEY=sk-ant-real\n"
        "OPENROUTER_API_KEY=sk-or-real\n"
        "XIAOMI_API_KEY=sk-xi-real\n"
        "HERMES_API_KEY=sk-hermes-real\n"
        "Z_AI_API_KEY=sk-z-real\n"
        "EXA_API_KEY=sk-exa-ignored\n"
        "SERPAPI_API_KEY=sk-serpapi-ignored\n",
        encoding="utf-8",
    )
    artifact = str(tmp_path / "credentials.enc")
    result = run_migration(
        str(env_file),
        artifact_path=artifact,
        key_bytes=_KEY,
    )
    assert len(result.stored) == 6
    assert len(result.errors) == 0
    assert "EXA_API_KEY" in result.unrecognized
    assert "SERPAPI_API_KEY" in result.unrecognized

    # Verify all keys are in the store and decryptable
    for env_var, handle in _PROVIDER_ENV_MAP:
        pk = _pipeline_kind(handle)
        creds = [
            m for m in list_credentials(artifact_path=artifact)
            if m.pipeline_kind == pk and m.account_handle == handle
        ]
        assert len(creds) == 1, f"expected 1 credential for {handle}, got {len(creds)}"
        cred = creds[0]
        assert cred.owner_user_id == "__operator__"
        plaintext = load_credential(cred.cred_id, artifact_path=artifact, key_bytes=_KEY).reveal()
        # Verify the stored value matches what was in the env file
        assert plaintext == _parse_env_file(str(env_file))[env_var]


# ── partial migration (some keys missing from env file) ────────────────


def test_partial_migration_skips_missing(tmp_path: Path) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=sk-deep\n",
        encoding="utf-8",
    )
    artifact = str(tmp_path / "credentials.enc")
    result = run_migration(
        str(env_file),
        artifact_path=artifact,
        key_bytes=_KEY,
    )
    assert len(result.stored) == 1
    assert result.stored[0] == ("deepseek", "DEEPSEEK_API_KEY")
    # All others should be in skipped_missing
    assert len(result.skipped_missing) == 5


# ── refuse overwrite without --overwrite ────────────────────────────────


def test_refuse_overwrite_by_default(tmp_path: Path) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text("DEEPSEEK_API_KEY=sk-new\n", encoding="utf-8")
    artifact = str(tmp_path / "credentials.enc")

    # First run: stores it
    result1 = run_migration(
        str(env_file),
        artifact_path=artifact,
        key_bytes=_KEY,
    )
    assert len(result1.stored) == 1

    # Second run without --overwrite: skips it
    result2 = run_migration(
        str(env_file),
        artifact_path=artifact,
        key_bytes=_KEY,
    )
    assert len(result2.stored) == 0
    assert len(result2.skipped_existing) == 1
    assert result2.skipped_existing[0] == ("deepseek", "DEEPSEEK_API_KEY")


def test_overwrite_with_flag(tmp_path: Path) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text("DEEPSEEK_API_KEY=sk-old\n", encoding="utf-8")
    artifact = str(tmp_path / "credentials.enc")

    # First run
    run_migration(str(env_file), artifact_path=artifact, key_bytes=_KEY)

    # Overwrite with new key
    env_file.write_text("DEEPSEEK_API_KEY=sk-new\n", encoding="utf-8")
    result = run_migration(
        str(env_file),
        overwrite=True,
        artifact_path=artifact,
        key_bytes=_KEY,
    )
    assert len(result.stored) == 1

    # Verify the NEW key is stored (there will be 2 credentials for deepseek
    # since the old one isn't deleted — the new one is just added)
    creds = [
        m for m in list_credentials(artifact_path=artifact)
        if m.pipeline_kind == _pipeline_kind("deepseek")
    ]
    assert len(creds) == 2  # old + new
    # Overwrite ADDS a new credential (documented: add, not delete-then-add).
    # list_credentials ordering is not insertion-ordered (cred_id is random),
    # so assert the new key is present anywhere, not at a list position.
    plaintexts = [
        load_credential(m.cred_id, artifact_path=artifact, key_bytes=_KEY).reveal()
        for m in creds
    ]
    assert "sk-new" in plaintexts
    assert "sk-old" in plaintexts


# ── unrecognized env vars are reported ──────────────────────────────────


def test_unrecognized_vars_reported(tmp_path: Path) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=sk-d\n"
        "SOME_RANDOM_KEY=sk-random\n"
        "ANOTHER_TOOL_KEY=sk-tool\n",
        encoding="utf-8",
    )
    artifact = str(tmp_path / "credentials.enc")
    result = run_migration(
        str(env_file),
        artifact_path=artifact,
        key_bytes=_KEY,
    )
    assert len(result.stored) == 1
    assert "SOME_RANDOM_KEY" in result.unrecognized
    assert "ANOTHER_TOOL_KEY" in result.unrecognized


# ── no recognized keys at all ───────────────────────────────────────────


def test_no_recognized_keys(tmp_path: Path) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text("EXA_API_KEY=sk-exa\nSERPAPI_API_KEY=sk-serp\n", encoding="utf-8")
    artifact = str(tmp_path / "credentials.enc")
    result = run_migration(
        str(env_file),
        artifact_path=artifact,
        key_bytes=_KEY,
    )
    assert len(result.stored) == 0
    assert len(result.unrecognized) == 2


# ── _existing_stored_handles ────────────────────────────────────────────


def test_existing_stored_handles(tmp_path: Path) -> None:
    artifact = str(tmp_path / "credentials.enc")
    # Pre-store a deepseek key
    store_credential(
        "deepseek",
        "pre-existing",
        pipeline_kind=_pipeline_kind("deepseek"),
        owner_user_id="__operator__",
        artifact_path=artifact,
        key_bytes=_KEY,
    )
    existing = _existing_stored_handles(["deepseek", "anthropic"], artifact_path=artifact)
    assert "deepseek" in existing
    assert "anthropic" not in existing
    assert existing["deepseek"].pipeline_kind == "provider:deepseek"


# ── empty key values are skipped ────────────────────────────────────────


def test_empty_values_skipped(tmp_path: Path) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=\n"  # empty value
        "ANTHROPIC_API_KEY=   \n"  # whitespace only -> after strip is empty
        "XIAOMI_API_KEY=sk-xi\n",
        encoding="utf-8",
    )
    artifact = str(tmp_path / "credentials.enc")
    result = run_migration(
        str(env_file),
        artifact_path=artifact,
        key_bytes=_KEY,
    )
    # Only XIAOMI should be stored; DEEPSEEK and ANTHROPIC are empty/whitespace
    assert len(result.stored) == 1
    assert result.stored[0] == ("xiaomi", "XIAOMI_API_KEY")


# ── pipeline_kind convention matches byok_key_source ────────────────────


def test_pipeline_kind_convention() -> None:
    """Verify the tool's pipeline_kind matches what byok_key_source expects."""
    for _env_var, handle in _PROVIDER_ENV_MAP:
        pk = _pipeline_kind(handle)
        assert pk == f"provider:{handle}"
        # This is exactly what byok_key_source._lookup_byok_key computes:
        # _PROVIDER_PIPELINE_PREFIX + provider_handle
