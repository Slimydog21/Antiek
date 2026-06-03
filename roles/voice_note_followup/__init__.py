"""Voice-note follow-up prompter role — Sprint 13.

After a voice note is ingested and the note_taker extracts insights +
open questions, this role looks at the new notes alongside the
operator's prior voice-note thread and produces 1-3 follow-up prompts
that pull on threads the operator left dangling.

The output drives the "Follow-up?" card the UI shows after each voice
note (master spec §12.2).
"""

from .parser import (
    FollowupPrompt,
    VoiceNoteFollowupResult,
    VoiceNoteFollowupValidationError,
    parse_voice_note_followup_response,
)
from .prompt import (
    VOICE_NOTE_FOLLOWUP_PROMPT_VERSION,
    VOICE_NOTE_FOLLOWUP_SYSTEM_PROMPT,
    VOICE_NOTE_FOLLOWUP_TEMPERATURE,
    VOICE_NOTE_FOLLOWUP_TIER,
    VoiceNoteFollowupContext,
    render_full_prompt,
    render_user_template,
)

__all__ = [
    "FollowupPrompt",
    "VOICE_NOTE_FOLLOWUP_PROMPT_VERSION",
    "VOICE_NOTE_FOLLOWUP_SYSTEM_PROMPT",
    "VOICE_NOTE_FOLLOWUP_TEMPERATURE",
    "VOICE_NOTE_FOLLOWUP_TIER",
    "VoiceNoteFollowupContext",
    "VoiceNoteFollowupResult",
    "VoiceNoteFollowupValidationError",
    "parse_voice_note_followup_response",
    "render_full_prompt",
    "render_user_template",
]
