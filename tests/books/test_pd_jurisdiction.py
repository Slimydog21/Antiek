"""A PD assertion limited to a non-serving jurisdiction is not PD for us
(audit wave 3, #12). One rule, three gates, every case through all three."""

from __future__ import annotations

import pytest

import acquisition.books.internet_archive as ia
import acquisition.books.library_of_congress as loc
import acquisition.books.public_domain as pdm
from acquisition.books.pd_jurisdiction import non_serving_pd_qualification

GATED = [
    "Public domain in Canada",
    "Public Domain in the United Kingdom only",
    "public domain (in Australia)",
    "Public domain outside the United States",
    "public domain outside of the U.S.",
    "public domain in the EU",
    "Public domain in Freedonia",  # a place this module has never heard of
    "Public domain in Canada; may be under copyright elsewhere",
]
PD = [
    "Public domain in the United States",
    "Public domain in the USA and Canada",
    "public domain worldwide",
    "public domain outside Canada",  # everywhere except Canada includes the US
    "public domain",
    "Public Domain Mark 1.0",
    "no known copyright restrictions",
]


def _verdicts(text: str) -> tuple[str, str, str]:
    a = "PD" if ia.ia_rights_input({"rights": text})[1] else "gated"
    b = "PD" if loc.loc_rights_input({"rights": text})[1] else "gated"
    c = "PD" if pdm._archive_pd_basis({"rights": text}, "item-x") else "gated"
    return a, b, c


@pytest.mark.parametrize("text", GATED)
def test_non_serving_qualification_gates_all_three(text: str) -> None:
    assert non_serving_pd_qualification(text) is not None, text
    assert _verdicts(text) == ("gated", "gated", "gated"), (text, _verdicts(text))


@pytest.mark.parametrize("text", PD)
def test_unqualified_or_serving_jurisdiction_still_pd(text: str) -> None:
    assert non_serving_pd_qualification(text) is None, text
    assert _verdicts(text) == ("PD", "PD", "PD"), (text, _verdicts(text))


def test_rule_names_the_place_it_gated_on() -> None:
    assert non_serving_pd_qualification("Public domain in Canada") == "Canada"
    assert (non_serving_pd_qualification("public domain outside the U.S.") or "").startswith("outside the U.S")


def test_hedged_copyright_stays_with_the_existing_conservative_reject() -> None:
    # The rule itself accepts a US-qualified assertion; the gates still reject
    # this string on their PRE-EXISTING "may be copyrighted" hedge. That reject
    # is theirs, deliberately conservative, and not this rule's to relax.
    text = "Public domain in the U.S.; may be copyrighted elsewhere"
    assert non_serving_pd_qualification(text) is None
    assert _verdicts(text) == ("gated", "gated", "gated")
