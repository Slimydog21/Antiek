"""The merge gate must be recorded, and the record must match the workflows.

Ruleset `main-gate-integrity` matches required checks by NAME. Rename a job and
its requirement stops resolving — silently, with nothing in the diff to show
it. Before `.github/required-checks.yml` existed, `grep -rF
required_status_checks` returned zero hits in this repo: the configuration
deciding whether anything could merge lived only as remote state.

These tests cannot read the live ruleset (that needs admin scope from CI), so
they pin the half that is checkable: every name declared required must actually
be emitted by a workflow job, and every emitted check must be accounted for —
either inside the fence or documented as deliberately outside it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_CONTRACT = _ROOT / ".github" / "required-checks.yml"
_WORKFLOWS = _ROOT / ".github" / "workflows"


def _contract() -> dict:
    return yaml.safe_load(_CONTRACT.read_text(encoding="utf-8"))


def _emitted_check_names() -> set[str]:
    """Every check-run name the workflows can produce.

    A check run is named by the job's ``name:`` when set, else its id. A matrix
    job expands its name once per matrix value, which is how ``pytest shard 0
    of 4`` .. ``3 of 4`` reach the ruleset as four distinct contexts.
    """
    names: set[str] = set()
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_id, job in (doc.get("jobs") or {}).items():
            name = job.get("name", job_id)
            matrix = ((job.get("strategy") or {}).get("matrix")) or {}
            list_keys = [k for k, v in matrix.items() if isinstance(v, list)]
            if list_keys and "${{" in str(name):
                for value in matrix[list_keys[0]]:
                    names.add(re.sub(r"\$\{\{[^}]*\}\}", str(value), str(name)))
            else:
                names.add(str(name))
    return names


def test_the_contract_file_exists_and_is_populated() -> None:
    """Not vacuous: an empty or missing file would make every test below pass."""
    assert _CONTRACT.is_file(), f"{_CONTRACT.relative_to(_ROOT)} is missing"
    data = _contract()
    assert data.get("required"), "the required list is empty"
    assert len(data["required"]) >= 5, (
        f"only {len(data['required'])} required checks recorded; the ruleset "
        "had 8 when this test was written — did the list get truncated?"
    )


def test_workflows_emit_a_plausible_number_of_checks() -> None:
    """Not vacuous: if the YAML walk broke, every name check would pass."""
    emitted = _emitted_check_names()
    assert len(emitted) >= 10, (
        f"found only {len(emitted)} check names across "
        f"{len(list(_WORKFLOWS.glob('*.yml')))} workflows — the job-name walk "
        "has broken and the assertions below are meaningless"
    )
    assert "tsc" in emitted, "expected the tsc job; the walk is wrong"


@pytest.mark.parametrize("required", _contract()["required"])
def test_every_required_check_is_actually_emitted(required: str) -> None:
    """A required name no job produces never resolves, and blocks main forever."""
    emitted = _emitted_check_names()
    assert required in emitted, (
        f"ruleset main-gate-integrity requires {required!r}, but no workflow "
        f"job emits that name. Either a job was renamed without updating the "
        f"ruleset — in which case that gate is now unhooked — or the ruleset "
        f"names a check that will never report, which blocks every PR on a "
        f"context that cannot resolve. Emitted names: {sorted(emitted)}"
    )


def test_every_emitted_check_is_accounted_for() -> None:
    """An omission from the fence must be written down, not merely absent.

    This is the test that would have caught `pytest` sitting outside the
    ruleset while running 17 invariant gates.
    """
    data = _contract()
    accounted = set(data["required"]) | set(
        (data.get("emitted_but_not_required") or {}).keys()
    )
    unaccounted = sorted(_emitted_check_names() - accounted)
    assert not unaccounted, (
        f"these checks are emitted by a workflow but appear in neither list "
        f"in {_CONTRACT.relative_to(_ROOT)}: {unaccounted}. Add each to "
        "`required` (and to the ruleset) or to `emitted_but_not_required` "
        "with a reason. A gate that is silently outside the fence is how "
        "`pytest` came to run 17 invariant checks that could not block a merge."
    )


def test_exemptions_carry_a_reason() -> None:
    for name, entry in (_contract().get("emitted_but_not_required") or {}).items():
        why = (entry or {}).get("why", "")
        assert len(why) >= 40, (
            f"{name!r} is exempted from the merge gate with a "
            f"{len(why)}-character reason. An exemption has to be argued."
        )
