"""GatedText and SourceRef, the one rights-bearing text shape (THREAD-CONTRACT
§1.2 rev 6, §2.10; signed rev 8.10). LB-9a, T-a9.

The shape is discriminated:

- ``served``: text is set and reason is null;
- ``cite_only``: text is null and reason is ``unresolved`` or ``not_servable``;
- ``withheld``: text is null and reason is any of the three.

Each case is checked in both directions: every legal combination builds, and
every illegal one is refused, so a validator that accepts everything and a
validator that refuses everything both fail here.
"""

from __future__ import annotations

import itertools
from typing import Any

import pytest
from pydantic import ValidationError

from substrate.schemas.gated_text import (
    GATE_REASONS,
    GATES,
    TEXT_ORIGINS,
    Gate,
    GatedText,
    GateReason,
    SourceAnchor,
    SourceRef,
    TextOrigin,
    most_restrictive,
)

REASONS: tuple[str | None, ...] = (None, *GATE_REASONS)


def _legal(gate: str, reason: str | None, has_text: bool) -> bool:
    """The signed discriminated shape, restated independently of the module."""
    if gate == "served":
        return has_text and reason is None
    if gate == "cite_only":
        return not has_text and reason in {"unresolved", "not_servable"}
    return not has_text and reason is not None


def test_vocabularies_are_exactly_the_signed_literals() -> None:
    assert GATES == ("served", "cite_only", "withheld")
    assert GATE_REASONS == ("unresolved", "not_servable", "lineage_unreconciled")
    assert TEXT_ORIGINS == ("source", "operator", "generated", "unsourced")


@pytest.mark.parametrize(
    ("gate", "reason", "has_text"),
    list(itertools.product(GATES, REASONS, (True, False))),
)
def test_gated_text_discriminated_shape_exhaustive(
    gate: str, reason: str | None, has_text: bool
) -> None:
    kwargs: dict[str, Any] = {
        "text": "Bridge decks fail at the joints." if has_text else None,
        "gate": gate,
        "reason": reason,
        "origin": "source",
        "source_refs": [],
    }
    if _legal(gate, reason, has_text):
        built = GatedText(**kwargs)
        assert built.gate == gate
        assert built.reason == reason
        assert (built.text is not None) is has_text
    else:
        with pytest.raises(ValidationError):
            GatedText(**kwargs)


def test_t_a9_named_rejections() -> None:
    """The three shape bugs the spec names, one by one."""
    with pytest.raises(ValidationError, match="served"):
        GatedText(text=None, gate="served", reason=None, origin="source")
    with pytest.raises(ValidationError, match="cite_only"):
        GatedText(text=None, gate="cite_only", reason="lineage_unreconciled", origin="source")
    with pytest.raises(ValidationError, match="withheld"):
        GatedText(text=None, gate="withheld", reason=None, origin="source")


def test_empty_string_is_set_text_not_absent_text() -> None:
    # ``text`` is set when it is a string; the validator keys on None, so an
    # empty served string is legal and an empty withheld string is not.
    assert GatedText(text="", gate="served", origin="operator").text == ""
    with pytest.raises(ValidationError):
        GatedText(text="", gate="withheld", reason="unresolved", origin="source")


@pytest.mark.parametrize("origin", TEXT_ORIGINS)
def test_every_signed_origin_is_accepted(origin: TextOrigin) -> None:
    assert GatedText(text="x", gate="served", origin=origin).origin == origin


@pytest.mark.parametrize(
    ("field", "value"),
    [("gate", "partial"), ("reason", "takedown"), ("origin", "model")],
)
def test_values_outside_the_signed_vocabulary_are_refused(field: str, value: str) -> None:
    kwargs: dict[str, Any] = {
        "text": None,
        "gate": "withheld",
        "reason": "unresolved",
        "origin": "source",
    }
    kwargs[field] = value
    with pytest.raises(ValidationError):
        GatedText(**kwargs)


def test_extra_fields_are_refused_on_both_models() -> None:
    with pytest.raises(ValidationError):
        GatedText(text="x", gate="served", origin="source", title="leak")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        SourceRef(kind="node", id="n1", gate="served", title="leak")  # type: ignore[call-arg]


def test_source_refs_default_empty_and_round_trip() -> None:
    ref = SourceRef(
        kind="chunk", id="c1", document_id="doc-1", gate="cite_only", reason="not_servable"
    )
    text = GatedText(
        text=None, gate="withheld", reason="not_servable", origin="source", source_refs=[ref]
    )
    again = GatedText.model_validate_json(text.model_dump_json())
    assert again == text
    assert GatedText(text="x", gate="served", origin="operator").source_refs == []


