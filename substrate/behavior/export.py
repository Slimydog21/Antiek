"""Training-corpus export path for the Tier-1 behavior store.

SPR-01 M3. All training-data egress from ``behavior_events`` MUST go
through ``export_training_batch`` (or its derivatives). The function:

1. Reads unshuffled rows from ``behavior_events``.
2. Hands them to the DP shuffler at ``substrate/dp_shuffler/``,
   which perturbs (a) row ordering and (b) timestamps within a
   documented epsilon.
3. Stamps each contributing row with the ``dp_shuffler_batch_id``
   so the same row never enters two training corpora.
4. Records the batch in ``dp_shuffler_batches`` for operator audit.

The operator-only direct query path is ``query_raw`` — gated on a
caller-supplied operator role check that defaults to refusing
everything. Wave 2 surfaces NEVER touch the raw rows; they only
emit. The export path is what feeds prime-rl + verifiers in
loop_3.

Privacy parameters
------------------
The shuffler operates with an epsilon-DP guarantee under the
configured registry surface. SPR-01 documents:
  - surface_name: "behavior_training_export"
  - sensitivity: "medium" → registry cap 2.0 ε/day
  - per-batch epsilon: 1.0 (conservative — leaves headroom for two
    daily exports under the cap)
  - delta: 1e-9 (negligible per master-spec §13.3)

See ``substrate/behavior/PRIVACY.md`` for the rationale.

Shuffling model
---------------
Two perturbations, both documented in PRIVACY.md:

  Ordering: Fisher-Yates with a per-batch seed. The output ordering
  has Kendall-tau distance from the input strictly > 0 with
  probability 1 - 1/n! for any non-trivial batch. We assert a
  quantitative floor in the M3 test (≥ 30% of pairs inverted
  relative to input order on n=1000).

  Timestamp jitter: each row's ``timestamp_utc`` gets a Laplace
  noise sample with scale ``1/epsilon``-seconds. For ε=1.0 the
  expected jitter is ~1s; the test asserts the empirical std-dev
  across n=1000 events exceeds a floor.

This is the substrate-aligned "local-DP + shuffler aggregation"
contract from master-spec §13.3. The shape is right; the cryptographic
shuffler (Prio) is a later integration.
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import duckdb

try:
    from ..dp_shuffler.epsilon_registry import (
        EpsilonRegistry,
        SurfaceConfig,
    )
    from ...runtime.db_lock import connect_write
    from .schema import default_db_path
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_write  # type: ignore[no-redef]
    from substrate.behavior.schema import default_db_path  # type: ignore[no-redef]
    from substrate.dp_shuffler.epsilon_registry import (  # type: ignore[no-redef]
        EpsilonRegistry,
        SurfaceConfig,
    )


def _connect_for_read(db_path: str) -> "duckdb.DuckDBPyConnection":
    """Open a non-read-only connection for a SELECT-only path.

    Mirrors substrate.behavior.consent._connect_for_read — DuckDB
    can't mix read-only + read-write connections in one process,
    and the queue worker holds an active read-write connection.
    """
    return duckdb.connect(db_path)


# ── DP parameters ──

EXPORT_SURFACE_NAME = "behavior_training_export"
EXPORT_SENSITIVITY = "medium"        # registry cap = 2.0 ε/day
EXPORT_EPSILON_PER_BATCH = 1.0       # leaves headroom for two daily exports
EXPORT_DELTA = 1e-9
"""(ε, δ)-DP guarantee for one export batch. See PRIVACY.md."""


# ── Operator role gate ──


class OperatorRoleRequired(PermissionError):
    """Raised by ``query_raw`` when no role-check passes. The behavior
    store's raw events are operator-only; Wave 2 surfaces NEVER call
    this path."""


def _default_operator_check() -> bool:
    """The default operator check refuses everything. The substrate
    must be told who's allowed; if the caller doesn't pass an
    ``operator_check``, they don't get raw rows."""
    return False


# ── Shuffler outputs ──


@dataclass(frozen=True)
class ShuffledEvent:
    """One row of training-corpus output after DP perturbation.

    Identifying fields are kept (the substrate's DP guarantee is
    over ordering + timestamps, not pseudonymisation; pseudonymising
    is a separate later concern handled by the pseudonym table in
    Sprint 22). ``timestamp_utc`` is post-jitter; ``original_event_id``
    lets the operator audit which raw row contributed.
    """

    original_event_id: str
    user_id: str
    session_id: str
    event_type: str
    document_id: Optional[str]
    timestamp_utc: datetime  # post-jitter
    state: dict[str, Any]
    action: dict[str, Any]
    outcome: Optional[dict[str, Any]]


