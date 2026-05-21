"""Notebook surface tests (Sprint 18 Wedge 2 linchpin, master-spec §4.2)."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.notebooks import (
    VALID_BLOCK_TYPES,
    VALID_NOTEBOOK_CONTENT_CLASSES,
    append_block,
    create_notebook,
    get_notebook,
    list_notebooks,
    promote_to_public,
)


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="antiek-notebooks-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="notebooks_test")
    init_database(con)
    yield con
    con.close()


def test_valid_block_types_match_master_spec():
    """Master-spec §4.2 Sprint 18-19 upgrade enumerates the block
    types. Drift between code and schema CHECK constraint is a silent
    invariant break — both must agree."""
    assert VALID_BLOCK_TYPES == frozenset({
        "prose", "region_embed", "claim_card", "note",
        "question_card", "cross_doc_link", "chat_exchange",
        "master_md_section", "image", "latex",
    })


def test_valid_content_classes():
    assert VALID_NOTEBOOK_CONTENT_CLASSES == frozenset({
        "user_owned", "user_public_contribution",
    })


def test_create_notebook_defaults(db):
    nb_id = create_notebook(db, title="My research notebook")
    nb = get_notebook(db, nb_id)
    assert nb is not None
    assert nb.title == "My research notebook"
    assert nb.content_class == "user_owned"
    assert nb.owner_user_id == "__operator__"
    assert nb.blocks == []


def test_create_notebook_rejects_invalid_content_class(db):
    with pytest.raises(ValueError):
        create_notebook(db, title="X", content_class="garbage")


def test_append_blocks_preserves_order(db):
    nb_id = create_notebook(db, title="Test")
    b1 = append_block(db, nb_id, block_type="prose", content={"text": "Intro"})
    b2 = append_block(db, nb_id, block_type="claim_card", content={}, ref_id="claim-A")
    b3 = append_block(db, nb_id, block_type="note", content={}, ref_id="note-B")

    nb = get_notebook(db, nb_id)
    assert nb is not None
    assert [b.block_id for b in nb.blocks] == [b1, b2, b3]
    assert [b.block_type for b in nb.blocks] == ["prose", "claim_card", "note"]
    assert [b.ref_id for b in nb.blocks] == [None, "claim-A", "note-B"]
    assert nb.blocks[0].content_json == {"text": "Intro"}


def test_append_block_rejects_invalid_type(db):
    nb_id = create_notebook(db, title="Test")
    with pytest.raises(ValueError):
        append_block(db, nb_id, block_type="bogus", content={})


def test_block_index_starts_at_zero(db):
    nb_id = create_notebook(db, title="Test")
    append_block(db, nb_id, block_type="prose", content={})
    nb = get_notebook(db, nb_id)
    assert nb is not None
    assert nb.blocks[0].block_index == 0


def test_promote_to_public_changes_content_class(db):
    nb_id = create_notebook(db, title="Public-bound notebook")
    nb = get_notebook(db, nb_id)
    assert nb and nb.content_class == "user_owned"

    promote_to_public(db, nb_id)
    nb = get_notebook(db, nb_id)
    assert nb and nb.content_class == "user_public_contribution"


def test_list_notebooks_filtered_by_investigation(db):
    nb1 = create_notebook(db, title="A", investigation_id="inv-1")
    nb2 = create_notebook(db, title="B", investigation_id="inv-1")
    nb3 = create_notebook(db, title="C", investigation_id="inv-2")
    listed = list_notebooks(db, investigation_id="inv-1")
    ids = {nb.notebook_id for nb in listed}
    assert ids == {nb1, nb2}
    assert nb3 not in ids


def test_get_notebook_returns_none_for_missing(db):
    assert get_notebook(db, "nonexistent-id") is None


def test_block_content_json_round_trips(db):
    nb_id = create_notebook(db, title="Test")
    content = {
        "text": "A prose block with **markdown** and a region embed below.",
        "region_id": "reg-abc",
        "metadata": {"author_voice": True, "depth": 3},
    }
    block_id = append_block(db, nb_id, block_type="prose", content=content)
    nb = get_notebook(db, nb_id)
    assert nb is not None
    assert nb.blocks[0].block_id == block_id
    assert nb.blocks[0].content_json == content
