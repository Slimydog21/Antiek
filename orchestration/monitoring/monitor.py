"""Monitoring mode — the MONITOR object, resumable REFRESH, puttering feed.

Personal-Reading Lane SPR-09. A *monitor* is a saved feed bound to a prior
deep-research investigation: it carries the thread's salient query terms,
an embedding centroid (the mean of the thread's chunk embeddings), and a
``last_seen_at`` checkpoint. The resumable ``refresh_monitor`` surfaces
the ``personal_reading`` documents acquired since that checkpoint, ranks
them against the centroid, advances the checkpoint, and returns the new
items exactly once. ``putter_feed`` renders those items as a grazing feed
for the owner to read in full on the owner path — never a query box.

DELIBERATELY A THIN SLICE. The full "puttering / frolic in information"
product — a learned relevance ranker, multi-thread / multi-monitor
fan-in, serendipity (off-thread surprise) injection, and any always-on
scheduling — is an explicit, documented north star, NOT built here. The
reversal condition (real daily use + the operator validating the puttering
loop) and the §16 box-bounded reason no daemon ships are recorded in the
deferral note: ``docs/decisions/monitoring-mode-north-star.md`` (relative
to the repo root). Read it before extending this module.

Box-bounded invariants (inherited, never re-implemented):

* Every write funnels through :func:`runtime.db_lock.connect_write` — the
  §16 single-writer lock. No raw DuckDB connection is opened here; reads go
  through :func:`runtime.db_lock.connect_read`.
* Refresh is operator-invoked (``python -m orchestration.monitoring
  --refresh <id> --once``) or reuses the continuous single-iteration
  pattern. It adds NO daemon, thread, or systemd unit.
* The feed never touches the public serve / ad-attribution path:
  ``personal_reading`` is excluded from the public search gate
  (:mod:`substrate.graph.search`) and is non-attributable by construction
  (:func:`substrate.collective_graph.eligibility.is_attribution_eligible`).
* Document bodies never enter the event log payload.
"""
from __future__ import annotations

import contextlib
import dataclasses
import datetime as _dt
import json
from typing import Any

from orchestration.continuous.research_topic import topic_id_for
from runtime.db_lock import connect_read, connect_write
from substrate.graph.search import (
    PRIVILEGED_POLICY_TAGS,
    EmbeddingModel,
    cosine_similarity_sql,
)
from substrate.research_bridge.db_path import default_db_path

# The personal lane — the ONLY content_class monitoring mode ever surfaces.
# Mirrors the owner-only class in substrate.graph.search; kept as a local
# constant so the refresh/feed queries and the defense-in-depth assertions
# share one literal. Do NOT widen this to a servable class.
PERSONAL_LANE_CONTENT_CLASS = "personal_reading"

# The owner/operator read path. Reuses the privileged tag the personal
# shelf already uses (substrate.graph.search.PRIVILEGED_POLICY_TAGS) so a
# monitor read is exactly as privileged as a personal-shelf read — and a
# NON-privileged caller (the public 'attribution_eligible' default) can
# never reach the body.
OWNER_POLICY_TAG = "operator_only"

# A grazing default, NOT a tuned number: 20 fresh items is "a handful to
# putter through," not an optimised page size. The full product (north
# star) would replace this with a learned/recency-decayed window.
DEFAULT_TOP_K = 20


def resolve_db_path(path: str | None) -> str:
    """Resolve the substrate DB path: the explicit ``path`` when given, else
    the canonical default (``substrate.research_bridge.db_path.default_db_path``
    — honors ANTIEK_DUCKDB_PATH / constants.DUCKDB_PATH). One resolver so every
    monitoring write/read targets the same file."""
    return path if path else default_db_path()


def _utcnow_str() -> str:
    """Current UTC instant as a NAIVE ISO-8601 string (no tz suffix).

    All monitor timestamps (last_seen_at, the checkpoint) are stored and
    compared as naive-UTC strings so they sit on the SAME basis as the
    ``documents.acquired_at`` values the refresh compares against. DuckDB
    renders a stored TIMESTAMP back as a naive local-tz string; if we wrote
    a tz-AWARE value it would be shifted to the box's local zone on readback
    and the ``acquired_at > checkpoint`` comparison would silently break
    across a tz offset. Keeping everything naive-UTC removes that hazard.
    Callers that pass acquired_at as a tz-aware ISO are normalized via
    ``_naive_utc`` before comparison.
    """
    return _dt.datetime.now(_dt.UTC).replace(tzinfo=None).isoformat()


