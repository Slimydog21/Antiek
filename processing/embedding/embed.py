"""Embedding providers for chunks + node-label search.

Two concerns:

1. **The Protocol** — every consumer (search, chunking, wrestling
   bridge) accepts an ``EmbeddingProvider``. Tests inject a
   deterministic ``HashEmbedding`` so cosine similarity ranks
   predictably without loading a real model; production uses
   ``SentenceTransformerEmbedding`` which lazy-imports
   ``sentence-transformers``.

2. **The default provider** — process-singleton accessed via
   ``default_embedding_provider()``. Honors ``ANTIEK_EMBEDDING_MODEL``
   env var (model name) and ``ANTIEK_EMBEDDING_PROVIDER`` env var
   (``"sentence-transformers"`` or ``"hash"``). Falls back to hash
   when sentence-transformers isn't installed — so dev environments
   without the ~500MB model dependency still produce working chunks +
   working cosine SQL, they just don't get semantic matching.

The hash fallback is deliberate: it lets the wrestling bridge populate
the graph end-to-end on every dev machine without making
sentence-transformers a hard dependency of the substrate. When the
operator wants real semantic grounding, they ``pip install
sentence-transformers`` and the default provider upgrades.
"""

from __future__ import annotations

import hashlib
import math
import os
import sys
from typing import Protocol, cast

# Default dimension when nothing else is configured. Matches MiniLM-L6-v2
# (the Researchmaxx default in tier_rules + embeddings_meta).
DEFAULT_EMBEDDING_DIM = 384


class EmbeddingProvider(Protocol):
    """Minimal contract: encode a string to a fixed-length float vector.
    The contract matches ``substrate.graph.search.EmbeddingModel`` so
    they're interchangeable — chunking + search consume the same
    abstraction."""

    dimension: int

    def encode(self, text: str) -> list[float]: ...


def embedding_provider_name(provider: object) -> str:
    """Canonical provider family used for persisted embedding metadata."""
    if isinstance(provider, HashEmbedding):
        return "hash"
    if isinstance(provider, SentenceTransformerEmbedding):
        return "sentence-transformers"
    name = getattr(provider, "provider_name", None)
    if isinstance(name, str) and name:
        return name
    return f"{provider.__class__.__module__}.{provider.__class__.__qualname__}"


def embedding_model_name(provider: object) -> str:
    """Canonical model/config name used for persisted embedding metadata."""
    if isinstance(provider, HashEmbedding):
        return f"hash-dim-{provider.dimension}"
    model_name = getattr(provider, "_model_name", None)
    if isinstance(model_name, str) and model_name:
        return model_name
    for attr in ("model_name", "name"):
        value = getattr(provider, attr, None)
        if isinstance(value, str) and value:
            return value
    dimension = getattr(provider, "dimension", "unknown")
    return f"{provider.__class__.__name__}-dim-{dimension}"


def embedding_provider_fingerprint(provider: object) -> str:
    """Stable identity for vectors produced by ``provider``.

    Vector compatibility is stricter than dimension equality: same length but
    different providers/models can rank unrelated chunks. This fingerprint is
    stored with chunk embeddings and checked before vector search.
    """
    typed_provider = cast(EmbeddingProvider, provider)
    dimension = int(typed_provider.dimension)
    return (
        "embedding-provider-id-v1:"
        f"{embedding_provider_name(provider)}:"
        f"{embedding_model_name(provider)}:"
        f"{dimension}"
    )


# ---------------------------------------------------------------------------
# Hash-based fallback — deterministic, dependency-free
# ---------------------------------------------------------------------------


