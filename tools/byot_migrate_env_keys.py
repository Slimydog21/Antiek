#!/usr/bin/env python3
"""BYOT env-key migration tool — onboard operator dispatch keys into the
encrypted BYOK store so they can be removed from ``secrets.env``.

This is the one-time migration that moves the operator's dispatch provider
keys (DEEPSEEK_API_KEY, ANTHROPIC_API_KEY, etc.) from an environment file
into the ``runtime.byok.store`` encrypted credential store under the
``provider:<handle>`` pipeline_kind convention established by
``byok_key_source.py`` and ``bootstrap.py``.

After migration, the operator sets ``ANTIEK_BYOT_ONLY=1`` and removes the
migrated lines from ``secrets.env``. The provider bootstrap resolves keys
BYOK-first; with BYOT-only mode, the env fallback is disabled entirely.

Usage::

    # preview what would be stored (no writes)
    python -m tools.byot_migrate_env_keys --dry-run

    # migrate keys from the default /etc/antiek/secrets.env
    python -m tools.byot_migrate_env_keys

    # migrate from a custom path, overwriting any existing stored keys
    python -m tools.byot_migrate_env_keys --env-file ./secrets.env --overwrite
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.byok.store import (  # noqa: E402
    CredentialMetadata,
    list_credentials,
    store_credential_with_metadata,
)

logger = logging.getLogger("tools.byot_migrate_env_keys")

# ── Provider env-var → BYOK handle mapping ──────────────────────────────
# Discovered from ``bootstrap.py``: each ``_maybe_<provider>()`` calls
# ``resolve_provider_key("<handle>", "<ENV_VAR>")``.  The BYOK store
# convention (``byok_key_source.py``) is
# ``pipeline_kind = "provider:<handle>"``, ``account_handle = "<handle>"``.

_PROVIDER_OWNER = "__operator__"

# (env_var_name, provider_handle) — order matches bootstrap.py
_PROVIDER_ENV_MAP: list[tuple[str, str]] = [
    ("DEEPSEEK_API_KEY", "deepseek"),
    ("ANTHROPIC_API_KEY", "anthropic"),
    ("OPENROUTER_API_KEY", "openrouter"),
    ("XIAOMI_API_KEY", "xiaomi"),
    ("HERMES_API_KEY", "hermes"),
    ("Z_AI_API_KEY", "zai"),
]


def _parse_env_file(path: str) -> dict[str, str]:
    r"""Parse a ``KEY=VALUE`` env file (shell-style, one per line).

    Handles:
    - ``export KEY=VALUE`` prefix
    - ``KEY="VALUE"`` and ``KEY='VALUE'`` (quotes stripped)
    - ``#`` comments and blank lines
    - Values may contain ``=`` signs

    Returns only non-empty values.
    """
    out: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"env file not found: {path}")
    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip optional ``export `` prefix
        if line.startswith("export "):
            line = line[len("export "):]
        # Split on first ``=``
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes
        if len(value) >= 2 and (
            (value[0] == '"' and value[-1] == '"')
            or (value[0] == "'" and value[-1] == "'")
        ):
            value = value[1:-1]
        if key and value:
            out[key] = value
    return out


def _pipeline_kind(handle: str) -> str:
    return f"provider:{handle}"


def _existing_stored_handles(
    handles: Sequence[str],
    artifact_path: str | None = None,
) -> dict[str, CredentialMetadata]:
    """Return a map of handle → metadata for credentials already in the store
    matching the ``provider:<handle>`` pipeline_kind."""
    all_meta = list_credentials(artifact_path=artifact_path)
    wanted_pk = {_pipeline_kind(h) for h in handles}
    out: dict[str, CredentialMetadata] = {}
    for meta in all_meta:
        # Extract the handle from pipeline_kind ("provider:deepseek" → "deepseek")
        if meta.pipeline_kind in wanted_pk and meta.pipeline_kind:
            handle = meta.pipeline_kind.split(":", 1)[1]
            if handle in set(handles):
                out[handle] = meta
    return out


class MigrationResult:
    """Result of a migration run."""

    def __init__(self) -> None:
        self.stored: list[tuple[str, str]] = []  # (handle, env_var)
        self.skipped_existing: list[tuple[str, str]] = []  # (handle, env_var)
        self.skipped_missing: list[str] = []  # env_var
        self.unrecognized: list[str] = []  # env_var
        self.errors: list[tuple[str, str]] = []  # (handle, error_message)

    @property
    def has_stores(self) -> bool:
        return bool(self.stored)

    @property
    def has_actions(self) -> bool:
        return bool(self.stored or self.errors)


def run_migration(
    env_file: str,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
    artifact_path: str | None = None,
    key_bytes: bytes | None = None,
    key_file: str | None = None,
) -> MigrationResult:
    """Run the migration: parse env file, map, store.

    Parameters
    ----------
    env_file:
        Path to the secrets.env-style file.
    overwrite:
        If False (default), skip credentials already in the BYOK store.
    dry_run:
        If True, print what would be stored but do not write.
    artifact_path:
        Override BYOK artifact path (tests inject a temp path).
    key_bytes:
        Injected master key bytes (tests use this).
    key_file:
        Override key file path.
    """
    env = _parse_env_file(env_file)
    result = MigrationResult()

    # Check what's already stored (only when not dry-run, since dry-run
    # has no artifact to read)
    handles = [h for _, h in _PROVIDER_ENV_MAP]
    existing: dict[str, CredentialMetadata] = {}
    if not dry_run:
        existing = _existing_stored_handles(handles, artifact_path=artifact_path)

    for env_var, handle in _PROVIDER_ENV_MAP:
        value = env.get(env_var)
        if not value:
            result.skipped_missing.append(env_var)
            continue

        pk = _pipeline_kind(handle)

        if not dry_run and handle in existing and not overwrite:
            result.skipped_existing.append((handle, env_var))
            continue

        if dry_run:
            result.stored.append((handle, env_var))
            continue

        try:
            store_credential_with_metadata(
                handle,
                value,
                pipeline_kind=pk,
                owner_user_id=_PROVIDER_OWNER,
                artifact_path=artifact_path,
                key_bytes=key_bytes,
                key_file=key_file,
            )
            result.stored.append((handle, env_var))
        except Exception as exc:
            result.errors.append((handle, str(exc)))

    # Identify unrecognized env vars
    recognized_keys = {ev for ev, _ in _PROVIDER_ENV_MAP}
    for key in sorted(env):
        if key not in recognized_keys:
            result.unrecognized.append(key)

    return result


def _print_report(result: MigrationResult, env_file: str, dry_run: bool) -> None:
    prefix = "[DRY RUN] " if dry_run else ""

    if result.stored:
        print(f"\n{prefix}Stored credentials:")
        for handle, env_var in result.stored:
            pk = _pipeline_kind(handle)
            print(f"  {env_var} -> BYOK store as pipeline_kind={pk!r}, "
                  f"account_handle={handle!r}, owner={_PROVIDER_OWNER!r}")

    if result.skipped_existing:
        print("\nSkipped (already in BYOK store, use --overwrite to replace):")
        for handle, env_var in result.skipped_existing:
            print(f"  {env_var} (handle={handle})")

    if result.skipped_missing:
        print(f"\nSkipped (not set or empty in {env_file}):")
        for env_var in result.skipped_missing:
            print(f"  {env_var}")

    if result.unrecognized:
        print(f"\nUnrecognized env vars in {env_file} (skipped, not dispatch providers):")
        for uv in result.unrecognized:
            print(f"  {uv}")

    if result.errors:
        print("\nErrors:")
        for handle, err in result.errors:
            print(f"  {handle}: {err}")

    # Migration guidance
    if result.has_stores and not dry_run:
        migrated_vars = [ev for _, ev in result.stored]
        print(f"\n{'─' * 60}")
        print("Migration complete. Next steps:\n")
        print("1. Remove these lines from " + env_file + ":")
        for ev in migrated_vars:
            print(f"   {ev}=...")
        print()
        print("2. Set ANTIEK_BYOT_ONLY=1 in your environment (e.g. in secrets.env")
        print("   or systemd unit) so providers ONLY resolve from the BYOK store.")
        print()
        print("3. Restart the Antiek process to pick up the new flag + store.")
        print()
        print("4. Verify with: python -m tools.byot_migrate_env_keys --dry-run")
        print("   (should show all keys as 'skipped — already in BYOK store').")

    if not result.has_stores and not result.errors:
        if result.skipped_existing:
            print("\nAll recognized keys already in BYOK store. Nothing to do.")
        else:
            print(f"\nNo recognized provider keys found in {env_file}.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.byot_migrate_env_keys",
        description=(
            "Migrate dispatch provider API keys from a secrets.env-style file "
            "into the encrypted BYOK credential store. "
            "After migration, set ANTIEK_BYOT_ONLY=1 and remove the migrated "
            "lines from the env file."
        ),
    )
    p.add_argument(
        "--env-file",
        default="/etc/antiek/secrets.env",
        help="Path to the secrets.env file (default: /etc/antiek/secrets.env)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be stored without writing anything",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing stored credentials for the same provider handle",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    try:
        result = run_migration(
            args.env_file,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: migration failed: {exc}", file=sys.stderr)
        return 1

    _print_report(result, args.env_file, args.dry_run)

    if result.errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
