"""SPR-05 SPIKE adapter — turbopuffer as a secondary read-optimized index.

STATUS: spike. NOT on the default retrieval path. Reachable only via an
explicit ``make_substrate(kind="turbopuffer")`` / ``--substrate turbopuffer``.

Design (faithful to ``docs/integration_turbopuffer.md`` §3): turbopuffer is a
**secondary read-optimized index over substrate-owned data. DuckDB stays the
primary writer.** This adapter NEVER writes the graph — it reads chunk rows
read-only from DuckDB (``runtime.db_lock.connect_read``), mirrors their
embeddings into a turbopuffer namespace (a derived index, not the source of
truth), and serves ranked queries from there. The §9.0 gate is applied by
filtering the mirrored set to servable ``content_class`` BEFORE upsert and by
re-applying the ``policy_tag`` predicate at query assembly, so a mirror can
never leak ``restricted_pending_opt_in`` content (§1 caveat 4: a candidate
that mirrors chunks without the gate FAILS regardless of recall).

Credential gating: turbopuffer requires ``TURBOPUFFER_API_KEY``. WITHOUT it
this adapter records ``status: "skipped — no credentials"`` and every
``query`` returns the honest-empty ``search()`` shape with that status — it
does NOT crash and does NOT touch the network. The real measured numbers come
only from a run where the key IS present (recorded in the artifact + decision
record). This environment has no key, so turbopuffer is UN-MEASURED here.
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


class TurbopufferSubstrate:
    """Secondary-index spike adapter. Read-only against DuckDB; credential-gated."""

    name = "turbopuffer"

    def __init__(self, con: Any, *, model: EmbeddingModel, api_key: str | None):
        self._con = con
        self._model = model
        self._api_key = api_key
        # Skipped iff no credentials. We deliberately do NOT import or call the
        # turbopuffer SDK on the skip path — no network, no crash.
        self.status: str | None = None if api_key else _SKIPPED

    @classmethod
    def open(
        cls,
        db_path: str,
        *,
        model: EmbeddingModel,
        api_key: str | None = None,
    ) -> TurbopufferSubstrate:
        # §16: read-only. The adapter is a *reader* of substrate-owned data;
        # the index it would build lives in turbopuffer, never in the graph.
        key = api_key if api_key is not None else os.environ.get("TURBOPUFFER_API_KEY")
        con = connect_read(db_path)
        return cls(con, model=model, api_key=key)

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
            # Honest skip — search() shape, empty results, status attached.
            return {
                "query": text,
                "top_k": top_k,
                "results": [],
                "node_matches": [],
                "status": _SKIPPED,
            }
        # --- credentialed path (UN-EXERCISED in this environment) ----------
        # A real implementation would, BEHIND the §9.0 gate:
        #   1. mirror gate-passing chunk embeddings into a tpuf namespace
        #      (derived index; DuckDB stays source of truth — never written),
        #   2. issue a hybrid BM25+vector query to tpuf,
        #   3. re-apply the policy_tag/source_tier predicate on assembly,
        #   4. shape the hits into the search() return contract.
        # Intentionally not implemented as a network call in the spike: the
        # measured numbers must come from a key-present operator run, recorded
        # in the artifact. We raise so a mis-configured run is loud, never a
        # silent fake number.
        raise NotImplementedError(  # pragma: no cover — no creds in this env
            "TurbopufferSubstrate credentialed path is a spike stub: wire the "
            "tpuf SDK behind the §9.0 gate and record the measured numbers in "
            "the decision record. Do not fabricate numbers."
        )

    def close(self) -> None:
        try:
            self._con.close()
        except Exception:  # pragma: no cover
            pass
