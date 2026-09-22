"""The detector's summary harvest must survive a colourised pytest.

``_run_pytest`` inherits the parent environment, so ``FORCE_COLOR`` or
``PY_COLORS`` makes pytest colour its output even through a pipe. The harvest
matches on a LINE PREFIX (``ERROR ``/``FAILED ``), so a colourised
``\x1b[31mERROR\x1b[0m ...`` matched nothing — while the ``N passed`` regex,
which searches rather than anchors, kept working.

That asymmetry is what made it dangerous: ``n_ran`` stayed correct while
``node_error_nodes`` was ALWAYS empty. No clean re-run ever ran, no node error
was ever credited as mutation-caused, and a mutant whose guard manifests as a
SETUP error reported ``no-tests`` — printed as "an unguarded load-bearing
line" — instead of ``killed``.

Measured with ``FORCE_COLOR=3``: the ``db_lock`` single-writer mutant reported
``n_tests=0`` while its selector's 7 tests all errored under mutation and all
passed clean. The most comprehensively guarded line in the repo read as the
only unguarded one, in the tool whose job is detecting exactly that.
"""
from __future__ import annotations

from tools import fake_gate_detector as fg

_PLAIN = """\
FAILED tests/test_thing.py::test_alpha - AssertionError: boom
ERROR tests/test_thing.py::test_beta - AttributeError: 'NoneType' has no attribute 'close'
ERROR tests/test_broken_import.py
2 failed, 3 passed in 1.23s
"""

_COLOURED = (
    "\x1b[31mFAILED\x1b[0m tests/test_thing.py::\x1b[1mtest_alpha\x1b[0m - AssertionError: boom\n"
    "\x1b[31mERROR\x1b[0m tests/test_thing.py::\x1b[1mtest_beta\x1b[0m - AttributeError: x\n"
    "\x1b[31mERROR\x1b[0m tests/test_broken_import.py\n"
    "\x1b[31m\x1b[1m2 failed\x1b[0m, \x1b[32m3 passed\x1b[0m\x1b[31m in 1.23s\x1b[0m\n"
)


def test_strip_ansi_removes_sgr_escapes():
    assert "\x1b[" not in fg._strip_ansi(_COLOURED)
    assert "ERROR tests/test_thing.py::test_beta" in fg._strip_ansi(_COLOURED)


def test_coloured_output_parses_identically_to_plain():
    """The whole point: colour must not change a single parsed field."""
    plain = fg._parse_pytest_output(_PLAIN)
    coloured = fg._parse_pytest_output(_COLOURED)
    assert coloured.node_error_nodes == plain.node_error_nodes
    assert coloured.failed_nodes == plain.failed_nodes
    assert coloured.n_ran == plain.n_ran
    assert coloured.n_failed_runtime == plain.n_failed_runtime
    assert coloured.collection_errors == plain.collection_errors


def test_node_errors_are_harvested_from_coloured_output():
    """The specific field that was always empty, and the reason a guarded line
    read as unguarded."""
    parsed = fg._parse_pytest_output(_COLOURED)
    assert parsed.node_error_nodes == ("tests/test_thing.py::test_beta",), (
        "a colourised node ERROR was not harvested — the blindness is back"
    )


def test_a_file_only_error_is_still_a_collection_error_not_a_node_error():
    """Control: the ``::``-less ERROR line must stay a collection error, or the
    fix would credit an import failure as a mutation-caused kill."""
    parsed = fg._parse_pytest_output(_COLOURED)
    assert parsed.collection_errors >= 1
    assert all("::" in n for n in parsed.node_error_nodes)


def test_the_runner_also_asks_pytest_not_to_colour():
    """Belt as well as braces: stripping is the fallback, --color=no is the fix.

    Either alone is sufficient today; both together mean a future edit that
    drops one does not silently restore the blindness.
    """
    assert "--color=no" in fg._PYTEST_BASE
