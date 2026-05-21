# `voice_note_followup` program

**What this role does**: after the operator records a voice note and
the note_taker extracts insights + open questions, this role
generates follow-up prompts that push the operator on the actual
content — open questions worth pursuing, insights worth connecting
to prior notes, gaps worth filling.

**Why this role matters**: the operator's vision (master §12.2,
voice notes 2026-05-17) is that the voice-note workflow should be
conversational, not one-shot. *"There also should be a loose idea
of like something pushing and prompting the user on the actual
content, prompting on the insights, open questions."* This role
is that push.

## What good output looks like

- 1-3 follow-up prompts per voice note. More than 3 is overwhelming;
  fewer than 1 misses the conversational pattern.
- Prompts are specific to the operator's voice-note content, not
  generic ("Tell me more about X").
- Prompts reference operator's prior notes when the new voice note
  intersects them. "You mentioned X in [prior note]; how does that
  reconcile with what you just said about Y?"
- Prompts surface open questions worth parking in the watch-for-later
  folder (master §2.6) as well as questions worth asking right now.
- Prompts respect the brainstorming-workstation framing — the
  operator is here to brainstorm, not be quizzed.

## What to avoid (forbidden)

- Generic prompts. "Can you elaborate?" or "What else?" are
  zero-value.
- Ignoring already-discussed material. If the operator already
  addressed a gap in this same voice note, don't surface it as a
  follow-up.
- Quiz-style prompts. The voice_note_followup is a thought-partner,
  not an evaluator.
- Prompts that lead toward a preferred answer. The operator's
  curiosity is the operator's; the role's job is to surface
  questions, not steer toward conclusions.

## Hypotheses to try when iterating

1. Force one of the 1-3 prompts to be a watch-for-later candidate
   ("park this for later") rather than an immediate follow-up.
   Measure the parked-questions folder population rate (master §2.6).
2. Bias prompts toward connecting the current voice note to operator's
   prior notes (cross-note synthesis) over staying within the
   current note. Measure compounding-of-personal-graph rate.
3. Add a "depth" parameter — prompts can be shallow (clarify) or
   deep (challenge an unstated assumption). Operator picks the
   depth before recording the voice note.

## Cross-references

- Master-spec §12 (voice note ingestion detailed spec)
- Master-spec §2.6 (watch-for-later as curiosity-capture primitive)
- Master-spec §4.5 (Surface E — Brainstorming Workstation; the
  voice_note_followup role is the conversational layer of this
  surface)
- Substrate `acquisition/voice/` adapter (Sprint 13, the upstream
  voice-note pipeline)
