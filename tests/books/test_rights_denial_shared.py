"""One deny-first rule, three gates, no drift (audit wave 3 design record,
"also noted"). Before: public_domain.py's copyright-claim regex lacked the
hedged forms, Internet Archive lacked "rights restricted", Library of
Congress lacked "not public domain" — the same record was PD or not
depending on which connector found it."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import acquisition.books.internet_archive as ia
import acquisition.books.library_of_congress as loc
import acquisition.books.public_domain as pdm
from acquisition.books.rights_denial import pd_denied_reason

ROOT = Path(__file__).resolve().parents[2]


def _verdicts(text: str) -> tuple[str, str, str]:
    a = "PD" if ia.ia_rights_input({"rights": text})[1] else "gated"
    b = "PD" if loc.loc_rights_input({"rights": text})[1] else "gated"
    c = "PD" if pdm._archive_pd_basis({"rights": text}, "item-x") else "gated"
    return a, b, c


# Each of these was accepted by at least one gate before the copies were unified.
DENIED = [
    # hedged copyright claims with NO negative phrase in them — only the
    # hedge regex catches these, and archive.org's copy lacked it
    ("Public domain; may be protected by copyright elsewhere", "copyright claim"),
    ("Public domain scan; likely copyright in the EU", "copyright claim"),
    ("Public domain (possibly still copyright-protected abroad)", "copyright claim"),
    # negative phrases the gates disagreed on
    ("Public domain; may be under copyright elsewhere", "negative phrase"),  # 'under copyright'
    ("Public domain. Rights restricted.", "negative phrase"),                # IA + archive lacked it
    ("Not public domain", "negative phrase"),                                # LoC lacked it
    ("This work is not in the public domain", "negative phrase"),
    ("Public domain in Canada", "non-serving jurisdiction"),
    ("© 1998 The Author. Public domain scan.", "copyright claim"),
]
ACCEPTED = ["public domain", "Public Domain Mark 1.0", "no known copyright restrictions", "public domain worldwide"]


@pytest.mark.parametrize(("text", "rule"), DENIED)
def test_denied_on_all_three_gates_with_the_same_reason(text: str, rule: str) -> None:
    reason = pd_denied_reason(text.lower())
    assert reason is not None and rule in reason, (text, reason)
    assert _verdicts(text) == ("gated", "gated", "gated"), (text, _verdicts(text))


@pytest.mark.parametrize("text", ACCEPTED)
def test_control_unqualified_pd_still_accepted_on_all_three(text: str) -> None:
    assert pd_denied_reason(text.lower()) is None
    assert _verdicts(text) == ("PD", "PD", "PD"), (text, _verdicts(text))


def test_no_gate_carries_its_own_copy_of_the_deny_lists() -> None:
    """The drift guard: the deny lists live in rights_denial.py only."""
    private = re.compile(r"^_(?:ARCHIVE_)?(?:NEGATIVE_TOKENS|NEGATED_PD_RE|COPYRIGHT_CLAIM_RE)\b", re.M)
    for rel in ("acquisition/books/internet_archive.py", "acquisition/books/library_of_congress.py", "acquisition/books/public_domain.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert not private.search(src), f"{rel} re-grew its own deny list"
        assert "pd_denied_reason(" in src, f"{rel} does not call the shared rule"
