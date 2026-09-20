"""A workflow step guarded on a path must name a path that can exist.

`substrate_floor.yml` carried:

    if [ -f substrate/invariants.py ]; then
      python -m substrate.invariants
    else
      echo "::notice::substrate/invariants.py absent on this branch — skipping"
    fi

`substrate/invariants` is a PACKAGE — a directory of TOMLs plus
`__init__.py` — so `-f` was permanently false. Every run printed a reassuring
notice for a condition that could never hold, and
`docs/substrate_quality_toolkit.md:177` told readers the workflow "runs ...
the invariants check". It ran nothing.

This is the session's recurring shape once more: a check whose negative
branch is indistinguishable from success. `|| true` announces itself in
review; `if [ -f <path-that-is-a-directory> ]` does not.

The test is deliberately narrow. It only looks at `[ -f X ]` and `[ -d X ]`
tests over repo-relative literal paths, and only asserts the path exists with
the kind being tested. A guard that survives is not thereby meaningful — it
has merely cleared the bar that it CAN match.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOWS = _ROOT / ".github" / "workflows"

# `-f X` where X is genuinely expected to be absent sometimes (generated
# artifacts, caches) belongs here WITH a reason. Empty: nothing qualifies yet.
ALLOWED_ABSENT: dict[str, str] = {}

_GUARD = re.compile(r"\[\s*-([fd])\s+\"?([A-Za-z0-9_./-]+)\"?\s*\]")


def _live_guards(path: Path) -> list[tuple[str, str]]:
    """Path guards in RUN script lines, not in comments.

    A correction that quotes the broken guard in a `#` comment is not itself
    a broken guard. Scanning raw text flagged this test's own explanation,
    which is the same mistake in miniature as the thing it checks.
    """
    out: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        out.extend(_GUARD.findall(line))
    return out


def _workflow_files() -> list[Path]:
    files = sorted(_WORKFLOWS.glob("*.y*ml"))
    assert len(files) >= 5, f"only {len(files)} workflows — check is vacuous"
    return files


def test_detector_matches_a_known_guard() -> None:
    """Guard the guard — against a FIXTURE, not against the repo.

    The first version asserted at least one live guard exists in the
    workflows. That held only while the broken one was still there: fixing it
    left zero, and the assertion then failed forever. A detector's
    correctness must not depend on the defect still being present.
    """
    sample = [
        '          if [ -f substrate/invariants.py ]; then',
        '          if [ -d some/dir ]; then',
        '        #   if [ -f quoted/in/a/comment.py ]',
    ]
    live = [ln for ln in sample if not ln.lstrip().startswith("#")]
    found = [m for ln in live for m in _GUARD.findall(ln)]
    assert ("f", "substrate/invariants.py") in found
    assert ("d", "some/dir") in found
    assert len(found) == 2, f"comment line leaked into the match: {found}"


def test_path_guards_reference_a_path_that_can_match() -> None:
    broken: list[str] = []
    for wf in _workflow_files():
        for kind, raw in _live_guards(wf):
            if raw.startswith(("$", "/", "~")) or "$" in raw:
                continue                      # runtime-expanded, not literal
            if raw in ALLOWED_ABSENT:
                continue
            target = _ROOT / raw
            word = "file" if kind == "f" else "directory"
            if not target.exists():
                # The case that actually shipped: `-f substrate/invariants.py`
                # where the package is `substrate/invariants` and no such .py
                # exists in ANY form. A kind-mismatch check alone misses this,
                # which the mutation test caught.
                broken.append(
                    f"{wf.name}: `[ -{kind} {raw} ]` but {raw} does not exist "
                    "at all — the test can never be true"
                )
            elif kind == "f" and target.is_dir():
                broken.append(
                    f"{wf.name}: `[ -f {raw} ]` but {raw} is a DIRECTORY — "
                    f"the test can never be true (it tests for a {word})"
                )
            elif kind == "d" and target.is_file():
                broken.append(
                    f"{wf.name}: `[ -d {raw} ]` but {raw} is a FILE — "
                    f"the test can never be true (it tests for a {word})"
                )
    assert not broken, (
        "workflow guards that can never match, so their step silently never "
        "runs:\n  " + "\n  ".join(broken)
    )
