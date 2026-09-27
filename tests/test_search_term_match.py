"""A lexical match gate for cosine-ranked graph searches."""

from __future__ import annotations

from pathlib import Path

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.graph.search import query_match_terms, search


class _ConstantEmbedding:
    dimension = 2

    def encode(self, text: str) -> list[float]:
        return [1.0, 0.0]


class _NeverEncode(_ConstantEmbedding):
    def encode(self, text: str) -> list[float]:
        raise AssertionError("stopword-only queries must not be encoded")


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    init_database_at_path(path)
    with connect_write(path, purpose="seed-term-match") as con:
        for name, body in (
            ("art", "Art belongs in this gallery."),
            ("start", "A fresh start is possible."),
            ("cafe", "café au lait"),
        ):
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, document_type, "
                "content_class) VALUES (?, ?, 1, 'article', 'public_domain')",
                [f"doc-{name}", f"Title {name}"],
            )
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
                "embedding, token_count) VALUES (?, ?, 0, ?, [1.0, 0.0], 8)",
                [f"chunk-{name}", f"doc-{name}", body],
            )
    return path


def test_term_gate_filters_equal_cosine_scores(db_path: str) -> None:
    with connect_read(db_path) as con:
        unfiltered = search(con, "art", model=_ConstantEmbedding(), top_k=10)
        filtered = search(
            con, "art", model=_ConstantEmbedding(), top_k=10, require_term_match=True
        )

    assert {hit["chunk_id"] for hit in unfiltered["results"]} == {
        "chunk-art", "chunk-start", "chunk-cafe"
    }
    assert [hit["chunk_id"] for hit in filtered["results"]] == ["chunk-art"]


def test_non_ascii_term_edge_matches(db_path: str) -> None:
    with connect_read(db_path) as con:
        result = search(
            con, "Café", model=_ConstantEmbedding(), top_k=10, require_term_match=True
        )

    assert [hit["chunk_id"] for hit in result["results"]] == ["chunk-cafe"]


def test_only_stopwords_return_empty_without_encoding(db_path: str) -> None:
    with connect_read(db_path) as con:
        result = search(
            con, "the of and", model=_NeverEncode(), top_k=10, require_term_match=True
        )

    assert result == {
        "query": "the of and", "top_k": 10, "results": [], "node_matches": []
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("zzz-no-such-term", ["zzz-no-such-term"]),
        ("The Quantum, the quantum!", ["quantum"]),
        ("", []),
    ],
)
def test_query_match_terms(query: str, expected: list[str]) -> None:
    assert query_match_terms(query) == expected
