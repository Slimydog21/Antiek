"""Deterministic offline NLI entailment backend (Groundedness Gate SPR-02).

A ``EntailmentBackend`` (same shape as ``lexical_entailment_score``) backed by
a small DeBERTa-v3 NLI cross-encoder. Scores whether a claim is **entailed**
by its cited chunks using a model trained on entailment — so it catches the
class a token-overlap proxy is blind to: a "densely-cited hallucination" that
reuses many surface tokens from its evidence (high lexical overlap) yet is
false via a subject-swap, causal inversion, unsupported superlative,
unit-class confusion, aggregation error, or dropped precondition.

CI-safety + determinism (the load-bearing properties, both tested):

- **Deterministic.** The model runs in eval/no-grad mode with no sampling;
  fixed published weights. Same ``(claim, chunk_texts)`` → byte-identical
  ``(score, rationale)`` every run (proven by ``test_nli_backend_deterministic``).
- **CI-safe (no live call at inference time).** The model is a local Hugging
  Face cache; inference never makes an outbound API request. The dependency
  (``sentence-transformers``/``transformers``/``torch``) is already an
  Antiek optional extra (``embedding``), so adding this backend introduces no
  new heavyweight dependency. If the model is not cached and the host is
  offline, the backend raises ``NLIModelUnavailable`` rather than silently
  falling back to a weaker scorer — a missing model is a hard stop, not a
  quiet gate-weakening (rigor #5 defensibility).
- **Aggregation = MAX over cited chunks.** A claim is supported if ANY cited
  chunk entails it — matches the lexical backend's union-of-chunks semantics.
- **Lazy + cached.** The model loads once per process (module-level cache),
  mirroring ``substrate/graph/search.py::SentenceTransformerEmbedding``.

The live ``_llm_judge_backend`` (an OPTIONAL structured LLM judge over the
Hermes dispatch path) is UNTOUCHED here — it stays off-by-default and out of
CI for A/B only. This backend is the deterministic alternative to it.
"""

from __future__ import annotations

import functools
import hashlib
from collections.abc import Sequence
from typing import Any

# The model is pinned (not "latest") so the determinism guarantee is bound to
# specific published weights. Bumping it is a deliberate act that must
# re-record the harness number (a model bump silently changes the gate).
DEFAULT_NLI_MODEL = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"

# A sibling scorer id to DEFAULT_SCORER_ID = "groundedness-lexical-v1".
NLI_SCORER_ID = "groundedness-nli-v1"


class NLIModelUnavailable(RuntimeError):
    """Raised when the NLI model cannot be loaded (not cached + offline, or
    the optional deps are absent). A missing model is a HARD STOP — the
    backend never silently falls back to lexical (that would quietly weaken
    the gate exactly where a new case enters). Callers that want graceful
    degradation must catch this explicitly and choose their own fallback."""


# ---------------------------------------------------------------------------
# The backend — module-level model cache so a process loads it once.
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=4)
def _load_nli_pipeline(model_name: str) -> Any:
    """Load (and memoize) the Hugging Face text-classification pipeline for
    ``model_name``. Raises ``NLIModelUnavailable`` on any failure so the
    caller gets a clear, un-catchable-by-accident signal."""
    try:
        import torch  # noqa: F401  (imported for its no_grad context)
        from transformers import pipeline
    except ImportError as exc:  # pragma: no cover — depends on env
        raise NLIModelUnavailable(
            f"transformers/torch not installed; cannot load NLI backend "
            f"({model_name!r}). Install the `embedding` extra or pass a "
            "different backend."
        ) from exc

    torch.set_grad_enabled(False)  # eval mode, process-wide
    try:
        return pipeline(
            "text-classification",
            model=model_name,
            tokenizer=model_name,
            top_k=None,  # return scores for ALL three labels (entail/neutral/contradict)
        )
    except Exception as exc:  # network error, model not cached, corrupt weights
        raise NLIModelUnavailable(
            f"could not load NLI model {model_name!r}: {exc}. If offline, "
            f"pre-cache the model (`huggingface-cli download {model_name}`) "
            "or use the lexical backend explicitly."
        ) from exc


