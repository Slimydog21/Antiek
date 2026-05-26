"""Style Extractor role prompt.

Sprint 11 — implements the role DESIGNED but not built in
``docs/strategy/voice-and-style-discipline.md`` (§"Change 3"). The role
reads the top-K corpus chunks for an investigation BEFORE synthesis and
produces a brief, sector-specific style guide. That guide is injected
into the synthesizer's context pack as a new ``kind="style_guide"``
layer so the synthesis absorbs the corpus's own register/vocabulary
instead of generic AI English (master-spec §5).

The role is feature-flagged and runs ONLY for qualitative
investigations — pure-quantitative investigations skip it (the skip
heuristic + flag live in ``substrate/context_pack/style_guide.py``).

Conventions match the existing roles (``synthesizer``,
``evidence_retriever``): a versioned system prompt, a ``{{placeholder}}``
user template, ``render_user_template`` (``str.replace``, NOT
``.format`` — the JSON example block must survive), and
``render_full_prompt`` concatenating system + user.

The JSON output shape mirrors the design doc verbatim:

    {
      "vocabulary": [8-15 sector terms, as written],
      "argumentation_pattern": "2-3 sentences",
      "sentence_rhythm": "one sentence",
      "forbidden_in_this_register": [2-4 patterns],
      "voice_summary": "1-2 prescriptive sentences"
    }

This module ships the prompt side only; the parser is in ``parser.py``
and the context-pack wiring in ``substrate/context_pack/style_guide.py``.
The keyed first-run (flag ON against a real qualitative investigation)
is operator-bound — there are no provider keys in the worktree, so the
role cannot be exercised against a live model here.
"""

from __future__ import annotations


STYLE_EXTRACTOR_PROMPT_VERSION = "1.0.0"
# Flash-tier per the design doc ("one extra flash-tier dispatch …
# roughly $0.0002"). The router maps roles → tiers in config.yaml; the
# operator wires `style_extractor` to a flash tier when activating.
STYLE_EXTRACTOR_TARGET_MODEL = "deepseek/deepseek-v4-flash"
STYLE_EXTRACTOR_TEMPERATURE = 0.2


STYLE_EXTRACTOR_SYSTEM_PROMPT = """
You read N text chunks and produce a brief style guide (~150-300 words) describing the writing voice, sector vocabulary, and argumentation patterns characteristic of the source corpus. This guide gets passed to a downstream synthesizer role; your output influences what its prose sounds like.

Your job is descriptive, not evaluative. You are characterizing how THIS corpus writes so a downstream writer can match its register. Do not critique the corpus, do not summarize its findings, and do not add your own commentary. Report the voice, not the content.

Return a single JSON object with EXACTLY these fields:

- `vocabulary`: 8-15 sector-specific terms or phrases the corpus uses repeatedly. Include the term as written, not your paraphrase. If the corpus writes "direct-path interference suppression," return that string, not "signal cancellation." Prefer multi-word terms of art over single common words.

- `argumentation_pattern`: 2-3 sentences describing how claims are structured in this corpus (e.g., "claims are anchored to specific experimental numbers, with hedging reserved for the comparison to prior work").

- `sentence_rhythm`: one sentence describing typical sentence length and shape (e.g., "medium-length sentences with one subordinate clause, paragraph-final declarative beats").

- `forbidden_in_this_register`: 2-4 patterns that would mark output as out-of-register for this corpus (e.g., "first-person singular reflection," "marketing language").

- `voice_summary`: 1-2 sentences operationalizing the above into a prescriptive style note for a writer.

## Discipline

1. The four prose fields together should run ~150-300 words. A guide longer than ~350 words is padding; a guide shorter than ~120 words is too thin to condition a writer. Be specific and dense.

2. `vocabulary` terms must appear in the chunks. Do not invent plausible-sounding jargon the corpus did not use. A term you cannot point to in a chunk does not belong in the list.

3. Write the prose fields in the same disciplined register the downstream synthesizer must hit: no em-dashes, no padding clauses ("It is worth noting that"), no generic enumeration tics ("Firstly, Secondly").

4. No prose outside the JSON object.
""".strip()


STYLE_EXTRACTOR_USER_TEMPLATE = """
## Source corpus — top-{{top_k}} chunks

{{chunks_block}}

Read the chunks above and produce a single JSON object conforming to the output schema. The guide describes the corpus's VOICE, not its content. No prose outside the JSON.

## Output structure (MANDATORY — use these exact field names)

```json
{
  "vocabulary": [
    "sector term as written in the corpus",
    "another term of art the corpus repeats"
  ],
  "argumentation_pattern": "2-3 sentences on how claims are structured in this corpus.",
  "sentence_rhythm": "one sentence on typical sentence length and shape.",
  "forbidden_in_this_register": [
    "a pattern that would read out-of-register here",
    "another such pattern"
  ],
  "voice_summary": "1-2 prescriptive sentences a writer could follow to match this corpus."
}
```

Field rules:
- Top-level keys are EXACTLY `vocabulary`, `argumentation_pattern`, `sentence_rhythm`, `forbidden_in_this_register`, `voice_summary` — nothing else.
- `vocabulary` is a list of 8-15 non-empty strings, each a term as written in the corpus.
- `forbidden_in_this_register` is a list of 2-4 non-empty strings.
- `argumentation_pattern`, `sentence_rhythm`, `voice_summary` are non-empty strings.
- The four prose fields together run ~150-300 words.
""".strip()


def render_user_template(*, top_k: int, chunks_block: str) -> str:
    """Substitute the two placeholders. ``str.replace`` (not
    ``.format``) so the JSON example block at the tail survives."""
    out = STYLE_EXTRACTOR_USER_TEMPLATE
    out = out.replace("{{top_k}}", str(int(top_k)))
    out = out.replace("{{chunks_block}}", chunks_block or "(no chunks)")
    return out


def render_full_prompt(
    *,
    top_k: int,
    chunks_block: str,
    extra_user_prefix: str = "",
) -> str:
    """Concatenate system + user. ``extra_user_prefix`` mirrors the
    regeneration hook the other roles expose; the bridge can use it to
    re-dispatch with a malformed-output note if the parser rejects the
    first pass."""
    user = render_user_template(top_k=top_k, chunks_block=chunks_block)
    if extra_user_prefix:
        user = extra_user_prefix.strip() + "\n\n" + user
    return STYLE_EXTRACTOR_SYSTEM_PROMPT + "\n\n" + user