class HashEmbedding:
    """Deterministic embedding via SHA-256 → fixed-dim float vector.

    Properties:

    - Same input → identical output. Reproducible across processes.
    - Token-bag aware: each whitespace-separated lowercase word
      contributes to a fixed slot, so texts with shared vocabulary
      score higher on cosine similarity than texts without.
    - L2-normalized output, so cosine similarity is bounded [-1, 1].
    - Zero deps. Works in every Python env.

    NOT semantically meaningful — "quantum" and "qubit" map to
    different slots because they hash differently, even though they're
    semantic neighbors. Sufficient for substrate-level testing and
    dev rounding; not sufficient for production grounding.
    """

    def __init__(self, dimension: int = DEFAULT_EMBEDDING_DIM):
        self.dimension = int(dimension)

    def encode(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        if not text:
            vec[0] = 1.0
            return vec
        # Tokenize on whitespace; lowercase; one slot per token via
        # SHA-256-derived index. Weight by an inverse-token-count so
        # short texts aren't dominated by their first word.
        words = text.lower().split()
        if not words:
            vec[0] = 1.0
            return vec
        weight = 1.0 / math.sqrt(len(words))
        for word in words:
            h = hashlib.sha256(word.encode("utf-8")).digest()
            slot = int.from_bytes(h[:4], "big") % self.dimension
            vec[slot] += weight
        # L2-normalize for cosine-similarity-friendly output.
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        else:
            vec[0] = 1.0
        return vec


# ---------------------------------------------------------------------------
# sentence-transformers wrapper — production path
# ---------------------------------------------------------------------------


class SentenceTransformerEmbedding:
    """Wraps ``sentence-transformers``. Lazy-imports the package so the
    rest of processing/embedding/ works in environments where the
    model isn't installed.

    First call to ``encode`` loads the model (~90MB for MiniLM-L6-v2).
    Subsequent calls reuse the loaded instance — keep one provider
    per process."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "sentence-transformers not installed. Install via "
                "`pip install sentence-transformers` or use HashEmbedding."
            ) from exc
        self._model = SentenceTransformer(model_name)
        self.dimension = int(self._model.get_sentence_embedding_dimension() or DEFAULT_EMBEDDING_DIM)
        self._model_name = model_name
        # Truncation accounting (audit wave 3, #2). The model reads at most
        # ``max_seq_length`` word-pieces (256 for MiniLM-L6-v2) and SILENTLY
        # drops the rest, while chunk_markdown's default is 2000 words: a
        # long chunk is embedded by its opening words only, yet the vector
        # is stored, ranked and served as if it stood for the whole text.
        # Every encode counts; the first truncation in a process warns once
        # with the numbers; ``truncation_ratio`` exposes the running rate.
        self.encode_count = 0
        self.truncated_count = 0
        self._warned_truncation = False

    @property
    def max_seq_length(self) -> int | None:
        value = getattr(self._model, "max_seq_length", None)
        return int(value) if value else None

    @property
    def truncation_ratio(self) -> float:
        return (self.truncated_count / self.encode_count) if self.encode_count else 0.0

    def _token_count(self, text: str) -> int | None:
        tokenizer = getattr(self._model, "tokenizer", None)
        if tokenizer is None:
            return None
        try:
            ids = tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"]
        except Exception:  # noqa: BLE001 — accounting must never break encode
            return None
        return len(ids)

    def encode(self, text: str) -> list[float]:
        self.encode_count += 1
        window = self.max_seq_length
        n_tokens = self._token_count(text) if window else None
        if window and n_tokens is not None and n_tokens > window:
            self.truncated_count += 1
            if not self._warned_truncation:
                self._warned_truncation = True
                print(
                    f"[embed] {self._model_name}: input of {n_tokens} word-pieces exceeds "
                    f"the model window of {window}; the vector represents the first "
                    f"{window} only. Further truncations are counted, not printed "
                    f"(see SentenceTransformerEmbedding.truncation_ratio).",
                    file=sys.stderr,
                )
        vec = self._model.encode([text])[0]
        return [float(x) for x in vec]


# ---------------------------------------------------------------------------
# Default provider resolution
# ---------------------------------------------------------------------------


_DEFAULT_PROVIDER: EmbeddingProvider | None = None


def default_embedding_provider() -> EmbeddingProvider:
    """Return the process-singleton default provider.

    Resolution order:

    1. If ``ANTIEK_EMBEDDING_PROVIDER=hash``, always use HashEmbedding.
    2. If ``ANTIEK_EMBEDDING_PROVIDER=sentence-transformers`` (or unset)
       and ``sentence-transformers`` is importable: use
       ``SentenceTransformerEmbedding(model_name)`` where ``model_name``
       comes from ``ANTIEK_EMBEDDING_MODEL`` or defaults to
       ``all-MiniLM-L6-v2``.
    3. Otherwise: HashEmbedding fallback with a stderr breadcrumb so
       the operator knows semantic matching is off.

    The result is cached for the process lifetime. Reset via
    ``_reset_default_provider`` for tests."""
    global _DEFAULT_PROVIDER
    if _DEFAULT_PROVIDER is not None:
        return _DEFAULT_PROVIDER

    requested = os.environ.get("ANTIEK_EMBEDDING_PROVIDER", "sentence-transformers").lower()
    if requested == "hash":
        _DEFAULT_PROVIDER = HashEmbedding()
        return _DEFAULT_PROVIDER

    model_name = os.environ.get("ANTIEK_EMBEDDING_MODEL") or None
    if model_name is None:
        # Lineup binding (indexer actions): the operator's lineup assignment
        # for `graph_embedding` wins when it names the local embedding family
        # with an admissible model; otherwise the MiniLM default. The
        # embedding-metadata layer rejects incompatible query/stored pairs,
        # so a switch is loud, never silent.
        from substrate.dispatch.lineup_override import effective_model_for_action
        model_name = effective_model_for_action(
            "graph_embedding", provider_family="local_embedding", default="all-MiniLM-L6-v2",
        )
    try:
        _DEFAULT_PROVIDER = SentenceTransformerEmbedding(model_name)
    except RuntimeError as exc:
        # Fall back to HashEmbedding ONLY when the package is genuinely
        # absent. ``SentenceTransformerEmbedding.__init__`` raises
        # ``RuntimeError(...) from ImportError`` for that case, so the cause
        # is the discriminator. Every other RuntimeError — torch OOM, a corrupt
        # weight file, a device that failed to initialise — used to take this
        # same branch, print "sentence-transformers unavailable" (false), and
        # silently make every subsequent chunk a 384-dim HASH vector: the same
        # dimension as MiniLM, so nothing downstream could tell, and retrieval
        # degraded to "lexical/hash collisions, not meaning" (see
        # tools/reembed_chunks.py, which records this having happened in prod).
        # A provider that cannot be constructed for any other reason is an
        # error, not a configuration choice.
        if not isinstance(exc.__cause__, ImportError):
            raise
        import sys as _sys
        _sys.stderr.write(
            "antiek: sentence-transformers not installed; falling back to "
            "HashEmbedding. Install via `pip install sentence-transformers` "
            "to enable semantic search.\n"
        )
        _DEFAULT_PROVIDER = HashEmbedding()
    return _DEFAULT_PROVIDER


def set_default_embedding_provider(provider: EmbeddingProvider) -> None:
    """Override the default provider — tests use this to inject a
    deterministic stub, production code should not."""
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = provider


def _reset_default_provider() -> None:
    """Test-only. Clears the process-singleton so the next
    ``default_embedding_provider()`` call re-resolves."""
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = None
