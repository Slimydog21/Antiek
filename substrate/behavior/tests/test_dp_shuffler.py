"""DP shuffler integration tests for the behavior store (SPR-01 M3).

Asserts:
- Export passes through the shuffler — ordering and timestamps are
  perturbed within the documented epsilon.
- A 1000-event load produces a shuffled batch whose ordering
  inversion rate exceeds a defensive floor (30%) and whose
  timestamp jitter has a sample std-dev exceeding a floor (0.5 s
  for ε=1.0).
- Source rows are stamped with ``dp_shuffler_batch_id`` after
  export so they cannot enter a second batch.
- ``query_raw`` enforces the operator-only gate.
- Exporting with ε above the surface daily cap raises.
"""

from __future__ import annotations

import math
import random
import statistics
from datetime import datetime, timedelta, timezone
from typing import Iterable

import duckdb
import pytest

from substrate.behavior import (
    EXPORT_EPSILON_PER_BATCH,
    EXPORT_SURFACE_NAME,
    OperatorRoleRequired,
    export_training_batch,
    grant_consent,
    query_raw,
)
from substrate.behavior.export import _shuffle_and_jitter
from substrate.dp_shuffler.epsilon_registry import EpsilonRegistry, SurfaceConfig


# ── Helpers ──


def _bulk_insert(
    db_path: str,
    n: int,
    *,
    start: datetime,
    step_s: float = 1.0,
) -> None:
    """Insert n rows directly via the substrate's write coordinator.

    We bypass the API/queue for this test because we need precise
    control over the input ordering (the M3 floor is measured
    against this).
    """
    from runtime.db_lock import connect_write

    con = connect_write(db_path, purpose="dp_test_seed")
    try:
        for i in range(n):
            ts = start + timedelta(seconds=i * step_s)
            con.execute(
                "INSERT INTO behavior_events "
                "(event_id, user_id, session_id, event_type, document_id, "
                " timestamp_utc, state, action, outcome, "
                " consent_version, dp_shuffler_batch_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, NULL)",
                [
                    f"evt-seed-{i:06d}",
                    "__operator__",
                    "sess-dp-test",
                    "document_opened",
                    f"doc-{i}",
                    ts,
                    '{"document_id": "doc-x"}',
                    '{"reading_mode": "researcher"}',
                ],
            )
    finally:
        con.close()


def _count_inversions(input_ids: list[str], output_ids: list[str]) -> int:
    """How many adjacent-input pairs are inverted in the output?

    Input order: input_ids. Output order: output_ids. We compute the
    position of each id in the output, then count adjacent-input
    pairs (i, i+1) whose output positions are inverted (pos[i+1] <
    pos[i]). This is a Kendall-tau-adjacent measure that's cheap and
    rigorous enough for the floor test.
    """
    pos = {eid: i for i, eid in enumerate(output_ids)}
    inversions = 0
    for i in range(len(input_ids) - 1):
        a, b = input_ids[i], input_ids[i + 1]
        if pos.get(b, 0) < pos.get(a, 0):
            inversions += 1
    return inversions


# ── Unit tests for the shuffler primitive ──


def test_shuffler_returns_same_length_and_data():
    """Ordering perturbation must not lose or duplicate rows."""
    rng = random.Random(42)
    rows = [
        {
            "event_id": f"evt-{i}",
            "timestamp_utc": datetime(2026, 1, 1, tzinfo=timezone.utc)
            + timedelta(seconds=i),
        }
        for i in range(100)
    ]
    perturbed, _ = _shuffle_and_jitter(rows, epsilon=1.0, rng=rng)
    assert len(perturbed) == len(rows)
    assert sorted(r["event_id"] for r in perturbed) == sorted(
        r["event_id"] for r in rows
    )


def test_shuffler_rejects_non_positive_epsilon():
    with pytest.raises(ValueError, match="positive"):
        _shuffle_and_jitter(
            [{"event_id": "x", "timestamp_utc": datetime.now(timezone.utc)}],
            0.0,
        )


# ── M3 quantitative gate ──


