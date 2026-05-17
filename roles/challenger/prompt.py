"""Challenger role prompts.

Currently the challenger is implicit (user clicks "challenge this
claim" in the UI; the bridge posts a claim.challenge_raised event
with a default user_question). Sprint 4 day 4-5 formalizes the role
module so the wording lives in one canonical place, ready for the
future autonomous challenger handler that decides WHICH claims to
challenge without operator input.

The DEFAULT_CHALLENGE_PROMPT is also duplicated in the TS UI
(``apps/reading/src/components/ClaimCard.tsx``); the role module is
the canonical source. The next refactor pass can codegen the TS
constant from here.
"""

# Default user_question sent when the operator clicks "challenge"
# without writing their own challenge text. Tuned to push the grounder
# toward strict source location (not paraphrase). The grounder's role
# prompt mirrors the strictness ("DIRECT textual support. Paraphrase
# is NOT direct.").
DEFAULT_CHALLENGE_PROMPT = (
    "Is this claim well-grounded? Show me the source passage that "
    "supports it, and flag anywhere the source is weaker than the "
    "claim implies."
)


# When the autonomous challenger lands (Sprint 6+), it will look at
# distillation.delivered events and decide which claims to challenge
# without operator input. This prompt is the role tail it uses on the
# parameter_extractor or constraint_checker output to select targets.
#
# Not used today — the human is the challenger. Reserved for the next
# autonomous-loop iteration so the wording is already settled when the
# handler lands.
AUTONOMOUS_CHALLENGER_ROLE_PROMPT = """
You are a challenger. Look at the claims the system just produced and
decide which ones deserve a grounding check. Respond with JSON only —
no prose, no markdown fences:

{
  "challenges": [
    {
      "challenged_claim_id": "<claim_id from the input>",
      "user_question": "<short, specific challenge prompt for the grounder>"
    }
  ]
}

Rules:
- Pick AT MOST 3 claims per call. Challenging every claim is noise.
- Prioritize claims with confidence='moderate' or 'low' — high-
  confidence claims rarely need a second look unless the source tier
  is also high.
- A claim with NO attribution_region_ids ALWAYS deserves a challenge
  — that's a hallucination flag.
- Phrase ``user_question`` as a strict-grounding request, not a
  general "are you sure". The grounder needs a specific anchor.
- If no claim deserves a challenge, return ``{"challenges": []}``.
""".strip()
