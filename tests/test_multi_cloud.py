"""Tests for ``substrate/dispatch/multi_cloud.py``.

DDIA-execution SPR-10. Verifies:
- Default OFF behavior (no secondary failover under any condition).
- Env var override turns it on per class.
- TOML override turns it on per class.
- Env beats TOML.
- Failover shim returns the right (bool, name) tuple.
- Default registry has the documented primary/secondary pairs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from substrate.dispatch.multi_cloud import (  # noqa: E402
    DEFAULT_REGISTRY,
    VendorClass,
    is_enabled,
    resolve,
    should_failover_to_secondary,
)

# ---------------------------------------------------------------------------
# Default registry shape
# ---------------------------------------------------------------------------


def test_registry_covers_all_classes() -> None:
    for cls in VendorClass:
        assert cls in DEFAULT_REGISTRY, f"missing default for {cls}"


def test_llm_primary_is_hermes() -> None:
    cfg = DEFAULT_REGISTRY[VendorClass.LLM]
    assert cfg.primary == "hermes"
    assert cfg.secondary == "openrouter"
    assert "OAuth-refresh" in cfg.reason or "I-DISPATCH-4" in cfg.reason


def test_browser_secondary_is_anchor() -> None:
    cfg = DEFAULT_REGISTRY[VendorClass.BROWSER]
    assert cfg.primary == "browserbase"
    assert cfg.secondary == "anchor_browser"
    assert "Plan B" in cfg.reason or "AnchorBrowser" in cfg.reason


def test_compute_has_no_secondary() -> None:
    """§16 REJECT-lists Modal+Daytona, so compute has no secondary."""
    cfg = DEFAULT_REGISTRY[VendorClass.COMPUTE]
    assert cfg.secondary is None
    assert "REJECT" in cfg.reason or "substrate" in cfg.reason.lower()


def test_vector_index_secondary_unset_until_turbopuffer_graduates() -> None:
    cfg = DEFAULT_REGISTRY[VendorClass.VECTOR_INDEX]
    assert cfg.primary == "duckdb_native"
    assert cfg.secondary is None


def test_object_store_has_no_secondary() -> None:
    cfg = DEFAULT_REGISTRY[VendorClass.OBJECT_STORE]
    assert cfg.secondary is None


# ---------------------------------------------------------------------------
# is_enabled — defaults + overrides
# ---------------------------------------------------------------------------


def test_is_enabled_off_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_HOME", "/nonexistent")
    for cls in VendorClass:
        monkeypatch.delenv(
            f"ANTIEK_MULTI_CLOUD_{cls.value.upper()}", raising=False
        )
        assert not is_enabled(cls), f"{cls} should be off by default"


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on"])
def test_is_enabled_env_truthy_values_turn_on(
    val: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTIEK_HOME", "/nonexistent")
    monkeypatch.setenv("ANTIEK_MULTI_CLOUD_LLM", val)
    assert is_enabled(VendorClass.LLM)


@pytest.mark.parametrize("val", ["0", "false", "FALSE", "no", "off"])
def test_is_enabled_env_falsey_values_stay_off(
    val: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTIEK_HOME", "/nonexistent")
    monkeypatch.setenv("ANTIEK_MULTI_CLOUD_LLM", val)
    assert not is_enabled(VendorClass.LLM)


def test_is_enabled_via_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "antiek_home"
    home.mkdir()
    (home / "multi_cloud.toml").write_text(
        "[llm]\nenabled = true\n"
        "[browser]\nenabled = false\n"
    )
    monkeypatch.setenv("ANTIEK_HOME", str(home))
    for cls in VendorClass:
        monkeypatch.delenv(
            f"ANTIEK_MULTI_CLOUD_{cls.value.upper()}", raising=False
        )
    assert is_enabled(VendorClass.LLM)
    assert not is_enabled(VendorClass.BROWSER)
    assert not is_enabled(VendorClass.COMPUTE)


def test_env_beats_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "antiek_home"
    home.mkdir()
    (home / "multi_cloud.toml").write_text("[llm]\nenabled = true\n")
    monkeypatch.setenv("ANTIEK_HOME", str(home))
    # Env explicitly OFF; TOML says ON; env wins.
    monkeypatch.setenv("ANTIEK_MULTI_CLOUD_LLM", "false")
    assert not is_enabled(VendorClass.LLM)


# ---------------------------------------------------------------------------
# resolve — operator overrides primary/secondary
# ---------------------------------------------------------------------------


def test_resolve_returns_default_when_no_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_HOME", "/nonexistent")
    cfg = resolve(VendorClass.LLM)
    assert cfg.primary == "hermes"
    assert cfg.secondary == "openrouter"


def test_resolve_honors_toml_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "antiek_home"
    home.mkdir()
    (home / "multi_cloud.toml").write_text(
        "[llm]\n"
        'primary = "anthropic"\n'
        'secondary = "openai"\n'
        'reason = "operator A/B test"\n'
    )
    monkeypatch.setenv("ANTIEK_HOME", str(home))
    cfg = resolve(VendorClass.LLM)
    assert cfg.primary == "anthropic"
    assert cfg.secondary == "openai"
    assert "operator A/B test" in cfg.reason


def test_resolve_can_clear_secondary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setting secondary to "none" in TOML clears it."""
    home = tmp_path / "antiek_home"
    home.mkdir()
    (home / "multi_cloud.toml").write_text(
        '[llm]\nsecondary = "none"\n'
    )
    monkeypatch.setenv("ANTIEK_HOME", str(home))
    cfg = resolve(VendorClass.LLM)
    assert cfg.secondary is None


