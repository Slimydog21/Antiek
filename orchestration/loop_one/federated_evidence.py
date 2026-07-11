"""Configured federated-corpus evidence provider for Loop One Phase 2."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping

from acquisition.core_cache import CoreSnapshotError
from acquisition.openalex_cache import OpenAlexSnapshotError
from acquisition.research_corpus_mounts import (
    MountConfigurationError,
    load_research_corpus_mounts,
)
from acquisition.s2_cache import S2SnapshotError
from substrate.corpus_contract import CorpusContractError
from substrate.corpus_evidence import render_chunks_block, select_evidence_spans
from substrate.corpus_federation import FederatedCorpus

FEDERATED_MOUNTS_ENV = "ANTIEK_RESEARCH_CORPUS_MOUNTS_JSON"
_MAX_CONFIG_BYTES = 16_384
_CACHE_ERRORS = (
    CoreSnapshotError,
    OpenAlexSnapshotError,
    S2SnapshotError,
    CorpusContractError,
    OSError,
)


def _configured_mounts(raw: str) -> list[str]:
    if not raw or len(raw.encode("utf-8")) > _MAX_CONFIG_BYTES:
        raise MountConfigurationError("mount configuration is empty or oversized")
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise MountConfigurationError("mount configuration must be JSON") from exc
    if type(decoded) is not list or any(type(value) is not str for value in decoded):
        raise MountConfigurationError("mount configuration must be a JSON string array")
    return decoded


def render_configured_federated_evidence(
    query: str,
    *,
    top_k: int,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Return configured federated chunks, or ``None`` when not configured.

    Presence of the environment variable is an explicit authority choice.
    Invalid configuration or snapshots therefore return a stable, citation-
    empty failure block rather than silently falling back to the graph corpus.
    """
    source = os.environ if environ is None else environ
    raw = source.get(FEDERATED_MOUNTS_ENV)
    if raw is None:
        return None
    try:
        mounts = load_research_corpus_mounts(_configured_mounts(raw))
        spans = select_evidence_spans(
            FederatedCorpus(mounts),
            query,
            max_spans=top_k,
        )
    except MountConfigurationError:
        return "(configured federated corpus unavailable: invalid configuration)"
    except _CACHE_ERRORS:
        return "(configured federated corpus unavailable: cache contract failed)"
    return render_chunks_block(spans)
