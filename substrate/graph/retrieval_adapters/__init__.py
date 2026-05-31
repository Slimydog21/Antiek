"""SPR-05 retrieval-substrate SPIKE adapters.

These are credential/extension-gated spike modules — NEVER on the default
retrieval path. They are reachable only through
``substrate.graph.retrieval_substrate.make_substrate(kind=...)`` with an
explicit ``kind``, or through the ``benchmarks/retrieval_bench.py`` harness's
``--substrate`` flag. The SPR-05 decision record
(``docs/decisions/retrieval-substrate-spike-2026-05-31.md``) references them as
the rejected/unmeasured candidates.

§16 single-writer: every adapter opens the graph DB READ-ONLY via
``runtime.db_lock.connect_read`` and changes no chunks/nodes/edges row count.
Without credentials they self-report ``status: "skipped — no credentials"``
rather than crash, so the harness is re-runnable by any operator.
"""
