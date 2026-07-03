"""AIIH SPR-01 — deterministic, sub-second regression test for issue #177.

Issue #177 (single-writer coexistence): DuckDB refuses to open a read-write
connection to a database file that already has a read-only connection open on
the same file (and vice-versa) — they have "different configurations." The
cascade launch path can hit this because the SPR-05 retrieval substrate holds a
persistent read-only connection (``retrieval_substrate._con``, opened via
``runtime.db_lock.connect_read``) which the reuse module
``substrate.context_pack.knowledge_reuse`` reads, while ``runtime.db_lock``
opens the same graph file read-write to persist cascade findings. When the two
coexist, DuckDB raises::

    duckdb.ConnectionException: Connection Error: Can't open a connection to
    same database file with a different configuration than existing connections

The only prior repro was a ~22-minute full-suite run under ``pytest -n auto``.
This module reproduces the *same mechanism* deterministically, single-process,
in well under a second.

TWO TESTS, DIFFERENT JOBS
-------------------------
1. ``test_writer_opens_while_reuse_substrate_is_alive`` — the **xfail GATE**.
   The one M4 flips green. It asserts ONLY the observable behavior that every
   one of #177's three reconciliation options guarantees post-fix, and is
   deliberately NOT coupled to *how* the substrate holds (or stops holding) its
   read connection. See "Why the gate is option-agnostic" below.

2. ``test_current_reuse_seam_holds_a_readonly_con`` — a **non-xfail
   characterization** of the CURRENT seam: that the reuse substrate holds a
   persistent read-only ``_con`` which ``knowledge_reuse._substrate_connection``
   reads. This is the design that *produces* the #177 coexistence. It passes on
   today's tree and pins the seam; a reconciliation (especially Option 1,
   transient reads, which abolishes the held ``_con``) will change this seam, at
   which point THIS test is updated to match the new connection model. Keeping
   it separate from the gate is what lets the gate stay option-agnostic.

WHY THIS IS NOT A FAKE GATE (sprint rigor #3)
---------------------------------------------
Neither test hand-rolls a ``duckdb.connect(..., read_only=True)`` /
``duckdb.connect(...)`` pair. Both drive the REAL production open sites:

  * read-only  — ``substrate.graph.retrieval_substrate.BruteForceSubstrate.open``
    which calls ``runtime.db_lock.connect_read`` (this IS the reuse substrate's
    read connection, exactly what #140 threaded into the launch path);
  * read-write — ``runtime.db_lock.connect_write`` (the sole graph writer,
    invariant #1);
  * the reuse accessor — ``knowledge_reuse._substrate_connection`` (exercised by
    the characterization test).

Because the gate exercises the real ``BruteForceSubstrate.open`` +
``connect_write`` open sites, it cannot go green while the real cascade
coexistence stays broken, and the M4 fix (whichever reconciliation option
#177's DB-owner ratifies) is what flips it.

WHY THE GATE IS OPTION-AGNOSTIC
-------------------------------
The gate asserts only that ``connect_write`` on the graph file SUCCEEDS while
the reuse substrate object is alive. That is the behavior all three options
deliver, by different means:

  * Option 1 (transient reads)   — no read handle is held at write time;
  * Option 2 (unified connection) — reads and writes share one handle;
  * Option 3 (lifecycle discipline) — the read handle is closed before the write.

It does NOT assert ``_substrate_connection(substrate) is substrate._con``: under
Option 1 there is no persistent ``_con`` to return, so coupling the gate to that
identity would (a) make the gate fail at setup rather than flip to green under
the recommended option, and (b) mislead an implementer into KEEPING a held
``_con`` (the higher-risk Option 2 shape) just to satisfy the gate. That
identity is characterized separately, in
``test_current_reuse_seam_holds_a_readonly_con``.

XFAIL SEMANTICS
---------------
The gate is marked ``xfail(strict=True, raises=duckdb.ConnectionException)``:

  * current tree  → ``connect_write`` raises the #177 coexistence error → XFAIL
    (suite stays green; the red is documented, not hidden);
  * a DIFFERENT exception (import/setup/generic) → NOT matched by ``raises=`` →
    reported as a real FAILURE (a broken test cannot hide as an xfail — this
    keeps it a true characterization of #177 specifically);
  * after the M4 fix (any ratified option) → ``connect_write`` succeeds → XPASS →
    ``strict=True`` reports it as a failure, forcing removal of the marker so the
    gate becomes a real green assertion.
"""

from __future__ import annotations

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.context_pack.knowledge_reuse import _substrate_connection
from substrate.graph.retrieval_substrate import BruteForceSubstrate