def _naive_utc(ts: str) -> str:
    """Normalize an ISO-8601 timestamp string to naive-UTC ISO (drop the tz,
    converting an explicit offset to UTC first). A value with no tz is
    assumed already-UTC and returned unchanged. This is the single point
    that reconciles tz-aware ingest timestamps with the naive-UTC checkpoint
    basis, so the strict ``acquired_at > last_seen_at`` boundary is exact."""
    if not ts:
        return ts
    try:
        dt = _dt.datetime.fromisoformat(ts)
    except ValueError:
        return ts
    if dt.tzinfo is not None:
        dt = dt.astimezone(_dt.UTC).replace(tzinfo=None)
    return dt.isoformat(sep=" ")


@contextlib.contextmanager
def _read(con: Any, path: str | None):
    """Yield a read connection.

    If the caller passed a live connection, reuse it (and do NOT close it —
    the caller owns its lifecycle). Otherwise open a fresh short-lived
    read-only connection from ``path`` and close it on exit.

    Reason this exists: holding a caller's ``connect_read`` open across a
    ``connect_write`` to the same DuckDB file in one process can make the
    writer attach a fresh, empty catalog (a "table does not exist" surprise).
    Letting reads self-manage a short-lived connection keeps the single-
    writer discipline clean and avoids the nested read+write conflict.
    """
    if con is not None:
        yield con
        return
    resolved = resolve_db_path(path)
    rcon = connect_read(resolved)
    try:
        yield rcon
    finally:
        rcon.close()


# ---------------------------------------------------------------------------
# Milestone 1 — the MONITOR object
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Monitor:
    """A saved feed bound to a deep-research investigation.

    Mirrors the ``PersonalAsset`` shape (a frozen dataclass with
    ``to_dict()``). ``centroid`` is ``None`` when the bound thread had no
    embedded chunks — an honest NULL, never a fabricated zero-vector.
    """

    monitor_id: str
    investigation_id: str
    title: str | None
    query_terms: list[str]
    centroid: list[float] | None
    centroid_dim: int | None
    last_seen_at: str
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "monitor_id": self.monitor_id,
            "investigation_id": self.investigation_id,
            "title": self.title,
            "query_terms": list(self.query_terms),
            "centroid": list(self.centroid) if self.centroid is not None else None,
            "centroid_dim": self.centroid_dim,
            "last_seen_at": self.last_seen_at,
            "created_at": self.created_at,
        }


def monitor_id_for(investigation_id: str) -> str:
    """Deterministic ``monitor-<sha256[:12]>`` id for an investigation.

    Reuses the ``topic_id_for`` hashing pattern so re-creating the same
    monitor is idempotent (never a duplicate row). Same investigation_id
    always maps to the same monitor_id.
    """
    if not investigation_id or not investigation_id.strip():
        raise ValueError("empty investigation_id")
    # topic_id_for returns "topic-<hash>"; re-prefix as "monitor-<hash>"
    # so the namespace is distinct but the hash derivation is shared.
    topic = topic_id_for(investigation_id)
    return "monitor-" + topic.split("-", 1)[1]


def _derive_query_terms(document_ids: list[str], con: Any) -> list[str]:
    """Salient terms from the thread's documents' titles.

    Deliberately simple (the spec defers a learned ranker to the north
    star): the distinct title tokens of the bound documents, lowercased,
    de-duped, length-bounded. Honest about being a heuristic, not an
    extracted keyphrase set.
    """
    if not document_ids:
        return []
    placeholders = ",".join("?" for _ in document_ids)
    rows = con.execute(
        f"SELECT title FROM documents WHERE document_id IN ({placeholders})",
        list(document_ids),
    ).fetchall()
    seen: list[str] = []
    for (title,) in rows:
        if not title:
            continue
        for tok in str(title).lower().split():
            tok = tok.strip(".,;:!?\"'()[]")
            if len(tok) >= 3 and tok not in seen:
                seen.append(tok)
    return seen[:32]


