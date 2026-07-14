from __future__ import annotations

import pytest

from interfaces.research.api.multimedia_hardening_routes import (
    multimedia_hardening_runtime_from_environment,
)

SIGNING_HEX = (b"provider-execution-signing-domain-1").hex()
SNAPSHOT_HEX = (b"ship-cost-snapshot-signing-domain-2").hex()


def test_hardening_runtime_is_optional_only_when_entirely_unconfigured() -> None:
    assert multimedia_hardening_runtime_from_environment({}) is None
    with pytest.raises(RuntimeError, match="incomplete"):
        multimedia_hardening_runtime_from_environment(
            {"ANTIEK_MULTIMEDIA_HARDENING_ENABLED": "true"}
        )


def test_hardening_runtime_requires_independent_strong_keys() -> None:
    base = {
        "ANTIEK_MULTIMEDIA_HARDENING_ENABLED": "true",
        "ANTIEK_MULTIMEDIA_HARDENING_DB_PATH": "/private/accounting.duckdb",
        "ANTIEK_MULTIMEDIA_HARDENING_SIGNING_KEY_HEX": SIGNING_HEX,
        "ANTIEK_MULTIMEDIA_HARDENING_SNAPSHOT_KEY_HEX": SNAPSHOT_HEX,
    }
    runtime = multimedia_hardening_runtime_from_environment(base)
    assert runtime is not None
    assert runtime.signing_key != runtime.snapshot_key

    with pytest.raises(RuntimeError, match="independent"):
        multimedia_hardening_runtime_from_environment(
            {**base, "ANTIEK_MULTIMEDIA_HARDENING_SNAPSHOT_KEY_HEX": SIGNING_HEX}
        )