# The exact substring DuckDB emits for the #177 configuration-mismatch. Pinning
# the message (not just the type) is what makes the gate a characterization of
# #177 rather than "any ConnectionException."
_COEXISTENCE_MSG = "different configuration than existing connections"


class _StubEmbedding:
    """Minimal EmbeddingModel stand-in. ``BruteForceSubstrate.open`` only stores
    the model on ``_model``; these tests never call ``encode``. Kept tiny so the
    tests have no sentence-transformers / model dependency and stay sub-second."""

    dimension = 8

    def encode(self, text: str) -> list[float]:  # pragma: no cover — never called here
        return [0.0] * self.dimension


def _init_graph_db(db_path: str) -> None:
    """Create a minimal graph DB through the REAL writer path
    (``db_lock.connect_write``), including db_lock's ``write_log`` observability
    table so the writer's best-effort log-on-close insert runs clean instead of
    emitting a ``CatalogException: Table with name write_log does not exist``
    breadcrumb to stderr. The DDL is the exact V9 block db_lock writes to
    (``substrate.graph.schema``)."""
    from substrate.graph.schema import ANTIEK_GRAPH_SCHEMA_V9_WRITE_LOG_SQL

    with connect_write(db_path, purpose="single_writer_coexistence_init") as w:
        w.execute("CREATE TABLE nodes (node_id VARCHAR)")
        for stmt in ANTIEK_GRAPH_SCHEMA_V9_WRITE_LOG_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                w.execute(stmt)


@pytest.mark.xfail(
    strict=True,
    raises=duckdb.ConnectionException,
    reason=(
        "#177: while the reuse substrate is alive "
        "(retrieval_substrate.BruteForceSubstrate.open -> db_lock.connect_read), "
        "db_lock.connect_write cannot open the same graph file read-write — "
        "DuckDB rejects the coexisting read-only + read-write configuration. "
        "Flips to XPASS -> remove marker once M4's ratified reconciliation "
        "(Option 1/2/3) lets the writer open safely."
    ),
)
def test_writer_opens_while_reuse_substrate_is_alive(tmp_path):
    """A graph writer must be able to open the file read-write while the reuse
    substrate is alive. It cannot today (#177). Option-agnostic: does not assume
    HOW the substrate holds its read connection."""
    db_path = str(tmp_path / "graph.duckdb")
    _init_graph_db(db_path)

    # Real reuse-substrate read path: BruteForceSubstrate.open -> connect_read ->
    # duckdb.connect(db_path, read_only=True), held on the substrate object.
    substrate = BruteForceSubstrate.open(db_path, model=_StubEmbedding())
    try:
        # The ONLY behavior all three #177 options guarantee post-fix: the sole
        # graph writer can open this file read-write while the reuse substrate
        # object is alive. On the current tree the held read-only connection
        # makes DuckDB raise the #177 coexistence error here.
        try:
            writer = connect_write(db_path, purpose="single_writer_coexistence_probe")
        except duckdb.ConnectionException as exc:
            # Characterize #177 precisely: only the configuration-mismatch
            # coexistence error is the expected pre-fix failure. Any other
            # ConnectionException is a different bug and must surface as a real
            # failure (the AssertionError below is not caught by raises=).
            assert _COEXISTENCE_MSG in str(exc), (
                f"ConnectionException raised, but not the #177 coexistence "
                f"config-mismatch: {exc!r}"
            )
            raise
        else:
            # Post-fix path: the reconciliation let the writer open safely.
            writer.close()
    finally:
        substrate.close()


def test_current_reuse_seam_holds_a_readonly_con(tmp_path):
    """Characterization of the CURRENT (pre-#177-fix) reuse seam — NOT a gate.

    Pins today's design: the reuse substrate holds a persistent read-only
    ``_con`` that ``knowledge_reuse._substrate_connection`` reads. This is the
    exact design that produces the #177 coexistence, so it is worth pinning —
    but it is the *implementation detail* the xfail gate deliberately avoids
    coupling to. A reconciliation (especially Option 1, transient reads, which
    removes the held ``_con``) changes this seam; when the ratified option
    lands, UPDATE this test to match the new connection model. It is
    intentionally non-xfail: it must pass on the current tree."""
    db_path = str(tmp_path / "graph.duckdb")
    _init_graph_db(db_path)

    substrate = BruteForceSubstrate.open(db_path, model=_StubEmbedding())
    try:
        con = _substrate_connection(substrate)  # the real reuse accessor
        assert con is substrate._con            # a held, persistent read handle
        assert con.execute("SELECT count(*) FROM nodes").fetchone()[0] == 0
    finally:
        substrate.close()