def _compute_centroid(
    document_ids: list[str], con: Any, model: EmbeddingModel
) -> tuple[list[float] | None, int | None]:
    """Element-wise mean of the bound documents' chunk embeddings.

    Returns ``(None, None)`` when the thread has zero embedded chunks —
    an honest NULL centroid; the refresh then degrades to chronological
    ranking rather than presenting meaningless similarity scores
    (rigor #1: calibrate confidence to evidence). The vector length is
    checked against ``model.dimension`` before it is returned, so a
    mismatched embedding never gets persisted.
    """
    if not document_ids:
        return None, None
    placeholders = ",".join("?" for _ in document_ids)
    rows = con.execute(
        f"SELECT embedding FROM chunks "
        f"WHERE document_id IN ({placeholders}) AND embedding IS NOT NULL",
        list(document_ids),
    ).fetchall()
    vectors = [list(r[0]) for r in rows if r[0] is not None]
    if not vectors:
        return None, None
    dim = len(vectors[0])
    # Drop any ragged vector rather than silently averaging mismatched
    # lengths (which would corrupt the centroid).
    clean = [v for v in vectors if len(v) == dim]
    if not clean:
        return None, None
    centroid = [sum(v[i] for v in clean) / len(clean) for i in range(dim)]
    if dim != model.dimension:
        # The stored embeddings disagree with the live model dimension —
        # refuse to persist a centroid the refresh can't compare against.
        # Honest degrade to term/chronological ranking.
        return None, None
    return centroid, dim


def create_monitor(
    con: Any,
    *,
    investigation_id: str,
    model: EmbeddingModel,
    document_ids: list[str] | None = None,
    title: str | None = None,
    path: str | None = None,
) -> Monitor:
    """Create (idempotently upsert) a monitor for an investigation.

    ``document_ids`` are the documents belonging to the investigation
    (the caller derives these from the event log / insight nodes — the
    substrate has no persisted documents↔investigation join, so the
    linkage is supplied rather than re-derived here, which keeps this
    module honest about what it actually knows). The centroid is the mean
    of those documents' chunk embeddings; ``query_terms`` are their
    salient title tokens. ``last_seen_at`` initialises to creation time so
    the first refresh only surfaces items ingested AFTER the monitor was
    made.

    Idempotent: same ``investigation_id`` → same ``monitor_id`` → a single
    upserted row, never a duplicate. The single write funnels through
    ``connect_write``.
    """
    doc_ids = list(document_ids or [])
    mid = monitor_id_for(investigation_id)
    # Read the thread's terms + centroid through a short-lived read connection
    # (released before the write opens — see _read for why).
    with _read(con, path) as rcon:
        query_terms = _derive_query_terms(doc_ids, rcon)
        centroid, centroid_dim = _compute_centroid(doc_ids, rcon, model)
    # Naive-UTC string basis (see _utcnow_str): last_seen_at must compare
    # cleanly against documents.acquired_at, which DuckDB renders as a naive
    # local string. Storing a naive-UTC string sidesteps the tz-render shift.
    now_iso = _utcnow_str()

    resolved = resolve_db_path(path)
    with connect_write(resolved, purpose="monitor_create") as wcon:
        wcon.execute(
            """
            INSERT INTO monitors (
                monitor_id, investigation_id, title, query_terms,
                centroid, centroid_dim, last_seen_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (monitor_id) DO UPDATE SET
                investigation_id = excluded.investigation_id,
                title = excluded.title,
                query_terms = excluded.query_terms,
                centroid = excluded.centroid,
                centroid_dim = excluded.centroid_dim
            """,
            [
                mid,
                investigation_id,
                title,
                json.dumps(query_terms),
                centroid,
                centroid_dim,
                now_iso,
                now_iso,
            ],
        )
    return Monitor(
        monitor_id=mid,
        investigation_id=investigation_id,
        title=title,
        query_terms=query_terms,
        centroid=centroid,
        centroid_dim=centroid_dim,
        last_seen_at=now_iso,
        created_at=now_iso,
    )


