"""Voice-note follow-up role prompt."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

VOICE_NOTE_FOLLOWUP_PROMPT_VERSION = "1.0.0"
VOICE_NOTE_FOLLOWUP_TIER = "pro"
VOICE_NOTE_FOLLOWUP_TEMPERATURE = 0.5  # moderate creativity for question-generation


VOICE_NOTE_FOLLOWUP_SYSTEM_PROMPT = """\
You are the operator's intellectual sparring partner. The operator has
just finished a voice note. Your job: spot the threads they left
dangling and prompt them to pull on the most fruitful one.

You will receive:
1. The just-completed voice note's transcript
2. The insights + open questions the note_taker extracted from it
3. A summary of the prior 3-5 voice notes in the thread (if any)

Produce 1-3 follow-up prompts. Each prompt should:

- Be a question the operator can answer in another 2-5 minute voice note
- Pull on a specific dangling thread — name the insight or open
  question by id when relevant
- Be open enough that the operator's response is genuinely additive,
  not a closed yes/no

What to avoid:

- Generic clarification prompts ("can you say more about X?") — the
  operator can do that for themselves
- Prompts that just rephrase an existing open_question — the
  open_question is already in the substrate; ask something the
  open_question doesn't already cover
- More than 3 prompts. Cognitive load matters; pick the highest-value
  threads

Return JSON:

```json
{
  "prompts": [
    {
      "prompt": "<the question text>",
      "anchor_block_id": "<insight/question id this builds on, or null>",
      "rationale": "<one-sentence why this is worth asking>"
    },
    ...
  ]
}
```
"""


VOICE_NOTE_FOLLOWUP_USER_TEMPLATE = """\
## Just-completed voice note

{transcript}

## Insights extracted

{insights_block}

## Open questions extracted

{questions_block}

## Prior voice-note thread context

{prior_context}

## Your output

Return JSON in the shape specified above. 1-3 prompts only.
"""


@dataclass(frozen=True)
class VoiceNoteFollowupContext:
    transcript: str
    insights: List[dict] = field(default_factory=list)  # each: {id, text}
    open_questions: List[dict] = field(default_factory=list)  # each: {id, text}
    prior_context: str = ""


def _format_blocks(items: List[dict]) -> str:
    if not items:
        return "_None._"
    return "\n".join(
        f"- `{item.get('id', '?')}`: {item.get('text', '')}"
        for item in items
    )


def render_user_template(ctx: VoiceNoteFollowupContext) -> str:
    return VOICE_NOTE_FOLLOWUP_USER_TEMPLATE.format(
        transcript=ctx.transcript.strip() or "_(empty transcript)_",
        insights_block=_format_blocks(ctx.insights),
        questions_block=_format_blocks(ctx.open_questions),
        prior_context=(
            ctx.prior_context.strip() or "_No prior voice notes in this thread._"
        ),
    )


def render_full_prompt(ctx: VoiceNoteFollowupContext) -> tuple[str, str]:
    return VOICE_NOTE_FOLLOWUP_SYSTEM_PROMPT, render_user_template(ctx)
