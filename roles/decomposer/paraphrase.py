"""Decomposer paraphrase check.

A sub-question whose embedding is within cosine similarity ≥ threshold
of the top-level question is treated as a restatement, not an
investigation — the decomposition has no value if it merely
paraphrases the input (spec §A.1 mitigation).

The threshold defaults to
``substrate.constants.DECOMPOSER_PARAPHRASE_COSINE_MAX`` (0.85). The
embedder is injected (``EmbeddingModel`` protocol from
``substrate/graph/search.py``); tests pass a deterministic stub.
``_load_default_embedder`` lazily constructs a
``SentenceTransformerEmbedding`` only when no embedder is supplied.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass

try:
    from ...constants import DECOMPOSER_PARAPHRASE_COSINE_MAX
    from ...graph.search import EmbeddingModel
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import DECOMPOSER_PARAPHRASE_COSINE_MAX  # type: ignore[no-redef]
    from substrate.graph.search import EmbeddingModel  # type: ignore[no-redef]


@dataclass(frozen=True)
class ParaphraseFlag:
    """One flagged sub-question. ``cosine`` is the similarity to the
    top-level question — ≥ threshold means it's too close."""

    index: int
    sub_question: str
    cosine: float

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "sub_question": self.sub_question,
            "cosine": self.cosine,
        }


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Plain Python cosine — keeps the module dependency-free for the
    test path that injects deterministic stub embeddings."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(dot / (na * nb))


def _load_default_embedder() -> EmbeddingModel:
    """Lazy default — only constructed when the caller didn't inject
    an embedder. Keeps test paths free of the sentence-transformers
    dependency."""
    from substrate.graph.search import SentenceTransformerEmbedding

    return SentenceTransformerEmbedding()


def check_paraphrases(
    question: str,
    sub_questions: Sequence[str],
    *,
    threshold: float = DECOMPOSER_PARAPHRASE_COSINE_MAX,
    embedder: EmbeddingModel | None = None,
) -> list[ParaphraseFlag]:
    """Return the list of flagged sub-questions (cosine ≥ threshold).

    Empty list ⇒ decomposition is acceptable. The threshold is the
    inclusive lower bound (a sub-question AT the threshold IS
    flagged) — matches the upstream's ``>= threshold`` semantics."""
    if not sub_questions:
        return []
    emb = embedder or _load_default_embedder()
    q_vec = emb.encode(question)
    flagged: list[ParaphraseFlag] = []
    for i, sq in enumerate(sub_questions):
        sq_vec = emb.encode(sq)
        cos = _cosine(q_vec, sq_vec)
        if cos >= threshold:
            flagged.append(ParaphraseFlag(index=i, sub_question=sq, cosine=cos))
    return flagged


def regenerate_instruction(flagged: Sequence[ParaphraseFlag]) -> str:
    """Build the operator-facing instruction string for a Decomposer
    regeneration pass. Empty string when no flags."""
    if not flagged:
        return ""
    bullets = "\n".join(
        f"  - [#{f.index}] (cos={f.cosine:.3f}) {f.sub_question!r}"
        for f in flagged
    )
    return (
        "Your previous decomposition contained sub-questions that paraphrase "
        "the top-level question. Regenerate the decomposition. The following "
        "sub-questions were flagged and must be replaced with investigations "
        "that surface dimensions requiring independent evidence:\n"
        f"{bullets}"
    )
