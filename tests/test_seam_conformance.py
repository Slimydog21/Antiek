"""Seam conformance (antiek-unified SPR-03 M7).

Every committed seam contract is a typed handoff with the four load-bearing
fields (from/to direction, entity reference, provenance ref, terminating
marker). These tests prove the shape holds, that the seam *event* payloads
mirror the seam contracts (so a handoff is reconstructable from the trajectory),
and that no seam carries a successor (the no-auto-loop invariant lives in the
absence of any next-handoff field).

SPR-08's e2e flywheel test composes these seams; this is the per-seam
conformance the gate rests on.
"""

from __future__ import annotations

from substrate.seams import (
    ALL_SEAMS,
    COMMITTED_SEAMS,
    PROVISIONAL_SEAMS,
    ReadToResearchSeam,
    ReadToWriteSeam,
    ResearchToReadSeam,
    SpeakToReadSeam,
    SpeakToWriteSeam,
    WriteToReadSeam,
    WriteToSpeakSeam,
    seam_status,
)
from substrate.seams.contracts import _SeamBase

# Field names that would let a seam name/schedule a successor — forbidden by
# the no-auto-loop rule. A seam advances the flywheel only on an explicit
# trigger; it never points at the next handoff.
_FORBIDDEN_SUCCESSOR_FIELDS = frozenset(
    {"next_seam", "successor", "successor_seam", "auto_fire", "then", "chain",
     "next_handoff", "follow_on"}
)


def test_seven_committed_no_provisional():
    assert len(COMMITTED_SEAMS) == 7
    assert len(PROVISIONAL_SEAMS) == 0
    assert WriteToSpeakSeam in COMMITTED_SEAMS
    assert set(ALL_SEAMS) == set(COMMITTED_SEAMS) | set(PROVISIONAL_SEAMS)


def test_every_seam_carries_the_load_bearing_fields():
    """Each seam has direction + entity ref + provenance ref + terminating
    marker — and nothing that inlines entity content."""
    for seam in ALL_SEAMS:
        fields = set(seam.model_fields.keys())
        for required in ("from_workflow", "to_workflow", "entity_id",
                         "entity_kind", "provenance_ref", "terminates"):
            assert required in fields, (seam.__name__, required)
        # No field literally named to inline the entity's content (a copy).
        assert "content" not in fields, seam.__name__
        assert "text" not in fields, seam.__name__


def test_direction_is_pinned_one_way():
    """Each seam fixes both endpoints with Literal defaults — direction is not
    a free field a caller can flip."""
    expected = {
        ResearchToReadSeam: ("research", "read"),
        ReadToResearchSeam: ("read", "research"),
        ReadToWriteSeam: ("read", "write"),
        WriteToReadSeam: ("write", "read"),
        SpeakToWriteSeam: ("speak", "write"),
        SpeakToReadSeam: ("speak", "read"),
        WriteToSpeakSeam: ("write", "speak"),
    }
    for seam, (frm, to) in expected.items():
        inst = _instantiate(seam)
        assert inst.from_workflow == frm
        assert inst.to_workflow == to


def test_no_seam_has_a_successor_field():
    """The no-auto-loop invariant: no seam carries a field that names or
    schedules a successor handoff."""
    for seam in ALL_SEAMS:
        fields = set(seam.model_fields.keys())
        leaked = fields & _FORBIDDEN_SUCCESSOR_FIELDS
        assert not leaked, (seam.__name__, leaked)
        # terminates is the explicit marker, fixed True.
        inst = _instantiate(seam)
        assert inst.terminates is True


def test_seam_status_helper():
    for seam in COMMITTED_SEAMS:
        assert seam_status(seam) == "committed"
    for seam in PROVISIONAL_SEAMS:
        assert seam_status(seam) == "provisional"


def test_seam_events_mirror_seam_contracts():
    """Each seam contract has a matching typed event payload (so a handoff is
    reconstructable from the trajectory) and the payloads carry no content
    field (no copy)."""
    from substrate.schemas import events as ev

    payload_map = {
        ResearchToReadSeam: ev.SeamResearchToReadPayload,
        ReadToResearchSeam: ev.SeamReadToResearchPayload,
        ReadToWriteSeam: ev.SeamReadToWritePayload,
        WriteToReadSeam: ev.SeamWriteToReadPayload,
        SpeakToWriteSeam: ev.SeamSpeakToWritePayload,
        SpeakToReadSeam: ev.SeamSpeakToReadPayload,
        WriteToSpeakSeam: ev.SeamWriteToSpeakPayload,
    }
    # The action_type each payload's class declares as its discriminator
    # default — read off the field default so we don't need to construct
    # payloads with required args.
    for payload in payload_map.values():
        pf = set(payload.model_fields.keys())
        # The handoff identity travels on both the contract and the event.
        for f in ("entity_id", "entity_kind", "provenance_ref", "terminates",
                  "from_workflow", "to_workflow"):
            assert f in pf, (payload.__name__, f)
        assert "content" not in pf and "text" not in pf, payload.__name__
        # Every seam action_type is registered in the typed union.
        action_default = payload.model_fields["action_type"].default
        assert action_default.value in ev.TYPED_PAYLOAD_ACTION_TYPES, payload.__name__


def _instantiate(seam: type[_SeamBase]) -> _SeamBase:
    """Build a minimal valid instance of a seam, filling required non-default
    fields with placeholder ids (references, never content)."""
    kwargs: dict[str, object] = {
        "entity_id": "node-abc123",
        "provenance_ref": "evt-prov-1",
    }
    extra = {
        ReadToResearchSeam: {"document_id": "doc-1"},
        ReadToWriteSeam: {"target_section_id": "sec-1"},
    }
    kwargs.update(extra.get(seam, {}))
    return seam(**kwargs)  # type: ignore[arg-type]
