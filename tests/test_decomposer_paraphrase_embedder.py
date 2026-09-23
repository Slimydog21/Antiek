"""The decomposer's paraphrase check uses the process's configured embedder.

``roles/decomposer/paraphrase._load_default_embedder`` constructed a real
sentence-transformers model unconditionally, ignoring
``ANTIEK_EMBEDDING_PROVIDER`` and the operator's lineup binding for the
embedding model, which every other embedding path honours through
``processing.embedding.embed.default_embedding_provider``. In tests that set
``ANTIEK_EMBEDDING_PROVIDER=hash`` it still loaded MiniLM (~20 s), which put
tests/test_loop_one_orchestrator.py's happy path at 21 s of a 30 s terminal
wait: a load-dependent flake in a required pytest shard.
"""

from __future__ import annotations

import pytest

import processing.embedding.embed as embed
from roles.decomposer import paraphrase


@pytest.fixture(autouse=True)
def _fresh_default_provider():
    embed._reset_default_provider()
    yield
    embed._reset_default_provider()


def test_default_embedder_honours_the_configured_provider(monkeypatch):
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    emb = paraphrase._load_default_embedder()
    assert isinstance(emb, embed.HashEmbedding)
    assert emb is embed.default_embedding_provider()


def test_paraphrase_check_runs_on_the_configured_provider(monkeypatch):
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    # An identical sub-question is a paraphrase under any embedder.
    flags = paraphrase.check_paraphrases("what limits qubit coherence",
                                         ["what limits qubit coherence"])
    assert len(flags) == 1
