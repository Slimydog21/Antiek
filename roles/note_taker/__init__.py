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

# DRW SPR-03 — the always-on, asynchronous note-taking surface. These turn
# the wrestling-only note-taker into a pass over every document and every
# research step, plus living notes that update in place. The pure role
# logic above (prompt/parser/ExtractedNote) is unchanged and reused.
from .distill import DispatchDistiller, Distillation, DistilledQuestion, Distiller
from .distill_query import (
    Distillation as DistilledView,
)

# DRW SPR-03 M2 — read seam: surface an investigation's distilled nodes.
# Aliased (the distill.py Distillation is the *write*-side shape; this is the
# *read*-side shape) so a caller imports the one it means.
from .distill_query import (
    DistilledNode,
    distillation_for,
)
from .document_pass import PassResult, run_document_pass
from .living_note import ChallengeResult, apply_refinement, challenge_note
from .parser import ExtractedNote, parse_notes_response
from .prompt import NOTE_TAKER_SYSTEM_PROMPT
from .replay import DurableNoteTakerReplay, NoteTakerReplayCorruption
from .scheduler import DEFAULT_DEBOUNCE_S, AsyncNoteScheduler, SchedulerStats
from .step_pass import RunNoteDeduper, notes_for_step

__all__ = [
    "NOTE_TAKER_SYSTEM_PROMPT",
    "ExtractedNote",
    "parse_notes_response",
    # SPR-03 always-on note-taking
    "Distillation", "DistilledQuestion", "Distiller", "DispatchDistiller",
    "PassResult", "run_document_pass",
    "RunNoteDeduper", "notes_for_step",
    "ChallengeResult", "apply_refinement", "challenge_note",
    "AsyncNoteScheduler", "SchedulerStats", "DEFAULT_DEBOUNCE_S",
    # SPR-03 read seam (M2)
    "DistilledNode", "DistilledView", "distillation_for",
    "DurableNoteTakerReplay", "NoteTakerReplayCorruption",
]
