"""The deploy gate's context list must keep covering the merge gate's.

`tools/deploy/require_green.sh` keeps its ten contexts as a LITERAL list, on purpose:

    "Kept as a LITERAL list so a ruleset change that silently drops a context does not
     silently widen what may deploy."

That reasoning covers one direction only. If the RULESET gains a context and this list does
not, the deploy gate goes on checking a subset and reports green while a newly required
check is red -- **the copy cannot notice an ADDITION.** The literal list is the right shape
(require_green.sh runs on a deploy host, not a checkout, so it must not depend on reading a
file), but nothing asserted the relationship between the two.

`.github/required-checks.yml` is the repo's record of the ruleset, and
`tests/test_required_checks_contract.py` already holds that record to the workflows. This
module holds the third copy to the record.

Supserset, not equality: the list deliberately carries `pytest`, which the record documents
as an emitted-but-not-required "KNOWN GAP" -- the deploy gate is allowed to demand MORE than
the merge gate. It is not allowed to demand less.
"""

from __future__ import annotations

import pathlib
import re

import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "tools" / "deploy" / "require_green.sh"
_CONTRACT = _ROOT / ".github" / "required-checks.yml"


def _bash_list(name: str) -> list[str]:
    """The entries of a bash array literal, read from the script."""
    text = _SCRIPT.read_text(encoding="utf-8")
    match = re.search(rf"^{name}=\((.*?)^\)", text, re.S | re.M)
    assert match, f"no {name}=() array found in {_SCRIPT.relative_to(_ROOT)}"
    return [m.group(1) for m in re.finditer(r"'([^']+)'|\"([^\"]+)\"", match.group(1))]


def test_the_contract_file_is_where_it_is_expected() -> None:
    assert _CONTRACT.is_file(), (
        f"{_CONTRACT.relative_to(_ROOT)} is missing. Without it this test has nothing to "
        "compare against, and must fail loudly rather than skip."
    )


def test_require_green_covers_every_required_context() -> None:
    """The load-bearing assertion: no required context is missing from the list."""
    required = yaml.safe_load(_CONTRACT.read_text(encoding="utf-8"))["required"]
    listed = _bash_list("REQUIRED")
    missing = [c for c in required if c not in listed]
    assert not missing, (
        f"the ruleset requires {missing!r} but require_green.sh does not check them, so a "
        "deploy could proceed while those contexts are red. Add them to the REQUIRED array "
        f"in {_SCRIPT.relative_to(_ROOT)}."
    )


def test_the_list_may_demand_more_than_the_merge_gate() -> None:
    """Extras are allowed -- and recorded, so an extra is a decision and not a drift."""
    required = set(yaml.safe_load(_CONTRACT.read_text(encoding="utf-8"))["required"])
    extras = [c for c in _bash_list("REQUIRED") if c not in required]
    for ctx in extras:
        assert ctx == "pytest", (
            f"{ctx!r} is demanded by require_green.sh but is not a required context. That is "
            "permitted only when .github/required-checks.yml records why it is outside the "
            "fence; add the entry there or remove it here."
        )


def test_the_reader_finds_the_list_it_claims_to() -> None:
    """Guard the parser: if the array syntax changes, this must fail rather than return []."""
    listed = _bash_list("REQUIRED")
    assert len(listed) >= 9, (
        f"only {len(listed)} contexts parsed out of require_green.sh. Either the array was "
        "emptied -- in which case the deploy gate now checks nothing and reports success -- or "
        "the parser no longer matches its syntax."
    )


def test_a_dropped_context_would_be_caught() -> None:
    """Drive the failure: prove the assertion above can fail, rather than trusting it.

    The literal list is defended by a comment claiming a ruleset change cannot silently widen
    what may deploy. This shows the OTHER direction is caught, which the comment does not claim.
    """
    required = yaml.safe_load(_CONTRACT.read_text(encoding="utf-8"))["required"]
    simulated_list = [c for c in required if c != "keystone"]  # a context that is required
    missing = [c for c in required if c not in simulated_list]
    assert missing == ["keystone"], (
        "the comparison must report a required context absent from the list; if this stops "
        "holding, the real assertion above has stopped testing anything"
    )
