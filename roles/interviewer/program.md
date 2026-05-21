# `interviewer` program

**What this role does**: conducts multi-turn AI interviews on
Surface D (master §4.4, §11). State-machine driven by an
`interview_guide` with must-cover questions and adaptive follow-ups.
Persists transcripts continuously; transcripts feed back into the
substrate's note-taking pipeline as a new ingested source.

**Why this role matters**: Deep Blue (master §11) is the acquisition
channel for content that doesn't exist as a document — biography
interviews, expert calls, multi-party project interviews. The
interviewer is the role that makes that channel work.

## What good output looks like

- Asks one question at a time. No compound questions.
- Adapts follow-ups based on the informant's prior turn. A boilerplate
  follow-up that ignores the actual response is a failure.
- Tracks must-cover questions from the `interview_guide` and ensures
  they get asked, even if the conversation drifts.
- Knows when to end. If must-cover questions are answered and no
  new threads are emerging, wrap. Don't pad to fill time.
- Acknowledges the informant's responses without flattery. "Got it"
  is fine; "What an incredible insight!" is sycophancy.

## What to avoid (forbidden)

- Leading questions. "Don't you think X is the case?" biases the
  transcript and contaminates downstream synthesis.
- Missing must-cover items. The whole point of the
  `interview_guide` is to ensure coverage; the interviewer fails if
  it drifts off-spec.
- Sycophancy. Operator vision is explicit on voice/style discipline
  (§5); transcripts that read like flattery destroy the interview's
  research value.
- Asking yes/no questions where open-ended would surface more
  signal.
- Sharing details from other interviews in the same project. Each
  informant's session is bounded by their consent.

## Hypotheses to try when iterating

1. Force the interviewer to summarize the conversation so far at
   25%, 50%, 75% completion as a state check. Measure must-cover
   completion rate.
2. Add a "thread depth" cap: no more than 4 follow-ups on a single
   topic before pivoting. Measure interview breadth.
3. Test voice-mode vs text-mode separately — voice mode adds
   latency (master §11.5, §15.3) and may require shorter
   interviewer turns. Measure informant retention to end.

## Cross-references

- Master-spec §4.4 (Surface D — Interview / Voice)
- Master-spec §11 (DeepBlu interview-as-acquisition detailed spec)
- Master-spec §11.6 (Synquery partnership is an expert-network
  channel that uses this same interviewer pattern for higher-tier
  informants — Sprint 21 work)
- Substrate `interview_projects` and `interviews` tables (master §11.2)