def _row_to_monitor(row) -> Monitor:
    (
        monitor_id,
        investigation_id,
        title,
        query_terms,
        centroid,
        centroid_dim,
        last_seen_at,
        created_at,
    ) = row
    terms = json.loads(query_terms) if query_terms else []
    return Monitor(
        monitor_id=monitor_id,
        investigation_id=investigation_id,
        title=title,
        query_terms=terms,
        centroid=list(centroid) if centroid is not None else None,
        centroid_dim=centroid_dim,
        last_seen_at=str(last_seen_at),
        created_at=str(created_at) if created_at is not None else None,
    )


_MONITOR_COLS = (
    "monitor_id, investigation_id, title, query_terms, "
    "centroid, centroid_dim, last_seen_at, created_at"
)


def get_monitor(
    con: Any = None, monitor_id: str = "", *, path: str | None = None
) -> Monitor | None:
    """Fetch one monitor by id. Reads via the caller's connection when given,
    else opens a short-lived read connection from ``path``."""
    with _read(con, path) as rcon:
        row = rcon.execute(
            f"SELECT {_MONITOR_COLS} FROM monitors WHERE monitor_id = ?",
            [monitor_id],
        ).fetchone()
    return _row_to_monitor(row) if row else None


def list_monitors(con: Any = None, *, path: str | None = None) -> list[Monitor]:
    """List all monitors, newest first."""
    with _read(con, path) as rcon:
        rows = rcon.execute(
            f"SELECT {_MONITOR_COLS} FROM monitors "
            "ORDER BY created_at DESC, monitor_id DESC"
        ).fetchall()
    return [_row_to_monitor(r) for r in rows]


def delete_monitor(con: Any, monitor_id: str, *, path: str | None = None) -> bool:
    """Delete a monitor. Returns True if a row was removed.

    The single write funnels through ``connect_write``. Deleting a monitor
    removes only the saved feed — never the documents it pointed at.
    """
    resolved = resolve_db_path(path)
    with connect_write(resolved, purpose="monitor_delete") as wcon:
        existing = wcon.execute(
            "SELECT monitor_id FROM monitors WHERE monitor_id = ?",
            [monitor_id],
        ).fetchone()
        if not existing:
            return False
        wcon.execute("DELETE FROM monitors WHERE monitor_id = ?", [monitor_id])
    return True


# ---------------------------------------------------------------------------
# Milestone 2 — resumable REFRESH
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RefreshResult:
    """The outcome of one refresh: the new items + the advanced checkpoint."""

    monitor_id: str
    new_items: list[FeedItem]
    new_checkpoint: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "monitor_id": self.monitor_id,
            "new_count": len(self.new_items),
            "new_checkpoint": self.new_checkpoint,
        }


def _select_new_personal_items(
    con: Any,
    *,
    last_seen_at: str,
    centroid: list[float] | None,
    centroid_dim: int | None,
    top_k: int,
) -> list[FeedItem]:
    """Personal-lane documents acquired strictly AFTER ``last_seen_at``.

    Strictly ``>`` on the checkpoint (NOT ``>=``) so an item ingested in
    the same microsecond as the last checkpoint is never re-surfaced — the
    no-duplicates boundary (rigor #3). Filtered to
    ``content_class='personal_reading'`` only (lane isolation). Ranked by
    cosine similarity against the centroid when one exists, else by
    ``acquired_at DESC`` (honest chronological fallback). Timestamp is
    parameterized — never string-interpolated — to avoid DuckDB coercion
    surprises, and the checkpoint is normalized to naive-UTC (``_naive_utc``)
    so it sits on the same basis as the stored ``acquired_at`` TIMESTAMP.
    """
    last_seen_at = _naive_utc(last_seen_at)
    params: list[Any] = []
    if centroid is not None and centroid_dim:
        sim_expr = cosine_similarity_sql("c.embedding", centroid, centroid_dim)
        # Rank a document by the best (max) similarity among its chunks.
        sql = f"""
            SELECT d.document_id, d.title, d.raw_text, d.acquired_at,
                   MAX({sim_expr}) AS similarity
            FROM documents d
            JOIN chunks c ON c.document_id = d.document_id
            WHERE d.content_class = ?
              AND d.acquired_at > ?
              AND c.embedding IS NOT NULL
            GROUP BY d.document_id, d.title, d.raw_text, d.acquired_at
            ORDER BY similarity DESC
            LIMIT ?
        """
        params = [PERSONAL_LANE_CONTENT_CLASS, last_seen_at, int(top_k)]
    else:
        sql = """
            SELECT d.document_id, d.title, d.raw_text, d.acquired_at,
                   NULL AS similarity
            FROM documents d
            WHERE d.content_class = ?
              AND d.acquired_at > ?
            ORDER BY d.acquired_at DESC
            LIMIT ?
        """
        params = [PERSONAL_LANE_CONTENT_CLASS, last_seen_at, int(top_k)]

    rows = con.execute(sql, params).fetchall()
    items: list[FeedItem] = []
    for document_id, title, raw_text, acquired_at, similarity in rows:
        items.append(
            FeedItem(
                document_id=document_id,
                title=title,
                body=raw_text,
                similarity=round(float(similarity), 4) if similarity is not None else None,
                acquired_at=str(acquired_at) if acquired_at is not None else None,
                content_class=PERSONAL_LANE_CONTENT_CLASS,
                open_route=f"/read/{document_id}",
            )
        )
    return items


