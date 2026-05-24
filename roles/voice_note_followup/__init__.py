"""Voice-note follow-up prompter role — Sprint 13.

After a voice note is ingested and the note_taker extracts insights +
open questions, this role looks at the new notes alongside the
operator's prior voice-note thread and produces 1-3 follow-up prompts
that pull on threads the operator left dangling.

The output drives the "Follow-up?" card the UI shows after each voice
note (master spec §12.2).
"""

from .prompt import (
    VOICE_NOTE_FOLLOWUP_PROMPT_VERSION,
    VOICE_NOTE_FOLLOWUP_SYSTEM_PROMPT,
    VOICE_NOTE_FOLLOWUP_TEMPERATURE,
    VOICE_NOTE_FOLLOWUP_TIER,
    VoiceNoteFollowupContext,
    render_full_prompt,
    render_user_template,
)
from .parser import (
    FollowupPrompt,
    VoiceNoteFollowupResult,
    VoiceNoteFollowupValidationError,
    parse_voice_note_followup_response,
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


# SPR-03: role-shape metadata (see substrate/role_shape.py)
from substrate.role_shape import RoleMetadata

__role_metadata__ = RoleMetadata.polecat(
    expected_input_tokens=3000,
    expected_output_tokens=500,
    spawn_pattern_doc=(
        'Pass a captured voice note plus context. Returns a single follow-up question to surface the next morning. Single-turn; idempotent.'
    ),
)
