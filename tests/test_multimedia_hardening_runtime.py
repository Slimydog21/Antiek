from __future__ import annotations

import pytest

from interfaces.research.api.multimedia_hardening_routes import (
    multimedia_hardening_runtime_from_environment,
)

SIGNING_HEX = (b"provider-execution-signing-domain-1").hex()
SNAPSHOT_HEX = (b"ship-cost-snapshot-signing-domain-2").hex()
LOCAL_ZERO_HEX = (b"local-zero-snapshot-signing-domain-3").hex()
PRODUCTION_HEX = (b"production-byte-snapshot-domain-4").hex()


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

    local_runtime = multimedia_hardening_runtime_from_environment(
        {
            **base,
            "ANTIEK_MULTIMEDIA_HARDENING_LOCAL_ZERO_KEY_HEX": LOCAL_ZERO_HEX,
            "ANTIEK_MULTIMEDIA_HARDENING_PRODUCTION_KEY_HEX": PRODUCTION_HEX,
        }
    )
    assert local_runtime is not None
    assert local_runtime.local_zero_snapshot_key is not None
    assert len(
        {
            local_runtime.signing_key,
            local_runtime.snapshot_key,
            local_runtime.local_zero_snapshot_key,
            local_runtime.production_snapshot_key,
        }
    ) == 4

    with pytest.raises(RuntimeError, match="independent"):
        multimedia_hardening_runtime_from_environment(
            {**base, "ANTIEK_MULTIMEDIA_HARDENING_SNAPSHOT_KEY_HEX": SIGNING_HEX}
        )
    with pytest.raises(RuntimeError, match="independent"):
        multimedia_hardening_runtime_from_environment(
            {**base, "ANTIEK_MULTIMEDIA_HARDENING_LOCAL_ZERO_KEY_HEX": SIGNING_HEX}
        )
    with pytest.raises(RuntimeError, match="independent"):
        multimedia_hardening_runtime_from_environment(
            {**base, "ANTIEK_MULTIMEDIA_HARDENING_PRODUCTION_KEY_HEX": SNAPSHOT_HEX}
        )
    with pytest.raises(RuntimeError, match="independent"):
        multimedia_hardening_runtime_from_environment(
            {**base, "ANTIEK_MULTIMEDIA_HARDENING_PRODUCTION_KEY_HEX": SIGNING_HEX}
        )
    with pytest.raises(RuntimeError, match="independent"):
        multimedia_hardening_runtime_from_environment(
            {
                **base,
                "ANTIEK_MULTIMEDIA_HARDENING_PRODUCTION_KEY_HEX": PRODUCTION_HEX,
                "ANTIEK_MULTIMEDIA_HARDENING_LOCAL_ZERO_KEY_HEX": PRODUCTION_HEX,
            }
        )
