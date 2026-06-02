"""Reader ad targeting — allowlisted signals only (SPR-05 M5).

The boundary that keeps ad targeting on the right side of the legal gate
and the privacy posture: targeting may use ONLY book *metadata* on the
allowlist (`READER_TARGETING_SIGNAL_ALLOWLIST`) — never the gated full
text of a book, and never anything derived from a reader's private notes.

A gated book contributes its `document_type` + coarse `topic` + `author`,
never its body. This is deliberately conservative: even though snippet
view is fair use (Authors Guild v. Google), *targeting an ad off* a
gated book's text would be deriving commercial value from content we are
explicitly withholding from serving — exactly the boundary the deny-by-
default gate exists to hold.

Differential-privacy posture (§16): any *aggregate* targeting claim is
capped at ε ≤ 10 and is enforced in `substrate/dp_shuffler/`, not here.
This module is the per-impression *input* boundary — it guarantees what
signals are even eligible to feed targeting.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from substrate.constants import READER_TARGETING_SIGNAL_ALLOWLIST


class TargetingSignalRefused(ValueError):
    """Raised when a caller tries to target on a non-allowlisted signal —
    e.g. body text, raw_text, a note, or anything not in the allowlist.
    The refusal is loud by design: a silent drop would let a gated-text
    targeting bug ship unnoticed."""


# Field names that must NEVER be used for targeting, even if a caller
# mislabels them. Defense in depth on top of the allowlist: an explicit
# denylist of the dangerous fields makes the intent unmissable.
_FORBIDDEN_SIGNAL_KEYS: frozenset[str] = frozenset({
    "raw_text", "body", "full_text", "text", "chunk_text",
    "note", "notes", "highlight", "highlights", "snippet",
})


def targeting_signals_for(book_metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Project a book's metadata to the allowlisted targeting signals.

    Drops everything not on `READER_TARGETING_SIGNAL_ALLOWLIST`; the
    output is safe to feed the ad matcher. Works for any book regardless
    of servability — a gated book yields the same metadata-only signals as
    a servable one, because targeting never reads the body either way.
    """
    return {
        k: v
        for k, v in book_metadata.items()
        if k in READER_TARGETING_SIGNAL_ALLOWLIST and v is not None
    }


def page_topics_from_signals(signals: Mapping[str, Any]) -> list[str]:
    """Reduce allowlisted signals to the topic tags the ad matcher
    (`select_lead_gen_ad`) consumes. Only the `topic` signal becomes a
    targeting topic; `document_type` / `author` / `servability` are
    contextual but not topic tags. Returns [] when there's no topic —
    in which case the matcher finds no fill and the slot goes to house."""
    topic = signals.get("topic")
    if topic is None:
        return []
    if isinstance(topic, (list, tuple)):
        return [str(t) for t in topic]
    return [str(topic)]


def assert_no_forbidden_signals(signals: Mapping[str, Any]) -> None:
    """Guard: raise if any forbidden (body/note-derived) key is present.
    Call this on any dict about to feed targeting when the provenance of
    the dict is not already `targeting_signals_for`'s output."""
    bad = [k for k in signals if k in _FORBIDDEN_SIGNAL_KEYS]
    if bad:
        raise TargetingSignalRefused(
            f"targeting signals contain forbidden gated/private keys {bad}; "
            "targeting may use only book metadata on "
            "READER_TARGETING_SIGNAL_ALLOWLIST, never body text or reader notes"
        )