@dataclass(frozen=True)
class ExportResult:
    """Per-batch summary returned by ``export_training_batch``."""

    batch_id: str
    epsilon: float
    delta: float
    row_count: int
    timestamp_jitter_max_s: float
    events: tuple[ShuffledEvent, ...]


# ── Shuffler ──


def _laplace_noise(scale: float, rng: random.Random) -> float:
    """Sample one value from Laplace(0, scale). Uses inverse-CDF
    sampling against a uniform draw so the M3 test is deterministic
    under a seeded RNG."""
    if scale <= 0:
        return 0.0
    u = rng.uniform(-0.5, 0.5)
    return -scale * math.copysign(1.0, u) * math.log(1 - 2 * abs(u))


def _shuffle_and_jitter(
    rows: list[dict[str, Any]],
    epsilon: float,
    *,
    rng: Optional[random.Random] = None,
) -> tuple[list[dict[str, Any]], float]:
    """Apply Fisher-Yates shuffle + Laplace timestamp jitter.

    Returns the perturbed list AND the empirical max-abs jitter so
    the caller can stamp it into ``dp_shuffler_batches``.
    """
    if epsilon <= 0:
        raise ValueError(
            f"export_training_batch: epsilon must be positive, got {epsilon}"
        )
    rng = rng or random.SystemRandom()
    perturbed = [dict(r) for r in rows]

    # Shuffle ordering.
    rng.shuffle(perturbed)

    # Jitter timestamps with Laplace noise, scale = 1/epsilon seconds.
    scale_s = 1.0 / epsilon
    max_abs_jitter = 0.0
    for row in perturbed:
        ts = row["timestamp_utc"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        elif ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        jitter_s = _laplace_noise(scale_s, rng)
        max_abs_jitter = max(max_abs_jitter, abs(jitter_s))
        row["timestamp_utc"] = ts + timedelta(seconds=jitter_s)

    return perturbed, max_abs_jitter


# ── Export ──


def _check_registry_allows(epsilon: float, registry: Optional[EpsilonRegistry]) -> None:
    """Verify our ε is within the registered surface's cap. If no
    registry is passed, we construct an ephemeral one with the M3
    defaults — production callers should hand in the substrate's
    central registry."""
    reg = registry or EpsilonRegistry()
    if EXPORT_SURFACE_NAME not in reg.surfaces:
        reg.register(
            SurfaceConfig(
                surface_name=EXPORT_SURFACE_NAME,
                epsilon_per_day=2.0,  # cap, not per-batch
                sensitivity=EXPORT_SENSITIVITY,
                description="behavior_events → training-corpus shuffled export",
                opt_in_required=True,
            )
        )
    config = reg.surfaces[EXPORT_SURFACE_NAME]
    if epsilon > config.epsilon_per_day:
        raise ValueError(
            f"export_training_batch: per-batch epsilon={epsilon} exceeds "
            f"surface daily cap {config.epsilon_per_day}. Either lower epsilon "
            f"or split into multiple batches."
        )


def export_training_batch(
    *,
    db_path: Optional[str] = None,
    epsilon: float = EXPORT_EPSILON_PER_BATCH,
    delta: float = EXPORT_DELTA,
    limit: Optional[int] = None,
    rng: Optional[random.Random] = None,
    registry: Optional[EpsilonRegistry] = None,
    stamp_source_rows: bool = True,
) -> ExportResult:
    """Pull unshuffled rows from ``behavior_events``, perturb them
    through the DP shuffler, and stamp the contributing rows with
    the resulting ``batch_id``.

    Args:
        db_path: DuckDB file. Defaults to ``schema.default_db_path()``.
        epsilon: Per-batch ε. Must be ≤ the registry's daily cap for
            ``EXPORT_SURFACE_NAME``.
        delta: δ; documented in PRIVACY.md. Not used by the perturbation
            itself (the shuffler is pure-ε); included for future composition.
        limit: Maximum rows in this batch. None = all unshuffled.
        rng: Optional seeded RNG (used by tests).
        registry: Optional shared ``EpsilonRegistry``. Defaults to an
            ephemeral one with the documented surface config.
        stamp_source_rows: If True (production default), write
            ``dp_shuffler_batch_id`` back onto each source row so it
            can never enter another batch. Tests sometimes set this
            False to keep the source unmodified for assertions.

    Returns:
        ``ExportResult`` with the perturbed events + metadata.
    """
    _check_registry_allows(epsilon, registry)

    path = db_path or default_db_path()

    # Read unshuffled rows.
    con_r = _connect_for_read(path)
    try:
        rows = con_r.execute(
            "SELECT event_id, user_id, session_id, event_type, "
            "       document_id, timestamp_utc, state, action, outcome "
            "FROM behavior_events "
            "WHERE dp_shuffler_batch_id IS NULL "
            "ORDER BY timestamp_utc, event_id "
            + (f"LIMIT {int(limit)}" if limit is not None else "")
        ).fetchall()
    finally:
        con_r.close()

    raw: list[dict[str, Any]] = []
    for r in rows:
        raw.append(
            {
                "event_id": r[0],
                "user_id": r[1],
                "session_id": r[2],
                "event_type": r[3],
                "document_id": r[4],
                "timestamp_utc": r[5],
                "state": json.loads(r[6]) if isinstance(r[6], str) else r[6],
                "action": json.loads(r[7]) if isinstance(r[7], str) else r[7],
                "outcome": json.loads(r[8]) if (r[8] and isinstance(r[8], str)) else r[8],
            }
        )

    perturbed, max_jitter_s = _shuffle_and_jitter(raw, epsilon, rng=rng)

    batch_id = f"batch-{uuid.uuid4().hex[:16]}"

    # Stamp source rows + record the batch.
    if perturbed:
        con_w = connect_write(path, purpose="behavior_export_stamp")
        try:
            con_w.execute(
                "INSERT INTO dp_shuffler_batches "
                "(batch_id, shuffled_at, row_count, epsilon, delta, "
                " surface_name, timestamp_jitter_max_s, notes) "
                "VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)",
                [
                    batch_id,
                    len(perturbed),
                    float(epsilon),
                    float(delta),
                    EXPORT_SURFACE_NAME,
                    float(max_jitter_s),
                    None,
                ],
            )
            if stamp_source_rows:
                # Mark each contributing source row with this batch id.
                # Tests sometimes skip this so they can re-export the
                # same set; production never skips.
                ids = [r["event_id"] for r in raw]
                # DuckDB doesn't have a clean parameterised IN with a
                # list of arbitrary length; chunk into modest batches
                # to keep the SQL bounded.
                CHUNK = 200
                for i in range(0, len(ids), CHUNK):
                    chunk = ids[i : i + CHUNK]
                    placeholders = ",".join("?" * len(chunk))
                    con_w.execute(
                        f"UPDATE behavior_events SET dp_shuffler_batch_id = ? "
                        f"WHERE event_id IN ({placeholders})",
                        [batch_id, *chunk],
                    )
        finally:
            con_w.close()

    events = tuple(
        ShuffledEvent(
            original_event_id=r["event_id"],
            user_id=r["user_id"],
            session_id=r["session_id"],
            event_type=r["event_type"],
            document_id=r["document_id"],
            timestamp_utc=r["timestamp_utc"],
            state=r["state"],
            action=r["action"],
            outcome=r["outcome"],
        )
        for r in perturbed
    )

    return ExportResult(
        batch_id=batch_id,
        epsilon=epsilon,
        delta=delta,
        row_count=len(perturbed),
        timestamp_jitter_max_s=max_jitter_s,
        events=events,
    )


def query_raw(
    sql: str,
    params: Optional[list[Any]] = None,
    *,
    db_path: Optional[str] = None,
    operator_check: Callable[[], bool] = _default_operator_check,
) -> list[tuple[Any, ...]]:
    """Operator-only direct query against ``behavior_events``.

    Wave 2 surfaces MUST NOT call this. Non-operator callers get a
    403-equivalent (``OperatorRoleRequired``).

    The check is caller-supplied so different orchestrator contexts
    (CLI, FastAPI, scheduler) can wire their own auth. The default
    refuses, so a forgotten ``operator_check`` is safe.
    """
    if not operator_check():
        raise OperatorRoleRequired(
            "behavior.export.query_raw is operator-only. "
            "Pass operator_check=lambda: <your check> to enable."
        )
    path = db_path or default_db_path()
    con = _connect_for_read(path)
    try:
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()


__all__ = [
    "EXPORT_DELTA",
    "EXPORT_EPSILON_PER_BATCH",
    "EXPORT_SENSITIVITY",
    "EXPORT_SURFACE_NAME",
    "ExportResult",
    "OperatorRoleRequired",
    "ShuffledEvent",
    "export_training_batch",
    "query_raw",
]
