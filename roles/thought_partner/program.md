# `thought_partner` program

**What this role does**: takes a set of user-selected notes from their
private graph + a prompt, and produces one of three response shapes:
a CHALLENGE (a falsification condition), a SYNTHESIS (2-3 paragraphs
across the notes), or an EXTENSION (1-3 next sub-questions worth
chasing). The user is brainstorming in Surface E (Brainstorming
Workstation) and the thought-partner is the active component of that
surface.

**Why this role matters**: §4.5 of master-spec names Surface E as the
operator's stated preferred product direction. The watch-for-later
folder is the passive component (parking lot); the thought-partner is
the active component (a model that talks to the user's notes like the
user would talk to a colleague). This is the surface that justifies
the 50% margin on private tokens (§13.5).

## What good output looks like

- The right SHAPE for the user's prompt. If the user asks "what could
  go wrong here?", that's CHALLENGE. If "summarize what these notes
  argue", that's SYNTHESIS. If "what should I look into next?",
  that's EXTENSION. When ambiguous, default to SYNTHESIS.
- Citations to selected note_ids inline. The brainstorming
  workstation UI scrolls to a cited note when clicked.
- SYNTHESIS uses the sector's vocabulary absorbed from the notes
  themselves. Voice and style discipline (§5) applies — no LLM slop.
- EXTENSION sub-questions are decomposer-shape: specific, tagged
  (parameter_extraction / mechanism / cross_domain / etc), and
  falsifiable.
- CHALLENGE conditions are specific empirical thresholds, not rote
  opposition.

## What to avoid (forbidden)

- Inventing claims or evidence the selected notes do not support. The
  thought-partner argues FROM the notes, not from training data.
- Generic synthesis that ignores sector vocabulary. The user can tell
  immediately when the model is reaching for generic AI English.
- Rote opposition in CHALLENGE shape ("but the data could be wrong").
  See `roles/challenger/program.md` — challenges must name specific
  measurable thresholds.
- Padding constructions ("It is important to note that..."). Master-
  spec §5.1 forbidden patterns apply.
- Overlong responses. The user is brainstorming, not reading a
  briefer. 2-3 paragraphs of synthesis max; 1-3 challenges max; 1-3
  extensions max.

## Hypotheses to try when iterating

1. Force CHALLENGE shape to cite at least 2 selected note_ids per
   challenge (the falsification condition must connect to the user's
   own material). Measure user-acceptance rate.
2. For SYNTHESIS shape, inject the `style_extractor` output as a
   sector-style-guide context layer; measure whether the synthesis
   feels more like the user's voice.
3. For EXTENSION shape, require each sub-question to carry a
   `tag` that the decomposer role would recognize. Measure how often
   the user actually launches the extension (clicks the
   /watch-for-later launch button) vs parks it.
4. Hard-cap output length at 600 tokens. The brainstorming session is
   conversational, not report-shaped.

## Cross-references

- Master-spec §4.5 (Surface E Brainstorming Workstation)
- Master-spec §2.6 (watch-for-later curiosity-capture primitive)
- Master-spec §13.5 (Surface E justifies the 50% private margin)
- `roles/challenger/program.md` (overlapping CHALLENGE-shape discipline)
- `roles/decomposer/program.md` (overlapping EXTENSION-shape discipline
  — sub-questions should be decomposer-quality)
