"""Interviewer role — Sprint 16.

A multi-turn conversational role. Differs from every other role in
the substrate:

- Multi-turn: each call's user prompt is the running transcript +
  the operator's interview_guide. The role's job is to produce the
  *next* interviewer utterance, not a final artifact.
- Adaptive: the guide carries must-cover questions but the role can
  reorder, follow up on threads, or skip questions the informant
  has already addressed implicitly.
- Terminating: when must-cover questions are answered (or the
  informant ends), the role signals ``should_end: true`` and the
  Loop 4 driver writes the final transcript document.

Voice/style canonical source: ``substrate.voice_style.constructions`` is the
single authority for the §5 forbidden constructions. The interviewer's
discipline (no hedging, no sycophancy) is woven into hard constraint #4 below
in a conversational register addressed to a real person, so its phrase list
("I'm wondering if", "would you maybe") is register-specific and not rendered
from the shared renderer. The forbidden *item* (hedging) is the same canonical
construction; ``tests/test_voice_style_constructions.py`` guards that this
prompt keeps banning hedging so the register cannot silently relax. A future
edit adds itself to the canonical source, not a fifth copy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

INTERVIEWER_PROMPT_VERSION = "1.0.0"
INTERVIEWER_TIER = "pro"  # multi-turn reasoning, not bulk
INTERVIEWER_TEMPERATURE = 0.55  # warm conversational, not deterministic


INTERVIEWER_SYSTEM_PROMPT = """\
You are the interviewer in a structured but conversational session.
The operator (a researcher / biographer / investor / journalist) has
configured an interview project with a topic, framing, and a list of
must-cover questions. You are talking with the informant the
operator invited.

Hard constraints:

1. **One utterance per turn.** No multi-paragraph monologues. You
   may follow up on the prior answer, then ask the next question.

2. **Cover the must-cover list, but adaptively.** If the informant
   has implicitly answered question N while addressing question M,
   acknowledge that and move on instead of mechanically asking N
   again.

3. **Follow-ups are first-class.** When an answer surfaces a
   surprising thread, pull on it before continuing down the guide.
   The operator hired you for the threads they could not have
   anticipated; rigid script execution defeats the purpose.

4. **No hedging modifiers.** Forbidden: "perhaps", "I'm wondering
   if", "would you maybe", "could you possibly". Ask the question.
   Operator's voice and style discipline applies here even more
   strictly because the informant is a real person who deserves
   real questions.

5. **End cleanly.** When the must-cover list is exhausted (or the
   informant signals they are done), thank them, summarize what you
   heard in two sentences, and set ``should_end: true`` in your
   response.

6. **Consent is structural.** If the informant has not affirmed
   consent (carried in the first user-template message), do NOT
   begin substantive questioning. Re-state the consent ask and
   wait.

Return JSON each turn:

```json
{
  "interviewer_text": "<your next utterance>",
  "should_end": false,
  "must_cover_remaining_indices": [2, 3, 5],
  "follow_up_for_prior_turn": false,
  "reasoning_note": "<optional one-liner the operator will see in the dashboard>"
}
```
"""


INTERVIEWER_USER_TEMPLATE = """\
## Project

**Title:** {project_title}
**Topic:** {topic_description}

## Operator's framing for the informant

{framing}

## Must-cover questions (indexed)

{must_cover_block}

## Consent

{consent_status}

## Transcript so far ({turn_count} turn{plural})

{transcript_block}

## Your output

Produce the next interviewer utterance per the system prompt.
Return JSON only.
"""


@dataclass(frozen=True)
class TranscriptTurn:
    role: str  # "interviewer" | "informant"
    text: str


@dataclass(frozen=True)
class InterviewerContext:
    project_title: str
    topic_description: str
    framing: str
    must_cover: List[str] = field(default_factory=list)
    consent_recorded: bool = False
    transcript: List[TranscriptTurn] = field(default_factory=list)


def _format_must_cover(items: List[str]) -> str:
    if not items:
        return "_No must-cover questions configured. Drive the conversation toward the topic naturally._"
    return "\n".join(f"{i}. {q}" for i, q in enumerate(items))


def _format_transcript(turns: List[TranscriptTurn]) -> str:
    if not turns:
        return "_No turns yet — this is the first interviewer utterance._"
    return "\n\n".join(
        f"**{t.role}:** {t.text}" for t in turns
    )


def render_user_template(ctx: InterviewerContext) -> str:
    consent_str = (
        "Consent recorded. Proceed with the substantive questions."
        if ctx.consent_recorded
        else "Consent NOT YET recorded. Begin by re-stating the consent ask."
    )
    return INTERVIEWER_USER_TEMPLATE.format(
        project_title=ctx.project_title,
        topic_description=ctx.topic_description.strip() or "(unspecified)",
        framing=ctx.framing.strip() or "(none provided)",
        must_cover_block=_format_must_cover(ctx.must_cover),
        consent_status=consent_str,
        turn_count=len(ctx.transcript),
        plural="" if len(ctx.transcript) == 1 else "s",
        transcript_block=_format_transcript(ctx.transcript),
    )


def render_full_prompt(ctx: InterviewerContext) -> tuple[str, str]:
    return INTERVIEWER_SYSTEM_PROMPT, render_user_template(ctx)
