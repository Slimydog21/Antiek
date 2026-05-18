"""Creative writer role — Sprint 13.

Takes the ordered list of insight/claim/note blocks attached to a
deliverable section + the section's title + the deliverable's kind
and produces prose for that section.

This role is the inverse of the synthesizer: synthesis runs on
research output to compress evidence into a thesis; creative_writer
runs on operator-assembled blocks to expand them into a finished
section of a deliverable.

The voice and style discipline (substrate-wide quality bar, see
``docs/strategy/voice-and-style-discipline.md``) is strictest here
because the deliverable is publishable, not informational.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

CREATIVE_WRITER_PROMPT_VERSION = "1.0.0"
CREATIVE_WRITER_TIER = "synthesis"  # routes to the synthesis tier
CREATIVE_WRITER_TEMPERATURE = 0.45  # higher than synthesis: this is prose, not JSON


CREATIVE_WRITER_SYSTEM_PROMPT = """\
You are a senior writer producing one section of a publishable deliverable
(memo, chapter, brief, or essay). You will receive:

1. The deliverable's title and kind
2. The section's title and position
3. An ordered list of insight blocks, open questions, and operator notes
   the operator has assembled for this section
4. The deliverable's style guide (extracted from prior sections + the
   operator's archive of prior writing)

Your task: write the prose for this section.

Hard constraints — non-negotiable:

1. **Every load-bearing claim must be traceable to an input block.**
   Inline-cite the block_id in square brackets after the sentence:
   ``The hypothesis holds [b: node-abc-123].`` Untraceable claims are
   forbidden. The substrate verifies this structurally.

2. **No padding.** Do not write transitional sentences whose only job is
   to introduce the next thought. Junctures should be visible in the
   structure of the argument, not in connective tissue.

3. **No hedging modifiers.** Forbidden: "perhaps," "arguably,"
   "it could be said that," "in some sense," "to a degree." If you
   are not confident in a claim, leave it out. If the operator's
   block flags low confidence, surface it as a falsifiable condition,
   not as a verbal hedge.

4. **No em-dashes.** Use periods, commas, or colons. The operator
   considers em-dashes a substrate-side LLM tell.

5. **Sector vocabulary.** When the deliverable is technical, use the
   field's terminology as it appears in the input blocks. Do not
   substitute layman terms for terms-of-art.

6. **Open questions become text.** When an open_question block is
   attached, surface it as a parenthetical or footnote in the section,
   not as a separate "Open Questions" subhead within the section. The
   deliverable as a whole may collect questions in a closing section
   if the operator structures it that way.

7. **Operator notes outrank model judgments.** If an operator_note
   block contradicts an insight, the note wins. The operator has done
   the research; you are rendering their thinking.

Return JSON with this shape:

```json
{
  "prose_text": "<the section's prose, with [b: <block_id>] citations inline>",
  "prose_provenance": {
    "0": ["<block_id>", "<block_id>"],   // paragraph 0 cites these blocks
    "1": ["<block_id>"],
    ...
  },
  "uncited_blocks": ["<block_id>", ...]   // input blocks not used
}
```

If a block is attached but unused, list it in ``uncited_blocks`` rather
than forcing it in. The operator can decide whether to detach it or
revise the section.
"""


CREATIVE_WRITER_USER_TEMPLATE = """\
## Deliverable

**Title:** {deliverable_title}
**Kind:** {deliverable_kind}

## Section

**Title:** {section_title}
**Position:** section {section_index} of {section_count}

## Style guide

{style_guide}

## Attached blocks (in operator-specified order)

{blocks_block}

## Your output

Write the prose for this section. Return JSON in the shape specified
above. No prose outside the JSON.
"""


@dataclass(frozen=True)
class CreativeWriterBlock:
    """One block attached to a section, ready to render."""

    block_id: str
    block_kind: str  # 'insight' | 'open_question' | 'operator_note' | 'claim'
    label: str  # short title or first-line for the block
    body: str  # the block's content
    source_tier: Optional[int] = None  # 1..5 if known


@dataclass(frozen=True)
class CreativeWriterContext:
    """All inputs the user template needs."""

    deliverable_title: str
    deliverable_kind: str
    section_title: str
    section_index: int
    section_count: int
    blocks: List[CreativeWriterBlock] = field(default_factory=list)
    style_guide: str = ""


def _render_block(block: CreativeWriterBlock) -> str:
    tier_str = (
        f" (Tier {block.source_tier})" if block.source_tier else ""
    )
    return (
        f"### [{block.block_kind}] {block.label} "
        f"`{block.block_id}`{tier_str}\n\n{block.body.strip()}"
    )


def render_user_template(ctx: CreativeWriterContext) -> str:
    """Fill the user template with the context."""
    blocks_block = (
        "\n\n".join(_render_block(b) for b in ctx.blocks)
        if ctx.blocks else "_No blocks attached to this section._"
    )
    style_guide = ctx.style_guide.strip() or (
        "_No style guide provided — default to substrate voice and style discipline._"
    )
    return CREATIVE_WRITER_USER_TEMPLATE.format(
        deliverable_title=ctx.deliverable_title,
        deliverable_kind=ctx.deliverable_kind,
        section_title=ctx.section_title or "(untitled section)",
        section_index=ctx.section_index,
        section_count=ctx.section_count,
        style_guide=style_guide,
        blocks_block=blocks_block,
    )


def render_full_prompt(
    ctx: CreativeWriterContext,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for dispatch."""
    return CREATIVE_WRITER_SYSTEM_PROMPT, render_user_template(ctx)
