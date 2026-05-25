"""Tests for the conformance harness (antiek-unified SPR-01 M7).

The harness is the mechanism that makes "no product forks a contract"
enforceable in CI (SPR-08 wires it). It must pass against real in-tree
implementations and fail *loudly, with a useful diff* against a divergent fake.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from substrate.contracts import (
    NoteTakerOutputContract,
    assert_conformance,
    verify_conformance,
)
from substrate.contracts.conformance import ConformanceError


def test_real_extracted_note_conforms():
    # The live note-taker output dataclass must satisfy the contract — this is
    # the proof the contract mirrors reality, not an invented shape.
    from roles.note_taker.parser import ExtractedNote

    result = verify_conformance(ExtractedNote, NoteTakerOutputContract)
    assert result.ok, result.diff
    assert result.missing == ()


def test_divergent_fake_fails_with_diff():
    @dataclass
    class FakeNote:
        note_id: str
        text: str
        # missing: confidence, source_event_ids

    result = verify_conformance(FakeNote, NoteTakerOutputContract)
    assert not result.ok
    assert set(result.missing) == {"confidence", "source_event_ids"}
    # the diff must name the missing fields so a CI log is actionable
    assert "confidence" in result.diff and "source_event_ids" in result.diff
    assert "FakeNote" in result.diff


def test_assert_conformance_raises_on_divergence():
    @dataclass
    class FakeNote:
        note_id: str

    with pytest.raises(ConformanceError) as exc:
        assert_conformance(FakeNote, NoteTakerOutputContract)
    assert "missing fields" in str(exc.value)


def test_superset_conforms():
    @dataclass
    class RicherNote:
        note_id: str
        text: str
        confidence: str
        source_event_ids: tuple
        extra_field: str = "ok"  # extra fields are allowed (a superset conforms)

    result = verify_conformance(RicherNote, NoteTakerOutputContract)
    assert result.ok, result.diff
    assert "extra" in result.diff.lower()


def test_dict_impl_conforms():
    record = {
        "note_id": "n1",
        "text": "x",
        "confidence": "high",
        "source_event_ids": ("e1",),
    }
    assert verify_conformance(record, NoteTakerOutputContract).ok


def test_contract_instance_conforms_to_itself():
    note = NoteTakerOutputContract(
        note_id="n1", text="x", confidence="high", source_event_ids=("e1",)
    )
    assert verify_conformance(note, NoteTakerOutputContract).ok
