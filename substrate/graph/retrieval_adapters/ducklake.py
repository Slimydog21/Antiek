"""SPR-05 SPIKE adapter — DuckLake object-store-backed retrieval.

STATUS: spike. NOT on the default retrieval path. Reachable only via an
explicit ``make_substrate(kind="ducklake")`` / ``--substrate ducklake``.

Design intent: DuckLake (the DuckDB lakehouse extension over Parquet on an
object store) is steelmanned for a FUTURE multi-user / shared-public graph
(master-spec §13.2 two-graph pivot) — object-store reach the single-file
DuckDB does not have. For the single-operator phase the graph is one local
DuckDB file, so this adapter has no production justification yet; it exists to
be MEASURED on the same harness, not adopted.

Extension/credential gating: DuckLake requires the ``ducklake`` extension AND
object-store credentials (e.g. an S3-compatible endpoint + keys). WITHOUT them
this adapter records ``status: "skipped — no credentials"`` and every
``query`` returns the honest-empty ``search()`` shape with that status — it
does NOT crash. This environment has no object-store credentials, so DuckLake
is UN-MEASURED here.

§16 single-writer: the adapter opens the local graph DB READ-ONLY
(``runtime.db_lock.connect_read``). The DuckLake catalog it would attach is a
*derived* read index over substrate-owned data; the local DuckDB file stays
the source of truth and is never written by this adapter.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from typing import Any

try:
    from ..search import EmbeddingModel
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(_here))))
    from substrate.graph.search import EmbeddingModel  # type: ignore[no-redef]

try:
    from ....runtime.db_lock import connect_read
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(_here))))
    from runtime.db_lock import connect_read  # type: ignore[no-redef]


_SKIPPED = "skipped — no credentials"

# Object-store credentials the DuckLake catalog would need. Presence of ALL of
# these is the gate; absence ⇒ skip.
_REQUIRED_ENV = ("DUCKLAKE_CATALOG", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")


def _has_object_store_creds() -> bool:
    return all(os.environ.get(k) for k in _REQUIRED_ENV)


class DuckLakeSubstrate:
    """Object-store-backed spike adapter. Read-only against the local graph;
    credential/extension-gated."""

    name = "ducklake"

    def __init__(self, con: Any, *, model: EmbeddingModel, has_creds: bool):
        self._con = con
        self._model = model
        self.status: str | None = None if has_creds else _SKIPPED

    @classmethod
    def open(
        cls,
        db_path: str,
        *,
        model: EmbeddingModel,
        has_creds: bool | None = None,
    ) -> DuckLakeSubstrate:
        # §16: read-only against the local source-of-truth file.
        creds = _has_object_store_creds() if has_creds is None else has_creds
        con = connect_read(db_path)
        return cls(con, model=model, has_creds=creds)

    @property
    def skipped(self) -> bool:
        return self.status == _SKIPPED

    def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        source_tier_max: int | None = None,
        document_ids: Sequence[str] | None = None,
        policy_tag: str = "attribution_eligible",
    ) -> dict:
        if self.skipped:
            return {
                "query": text,
                "top_k": top_k,
                "results": [],
                "node_matches": [],
                "status": _SKIPPED,
            }
        # --- credentialed path (UN-EXERCISED in this environment) ----------
        # A real implementation would ATTACH a DuckLake catalog over the
        # object store, build/refresh a vector index over the gate-passing
        # chunk set, query it, re-apply the §9.0 policy_tag predicate, and
        # shape the hits into the search() return contract. Not wired as a
        # network call in the spike — measured numbers must come from a
        # creds-present operator run, never fabricated.
        raise NotImplementedError(  # pragma: no cover — no creds in this env
            "DuckLakeSubstrate credentialed path is a spike stub: attach the "
            "DuckLake catalog behind the §9.0 gate and record measured numbers "
            "in the decision record. Do not fabricate numbers."
        )

    def close(self) -> None:
        try:
            self._con.close()
        except Exception:  # pragma: no cover
            pass