@pytest.mark.parametrize(("gate", "reason"), list(itertools.product(GATES, REASONS)))
def test_source_ref_gate_reason_discipline_exhaustive(gate: str, reason: str | None) -> None:
    # A ref carries no text, so its legality is the text-null half of the rule
    # for the non-served gates and "reason is null" for served.
    legal = {
        "served": reason is None,
        "cite_only": reason in {"unresolved", "not_servable"},
        "withheld": reason is not None,
    }[gate]
    document_id = None if gate == "withheld" else "doc-1"
    kwargs: dict[str, Any] = {
        "kind": "node",
        "id": "n1",
        "document_id": document_id,
        "gate": gate,
        "reason": reason,
    }
    if legal:
        assert SourceRef(**kwargs).gate == gate
    else:
        with pytest.raises(ValidationError):
            SourceRef(**kwargs)


def test_withheld_ref_is_opaque() -> None:
    """Nothing stands in for withheld text (§1.2): a withheld ref may not name
    the document or passage it came from."""
    anchor = SourceAnchor(document_id="doc-9", page_index=3)
    with pytest.raises(ValidationError, match="opaque"):
        SourceRef(kind="node", id="n1", document_id="doc-9", gate="withheld", reason="not_servable")
    with pytest.raises(ValidationError):
        SourceRef(kind="node", id="n1", anchor=anchor, gate="withheld", reason="not_servable")
    opaque = SourceRef(kind="node", id="n1", gate="withheld", reason="not_servable")
    assert opaque.document_id is None and opaque.anchor is None


def test_anchor_must_name_the_refs_own_document() -> None:
    anchor = SourceAnchor(document_id="doc-1", page_index=0)
    assert (
        SourceRef(kind="node", id="n1", document_id="doc-1", anchor=anchor, gate="served").anchor
        == anchor
    )
    with pytest.raises(ValidationError):
        SourceRef(
            kind="node",
            id="n1",
            document_id=None,
            anchor=anchor,
            gate="cite_only",
            reason="unresolved",
        )
    with pytest.raises(ValidationError):
        SourceRef(kind="node", id="n1", document_id="doc-2", anchor=anchor, gate="served")


def test_anchor_is_pointer_only() -> None:
    """A source ref is a pointer; the anchor carries no quote, prefix or
    suffix, so a cite-only or withheld ref can never carry the words."""
    with pytest.raises(ValidationError):
        SourceAnchor(document_id="doc-1", quote="the withheld words")  # type: ignore[call-arg]
    locator = {"start": 4, "end": 9, "text_sha256": "a" * 64}
    built = SourceAnchor.model_validate({"document_id": "doc-1", "source_locator": locator})
    assert built.source_locator is not None and built.source_locator.end == 9
    with pytest.raises(ValidationError):
        SourceAnchor.model_validate(
            {"document_id": "doc-1", "source_locator": {**locator, "end": 4}}
        )
    with pytest.raises(ValidationError):
        SourceAnchor.model_validate(
            {"document_id": "doc-1", "source_locator": {**locator, "text_sha256": "x"}}
        )


def test_models_are_frozen() -> None:
    text = GatedText(text="x", gate="served", origin="source")
    with pytest.raises(ValidationError):
        text.text = "y"


# ── most_restrictive: the mixed-sources rule (§1.2 rev 6) ────────────────


def test_most_restrictive_gate_order() -> None:
    assert most_restrictive([("served", None)]) == ("served", None)
    assert most_restrictive([("served", None), ("cite_only", "not_servable")]) == (
        "cite_only",
        "not_servable",
    )
    assert most_restrictive([("cite_only", "unresolved"), ("withheld", "not_servable")]) == (
        "withheld",
        "not_servable",
    )


def test_most_restrictive_reason_precedence_among_equal_gates() -> None:
    assert most_restrictive([("withheld", "not_servable"), ("withheld", "unresolved")]) == (
        "withheld",
        "unresolved",
    )
    assert most_restrictive([("withheld", "unresolved"), ("withheld", "lineage_unreconciled")]) == (
        "withheld",
        "lineage_unreconciled",
    )
    assert most_restrictive([("cite_only", "not_servable"), ("cite_only", "unresolved")]) == (
        "cite_only",
        "unresolved",
    )
    # The reason comes from the most restrictive GATE, never from a lower one.
    assert most_restrictive([("cite_only", "unresolved"), ("withheld", "not_servable")]) == (
        "withheld",
        "not_servable",
    )


def test_most_restrictive_is_order_independent() -> None:
    parts: list[tuple[Gate, GateReason | None]] = [
        ("served", None),
        ("withheld", "not_servable"),
        ("cite_only", "unresolved"),
        ("withheld", "unresolved"),
    ]
    answers = {most_restrictive(list(p)) for p in itertools.permutations(parts)}
    assert answers == {("withheld", "unresolved")}


def test_most_restrictive_of_nothing_is_refused() -> None:
    # No parts means no evidence; the caller decides (a synthesis with no
    # sources is withheld · unresolved), never a silent "served".
    with pytest.raises(ValueError):
        most_restrictive([])
