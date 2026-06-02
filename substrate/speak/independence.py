"""Speak SPR-05 M4 — the independence guard.

The case that bites: "a claim attested by five people who heard it from
each other is one rumor, not five attestations." Multiply-attested is
already not "proven true"; the independence guard makes sure it isn't
even *over-counted*. Confidence must reflect INDEPENDENT attestation,
not raw member count.

Each attestation carries an ``independence_key``. Attestations that
share a key trace to the same origin — the same source repeated, or
interviewees who heard it from each other — and count once. An
attestation with no explicit key defaults to its interviewee
(``iv:<interview_id>``), so:

  • the same interviewee repeating a claim → one attestation;
  • distinct interviewees with no shared-origin marker → independent;
  • a shared rumor the operator/interviewer tagged with one key → one.

What this cannot do: detect a shared false memory nobody flagged. That
is named honestly in the docs and labels — the system never asserts
truth (rigor #1).
"""

from __future__ import annotations

from collections.abc import Iterable


def effective_key(*, independence_key: str | None, interview_id: str | None) -> str:
    """The key an attestation counts under. Explicit shared-origin key
    wins; otherwise the interviewee is the unit (so one person repeating
    themselves isn't N attestations)."""
    if independence_key:
        return f"src:{independence_key}"
    if interview_id:
        return f"iv:{interview_id}"
    return "anon"


def count_independent(members: Iterable[dict]) -> int:
    """Number of INDEPENDENT attesters among ``attests`` members. Members
    are dicts with ``interview_id``, optional ``independence_key``, and
    optional ``stance`` (default 'attests')."""
    keys: set[str] = set()
    for m in members:
        if m.get("stance", "attests") != "attests":
            continue
        keys.add(effective_key(
            independence_key=m.get("independence_key"),
            interview_id=m.get("interview_id"),
        ))
    return len(keys)
