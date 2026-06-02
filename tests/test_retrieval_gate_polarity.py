"""RG-01 polarity agreement — chunk denylist vs book-serve allowlist.

The chunk-search gate excludes ``_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES``
(denylist). Public book serve keys on ``SERVABLE_CONTENT_CLASSES`` (allowlist).
Different polarity; no withheld class may also be servable.
"""

from __future__ import annotations

from substrate.constants import SERVABLE_CONTENT_CLASSES
from substrate.graph.retrieval_gate import (
    PERSONAL_ONLY_CONTENT_CLASSES,
    _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES,
)


def test_non_privileged_excluded_is_superset_of_personal_only():
    assert PERSONAL_ONLY_CONTENT_CLASSES <= _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES


def test_non_privileged_excluded_disjoint_from_servable():
    overlap = _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES & SERVABLE_CONTENT_CLASSES
    assert overlap == frozenset(), (
        f"withheld chunk classes must not intersect servable allowlist: {overlap!r}"
    )


def test_restricted_only_predicate_would_leak_personal_reading():
    """Fail-before pin: RESTRICTED-only SQL is NOT equivalent to the canonical union.

    This test bites if someone reverts ``search()`` to filter only
    ``RESTRICTED_CONTENT_CLASSES`` — the pre-RG-01 VSS/get_chunk mistake.
    """
    from substrate.graph.retrieval_gate import RESTRICTED_CONTENT_CLASSES

    assert "personal_reading" not in RESTRICTED_CONTENT_CLASSES
    assert "personal_reading" in _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES