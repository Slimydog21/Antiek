"""The `__main__` entry of tools/lints/cli_with_baseline is what CI executes.

The keystone job runs this module as `python -m tools.lints.cli_with_baseline
enforce <lint> ...` (six invocations across the write-lock async floor and the
resilience floor). The existing suites import the module and call `main(argv)`
directly, which covers the lint logic - but not the two lines CI actually runs:

    if __name__ == "__main__":
        sys.exit(main())

Those two lines can break (a moved module, a dropped `sys` import, an edited
guard) while every imported-main test stays green. This module exercises the
real entry as a subprocess and pins its observable contract:

    --help      -> exit 0, usage line on stdout
    no args     -> exit 2, "mode" named as the required argument
    bad lint    -> exit 2, and the seven CI-enforced lints remain valid choices

The last case matters most: if a lint is renamed or removed from the parser,
this reds before the keystone job does - and it names the missing choice rather
than reporting a green exit.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The lints the keystone job enforces (ci.yml, write-lock async floor +
# resilience floor). Pinned here so a parser edit surfaces in a test failure
# with a diff, not as a CI red three layers away.
CI_ENFORCED_LINTS = (
    "raw_read_only_connect",
    "blocking_write_in_async",
    "indirect_write_in_async",
    "unbounded_external_call",
    "seam_under_write_lock",
)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.lints.cli_with_baseline", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )


def test_help_exits_zero_and_prints_usage() -> None:
    proc = _run("--help")
    assert proc.returncode == 0, proc.stderr
    assert "usage: cli_with_baseline" in proc.stdout
    assert "{capture,enforce}" in proc.stdout


def test_no_args_is_an_error_that_names_the_missing_mode() -> None:
    proc = _run()
    assert proc.returncode == 2, (proc.returncode, proc.stderr)
    assert "required: mode" in proc.stderr


def test_every_ci_enforced_lint_is_a_valid_choice() -> None:
    """An unknown lint must fail by NAME, and the CI lints must not be among
    the unknowns: prove each is accepted by the parser by observing that the
    error for a definitely-unknown lint lists all of them as valid choices."""
    proc = _run("enforce", "definitely_not_a_lint")
    assert proc.returncode == 2, (proc.returncode, proc.stderr)
    # NOTE: argparse quotes choices on some Python versions and not others
    # (3.14 quotes, older does not), so assert on the bare name - never on
    # the surrounding quote characters.
    for lint in CI_ENFORCED_LINTS:
        assert lint in proc.stderr, (
            f"lint {lint!r} is no longer a parser choice; the keystone job "
            f"invokes it and would red. Parser said:\n{proc.stderr}"
        )
