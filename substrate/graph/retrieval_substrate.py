"""SPR-05 — the reversible ``RetrievalSubstrate`` seam.

The read side of the flywheel: given a query, rank the relevant prior
knowledge units over the accumulating graph. Today the only read path is a
brute-force full cosine scan (``substrate/graph/search.py::search``), which
gets linearly slower as the graph grows. This module wraps that path behind
a swappable Protocol so a future operator can swap in a vector-indexed
substrate (or a managed vendor) by touching ONE factory, not every call site.

What's here:

- ``RetrievalSubstrate`` — a Protocol with exactly one ``query`` method whose
  return dict is byte-for-byte the shape ``search()`` already returns
  (``{"query","top_k","results","node_matches"}``) so no caller needs adapter
  code. This is the open seam SPR-06 wires into the research loop.
- ``BruteForceSubstrate`` — the reference impl. A thin wrapper over the
  existing ``search()``; the canonical behaviour every other candidate must
  match for correctness (identical schema + ordering).
- ``DuckDbVssSubstrate`` — the WINNING default impl. Installs + loads the
  DuckDB ``vss`` extension and builds an HNSW index over ``chunks.embedding``
  once, then reuses it. If ``vss`` is unavailable it FALLS BACK to the
  brute-force path and logs why (never a hard crash) — so the default path
  is always live.
- ``make_substrate(kind, ...)`` — the one factory. Default-on-tie is
  ``"vss"`` (no new dependency: ``vss`` is an installable DuckDB extension,
  not a Python dep). The losing adapters (turbopuffer, ducklake) are reachable
  ONLY through this factory's explicit ``kind`` argument, never on the default
  path; they live in ``substrate/graph/retrieval_adapters/`` as flag-gated
  spike modules referenced by the SPR-05 decision record.

§9.0 gate (CRITICAL — composed, never re-implemented): every impl delegates
the restricted-content gate to the *same* ``search()`` call (or, for VSS, the
*same* ``retrieval_gate.non_privileged_chunk_sql_clause`` helper that
``search()`` applies). On non-privileged paths the gate is a fail-closed DENYLIST
(``content_class NOT IN (...)``; NULL excluded). This seam composes the
canonical ``retrieval_gate`` helper; it does not re-implement gate SQL.

§16 single-writer (CRITICAL): no substrate is a writer. Every impl reads
through a read-only connection (``runtime.db_lock.connect_read``); the
non-default adapters MUST open read-only and change no row count.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

try:
    from .retrieval_gate import non_privileged_chunk_sql_clause
    from .search import (
        EmbeddingModel,
        search,
        search_nodes_by_label,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.graph.retrieval_gate import (
        non_privileged_chunk_sql_clause,
    )
    from substrate.graph.search import (
        EmbeddingModel,
        search,
        search_nodes_by_label,
    )

try:
    from ...runtime.db_lock import connect_read
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_read  # type: ignore[no-redef]


_log = logging.getLogger("antiek.retrieval_substrate")


# ---------------------------------------------------------------------------
# The seam — one method, the search() return shape
# ---------------------------------------------------------------------------


@runtime_checkable
class RetrievalSubstrate(Protocol):
    """The swappable retrieval seam.

    Exactly one query method. Its return dict is the SAME shape the existing
    ``search()`` returns — ``{"query", "top_k", "results", "node_matches"}`` —
    so SPR-06 (and every caller) depends on the Protocol, and a substrate swap
    touches only ``make_substrate``.

    ``query`` mirrors ``search()``'s keyword contract exactly so the seam is a
    drop-in: ``top_k``, ``source_tier_max``, ``document_ids``, ``policy_tag``
    all carry the same meaning, including the §9.0 retrieval-time gate that
    ``policy_tag`` drives.
    """

    name: str

    def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        source_tier_max: int | None = None,
        document_ids: Sequence[str] | None = None,
        policy_tag: str = "attribution_eligible",
    ) -> dict: ...


# ---------------------------------------------------------------------------
# Reference impl — wraps the existing brute-force search()
# ---------------------------------------------------------------------------


class BruteForceSubstrate:
    """Reference impl. A thin wrapper over the existing ``search()`` — the
    canonical behaviour (schema + ordering + §9.0 gate) every candidate must
    match. No vector index: a full cosine scan, exactly what main does today.

    Holds an open read-only connection so a benchmark can time repeated
    queries without re-opening the DB each call (§16: read-only, never a
    writer)."""

    name = "brute_force"

    def __init__(self, con: Any, *, model: EmbeddingModel):
        self._con = con
        self._model = model

    @classmethod
    def open(cls, db_path: str, *, model: EmbeddingModel) -> BruteForceSubstrate:
        return cls(connect_read(db_path), model=model)

    @classmethod
    def from_con(cls, con: Any, *, model: EmbeddingModel) -> BruteForceSubstrate:
        """Construct from an ALREADY-OPEN connection, sharing its DuckDB
        instance via ``con.cursor()`` instead of opening a fresh
        ``connect_read`` (which DuckDB forbids alongside a read-write handle to
        the same file in the same process — see
        ``docs/decisions/flywheel-reuse-single-writer.md``). The cursor is a
        logical read handle on ``con``'s instance, so there is NO second
        connection and the single-writer invariant is preserved. Reads are
        live: the cursor sees writes committed on ``con`` after the cursor was
        created."""
        return cls(con.cursor(), model=model)

    def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        source_tier_max: int | None = None,
        document_ids: Sequence[str] | None = None,
        policy_tag: str = "attribution_eligible",
    ) -> dict[str, Any]:
        return search(
            self._con,
            text,
            model=self._model,
            top_k=top_k,
            source_tier_max=source_tier_max,
            document_ids=document_ids,
            policy_tag=policy_tag,
        )

    def close(self) -> None:
        with contextlib.suppress(Exception):  # pragma: no cover
            self._con.close()


# ---------------------------------------------------------------------------
# DuckDB-VSS impl — HNSW index, falls back to brute force if vss unavailable
# ---------------------------------------------------------------------------


# Process-level memo for the vss-loadable probe. The probe runs AT MOST ONCE
# per process (None = not yet probed), so neither the interface tests nor the
# bench re-pay the cost per call. Reset only via _reset_vss_probe (tests).
_VSS_PROBE_RESULT: bool | None = None
_VSS_PROBE_COUNT = 0  # observability: proves the probe runs once, not per-test.

# Explicit opt-in env flag for the NETWORK install of the vss extension. Unset
# (the CI default) means the probe is LOAD-only and never makes a network call,
# so a fresh/network-restricted runner cannot hang on `INSTALL vss`.
_VSS_ALLOW_INSTALL_ENV = "ANTIEK_VSS_ALLOW_INSTALL"


def _probe_vss_loadable(con: Any) -> bool:
    """Hang-proof probe: can the vss extension be made active on ``con``?

    Strategy (no unconditional network call):
      1. ``LOAD vss`` FIRST — pure-local, no download. Succeeds whenever the
         extension is already installed/bundled (e.g. local dev where DuckDB
         has cached it). This is the only path CI ever takes.
      2. ONLY if LOAD fails AND ``ANTIEK_VSS_ALLOW_INSTALL=1`` is set, attempt
         the NETWORK ``INSTALL vss`` then re-``LOAD``. This is the explicit
         opt-in for a fresh dev box; CI leaves the flag unset, so there is no
         network fetch to hang on — vss is simply reported unavailable and the
         caller falls back to brute force.

    Never raises — a missing/unloadable extension is a fallback condition, not
    a crash. Returns True iff vss is loaded and usable on ``con``."""
    try:
        con.execute("LOAD vss")
        return True
    except Exception as load_exc:
        allow_install = os.environ.get(_VSS_ALLOW_INSTALL_ENV, "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        if not allow_install:
            _log.warning(
                "vss extension not loadable (LOAD failed: %s) and %s is unset; "
                "falling back to brute force (no network install attempted)",
                load_exc, _VSS_ALLOW_INSTALL_ENV,
            )
            return False
        # Explicit opt-in: a network INSTALL is permitted on this box.
        try:
            con.execute("INSTALL vss")
            con.execute("LOAD vss")
            return True
        except Exception as install_exc:  # pragma: no cover — env-dependent
            _log.warning(
                "vss extension unavailable after opt-in INSTALL, falling back "
                "to brute force: %s", install_exc,
            )
            return False


def _vss_loadable_probe() -> bool:
    """Memoized, hang-proof boolean: is the vss extension loadable in this
    process? Probes AT MOST ONCE (the result is cached at module level), on a
    throwaway in-memory connection, via the LOAD-first/env-gated strategy. Safe
    to call from a ``skipif`` marker — never hangs, never makes a network call
    unless ``ANTIEK_VSS_ALLOW_INSTALL`` is explicitly set."""
    global _VSS_PROBE_RESULT, _VSS_PROBE_COUNT
    if _VSS_PROBE_RESULT is not None:
        return _VSS_PROBE_RESULT
    _VSS_PROBE_COUNT += 1
    try:
        import duckdb

        probe_con = duckdb.connect(":memory:")
        try:
            _VSS_PROBE_RESULT = _probe_vss_loadable(probe_con)
        finally:
            probe_con.close()
    except Exception as exc:  # pragma: no cover — duckdb import/connect failure
        _log.warning("vss probe could not open a connection (%s); treating vss as unavailable", exc)
        _VSS_PROBE_RESULT = False
    return _VSS_PROBE_RESULT


def _reset_vss_probe() -> None:
    """Test hook: clear the memo so a test can force/observe a re-probe."""
    global _VSS_PROBE_RESULT, _VSS_PROBE_COUNT
    _VSS_PROBE_RESULT = None
    _VSS_PROBE_COUNT = 0


def _vss_available(con: Any) -> bool:
    """Make the vss extension active on ``con`` iff it is loadable in this
    process (memoized probe). Hang-proof: never attempts a network ``INSTALL``
    unless ``ANTIEK_VSS_ALLOW_INSTALL`` is set, so a network-restricted CI
    runner reports unavailable instantly instead of hanging on a download.

    Returns True iff vss is loaded and usable on ``con``. Never raises — a
    missing extension is a fallback condition, not a crash."""
    if not _vss_loadable_probe():
        return False
    # The process-level probe already confirmed vss is loadable with no network
    # cost; LOADing it onto this specific connection is the only per-connection
    # step and is itself network-free here.
    try:
        con.execute("LOAD vss")
        return True
    except Exception as exc:  # pragma: no cover — env-dependent
        _log.warning("vss loadable in process but LOAD on connection failed: %s", exc)
        return False


class DuckDbVssSubstrate:
    """Default winning impl. Builds an HNSW index over ``chunks.embedding``
    using the DuckDB ``vss`` extension, then ranks by ``array_cosine_distance``
    against the index. Returns the SAME ``search()`` shape.

    Index build is a one-time cost recorded separately by the benchmark. The
    index lives in a *temp copy* of the graph DB so the source-of-truth file
    is never written (DuckDB cannot build a persistent HNSW index on a
    read-only connection, and §16 forbids us writing the real graph). The copy
    is built once at ``open`` time and reused for every query.

    Fallback: if ``vss`` won't load, every method degrades to the brute-force
    ``search()`` on a read-only connection and ``vss_active`` is False. The
    decision record reads ``vss_active`` to know whether the HNSW path or the
    fallback produced the numbers.
    """

    name = "vss"

    # The HNSW-indexed, fixed-size embedding column materialised on the temp
    # copy. The source `chunks.embedding` is an UNSIZED FLOAT[] (DuckDB HNSW
    # requires a fixed-size FLOAT[N] key), so the VSS path indexes this derived
    # sized column instead. Querying targets the same column.
    _VSS_COL = "embedding_vss"

    def __init__(self, con: Any, *, model: EmbeddingModel, vss_active: bool):
        self._con = con
        self._model = model
        self.vss_active = vss_active
        # Which column to rank against. Sized + indexed on the VSS path; the
        # original unsized column on the fallback path (where _vss_query is not
        # reached anyway).
        self._emb_col = self._VSS_COL if vss_active else "embedding"

    @classmethod
    def open(cls, db_path: str, *, model: EmbeddingModel) -> DuckDbVssSubstrate:
        """Open the substrate. Tries to build an HNSW index over a temp copy
        of the graph; falls back to a read-only brute-force connection if vss
        is unavailable or the index cannot be built.

        The temp copy is the §16-safe place to materialise an index: we never
        write the operator's graph file. A production wiring (SPR-06+) would
        instead build the index once inside the single-writer's own
        transaction — out of scope here; the spike only needs the measured
        query/build cost, which the temp copy gives faithfully.

        DuckDB HNSW requires a fixed-size ``FLOAT[N]`` key. The graph's
        ``chunks.embedding`` is an unsized ``FLOAT[]``, so we materialise a
        derived sized column ``embedding_vss FLOAT[dim]`` on the temp copy and
        index that. ``dim`` comes from the model (the contract guarantees
        ``encode`` returns ``model.dimension`` floats)."""
        import shutil
        import tempfile

        from substrate.errors import RetrieverInfraError

        dim = int(getattr(model, "dimension", 0) or 0)
        if dim < 1:  # pragma: no cover — defensive
            _log.warning("model.dimension is %r; brute-force fallback", dim)
            return cls(connect_read(db_path), model=model, vss_active=False)

        scratch = tempfile.mkdtemp(prefix="antiek-vss-")
        copy_path = os.path.join(scratch, "vss_index.duckdb")
        try:
            shutil.copy(db_path, copy_path)
        except OSError as exc:
            # I-LOUD (nygard SPR-02): a read-only FS / disk-full / permission
            # error at the vss-index copy is an INFRA fault — NOT the expected
            # "vss unavailable" degradation. The expected condition (the DuckDB
            # vss extension being unavailable) is handled by `_vss_available`
            # below and keeps its benign brute-force fallback; an OSError here
            # must SURFACE typed instead of being silently masked as
            # "brute-force fallback", which erased the cause of the 2026-05-17
            # read-only-FS incident. See tests/regression/
            # test_retriever_readonly_fs_2026_05_17.py.
            raise RetrieverInfraError(
                "could not copy graph for vss index",
                seam="retrieval_substrate.vss_index_copy",
                cause=exc,
            ) from exc

        import duckdb

        con = duckdb.connect(copy_path)
        if not _vss_available(con):
            con.close()
            return cls(connect_read(db_path), model=model, vss_active=False)

        try:
            con.execute("SET hnsw_enable_experimental_persistence = true")
            # Materialise the sized column from the unsized source. Rows whose
            # embedding has the wrong length are left NULL (excluded by the
            # IS NOT NULL predicate at query time) rather than crashing the
            # build — honest partial index over the well-formed rows.
            con.execute(
                f"ALTER TABLE chunks ADD COLUMN IF NOT EXISTS {cls._VSS_COL} FLOAT[{dim}]"
            )
            con.execute(
                f"UPDATE chunks SET {cls._VSS_COL} = embedding::FLOAT[{dim}] "
                f"WHERE embedding IS NOT NULL AND len(embedding) = {dim}"
            )
            con.execute(
                f"CREATE INDEX IF NOT EXISTS hnsw_chunks_embedding "
                f"ON chunks USING HNSW ({cls._VSS_COL}) WITH (metric = 'cosine')"
            )
        except Exception as exc:  # pragma: no cover — env-dependent
            _log.warning("HNSW index build failed (%s); brute-force fallback", exc)
            con.close()
            return cls(connect_read(db_path), model=model, vss_active=False)
        return cls(con, model=model, vss_active=True)

    @classmethod
    def from_con(cls, con: Any, *, model: EmbeddingModel) -> DuckDbVssSubstrate:
        """Construct from an ALREADY-OPEN connection, sharing its DuckDB
        instance via ``con.cursor()`` — no second connection (single-writer
        preserved; see ``docs/decisions/flywheel-reuse-single-writer.md``).

        M6 caveat (verified): the HNSW path is NOT taken on a shared connection.
        Building the index materialises a sized column + ``CREATE INDEX`` — those
        are WRITES to the graph, which is forbidden on the single-writer's shared
        handle (§16) and would need the write flock the funnel already holds.
        ``.open()`` builds the index on a private temp COPY precisely to avoid
        writing the real graph; there is no such copy here. So the shared-cursor
        substrate always runs ``vss_active=False`` — the brute-force query path
        over the SAME cursor (never a 2nd connection). The vss extension may well
        LOAD on the cursor; loading is not the same as being able to build a
        persistent index on the live graph. A future cursor-native index (built
        inside the single writer's own transaction) is the SPR-06+ follow-up the
        ``.open()`` docstring flags."""
        return cls(con.cursor(), model=model, vss_active=False)

    def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        source_tier_max: int | None = None,
        document_ids: Sequence[str] | None = None,
        policy_tag: str = "attribution_eligible",
    ) -> dict[str, Any]:
        if not self.vss_active:
            # Fallback path — identical to the brute-force reference.
            return search(
                self._con, text, model=self._model, top_k=top_k,
                source_tier_max=source_tier_max, document_ids=document_ids,
                policy_tag=policy_tag,
            )
        return self._vss_query(
            text, top_k=top_k, source_tier_max=source_tier_max,
            document_ids=document_ids, policy_tag=policy_tag,
        )

    def _vss_query(
        self, text: str, *, top_k: int, source_tier_max: int | None,
        document_ids: Sequence[str] | None, policy_tag: str,
    ) -> dict[str, Any]:
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")

        # Honest empty for an explicitly-empty document scope (mirrors search()).
        scoped_ids: list[str] | None = None
        if document_ids is not None:
            scoped_ids = list(dict.fromkeys(document_ids))
            if not scoped_ids:
                return {"query": text, "top_k": top_k, "results": [], "node_matches": []}

        query_vec = list(self._model.encode(text))
        dim = self._model.dimension
        if len(query_vec) != dim:
            raise ValueError(
                f"EmbeddingModel.encode returned {len(query_vec)} dims; "
                f"model.dimension is {dim}. Match them."
            )
        vec_str = "[" + ",".join(repr(float(x)) for x in query_vec) + f"]::FLOAT[{dim}]"
        emb = f"c.{self._emb_col}"

        # Cosine SIMILARITY = 1 - cosine DISTANCE. The HNSW index serves the
        # ORDER BY array_cosine_distance ASC; we report similarity to match
        # search()'s contract exactly.
        sql = f"""
            SELECT
                c.chunk_id, c.section_path, c.text, c.token_count,
                c.document_id, c.chunk_index,
                d.title, d.source_tier, d.document_type,
                (1.0 - array_cosine_distance({emb}, {vec_str})) AS similarity
            FROM chunks c
            JOIN documents d ON c.document_id = d.document_id
            WHERE {emb} IS NOT NULL
        """
        params: list[Any] = []
        if scoped_ids is not None:
            placeholders = ",".join("?" for _ in scoped_ids)
            sql += f" AND c.document_id IN ({placeholders})"
            params.extend(scoped_ids)
        if source_tier_max is not None:
            sql += " AND d.source_tier <= ?"
            params.append(int(source_tier_max))
        # §9.0 gate — composed from retrieval_gate (same helper as search()).
        gate_sql, gate_params = non_privileged_chunk_sql_clause(
            table_alias="d",
            policy_tag=policy_tag,
        )
        sql += gate_sql
        params.extend(gate_params)
        sql += " ORDER BY array_cosine_distance(" + emb + ", " + vec_str + ") ASC LIMIT ?"
        params.append(int(top_k))

        rows = self._con.execute(sql, params).fetchall()
        results: list[dict[str, Any]] = []
        for (
            chunk_id, section, ctext, tokens, doc_id, chunk_index,
            title, tier, dtype, sim,
        ) in rows:
            results.append({
                "chunk_id": chunk_id,
                "section_path": section,
                "chunk_text": ctext[:500] + ("…" if ctext and len(ctext) > 500 else ""),
                "token_count": tokens,
                "document_id": doc_id,
                "chunk_index": chunk_index,
                "document_title": title,
                "source_tier": tier,
                "document_type": dtype,
                "similarity": round(float(sim), 4),
            })
        return {
            "query": text,
            "top_k": top_k,
            "results": results,
            "node_matches": search_nodes_by_label(
                self._con, text, limit=10, policy_tag=policy_tag,
            ),
        }

    def close(self) -> None:
        with contextlib.suppress(Exception):  # pragma: no cover
            self._con.close()


def _exists(path: str) -> bool:
    return os.path.exists(path)


# ---------------------------------------------------------------------------
# The one factory — default-on-tie is "vss"
# ---------------------------------------------------------------------------


_DEFAULT_SUBSTRATE = "vss"


def make_substrate(
    kind: str,
    db_path: str,
    *,
    model: EmbeddingModel,
    **adapter_kwargs: Any,
) -> RetrievalSubstrate:
    """Construct a ``RetrievalSubstrate`` for ``kind``.

    ``kind`` ∈ {"vss" (default winner), "brute_force" (reference),
    "turbopuffer", "ducklake"}. The two vendor adapters are SPIKE modules
    imported lazily ONLY when explicitly requested — they never sit on the
    default import path, so a grep of the default factory shows no vendor
    import unless ``kind`` selected it. They are credential/extension-gated
    and self-report ``status: "skipped — no credentials"`` rather than crash.

    Default-on-tie is ``"vss"``: the SPR-05 decision record's verdict. No new
    Python dependency — ``vss`` is an installable DuckDB extension.
    """
    kind = (kind or _DEFAULT_SUBSTRATE).lower()
    if kind in ("vss", "duckdb-vss", "duckdb_vss", "default"):
        return DuckDbVssSubstrate.open(db_path, model=model)
    if kind in ("brute_force", "bruteforce", "reference"):
        return BruteForceSubstrate.open(db_path, model=model)
    if kind == "turbopuffer":
        from .retrieval_adapters.turbopuffer import TurbopufferSubstrate
        return TurbopufferSubstrate.open(db_path, model=model, **adapter_kwargs)
    if kind == "ducklake":
        from .retrieval_adapters.ducklake import DuckLakeSubstrate
        return DuckLakeSubstrate.open(db_path, model=model, **adapter_kwargs)
    raise ValueError(
        f"unknown substrate kind {kind!r}; "
        f"expected one of vss|brute_force|turbopuffer|ducklake"
    )


def make_substrate_from_con(
    kind: str,
    con: Any,
    *,
    model: EmbeddingModel,
) -> RetrievalSubstrate:
    """Construct a ``RetrievalSubstrate`` that SHARES an already-open DuckDB
    connection via ``con.cursor()`` instead of opening its own connection.

    This is the single-writer-safe construction path for the knowledge-reuse
    flywheel (``docs/decisions/flywheel-reuse-single-writer.md``). ``make_substrate``
    (above) opens a fresh ``connect_read`` — which DuckDB refuses when a
    read-write handle to the same file is already open in the process
    (``ConnectionException``), the bug that broke every cascade launch in #140.
    ``make_substrate_from_con`` never calls ``connect_read``: it hands each impl
    a ``con.cursor()`` — a logical read handle on the caller's DuckDB instance,
    so exactly ONE connection/instance exists and the reads are live.

    ``kind`` ∈ {"brute_force" (the reuse default — no whole-DB copy),
    "vss"}. On this shared-connection path ``vss`` degrades to the brute-force
    query over the SAME cursor (``DuckDbVssSubstrate.from_con`` documents why the
    HNSW index cannot be built on a shared single-writer handle). The vendor
    adapters (turbopuffer/ducklake) are open-only and have no shared-connection
    constructor, so they are not reachable here."""
    kind = (kind or "brute_force").lower()
    if kind in ("brute_force", "bruteforce", "reference"):
        return BruteForceSubstrate.from_con(con, model=model)
    if kind in ("vss", "duckdb-vss", "duckdb_vss", "default"):
        return DuckDbVssSubstrate.from_con(con, model=model)
    raise ValueError(
        f"unknown shared-connection substrate kind {kind!r}; "
        f"expected one of brute_force|vss"
    )
