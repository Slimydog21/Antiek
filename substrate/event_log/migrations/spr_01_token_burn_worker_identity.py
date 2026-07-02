"""SPR-01 (antiek-yegge-execute) — token_burn + worker_identity schema delta.

**This migration is an explicit NO-OP.** It exists to document, in code, why
no migration runs — satisfying sprint SPR-01 milestone 4's "migration script
committed + idempotent + backfill explicitly a no-op" acceptance bar.

Why no migration is needed (diligence — the exact reason, read from the
substrate):

* event_log storage is **append-only per-event JSONL** (live) rewritten to
  **Parquet** (sealed), one row per event, keyed by ``investigation_id``
  (``substrate/event_log/events.py``: ``_jsonl_path`` / ``_parquet_path``,
  ``_append_jsonl``). There is no shared wide table whose columns must change.
* Adding the ``worker.identity`` action type + the five optional
  ``DispatchCallPayload`` fields (``cached_input_tokens``, ``task_id``,
  ``parent_run_id``, ``feature_label``, ``session_id``) introduces NEW payload
  shapes for NEW rows only. Old rows simply lack those keys; readers use
  ``payload.get(...)`` (see ``cost_view.py``), so absent keys read as the
  field's default (None / 0), never as corruption.
* No backfill is possible or needed: historical token usage is not synthesizable
  from the append-only log, and the spec explicitly forbids it (milestone 4).
* There is **no boot-time migration runner for event_log** — one does not
  exist because append-only JSONL/Parquet needs none. This script is therefore
  NOT registered with any runner (rigor #4: do not invent a parallel runner).
  ``EVENT_SCHEMA_VERSION`` (27 -> 28 in ``substrate/schemas/events.py``) is the
  only stamp; it is written into every new row and never migrates old ones.

Idempotent by construction: the function does nothing, so running it zero,
one, or many times yields the same end state.
"""

from __future__ import annotations


def apply() -> None:
    """No-op. New event types + optional payload fields are append-only; the
    JSONL/Parquet store needs no schema migration. See module docstring."""
    return


if __name__ == "__main__":  # pragma: no cover — diagnostic only
    apply()
