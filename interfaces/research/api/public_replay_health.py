"""The public worker phase is separate from its private recovery report."""

from __future__ import annotations


def _public_note_taker_replay(report: object) -> dict[str, str]:
    """Expose only an admitted worker phase, without copying private report fields."""
    if type(report) is not dict:
        return {}
    status = report.get("status")
    if type(status) is not str or status not in (
        "starting",
        "waiting_for_database",
        "waiting_for_writer",
        "catching_up",
        "current",
        "backoff",
        "idle",
    ):
        return {}
    return {"status": status}
