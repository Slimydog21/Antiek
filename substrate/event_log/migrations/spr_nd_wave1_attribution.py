"""SPR-02 NotDiamond attribution schema delta.

This is an explicit no-op migration. Antiek's event log on current main is
append-only JSONL sealed to Parquet, with Pydantic models as the schema source
of truth. Adding nullable/defaulted ``nd_*`` fields to ``DispatchCallPayload``
requires no table migration or historical backfill; old rows validate by
schema-on-read defaults.
"""

from __future__ import annotations


def apply() -> None:
    """No-op: additive optional payload fields need no JSONL migration."""
    return
