# `visual` program

**What this role does**: extracts structured, region-grounded claims
from one still image or video frame. The role receives a stable frame
handle plus optional surrounding document text and returns JSON with a
short frame summary, confident claims tied to normalized bounding
boxes, and low-confidence uncited observations when a region cannot be
identified.

**Why this role matters**: visual evidence must enter the knowledge
graph with the same provenance discipline as text evidence. A visual
claim without a concrete region cannot be reviewed, replayed, or
rendered back onto the source frame. This role is the substrate boundary
between pixels and citable claims.

## What good output looks like

- JSON only, with no prose wrapper.
- `frame_summary` is one short declarative sentence.
- Every confident claim has a `region` whose `page_or_frame_id` echoes
  the input frame and whose `bbox` is normalized `[x_min, y_min, x_max,
  y_max]` in `[0, 1]`.
- `claim_text` states an observation directly. It does not narrate that
  an image exists.
- Uncertain observations move to `uncited_observations` with low
  confidence instead of pretending a precise region exists.

## What to avoid (forbidden)

- "The image shows" / "we can see" filler.
- Claims without regions in the `claims` array.
- Pixel-coordinate bounding boxes; the substrate needs normalized
  coordinates.
- Multiple observations packed into one claim.
- Inferring intent, identity, or causality unless the visual evidence
  itself supports it.
- Adding commentary outside the JSON object.

## Hypotheses to try when iterating

These are mutation targets for autoresearch Wedge 1:

1. Require exactly one observation per claim and measure parser
   rejection rate against visual fixtures.
2. Add a stricter "no intent inference" line and measure false-positive
   reductions on ambiguous frames.
3. Ask for smaller bounding boxes around the minimum visual evidence
   rather than broad object boxes; compare review usability.
4. Route low-confidence region guesses to `uncited_observations` more
   aggressively; measure downstream grounding precision.
5. Include surrounding caption text only as disambiguation, never as
   evidence for claims not visible in the frame.

## Cross-references

- `roles/visual/prompt.py` for the prompt constants and context shape.
- `roles/visual/parser.py` for the enforced JSON contract.
- Master-spec visual-role audit trail events.
- `integration_autoresearch.md` Wedge 1: this file is the human-written
  program that prompt autoresearch reads before proposing prompt
  mutations.
