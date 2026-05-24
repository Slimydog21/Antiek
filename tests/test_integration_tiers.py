"""
Tests for ``scripts/check_integration_tiers.py``.

The test surface is intentionally split into two halves:

1. Unit tests against a synthetic mini-registry + tmp-repo fixture.
   These cover every code path (tier 0/1/2/3 rules, sunset-date
   handling, tier-allow markers, missing fields) without needing the
   real Antiek tree.

2. Integration tests against the real ``integrations.toml`` and the
   real codebase. These prove the live registry is consistent today
   and would catch a regression on the next push.

Why both: the unit tests don't need a green production state to pass
(they parametrize the logic), so a fresh checkout can verify the
checker is sound even if integrations.toml drifts.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e3-vouching.html
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from textwrap import dedent

import pytest

# Add scripts/ to sys.path so we can import the checker.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_integration_tiers as cit  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers: build a synthetic repo + registry
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content).lstrip("\n"), encoding="utf-8")


@pytest.fixture
def synth_repo(tmp_path: Path) -> Path:
    """Skeleton Antiek-like layout with the production layers under tmp."""
    for layer in ("substrate", "acquisition", "middleware", "tools", "tests", "scripts"):
        (tmp_path / layer).mkdir()
    _write(
        tmp_path / "integrations.toml",
        """
        [tier_zero_vendor]
        package = "vendor_zero"
        tier = 0
        voucher = ""
        vouched_at = "2026-05-24"
        justification = "spec only"

        [tier_one_vendor]
        package = "vendor_one"
        tier = 1
        voucher = "tester"
        vouched_at = "2026-05-24"
        justification = "prototype"

        [tier_two_vendor]
        package = "vendor_two"
        tier = 2
        voucher = "tester"
        vouched_at = "2026-05-24"
        sunset_date = "2099-12-31"
        prod_call_sites = ["acquisition/urls/client_vendor_two.py"]
        justification = "prod with sunset"

        [tier_three_vendor]
        package = "vendor_three"
        tier = 3
        voucher = "tester"
        vouched_at = "2026-05-24"
        justification = "adopted indefinitely"
        """,
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------


def test_load_registry_round_trip(synth_repo: Path) -> None:
    specs = cit.load_registry(synth_repo / "integrations.toml")
    assert len(specs) == 4
    by_name = {s.name: s for s in specs}
    assert by_name["tier_zero_vendor"].tier == 0
    assert by_name["tier_two_vendor"].prod_call_sites == ("acquisition/urls/client_vendor_two.py",)
    assert by_name["tier_three_vendor"].voucher == "tester"


def test_load_registry_rejects_tier_2_without_sunset(tmp_path: Path) -> None:
    bad = tmp_path / "registry.toml"
    bad.write_text(
        '[bad]\npackage = "bad"\ntier = 2\nvoucher = "x"\n'
        'vouched_at = "2026-05-24"\njustification = "no sunset"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sunset_date"):
        cit.load_registry(bad)


def test_load_registry_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cit.load_registry(tmp_path / "absent.toml")


# ---------------------------------------------------------------------------
# Tier rule enforcement
# ---------------------------------------------------------------------------


def test_tier_zero_import_in_prod_is_violation(synth_repo: Path, monkeypatch) -> None:
    """A tier-0 vendor imported anywhere in production layers is a violation."""
    monkeypatch.setattr(cit, "REPO_ROOT", synth_repo)
    monkeypatch.setattr(cit, "REGISTRY_FILE", synth_repo / "integrations.toml")
    _write(synth_repo / "substrate" / "uh_oh.py", "import vendor_zero\n")
    specs = cit.load_registry(synth_repo / "integrations.toml")
    violations, _ = cit.find_violations(specs, repo_root=synth_repo)
    assert any(
        "vendor_zero" in v.package and "Tier 0" in v.reason
        for v in violations
    )


def test_tier_zero_import_in_tools_is_also_violation(synth_repo: Path, monkeypatch) -> None:
    """Tier 0 forbids imports everywhere, including tools/."""
    monkeypatch.setattr(cit, "REPO_ROOT", synth_repo)
    _write(synth_repo / "tools" / "experiment.py", "import vendor_zero\n")
    specs = cit.load_registry(synth_repo / "integrations.toml")
    violations, _ = cit.find_violations(specs, repo_root=synth_repo)
    assert any(v.package == "vendor_zero" for v in violations)


def test_tier_one_import_in_tools_is_allowed(synth_repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(cit, "REPO_ROOT", synth_repo)
    _write(synth_repo / "tools" / "spike.py", "import vendor_one\n")
    specs = cit.load_registry(synth_repo / "integrations.toml")
    violations, _ = cit.find_violations(specs, repo_root=synth_repo)
    assert not any(v.package == "vendor_one" for v in violations)


def test_tier_one_import_in_substrate_is_violation(synth_repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(cit, "REPO_ROOT", synth_repo)
    _write(synth_repo / "substrate" / "premature.py", "import vendor_one\n")
    specs = cit.load_registry(synth_repo / "integrations.toml")
    violations, _ = cit.find_violations(specs, repo_root=synth_repo)
    assert any(
        v.package == "vendor_one" and "Tier 1" in v.reason
        for v in violations
    )


def test_tier_two_at_declared_call_site_is_allowed(synth_repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(cit, "REPO_ROOT", synth_repo)
    _write(
        synth_repo / "acquisition" / "urls" / "client_vendor_two.py",
        "from vendor_two import Client\n",
    )
    specs = cit.load_registry(synth_repo / "integrations.toml")
    violations, _ = cit.find_violations(specs, repo_root=synth_repo)
    assert not any(v.package == "vendor_two" for v in violations)


def test_tier_two_outside_declared_call_site_is_violation(synth_repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(cit, "REPO_ROOT", synth_repo)
    _write(synth_repo / "substrate" / "leak.py", "import vendor_two\n")
    specs = cit.load_registry(synth_repo / "integrations.toml")
    violations, _ = cit.find_violations(specs, repo_root=synth_repo)
    assert any(
        v.package == "vendor_two" and "outside declared prod_call_sites" in v.reason
        for v in violations
    )


def test_tier_two_sunset_in_the_past_is_violation(synth_repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(cit, "REPO_ROOT", synth_repo)
    monkeypatch.setattr(cit, "REGISTRY_FILE", synth_repo / "integrations.toml")
    # Rewrite the registry with a past sunset.
    (synth_repo / "integrations.toml").write_text(
        '[expired]\npackage = "vendor_two"\ntier = 2\n'
        'voucher = "x"\nvouched_at = "2020-01-01"\n'
        'sunset_date = "2020-12-31"\n'
        'prod_call_sites = []\n'
        'justification = "expired"\n',
        encoding="utf-8",
    )
    specs = cit.load_registry(synth_repo / "integrations.toml")
    violations, _ = cit.find_violations(specs, repo_root=synth_repo)
    assert any("sunset_date" in v.reason and "past" in v.reason for v in violations)


def test_tier_allow_marker_bypasses_check(synth_repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(cit, "REPO_ROOT", synth_repo)
    _write(
        synth_repo / "substrate" / "exception.py",
        "import vendor_zero  # tier-allow: scientifically-justified exception\n",
    )
    specs = cit.load_registry(synth_repo / "integrations.toml")
    violations, overrides = cit.find_violations(specs, repo_root=synth_repo)
    assert not any(v.package == "vendor_zero" for v in violations)
    assert any("scientifically-justified" in o for o in overrides)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_unregistered_package_is_ignored(synth_repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(cit, "REPO_ROOT", synth_repo)
    _write(synth_repo / "substrate" / "ok.py", "import unregistered_package\n")
    specs = cit.load_registry(synth_repo / "integrations.toml")
    violations, _ = cit.find_violations(specs, repo_root=synth_repo)
    assert not violations


def test_relative_imports_are_ignored(synth_repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(cit, "REPO_ROOT", synth_repo)
    _write(synth_repo / "substrate" / "sibling.py", "from . import foo\n")
    specs = cit.load_registry(synth_repo / "integrations.toml")
    violations, _ = cit.find_violations(specs, repo_root=synth_repo)
    assert not violations


def test_function_local_import_is_detected(synth_repo: Path, monkeypatch) -> None:
    """Tier 0 imports inside functions must still surface."""
    monkeypatch.setattr(cit, "REPO_ROOT", synth_repo)
    _write(
        synth_repo / "substrate" / "lazy.py",
        "def make():\n    import vendor_zero  # not at top-level\n    return vendor_zero\n",
    )
    specs = cit.load_registry(synth_repo / "integrations.toml")
    violations, _ = cit.find_violations(specs, repo_root=synth_repo)
    assert any(v.package == "vendor_zero" for v in violations)


def test_dotted_imports_split_at_top_level(synth_repo: Path, monkeypatch) -> None:
    """``from vendor_zero.submodule import X`` registers as vendor_zero."""
    monkeypatch.setattr(cit, "REPO_ROOT", synth_repo)
    _write(synth_repo / "substrate" / "dotted.py", "from vendor_zero.sub import X\n")
    specs = cit.load_registry(synth_repo / "integrations.toml")
    violations, _ = cit.find_violations(specs, repo_root=synth_repo)
    assert any(v.package == "vendor_zero" for v in violations)


# ---------------------------------------------------------------------------
# Overrides log
# ---------------------------------------------------------------------------


def test_overrides_log_is_written_when_overrides_exist(tmp_path: Path) -> None:
    cit.write_overrides_log(["entry1", "entry2"], log_path=tmp_path / "log.txt")
    text = (tmp_path / "log.txt").read_text(encoding="utf-8")
    assert "entry1" in text and "entry2" in text


def test_overrides_log_is_removed_when_no_overrides(tmp_path: Path) -> None:
    log = tmp_path / "log.txt"
    log.write_text("stale\n", encoding="utf-8")
    cit.write_overrides_log([], log_path=log)
    assert not log.exists()


# ---------------------------------------------------------------------------
# Live registry sanity
# ---------------------------------------------------------------------------


def test_live_registry_loads() -> None:
    """The real integrations.toml must parse without error."""
    specs = cit.load_registry()
    assert specs, "integrations.toml is empty?"
    # Distribution sanity — we expect roughly: a handful of Tier 0
    # spec-only, a few Tier 2/3, and many Tier 3 foundationals.
    tiers = [s.tier for s in specs]
    assert any(t == 0 for t in tiers), "expected at least one Tier 0 (spec only)"
    assert any(t == 3 for t in tiers), "expected at least one Tier 3 (foundational)"


def test_live_registry_passes_checker() -> None:
    """The real codebase must be consistent with the registry as of
    today's commit. A regression in either direction (new untracked
    import OR rebooked tier) surfaces here."""
    specs = cit.load_registry()
    violations, _ = cit.find_violations(specs, repo_root=REPO_ROOT)
    if violations:
        msg = ["integrations.toml is inconsistent with the codebase:"]
        msg.extend(f"  {v}" for v in violations[:20])
        if len(violations) > 20:
            msg.append(f"  ... and {len(violations) - 20} more")
        pytest.fail("\n".join(msg), pytrace=False)


def test_tier_3_packages_are_in_prod_vendors_allowlist() -> None:
    """Every Tier 3 integration must appear in
    ``substrate/integrations.py``'s ``PROD_VENDORS`` frozenset, so
    a future grep for "what counts as adopted" lands on the same set."""
    integrations_module = REPO_ROOT / "substrate" / "integrations.py"
    if not integrations_module.exists():
        pytest.skip("substrate/integrations.py not present on this branch")
    text = integrations_module.read_text(encoding="utf-8")
    specs = cit.load_registry()
    missing = [s.name for s in specs if s.tier == 3 and s.name not in text]
    assert not missing, (
        f"Tier 3 integrations missing from substrate/integrations.py PROD_VENDORS: {missing}"
    )
