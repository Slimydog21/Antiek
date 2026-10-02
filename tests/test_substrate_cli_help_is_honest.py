"""The unified CLI must not advertise what it cannot run.

Written because it did. `antiek --help` listed seven subcommands as available
while all seven failed: six raised ModuleNotFoundError for modules shipping with
an unmerged branch, and `lint` pointed at a script that is not in the tree. The
two test modules that would have caught it are skipped by design (they
importorskip the same missing modules), so CI was green on a help screen that
could not be true.

A help screen that cannot be true is the same defect as a gate that cannot fail:
detection that never reaches a decision, on the user's side of the boundary.
"""

from __future__ import annotations

import pytest

from substrate.cli.__main__ import SUBCOMMANDS, _load_failure, _print_usage, main


def test_help_marks_every_unloadable_subcommand(capsys) -> None:
    """The regression this file exists for.

    For each advertised verb, if it cannot load, the help must say so. This fails
    against the version that printed a fixed list, whatever the state of the tree.
    """
    _print_usage()
    usage = capsys.readouterr().out

    for name in SUBCOMMANDS:
        failure = _load_failure(name)
        if failure is None:
            assert "UNAVAILABLE -- " not in usage.split(name, 1)[1][:200], (
                f"{name} loads but is marked unavailable"
            )
        else:
            assert name in usage
            after = usage.split(name, 1)[1][:220]
            assert "UNAVAILABLE" in after, f"{name} cannot load and the help does not say so"


def test_an_unloadable_subcommand_exits_three_not_a_traceback(capsys) -> None:
    """Distinct from an unknown verb (2): 3 means "known, cannot load here"."""
    for name in SUBCOMMANDS:
        if _load_failure(name) is None:
            continue
        assert main([name]) == 3

        err = capsys.readouterr().err
        assert "unavailable on this installation" in err
        assert "Traceback" not in err
        return

    pytest.skip("every subcommand loads in this environment")


def test_an_unknown_subcommand_is_still_a_usage_error(capsys) -> None:
    assert main(["definitely-not-a-verb"]) == 2
    assert "unknown subcommand" in capsys.readouterr().err


def test_bare_invocation_prints_help_and_succeeds(capsys) -> None:
    assert main([]) == 0
    assert "usage: antiek" in capsys.readouterr().out