def _score_pair(premise: str, hypothesis: str, pipe: Any) -> dict[str, float]:
    """Score one (premise→hypothesis) NLI pair; return a dict with keys
    entailment/neutral/contradiction in [0,1]. Deterministic: the pipeline
    runs under no_grad with no sampling."""
    import torch

    with torch.no_grad():
        out = pipe(
            {"text": premise, "text_pair": hypothesis},
            truncation=True,
            max_length=512,
            top_k=None,
        )
    # transformers pipeline returns a list of {label, score}; normalize the
    # label spelling (some models emit 'entailment' vs 'ENTAILMENT').
    scores: dict[str, float] = {}
    if out and isinstance(out, list):
        for d in out:
            label = str(d.get("label", "")).lower()
            try:
                score = float(d.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            scores[label] = max(scores.get(label, 0.0), score)
    # Ensure the canonical three keys exist (default 0.0 if the model dropped one).
    return {
        "entailment": scores.get("entailment", 0.0),
        "neutral": scores.get("neutral", 0.0),
        "contradiction": scores.get("contradiction", 0.0),
    }


def nli_entailment_score(
    claim: str,
    chunk_texts: Sequence[str],
    *,
    model_name: str = DEFAULT_NLI_MODEL,
) -> tuple[float, str]:
    """NLI cross-encoder entailment backend.

    Returns ``(score in [0,1], rationale)`` where ``score`` is the MAX
    entailment probability over the cited chunks (a claim is supported if
    ANY cited chunk entails it — union semantics, matching the lexical
    backend). ``claim`` is the hypothesis; each cited chunk is a premise.

    No cited chunks → 0.0 (a claim with no evidence cannot be grounded —
    identical to the lexical backend's floor).

    Deterministic: fixed model weights, eval/no_grad, no sampling. Proven by
    ``test_nli_backend_deterministic`` (runs twice, asserts byte-identical).

    CI-safe: inference makes no outbound call; the model is a local HF cache.
    Raises ``NLIModelUnavailable`` if the model is absent + offline, rather
    than silently falling back.
    """
    chunk_blob = "\n".join(t for t in chunk_texts if t and t.strip())
    if not chunk_texts or not chunk_blob.strip():
        return 0.0, "no cited evidence — claim cannot be grounded"

    pipe = _load_nli_pipeline(model_name)
    best = 0.0
    best_detail = ""
    for chunk in chunk_texts:
        if not chunk or not chunk.strip():
            continue
        s = _score_pair(chunk, claim, pipe)
        ent = s["entailment"]
        if ent > best:
            best = ent
            best_detail = (
                f"entail={ent:.3f} neutral={s['neutral']:.3f} "
                f"contradict={s['contradiction']:.3f}"
            )
    best = max(0.0, min(1.0, best))
    return best, f"max entailment over {len(chunk_texts)} chunk(s): {best_detail}"


def make_nli_backend(
    *,
    model_name: str = DEFAULT_NLI_MODEL,
) -> Any:
    """Return a callable matching ``EntailmentBackend`` (
    ``(claim, chunk_texts) -> (score, rationale)``) bound to ``model_name``.
    Use this to pass the NLI backend explicitly as ``backend=`` to
    ``score_claim`` / ``score_synthesis_groundedness`` / the harness, without
    changing any default.

    Mirrors ``make_llm_judge_backend``'s shape so the two optional backends
    plug in symmetrically.
    """
    def _backend(claim: str, chunk_texts: Sequence[str]) -> tuple[float, str]:
        return nli_entailment_score(claim, chunk_texts, model_name=model_name)
    _backend.__name__ = "nli_backend"
    return _backend


def input_fingerprint(claim: str, chunk_texts: Sequence[str], model_name: str) -> str:
    """A stable content hash of (model, claim, chunks) — used by callers that
    want to record/replay verdicts for full auditability (the recorded-replay
    alternative the spec mentions; not required for the live NLI backend but
    exposed so a future audit pass can key on it)."""
    h = hashlib.sha256(usedforsecurity=False)
    h.update(model_name.encode("utf-8"))
    h.update(b"\x1e")
    h.update(claim.encode("utf-8"))
    h.update(b"\x1e")
    for c in chunk_texts:
        h.update(c.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()
