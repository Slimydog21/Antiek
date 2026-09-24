"""The rights register's derivation rule (SPR-07 task 3).

``derived_content_class`` is the rights half of fork / merge / compress /
expand: a pure decision table from a source document's ``content_class`` to
the class a user-generated transformation of it must carry, refusing outright
for the two classes that carry no rights basis (``restricted_pending_opt_in``
and ``personal_reading``).

The table is pinned against ``VALID_CONTENT_CLASSES`` by count, not by a
hand-written list, so a class added later fails here instead of being
silently skipped.
"""

from __future__ import annotations

import inspect

import pytest

from substrate.constants import (
    GATED_DEFAULT_CONTENT_CLASS,
    PERSONAL_READING_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from substrate.rights import register
from substrate.rights.register import (
    DERIVED_CONTENT_CLASS_TABLE,
    VALID_CONTENT_CLASSES,
    DerivationRefusedError,
    derived_content_class,
)

REFUSED = frozenset({GATED_DEFAULT_CONTENT_CLASS, PERSONAL_READING_CONTENT_CLASS})

EXPECTED = {
    "public_domain": "user_owned",
    "user_owned": "user_owned",
    "user_public_contribution": "user_public_contribution",
    "opt_in_licensed": "opt_in_licensed",
    "source_declared_open": "source_declared_open",
}


def test_every_valid_class_has_exactly_one_row() -> None:
    """The spec's loop: one line per class, no KeyError, no None, and the
    row count equals len(VALID_CONTENT_CLASSES) so a new class cannot be
    silently skipped."""
    rows: dict[str, str] = {}
    for source in sorted(VALID_CONTENT_CLASSES):
        try:
            rows[source] = derived_content_class(source)
        except DerivationRefusedError as exc:
            rows[source] = f"REFUSED: {exc}"
    assert len(rows) == len(VALID_CONTENT_CLASSES)
    assert all(isinstance(v, str) and v for v in rows.values())
    assert frozenset(DERIVED_CONTENT_CLASS_TABLE) == VALID_CONTENT_CLASSES


@pytest.mark.parametrize(("source", "expected"), sorted(EXPECTED.items()))
def test_derivable_classes_map_as_the_table_says(source: str, expected: str) -> None:
    assert derived_content_class(source) == expected


def test_expected_table_covers_every_derivable_class() -> None:
    """If a derivable class is added to VALID_CONTENT_CLASSES, EXPECTED above
    must be extended by hand: the ruling is a rights decision, not a default."""
    assert frozenset(EXPECTED) | REFUSED == VALID_CONTENT_CLASSES


@pytest.mark.parametrize("source", sorted(REFUSED))
def test_no_rights_basis_classes_are_refused(source: str) -> None:
    with pytest.raises(DerivationRefusedError, match="no rights basis"):
        derived_content_class(source)


def test_refusal_is_a_value_error_but_distinct_from_a_typo() -> None:
    """Callers that catch ValueError see both; callers that want to tell a
    refusal from a misspelt class can."""
    assert issubclass(DerivationRefusedError, ValueError)
    with pytest.raises(ValueError, match="unrecognised content_class") as typo:
        derived_content_class("open_access")  # a source name, not a class
    assert not isinstance(typo.value, DerivationRefusedError)


def test_every_derived_class_is_servable_and_a_fixed_point() -> None:
    """A derivative always lands on a servable class, and a fork of a fork
    carries the same class as the fork."""
    for source in VALID_CONTENT_CLASSES - REFUSED:
        derived = derived_content_class(source)
        assert derived in SERVABLE_CONTENT_CLASSES, source
        assert derived_content_class(derived) == derived, source


def test_refused_classes_are_exactly_the_non_servable_ones() -> None:
    assert REFUSED == VALID_CONTENT_CLASSES - SERVABLE_CONTENT_CLASSES


def test_derivation_is_pure_no_connection_no_write() -> None:
    """No LockedConnection parameter and no write: the function must never
    become a second writer beside register_source_document."""
    params = inspect.signature(derived_content_class).parameters
    assert list(params) == ["source_content_class"]
    src = inspect.getsource(derived_content_class)
    for forbidden in ("execute(", "update_document_gate_columns", "LockedConnection", "con."):
        assert forbidden not in src, forbidden
    assert isinstance(DERIVED_CONTENT_CLASS_TABLE, register.MappingProxyType)
    with pytest.raises(TypeError):
        DERIVED_CONTENT_CLASS_TABLE["public_domain"] = "x"  # type: ignore[index]