def refresh_monitor(
    con: Any = None,
    monitor_id: str = "",
    *,
    model: EmbeddingModel | None = None,
    top_k: int = DEFAULT_TOP_K,
    path: str | None = None,
    events_dir: str | None = None,
) -> RefreshResult:
    """Surface personal-lane items ingested since the monitor's checkpoint.

    Finds ``personal_reading`` documents with ``acquired_at >
    last_seen_at``, ranks them against the centroid (or chronologically
    when no centroid), advances the checkpoint to the max ``acquired_at``
    consumed, and returns the new items exactly once. A second call with
    no intervening ingest returns ``new_items == []``.

    ``model`` is OPTIONAL and intentionally unused for ranking: a refresh
    ranks against the STORED centroid (the thread's own embeddings persisted
    at create time), so a query is never re-encoded here. The parameter is
    kept only so a caller that already holds a model may pass it for
    interface symmetry with ``create_monitor`` / the search API — but the
    CLI and most callers should leave it ``None`` and avoid loading an
    embedding model purely to pass it through. (Only ``create_monitor``
    genuinely needs a live model, to compute the centroid.)

    Emits an auditable ``monitor.refresh`` event via the legacy
    ``log_event`` path — counts + the new checkpoint only. Document bodies
    NEVER enter the event-log payload (they stay on the owner path).
    """
    del model  # explicitly unused: ranking is centroid-based, never re-encoded
    with _read(con, path) as rcon:
        monitor = get_monitor(rcon, monitor_id)
        if monitor is None:
            raise ValueError(f"unknown monitor_id {monitor_id!r}")

        items = _select_new_personal_items(
            rcon,
            last_seen_at=monitor.last_seen_at,
            centroid=monitor.centroid,
            centroid_dim=monitor.centroid_dim,
            top_k=top_k,
        )

    # Advance the checkpoint to the newest acquired_at we actually consumed.
    # Normalize to naive-UTC so the stored checkpoint stays on one basis and
    # the next refresh's strict ``> checkpoint`` boundary is exact.
    new_checkpoint = _naive_utc(monitor.last_seen_at)
    consumed_ts = [_naive_utc(it.acquired_at) for it in items if it.acquired_at]
    if consumed_ts:
        new_checkpoint = max(consumed_ts)

    if items:
        resolved = resolve_db_path(path)
        with connect_write(resolved, purpose="monitor_refresh") as wcon:
            wcon.execute(
                "UPDATE monitors SET last_seen_at = ? WHERE monitor_id = ?",
                [new_checkpoint, monitor_id],
            )

    # Audit emit — counts + checkpoint only, no bodies. Best-effort: an
    # event-log failure must not fail the refresh.
    try:
        from substrate.event_log.events import log_event

        log_event(
            monitor.investigation_id,
            "monitor.refresh",
            payload={
                "monitor_id": monitor_id,
                "new_count": len(items),
                "new_checkpoint": new_checkpoint,
            },
            events_dir=events_dir,
        )
    except Exception:  # pragma: no cover — audit is best-effort
        pass

    return RefreshResult(
        monitor_id=monitor_id,
        new_items=items,
        new_checkpoint=new_checkpoint,
    )


