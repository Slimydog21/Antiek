"""Reading-surface substrate — the model + persistence logic the one Reader's
FloatMenu Dialogue composes against (antiek-reader SPR-06).

This package owns the *real* passage-Dialogue path that replaced the canned,
passage-independent ``/thought-partner`` scaffold:

* :mod:`substrate.reading.passage_dialogue` — build the user-sourced prompt over
  a highlighted passage, dispatch it through the ONE Hermes-routed dispatch tier
  (``substrate.dispatch.router.dispatch``, role ``user_agent`` — the same role
  ``substrate.books.book_qa`` answers free-form reader questions through), and
  chunk the reply into incremental tokens for SSE streaming.
* :mod:`substrate.reading.thread_anchor` — anchor a Dialogue thread to the
  SPR-01 ``Region`` (``document_id`` + ``block_id`` + char range) and persist it
  to the graph through the SINGLE sanctioned writer, so the thread survives
  reload and is a queryable graph node anchored to the passage.

INERT-WITHOUT-KEYS: the dispatch call needs a keyed provider (activation
SPR-03). Until a key lands, ``dispatch`` raises ``ProviderError`` and the
endpoint surfaces an HONEST 503 ("needs a provider key") — never a fabricated
reply. Tests inject a fake provider (a cassette) so the path is exercised
offline; a green test means "the gesture is real and lights up with keys," NOT
"the operator can talk to a passage."
"""

from __future__ import annotations