def test_perturbation_quantitative(behavior_db):
    """Spec verification gate: 1000 events through export → ordering
    inverted ≥ 30%, timestamp jitter std-dev ≥ 0.5s for ε=1.0.

    The floors are deliberately well below the expected uniform-
    shuffle behaviour but well above the noise level a regressed
    shuffler would produce — they are the substrate's "is the
    shuffler still applied?" gate, not a tight DP guarantee."""
    grant_consent("__operator__", db_path=behavior_db)

    n = 1000
    start = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)
    _bulk_insert(behavior_db, n, start=start, step_s=1.0)

    # Run the export with a seeded RNG so the test is deterministic.
    rng = random.Random(20260521)
    result = export_training_batch(
        db_path=behavior_db,
        epsilon=1.0,
        rng=rng,
    )

    assert result.row_count == n
    assert math.isclose(result.epsilon, 1.0)

    # Ordering — count inversions of adjacent input pairs.
    input_ids = [f"evt-seed-{i:06d}" for i in range(n)]
    output_ids = [e.original_event_id for e in result.events]
    inversions = _count_inversions(input_ids, output_ids)
    # 30% floor of adjacent-pair inversions. Uniform shuffle would
    # produce ~50% in expectation.
    floor = int(0.30 * (n - 1))
    assert inversions >= floor, (
        f"shuffler ordering looks weak: {inversions} inversions of "
        f"{n - 1} adjacent pairs (floor {floor})"
    )

    # Timestamp jitter — measure absolute deviation from the
    # original timestamp. Each row's post-jitter ts is the input ts
    # plus Laplace(0, 1/ε); std-dev should be √2/ε ≈ 1.41s for ε=1.0.
    # Floor at 0.5s catches a regression to zero jitter.
    deviations_s = []
    for ev in result.events:
        # Find this row's original timestamp from the seed.
        idx = int(ev.original_event_id.split("-")[-1])
        original_ts = start + timedelta(seconds=idx * 1.0)
        observed = ev.timestamp_utc
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        deviations_s.append((observed - original_ts).total_seconds())
    sample_std = statistics.pstdev(deviations_s)
    assert sample_std >= 0.5, (
        f"timestamp jitter std-dev {sample_std:.3f}s below 0.5s floor; "
        f"shuffler may have regressed to zero jitter for ε=1.0"
    )

    # Also stamp the documented batch metadata for operator audit.
    assert result.timestamp_jitter_max_s > 0.0
    assert result.batch_id.startswith("batch-")


def test_export_stamps_source_rows(behavior_db):
    """A row that's been exported once must never enter another
    batch. The stamp + the WHERE clause in the export query are the
    two halves of that guarantee; this test exercises both."""
    grant_consent("__operator__", db_path=behavior_db)
    _bulk_insert(
        behavior_db,
        10,
        start=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )

    # First export — all 10.
    rng1 = random.Random(1)
    r1 = export_training_batch(db_path=behavior_db, rng=rng1)
    assert r1.row_count == 10

    # Second export — nothing left.
    rng2 = random.Random(2)
    r2 = export_training_batch(db_path=behavior_db, rng=rng2)
    assert r2.row_count == 0

    # Inspect the source rows: every one should now carry r1.batch_id.
    con = duckdb.connect(behavior_db)
    try:
        rows = con.execute(
            "SELECT dp_shuffler_batch_id FROM behavior_events"
        ).fetchall()
    finally:
        con.close()
    assert all(r[0] == r1.batch_id for r in rows)


def test_export_above_cap_raises():
    """The registry's daily cap is the policy gate; the export
    function asks it before running. ε=5 is comfortably above the
    medium cap (2.0)."""
    with pytest.raises(ValueError, match="exceeds surface daily cap"):
        export_training_batch(epsilon=5.0)


def test_export_records_batch_metadata(behavior_db):
    """dp_shuffler_batches must carry epsilon, delta, row_count,
    surface_name, and the empirical max jitter."""
    grant_consent("__operator__", db_path=behavior_db)
    _bulk_insert(behavior_db, 20, start=datetime(2026, 5, 21, tzinfo=timezone.utc))
    result = export_training_batch(
        db_path=behavior_db,
        rng=random.Random(0),
    )

    con = duckdb.connect(behavior_db)
    try:
        row = con.execute(
            "SELECT batch_id, row_count, epsilon, delta, surface_name, "
            "       timestamp_jitter_max_s "
            "FROM dp_shuffler_batches WHERE batch_id = ?",
            [result.batch_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    batch_id, row_count, epsilon, delta, surface, jitter = row
    assert batch_id == result.batch_id
    assert row_count == 20
    assert math.isclose(epsilon, EXPORT_EPSILON_PER_BATCH)
    assert surface == EXPORT_SURFACE_NAME
    assert jitter > 0.0
    assert delta > 0.0


def test_query_raw_refuses_by_default():
    with pytest.raises(OperatorRoleRequired):
        query_raw("SELECT 1")


def test_query_raw_accepts_with_operator_check(behavior_db):
    grant_consent("__operator__", db_path=behavior_db)
    _bulk_insert(behavior_db, 3, start=datetime(2026, 5, 21, tzinfo=timezone.utc))
    rows = query_raw(
        "SELECT COUNT(*) FROM behavior_events",
        db_path=behavior_db,
        operator_check=lambda: True,
    )
    assert rows[0][0] == 3