# ---------------------------------------------------------------------------
# Milestone 3 — the puttering read surface
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class FeedItem:
    """One grazed item in the puttering feed.

    Carries the full ``body`` ONLY because the read happens on the owner /
    ``operator_only`` path. ``content_class`` is always
    ``personal_reading`` (the feed surfaces nothing else); ``open_route``
    reuses the SPR-07 reader convention (``/read/{document_id}``).
    """

    document_id: str
    title: str | None
    body: str | None
    similarity: float | None
    acquired_at: str | None
    content_class: str
    open_route: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "body": self.body,
            "similarity": self.similarity,
            "acquired_at": self.acquired_at,
            "content_class": self.content_class,
            "open_route": self.open_route,
        }


def putter_feed(
    con: Any = None,
    monitor_id: str = "",
    *,
    model: EmbeddingModel | None = None,
    with_body: bool = True,
    policy_tag: str = OWNER_POLICY_TAG,
    top_k: int = DEFAULT_TOP_K,
    path: str | None = None,
) -> list[FeedItem]:
    """The grazing feed for a monitor — NOT a query box.

    Returns the monitor's fresh personal-lane items ordered by similarity
    (when a centroid exists) else chronologically. There is intentionally
    NO free-text ``query`` parameter: this is grazing, not querying.

    ``model`` is OPTIONAL and unused for ranking (same reason as
    ``refresh_monitor``: the feed ranks against the stored centroid, never
    re-encodes). Leave it ``None`` unless you already hold a model and want
    interface symmetry.

    The full ``body`` is included only on the owner path. If ``policy_tag``
    is not one of the privileged owner tags
    (``substrate.graph.search.PRIVILEGED_POLICY_TAGS``) the body is
    withheld — the same personal_reading content is invisible to the
    public / attribution-eligible gate, mirroring ``search.py``.

    Defense-in-depth: every item is asserted ``personal_reading`` AND
    asserted non-attributable; a non-personal-lane row can never appear in
    the output (it is filtered at the query AND re-checked here).
    """
    del model  # explicitly unused: ranking is centroid-based, never re-encoded
    owner_path = policy_tag in PRIVILEGED_POLICY_TAGS

    with _read(con, path) as rcon:
        monitor = get_monitor(rcon, monitor_id)
        if monitor is None:
            raise ValueError(f"unknown monitor_id {monitor_id!r}")

        items = _select_new_personal_items(
            rcon,
            last_seen_at=monitor.last_seen_at,
            centroid=monitor.centroid,
            centroid_dim=monitor.centroid_dim,
            top_k=top_k,
        )

    out: list[FeedItem] = []
    for it in items:
        # Defense-in-depth: never surface a non-personal-lane document, even
        # if the query somehow returned one. This is the "lane has not
        # leaked" guard the SPR-10 audit relies on.
        if it.content_class != PERSONAL_LANE_CONTENT_CLASS:
            continue
        # Non-attributability is a structural property of the content_class,
        # proven here so the feed can never accrue ad attribution / IP
        # payout: build the matching collective-graph doc and assert the
        # eligibility predicate says False.
        if _is_attribution_eligible_for_class(it.content_class):
            continue
        body = it.body if (with_body and owner_path) else None
        out.append(dataclasses.replace(it, body=body))
    return out


def _is_attribution_eligible_for_class(content_class: str) -> bool:
    """Whether a document of this content_class could ever earn attribution.

    Composes the real predicate
    :func:`substrate.collective_graph.eligibility.is_attribution_eligible`
    against a minimal doc carrying only this content_class. For
    ``personal_reading`` (a member of ``NON_ATTRIBUTABLE_CONTENT_CLASSES``)
    this returns False at the first branch regardless of any gate result —
    which is exactly the §9.0 proof the lane leans on.
    """
    from substrate.collective_graph.eligibility import (
        CollectiveGraphDocument,
        is_attribution_eligible,
    )

    doc = CollectiveGraphDocument(
        document_id="_probe",
        note_id="_probe",
        owner_user_id="_owner",
        content_class=content_class,
        quality_gate_result=None,
    )
    return is_attribution_eligible(doc)


def main() -> None:  # pragma: no cover — module is library code
    pass


if __name__ == "__main__":  # pragma: no cover
    main()
