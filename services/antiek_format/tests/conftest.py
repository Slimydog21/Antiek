"""Shared fixtures for services.antiek_format tests."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


from services.antiek_format import WriterInput, ensure_keypair


@pytest.fixture
def antiek_db(tmp_path) -> Iterator[str]:
    """Per-test DuckDB path. Used for keypair storage. We do NOT
    initialise any substrate schema here — the keypair table is
    creation-on-demand by ``ensure_keypair``."""
    path = str(tmp_path / "antiek-format-test.duckdb")
    yield path


@pytest.fixture
def keypair(antiek_db: str):
    return ensure_keypair("user-test", db_path=antiek_db)


@pytest.fixture
def fixed_created_at() -> datetime:
    return datetime(2026, 5, 21, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def simple_notebook_input(fixed_created_at) -> WriterInput:
    """A minimal but realistic notebook: one highlight card + one
    prose paragraph. Used by the writer + reader + projector tests."""
    return WriterInput(
        notebook_id="nbk-fixture-simple-1",
        user_id="user-test",
        document_id="doc-fixture-1",
        parent_document_id="doc-fixture-1",
        content_class="notebook",
        title="Fixture: simple",
        content_tiptap={
            "type": "doc",
            "content": [
                {
                    "type": "antiek_highlight_card",
                    "attrs": {
                        "block_id": "blk-fixture-h",
                        "passage_text": "An important sentence.",
                        "operator_framing": "Why this matters.",
                    },
                },
                {
                    "type": "antiek_prose",
                    "attrs": {"block_id": "blk-fixture-p"},
                    "content": [
                        {"type": "text", "text": "A follow-up paragraph."}
                    ],
                },
            ],
        },
        blocks_index=[
            {
                "block_id": "blk-fixture-h",
                "block_type": "highlight_card",
                "position": 1.0,
                "source_event_ids": ["evt-1"],
            },
            {
                "block_id": "blk-fixture-p",
                "block_type": "prose",
                "position": 2.0,
                "source_event_ids": [],
            },
        ],
        edges=[],
        audio_blobs={},
        created_at=fixed_created_at,
        format_version=1,
    )


@pytest.fixture
def complex_notebook_input(fixed_created_at) -> WriterInput:
    """A notebook touching every block type, plus a voice-block audio
    payload + one user-asserted edge. Used to stress round-trip and
    determinism."""
    audio_bytes = b"\x00\x01\x02\x03RIFF-fake-audio-bytes\xff\xee" * 10
    return WriterInput(
        notebook_id="nbk-fixture-complex-1",
        user_id="user-test",
        document_id="doc-fixture-2",
        parent_document_id="doc-fixture-2",
        content_class="notebook",
        title="Fixture: complex (all six block types)",
        content_tiptap={
            "type": "doc",
            "content": [
                {
                    "type": "antiek_highlight_card",
                    "attrs": {
                        "block_id": "blk-h",
                        "passage_text": "Highlighted passage with unicode: 注釈.",
                    },
                },
                {
                    "type": "antiek_voice_block",
                    "attrs": {
                        "block_id": "blk-v",
                        "duration_seconds": 34,
                        "transcript": "voice transcript text here",
                    },
                },
                {
                    "type": "antiek_ai_qa",
                    "attrs": {
                        "block_id": "blk-q",
                        "question": "What's the central claim?",
                        "answer": "The central claim is X.",
                        "attribution": "doc-fixture-2 §3",
                    },
                },
                {
                    "type": "antiek_cite_link",
                    "attrs": {
                        "block_id": "blk-c",
                        "label": "See ref §4",
                        "target_url": "/wrestle/doc-fixture-2?chunk=ck-99",
                    },
                },
                {
                    "type": "antiek_cross_doc_jump",
                    "attrs": {
                        "block_id": "blk-x",
                        "label": "related doc",
                        "target_document_id": "doc-fixture-99",
                    },
                },
                {
                    "type": "antiek_prose",
                    "attrs": {"block_id": "blk-p"},
                    "content": [{"type": "text", "text": "prose continuation."}],
                },
            ],
        },
        blocks_index=[
            {"block_id": "blk-h", "block_type": "highlight_card", "position": 1.0,
             "source_event_ids": ["evt-1"]},
            {"block_id": "blk-v", "block_type": "voice_block", "position": 2.0,
             "source_event_ids": ["evt-2"]},
            {"block_id": "blk-q", "block_type": "ai_qa", "position": 3.0,
             "source_event_ids": ["evt-3", "evt-4"]},
            {"block_id": "blk-c", "block_type": "cite_link", "position": 4.0,
             "source_event_ids": ["evt-5"]},
            {"block_id": "blk-x", "block_type": "cross_doc_jump", "position": 5.0,
             "source_event_ids": ["evt-6"]},
            {"block_id": "blk-p", "block_type": "prose", "position": 6.0,
             "source_event_ids": []},
        ],
        edges=[
            {
                "edge_id": "edg-fixture-1",
                "from_block_id": "blk-h",
                "to_content_hash": "a" * 64,
                "to_document_id": "doc-fixture-99",
                "kind": "supports",
                "asserted_at": "2026-05-21T12:30:00+00:00",
                "operator_note": "supporting evidence",
            }
        ],
        audio_blobs={"blk-v": audio_bytes},
        created_at=fixed_created_at,
        format_version=1,
    )
