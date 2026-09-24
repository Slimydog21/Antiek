"""The provenance-pointer walker reads key shapes, not a field list.

Export gates clear content against every row it stood on. The rows are named
in free-form JSON (node metadata, event payloads) under fields writers keep
adding, so ``collect_pointers`` finds them by the shape of the key at any
depth. These tests pin the shape rule in both directions: every pointer-shaped
key is read, whatever its prefix and nesting, and keys that name events or
nodes are not mistaken for sources.
"""

from __future__ import annotations

import json

import pytest

from substrate.provenance.pointers import (
    collect_child_investigations,
    collect_parent_investigations,
    collect_pointers,
    collect_syntheses,
    evidence_payload_intact,
    pointer_kind,
)


@pytest.mark.parametrize(
    ("key", "kind"),
    [
        ("chunk_id", "chunk"),
        ("chunk_ids", "chunk"),
        ("source_chunk_ids", "chunk"),
        ("supporting_chunk_ids", "chunk"),
        ("backup_chunk_ids", "chunk"),
        ("Cited_Chunk_IDs", "chunk"),
        ("document_id", "document"),
        ("source_document_id", "document"),
        ("corpus_document_ids", "document"),
        ("doc_id", "document"),
        ("alt_doc_ids", "document"),
        ("edge_id", "edge"),
        ("path_edge_ids", "edge"),
        ("source_id", "source"),
        ("source_ids", "source"),
    ],
)
def test_pointer_shaped_keys_are_read(key, kind):
    assert pointer_kind(key) == kind


@pytest.mark.parametrize(
    "key",
    [
        "source_event_ids", "source_node_id", "node_id", "event_id",
        "investigation_id", "chunks_block", "document", "chunkid",
        "rechunk_idx", "docs", "sourced", "resource_id", "unit_id",
    ],
)
def test_other_keys_are_not_pointers(key):
    assert pointer_kind(key) is None


def test_every_pointer_is_found_at_any_depth_in_first_seen_order():
    value = {
        "source_document_id": "d1",
        "supporting_claims": [
            {"claim": "x", "chunk_ids": ["c1", "c2"], "edge_ids": ["e1"]},
            {"claim": "y", "chunk_ids": ["c2", ["c3"]], "edge_ids": []},
        ],
        "nested": {"deeper": [{"backup_chunk_ids": "c4"}]},
        "source_event_ids": ["evt-1"],
        "chunk_id": None,
        "edge_id": "",
    }
    assert collect_pointers(value) == [
        ("document", "d1"),
        ("chunk", "c1"), ("chunk", "c2"), ("edge", "e1"),
        ("chunk", "c3"), ("chunk", "c4"),
    ]


def test_pointers_inside_serialized_json_are_found():
    # Metadata embedded as a JSON string, and a list written as text.
    value = {
        "metadata": json.dumps({"source_chunk_ids": ["c9"]}),
        "doc_ids": '["d7", "d8"]',
    }
    assert collect_pointers(value) == [
        ("chunk", "c9"), ("document", "d7"), ("document", "d8"),
    ]


def test_a_non_string_id_is_kept_not_dropped():
    # An id written as a number is still a pointer; the resolver decides
    # whether it names a row, and one that names none withholds.
    assert collect_pointers({"chunk_id": 42, "doc_id": 1.5}) == [
        ("chunk", "42"), ("document", "1.5"),
    ]


def test_child_investigations_and_syntheses_are_found_by_key_shape():
    row = {
        "synthesis_id": "s1",
        "payload": {
            "child_investigation_id": "inv-c1",
            "steps": [{"launched_investigation_id": "inv-c2", "archived_synthesis_ids": ["s2"]}],
            "parent_investigation_id": "inv-p",
        },
    }
    assert collect_child_investigations(row) == ["inv-c1", "inv-c2"]
    assert collect_syntheses(row) == ["s1", "s2"]


def test_parent_investigations_are_found_by_key_shape():
    # The backward link a spawned child records in its own log: the spawn
    # event's and the start request's parent_investigation_id, at any depth.
    row = {
        "payload": {
            "parent_investigation_id": "inv-p1",
            "lineage": [{"parent_investigation_ids": ["inv-p2"]}],
            "child_investigation_id": "inv-c",
            "parent_event_id": "ev-1",
        },
    }
    assert collect_parent_investigations(row) == ["inv-p1", "inv-p2"]


@pytest.mark.parametrize(("action_type", "payload", "intact"), [
    # A typed event that records evidence must carry what its schema requires.
    ("evidence.retrieve.delivered", {"sub_question": "q", "answer": "a", "supporting_claims": []}, True),
    ("evidence.retrieve.delivered", {}, False),
    ("evidence.retrieve.delivered", None, False),
    ("evidence.retrieve.delivered", {"sub_question": "q"}, False),
    ("evidence.retrieve.delivered", "not an object", False),
    # A key its schema does not declare is ignored, not a defect.
    ("evidence.retrieve.delivered", {"sub_question": "q", "answer": "a", "writer_extra": 1}, True),
    # Events that carry no evidence pointers are not judged here: the research
    # runners write lineage events their typed models would reject.
    ("investigation.start_requested", {"sub_question": "q"}, True),
    ("investigation.spawned_from", {"parent_investigation_id": "p", "sub_question": "q"}, True),
    ("graph.node_inserted", {}, True),
    ("some.untyped_action", None, True),
])
def test_evidence_payload_intact(action_type, payload, intact):
    assert evidence_payload_intact(action_type, payload) is intact