def test_resolve_unknown_class_raises() -> None:
    """Calling resolve with a value that isn't a VendorClass raises."""
    with pytest.raises((KeyError, TypeError, ValueError)):
        resolve("not-a-class")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Failover shim
# ---------------------------------------------------------------------------


def test_failover_off_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even if the primary fails, the shim returns (False, None) when
    the per-class flag is off — the default state.
    """
    monkeypatch.setenv("ANTIEK_HOME", "/nonexistent")
    for cls in VendorClass:
        monkeypatch.delenv(
            f"ANTIEK_MULTI_CLOUD_{cls.value.upper()}", raising=False
        )
    should, secondary = should_failover_to_secondary(
        VendorClass.LLM, primary_failed=True
    )
    assert should is False
    assert secondary is None


def test_failover_on_when_enabled_and_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_HOME", "/nonexistent")
    monkeypatch.setenv("ANTIEK_MULTI_CLOUD_LLM", "1")
    should, secondary = should_failover_to_secondary(
        VendorClass.LLM, primary_failed=True
    )
    assert should is True
    assert secondary == "openrouter"


def test_failover_off_when_enabled_but_primary_not_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_HOME", "/nonexistent")
    monkeypatch.setenv("ANTIEK_MULTI_CLOUD_LLM", "1")
    should, _ = should_failover_to_secondary(
        VendorClass.LLM, primary_failed=False
    )
    assert should is False


def test_failover_off_when_no_secondary_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """COMPUTE has no secondary — even with flag on + primary failed,
    the shim returns (False, None).
    """
    monkeypatch.setenv("ANTIEK_HOME", "/nonexistent")
    monkeypatch.setenv("ANTIEK_MULTI_CLOUD_COMPUTE", "1")
    should, secondary = should_failover_to_secondary(
        VendorClass.COMPUTE, primary_failed=True
    )
    assert should is False
    assert secondary is None


# ---------------------------------------------------------------------------
# Router is NOT yet wired — defense against accidental activation
# ---------------------------------------------------------------------------


def test_router_does_not_import_multi_cloud_yet() -> None:
    """SPR-10's contract: the registry + shim land in this commit, but
    ``router.py`` does NOT consult them yet. The wiring is a separate
    operator-authorized step.

    This test confirms the inertness invariant. If a future change wires
    the shim into the router, this test fails — surfacing the activation
    as a deliberate decision the operator made.
    """
    router_path = _REPO / "substrate" / "dispatch" / "router.py"
    text = router_path.read_text()
    # The router can mention ``multi_cloud`` in comments, but it must
    # not IMPORT from it (which would imply runtime use).
    forbidden_patterns = [
        "from .multi_cloud import",
        "from substrate.dispatch.multi_cloud import",
        "import multi_cloud",
    ]
    for pat in forbidden_patterns:
        assert pat not in text, (
            f"router.py imports multi_cloud via '{pat}'. The SPR-10 "
            f"contract is that the registry+shim live in tree but are "
            f"NOT wired into the router yet. Activation requires "
            f"operator authorization."
        )
