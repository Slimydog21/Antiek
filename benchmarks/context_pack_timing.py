"""DRW SPR-04 M5 — context-pack note-injection timing.

Measures the added retrieval + budget cost the maximum-context pack pays at
both ends of the note-set size distribution (small: 5 notes, large: 50k
notes). Unlike the rubric latency lock, this is an *observability* benchmark
— there is no enforced regression gate, because note retrieval scales with
graph size (legitimately) rather than being a fixed-cost craft signature.
Run it to confirm injection stays well under the assembly path's own cost.

    python -m benchmarks.context_pack_timing
"""

from __future__ import annotations

import os
import sys
import tempfile
import time


class _HashEmbedding:
    dimension = 16

    def encode(self, text: str) -> list[float]:
        import hashlib
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


def _seed_notes(db_path: str, n: int, provider) -> None:
    from substrate.graph.schema import init_database_at_path
    from substrate.graph.insight_question import promote_insight
    from runtime.db_lock import connect_write
    init_database_at_path(db_path)
    con = connect_write(db_path, purpose="bench_seed")
    try:
        con.execute("BEGIN")
        for i in range(n):
            promote_insight(text=f"Benchmark insight number {i} about topic {i % 50}.",
                            investigation_id="bench", confidence="moderate",
                            embedding_provider=provider, con=con)
        con.execute("COMMIT")
    finally:
        con.close()


def _time_injection(db_path: str, provider) -> float:
    from runtime.db_lock import connect_read
    from substrate.context_pack.note_injection import build_project_notes_layer, notes_token_budget
    con = connect_read(db_path)
    try:
        t0 = time.perf_counter()
        build_project_notes_layer(
            con, task_text="what matters about topic 7?",
            embedding_provider=provider, token_budget=notes_token_budget("note_taker"),
        )
        return (time.perf_counter() - t0) * 1000.0
    finally:
        con.close()


def main() -> int:
    os.environ.setdefault("ANTIEK_EMBEDDING_PROVIDER", "hash")
    provider = _HashEmbedding()
    print("context-pack note-injection timing")
    print("==================================")
    for label, n in (("small", 5), ("large", 50_000)):
        d = tempfile.mkdtemp()
        db = os.path.join(d, "g.duckdb")
        seed0 = time.perf_counter()
        _seed_notes(db, n, provider)
        seed_ms = (time.perf_counter() - seed0) * 1000.0
        # warm + measure
        _time_injection(db, provider)
        ms = min(_time_injection(db, provider) for _ in range(3))
        print(f"  {label:>5} ({n:>6} notes): inject {ms:8.2f} ms   (seed {seed_ms/1000:.1f}s)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
