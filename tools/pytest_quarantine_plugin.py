"""Opt-in pytest plugin: quarantined tests run but intermittent failures do not red the gate.

Enable explicitly — does NOT alter default ``pytest tests/ -q`` behavior::

    python -m pytest -p tools.pytest_quarantine_plugin ...

Reads ``tests/quarantine.toml`` (override via ``--quarantine-toml`` ini option).
Applies ``xfail(strict=False)``-style gate isolation for entries with
``ignore_failures = true`` (the default for flap quarantines). Entries with
``ignore_failures = false`` still surface failures — quarantine handles flaps,
not consistent regressions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.flaky_quarantine import QuarantineEntry, load_quarantine

_QUARANTINE_BY_NODEID: dict[str, QuarantineEntry] = {}


def pytest_addoption(parser) -> None:
    parser.addini(
        "quarantine_toml",
        "Path to quarantine.toml ledger",
        default="tests/quarantine.toml",
    )


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "quarantine: test is quarantined (runs; gate may ignore intermittent failures)",
    )
    toml_path = Path(config.getini("quarantine_toml"))
    if not toml_path.is_absolute():
        toml_path = Path(config.rootpath) / toml_path
    entries = load_quarantine(toml_path)
    _QUARANTINE_BY_NODEID.clear()
    _QUARANTINE_BY_NODEID.update({e.nodeid: e for e in entries})


def _entry_for(item: pytest.Item) -> QuarantineEntry | None:
    return _QUARANTINE_BY_NODEID.get(item.nodeid)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    entry = _entry_for(item)
    if entry is not None:
        item.add_marker(pytest.mark.quarantine(reason=entry.reason))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call):
    outcome = yield
    report = outcome.get_result()
    if call.when != "call":
        return
    entry = _entry_for(item)
    if entry is None:
        return
    if report.failed and entry.ignore_failures:
        # xfail(strict=False)-style: intermittent flap failure does not red gate.
        report.outcome = "skipped"
        report.wasxfail = f"quarantined ({entry.reason}): {entry.evidence}"