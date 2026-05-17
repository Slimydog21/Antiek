"""Note-taker role — extracts emergent insights from wrestling history.

The note-taker watches the chat surface (distillations, challenges,
grounding verdicts) and surfaces TRUTHS that crystallized across the
wrestling, not just individual claims. Operator vision: "a process that
is taking notes in the background of the key insights and truths that
emerge from the interaction with that document, so that the agent
after wrestling through the ideas with my can have a compressed
document that reminds it of what matters with that document."

Sprint 4 day 1-2 ships:

- The pure role logic (prompt + parser + ExtractedNote dataclass).
- The bridge wiring in ``interfaces/research/api/note_taking.py``
  registers the handler against ``distillation.delivered`` +
  ``claim.grounding_check_passed/failed``, runs synthesis every N
  events, emits ``note.emerged`` per insight.

Deferred to a later turn: ``note.compressed_doc_written`` (materialize
the per-document reminder file when the per-doc insight count crosses
a higher threshold), ``note.refined`` (rewrite a prior note as
understanding grows).
"""

from .prompt import NOTE_TAKER_SYSTEM_PROMPT
from .parser import ExtractedNote, parse_notes_response

__all__ = [
    "NOTE_TAKER_SYSTEM_PROMPT",
    "ExtractedNote",
    "parse_notes_response",
]
