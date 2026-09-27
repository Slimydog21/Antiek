"""Every ANTIEK_* variable a systemd unit sets must be read by some code.

A unit that sets a name no code reads is configuration that silently does
nothing. The continuous-research unit set ANTIEK_DAEMON_BUDGET_USD_PER_DAY
while orchestration/continuous/budget.py reads
ANTIEK_DAEMON_HOURLY_BUDGET_USD, so the §16 daily spend cap written in the
unit (or overridden in secrets.env, as the unit invites) was ignored; only
the coincidence that both said 5.0 hid it.

"Read" means the name appears as a quoted string literal in a non-test
Python file: a docstring or comment naming the variable does not count
(the daemon's own ``__main__`` docstring named the unread one).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "infrastructure" / "ansible" / "templates"
_SETTER = re.compile(r'^\s*Environment="?(ANTIEK_[A-Z0-9_]+)=', re.MULTILINE)


def unit_env_names(text: str) -> set[str]:
    return set(_SETTER.findall(text))


def is_read(name: str, sources: list[str]) -> bool:
    return any(f'"{name}"' in s or f"'{name}'" in s for s in sources)


def _non_test_python_sources() -> list[str]:
    files = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [(ROOT / f).read_text(errors="ignore") for f in files if not f.startswith("tests/")]


def test_matcher_on_planted_cases():
    unit = 'Environment="ANTIEK_A=1"\n# Environment="ANTIEK_COMMENTED=1"\nEnvironment=ANTIEK_B=2\n'
    assert unit_env_names(unit) == {"ANTIEK_A", "ANTIEK_B"}
    assert is_read("ANTIEK_A", ['os.environ.get("ANTIEK_A")'])
    assert is_read("ANTIEK_A", ["_ENV = 'ANTIEK_A'"])
    assert not is_read("ANTIEK_A", ["Config: ``ANTIEK_A`` sets the cap."])
    assert not is_read("ANTIEK_A", ['os.environ.get("ANTIEK_AB")'])


def test_every_antiek_variable_a_unit_sets_is_read_by_code():
    units = sorted(TEMPLATES.glob("*.service.j2"))
    assert units, "no systemd templates found; the guard would be vacuous"
    sources = _non_test_python_sources()
    unread = [
        f"{u.name}: {name}"
        for u in units
        for name in sorted(unit_env_names(u.read_text()))
        if not is_read(name, sources)
    ]
    assert not unread, (
        "systemd unit(s) set ANTIEK_* variables that no non-test code reads, so the "
        "setting silently does nothing: " + "; ".join(unread)
    )
