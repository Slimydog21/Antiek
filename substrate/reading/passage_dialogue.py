"""The REAL passage-Dialogue path (antiek-reader SPR-06, M1 + M2).

Replaces the canned, passage-independent ``/thought-partner`` scaffold: a reader
highlights a passage and talks to it, and the reply comes from a REAL model via
the ONE Hermes-routed dispatch tier — or, when no provider key is configured, an
HONEST 503 ("needs a provider key"), NEVER a fabricated reply.

DISPATCH-TIER DECISION (rigor #5 — what would reverse it):
  Dialogue dispatches through ``substrate.dispatch.router.dispatch`` with
  ``role="user_agent"`` — the SAME role ``substrate.books.book_qa`` answers
  free-form reader questions through, and the role whose name means "the user is
  talking to the system." We do NOT add a new ``role_tiers`` entry (that would be
  a config change for no behavioural gain) and we do NOT call a provider directly
  (that would bypass the sanctioned path, the §16 invariant). WHAT WOULD REVERSE
  IT: if passage-Dialogue needs its own cost/latency tier separate from
  ``user_agent``'s ``pro`` tier, add a ``passage_dialogue`` role to
  ``substrate/dispatch/config.yaml``'s ``role_tiers`` — an additive config
  change, still on the one dispatch path.

STREAMING (M2): the dispatch router is SYNCHRONOUS (``substrate.dispatch.base``'s
``Provider.call`` returns a complete ``RawProviderResponse`` — there is no native
token stream in the provider protocol). So streaming is honest at the TRANSPORT
layer: ``dispatch`` produces the full reply, and :func:`stream_reply_chunks`
splits it into incremental word-sized pieces the SSE endpoint emits as separate
frames. The cassette in test yields these chunks (multiple frames), not one
blob, so the client's progressive-render path is exercised offline. This is NOT
dressed up as token-by-token model streaming it isn't — it is incremental
delivery of a completed reply, labelled as such.

INERT-WITHOUT-KEYS: ``dispatch`` raises ``ProviderError`` when no provider in the
fallback chain is registered/keyed (activation SPR-03). The endpoint catches it
and returns 503; the UI shows the shared ``AIActionFailure`` no-key state. A
green cassette-backed test means "the gesture is real and lights up with keys,"
NOT "the operator can talk to a passage."
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

# The one sanctioned model path (§16). ``ProviderError`` is the no-key signal.
from substrate.dispatch.router import DispatchResult, dispatch

# Role the Dialogue dispatches through — see the module docstring's decision.
DIALOGUE_ROLE = "user_agent"

# How many prior turns of the running conversation to carry into the next
# prompt. Bounded so a long thread does not blow the context budget; the recent
# tail is what a follow-up actually references.
MAX_HISTORY_TURNS = 6


@dataclass(frozen=True)
class DialogueTurn:
    """One prior turn carried into the next prompt. ``question`` is USER-sourced
    (what the reader typed/spoke); ``answer`` is MODEL-sourced. Kept distinct so
    the prompt builder never conflates the reader's words with the model's (§9 —
    relabelling either way is a violation)."""

    question: str
    answer: str


def build_dialogue_prompt(
    *,
    passage: str,
    follow_up: str,
    history: Sequence[DialogueTurn] = (),
    document_title: str | None = None,
) -> str:
    """Assemble the dispatch prompt: the quoted passage (the reader's own
    selection) + the bounded running conversation + the reader's new message.

    The model is a thought-partner over THIS passage — it reasons about the
    quoted text, not a passage-independent canned line. ``follow_up`` is the
    reader's question/comment; when empty the passage itself is the prompt (the
    reader selected a span and hit Ask to get a first reaction)."""
    parts: list[str] = []
    where = f"in “{document_title}”" if document_title else "the reader is reading"
    parts.append(
        "You are a thought-partner the reader is talking to about a passage "
        f"they highlighted while reading ({where}). Engage with the SPECIFIC "
        "passage quoted below — sharpen it, challenge it, or extend it as the "
        "reader's message directs. Do not pad, do not invent facts the passage "
        "does not support, and do not give a generic answer that would fit any "
        "passage."
    )
    parts.append(f"\nThe highlighted passage:\n“{passage}”")
    if history:
        parts.append("\nThe conversation so far:")
        for t in history[-MAX_HISTORY_TURNS:]:
            parts.append(f"Reader: {t.question}")
            parts.append(f"You: {t.answer}")
    msg = follow_up.strip()
    if msg:
        parts.append(f"\nThe reader's message: {msg}")
    else:
        parts.append("\nThe reader opened this passage for discussion with no specific question yet — give them your sharpest first reaction to it.")
    return "\n".join(parts)


def answer_passage_dialogue(
    *,
    passage: str,
    follow_up: str,
    investigation_id: str,
    history: Sequence[DialogueTurn] = (),
    document_title: str | None = None,
    config: object | None = None,
) -> DispatchResult:
    """Run ONE Dialogue turn against the real model via the dispatch tier.

    Raises ``substrate.dispatch.router.ProviderError`` when no provider is keyed
    (the endpoint maps this to an honest 503). The reply text is MODEL-sourced;
    the caller keeps it distinct from the user's prompt.
    """
    prompt = build_dialogue_prompt(
        passage=passage,
        follow_up=follow_up,
        history=history,
        document_title=document_title,
    )
    return dispatch(
        prompt,
        role=DIALOGUE_ROLE,
        investigation_id=investigation_id,
        config=config,  # type: ignore[arg-type]  # tests inject a DispatchConfig
    )


# A token boundary that keeps whitespace attached to the preceding word, so
# re-joining the chunks reproduces the reply byte-for-byte (the SSE client
# concatenates them with no separator).
_CHUNK_RE = re.compile(r"\S+\s*")


def stream_reply_chunks(reply: str) -> Iterator[str]:
    """Split a completed model ``reply`` into incremental, word-sized pieces for
    SSE delivery (M2). Concatenating every yielded chunk reproduces ``reply``
    exactly — the stream is loss-less, just delivered progressively.

    This is incremental delivery of a COMPLETED reply (the provider protocol is
    synchronous), NOT token-by-token model streaming — named honestly so a
    maintainer does not mistake it for the latter. An empty reply yields nothing
    (the endpoint then emits a clean ``done`` with no content frames)."""
    for m in _CHUNK_RE.finditer(reply):
        yield m.group(0)
