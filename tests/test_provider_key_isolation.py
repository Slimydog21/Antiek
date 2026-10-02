"""No test reaches a live provider because the developer happens to have keys.

`register_default_providers()` registers every provider whose key resolves, and
a registered real provider OUTRANKS a stub the test installed. On CI no key
exists, so stubs win. On a developer machine they do not.

Measured 2026-09-22: `tests/test_loop_one_orchestrator.py` — whose own docstring
says "the fixtures stub every role's provider so the orchestrator can run" —
dispatched to the live `api.mimo.xiaomi.com` and failed, while passing in CI.
`env -u XIAOMI_API_KEY` made it pass. Three tests behaved that way.

That is worse than a flake: a unit test billing a live API key and egressing
real data. The `_isolate_provider_keys` autouse fixture closes it; these tests
keep it closed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import PROVIDER_KEY_ENV_VARS

_ROOT = Path(__file__).resolve().parents[1]
_BOOTSTRAP = _ROOT / "substrate" / "dispatch" / "providers" / "bootstrap.py"

# `resolve_provider_key("<handle>", "<ENV_VAR>")` — the single seam every
# provider factory uses to find a credential.
_RESOLVE = re.compile(r'resolve_provider_key\(\s*"[a-z_]+"\s*,\s*"([A-Z0-9_]+)"\s*\)')


def _env_vars_bootstrap_reads() -> set[str]:
    return set(_RESOLVE.findall(_BOOTSTRAP.read_text(encoding="utf-8")))


def test_the_source_scan_finds_something() -> None:
    """Anti-vacuity: if the regex stops matching, every check below passes.

    A drift guard that silently matches nothing is worse than no guard — it
    reports the hole is closed while measuring an empty set.
    """
    found = _env_vars_bootstrap_reads()
    assert len(found) >= 5, (
        f"parsed only {sorted(found)} from {_BOOTSTRAP.name}; the "
        f"resolve_provider_key call shape changed and this guard went blind"
    )


def test_the_isolated_set_covers_every_key_bootstrap_reads() -> None:
    """Adding a provider must not silently reopen the egress hole."""
    missing = _env_vars_bootstrap_reads() - set(PROVIDER_KEY_ENV_VARS)
    assert not missing, (
        f"bootstrap.py resolves {sorted(missing)} but PROVIDER_KEY_ENV_VARS in "
        f"tests/conftest.py does not clear it — a test run by a developer "
        f"holding that key would reach the live provider"
    )


@pytest.mark.parametrize("var", PROVIDER_KEY_ENV_VARS)
def test_every_provider_key_is_absent_inside_a_test(var: str) -> None:
    """The fixture is autouse, so this must hold with no opt-in."""
    assert os.environ.get(var) is None, (
        f"{var} is visible inside a test; _isolate_provider_keys did not run or was overridden"
    )


def test_the_fixture_really_removes_a_key_that_was_set() -> None:
    """Prove the fixture ACTS rather than passing because the env was already clean.

    Runs a child pytest with a key exported. Without the fixture the inner test
    would see it; with the fixture it must not. This is the mutation the other
    assertions cannot perform on themselves.
    """
    probe = _ROOT / "tests" / "_provider_key_probe.py"
    probe.write_text(
        "import os\n\n\n"
        "def test_key_is_not_visible() -> None:\n"
        "    assert os.environ.get('XIAOMI_API_KEY') is None\n",
        encoding="utf-8",
    )
    try:
        env = {**os.environ, "XIAOMI_API_KEY": "probe-value-not-a-real-key"}
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(probe), "-q", "-p", "no:cacheprovider"],
            cwd=_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            "a child pytest run with XIAOMI_API_KEY exported still saw the key "
            f"inside the test — the fixture is not removing it:\n{proc.stdout[-2000:]}"
        )
    finally:
        probe.unlink(missing_ok=True)
