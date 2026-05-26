"""Canonical §5 forbidden-construction source — ONE list, every role references it.

WHY THIS MODULE EXISTS (drift prevention).
------------------------------------------
The voice/style discipline (master-spec §5; design authority
``docs/strategy/voice-and-style-discipline.md``) is load-bearing: Antiek's
product proposition collapses if generated output reads like LLM slop. The
discipline's forbidden-construction list (em-dashes, padding sentences, hedging
modifiers, enumeration tics, confidence-repetition, the "context indicates"
preamble) was, before Sprint 11, **copy-pasted inline into four role prompts**
(synthesizer, evidence_retriever, creative_writer, interviewer) plus the scorer.
Four copies of a list drift — and they already had: the synthesizer banned
"Firstly/Secondly/Finally," the creative_writer banned "perhaps/arguably," and
neither knew about the other. A surface whose copy silently relaxed would go
sloppy without any test noticing.

This module is the **single canonical source** of the §5 forbidden constructions
+ permitted-construction guidance. The discipline lives here two complementary
ways: as machine-readable data (:data:`FORBIDDEN_CONSTRUCTIONS` — the index a
drift guard and non-prose consumers read) and as the canonical rendered prose
per register (:func:`render_voice_addendum`, byte-pinned to the pre-Sprint-11
text by test). Roles import the renderer (or the data) instead of inlining their
own list, and a test asserts every canonical construction is rendered in some
register, so the discipline cannot fork.

WHERE A FUTURE ROLE ADDS ITSELF.
--------------------------------
A new operator-facing role does NOT copy-paste a forbidden list. It either:

1. calls ``render_voice_addendum(register=...)`` for one of the existing
   registers (``synthesizer`` is the canonical full discipline;
   ``evidence_retriever`` is the upstream-claim-text flavor), or
2. if it needs a genuinely new register (a stricter or differently-framed
   variant), it adds that register HERE — extending this one source — so the
   shared discipline stays the single point of truth. A new register's *framing*
   and exact wording may differ (the synthesizer renders "Padding sentences"
   where the evidence register renders "Padding clauses"); the no-orphan test
   (every :data:`FORBIDDEN_CONSTRUCTIONS` item must surface in some rendered
   register) keeps the discipline from forking.

EQUIVALENCE CONTRACT.
---------------------
``render_voice_addendum("synthesizer")`` and ``render_voice_addendum(
"evidence_retriever")`` reproduce, byte-for-byte, the addendum text those two
prompts carried before Sprint 11. This is a de-duplication, NOT a change to the
discipline. ``tests/test_voice_style_constructions.py`` pins the rendered text
and asserts every canonical forbidden item is present.

This is a pure-data + pure-string module: no LLM call, no I/O, offline. It is
the prompt-side sibling of :mod:`substrate.voice_style.rubric` (the
deterministic *scorer* of the same discipline). The scorer measures output; this
module instructs the model that produces it. They share the §5 origin; see the
note in ``score.py`` and ``rubric.py`` for why they are intentionally not the
same code object (the scorer's regex weights are tuned independently).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# ── Canonical forbidden constructions (master-spec §5.1) ─────────────
#
# One item per slop construction. ``examples`` are the verbatim forbidden
# phrases (the part most prone to silent divergence across copies); ``rule`` is
# the one-line instruction; ``alternative`` is the permitted substitute where
# one exists. Roles render subsets/variants of these; they never re-list them.


@dataclass(frozen=True)
class ForbiddenConstruction:
    """One forbidden construction from the §5.1 slop pattern."""

    key: str
    rule: str
    examples: tuple[str, ...]
    alternative: str = ""


EM_DASH = ForbiddenConstruction(
    key="em_dash",
    rule="Em-dashes",
    examples=("—",),
    alternative="Use commas, parentheses, or two sentences.",
)

PADDING = ForbiddenConstruction(
    key="padding",
    rule="Padding sentences",
    examples=(
        "It is important to note that",
        "It is worth observing that",
        "This indicates that",
    ),
    alternative="State the claim.",
)

HEDGING = ForbiddenConstruction(
    key="hedging",
    rule="Hedging modifiers that undermine claims you have evidence for",
    examples=(
        "It could be argued that",
        "Some might suggest that",
    ),
    alternative=(
        "If evidence supports it, say it. If it doesn't, the claim doesn't belong."
    ),
)

ENUMERATION_TICS = ForbiddenConstruction(
    key="enumeration_tics",
    rule="Generic enumeration tics",
    examples=("Firstly,", "Secondly,", "Finally,"),
)

CONFIDENCE_REPETITION = ForbiddenConstruction(
    key="confidence_repetition",
    rule="Repetition of confidence levels in prose",
    examples=("(high confidence)",),
    alternative=(
        "The structured `confidence` field carries the confidence metadata; "
        "the prose carries the substance."
    ),
)

# The evidence_retriever's structured-output role has one extra construction the
# prose roles don't: the "context indicates" preamble that structured-output
# models reach for. It lives in the canonical source so the upstream surface and
# any future structured role share it rather than re-inventing it.
CONTEXT_PREAMBLE = ForbiddenConstruction(
    key="context_preamble",
    rule='"The context indicates that..." preamble',
    examples=("The context indicates that",),
    alternative="State the claim.",
)


# The full canonical list (master-spec §5.1). Order is the synthesizer's
# addendum order — the one the lock-in test pins.
FORBIDDEN_CONSTRUCTIONS: tuple[ForbiddenConstruction, ...] = (
    EM_DASH,
    PADDING,
    HEDGING,
    ENUMERATION_TICS,
    CONFIDENCE_REPETITION,
    CONTEXT_PREAMBLE,
)


# Registers a role can request. Adding a genuinely new variant means adding a
# value here AND a branch in render_voice_addendum that draws its forbidden
# items from FORBIDDEN_CONSTRUCTIONS — not a new inline list in the role file.
Register = Literal["synthesizer", "evidence_retriever"]


# ── Synthesizer register (canonical full discipline) ─────────────────
#
# Reproduces, byte-for-byte, the addendum the synthesizer prompt carried before
# Sprint 11. The forbidden-construction lines below are the canonical RENDERED
# PROSE for this register — bespoke wording the dataclasses cannot mechanically
# derive (this register adds an "at most one em-dash per thesis" beat; the
# evidence register renders "Padding clauses" where this one renders "Padding
# sentences"). FORBIDDEN_CONSTRUCTIONS above is the canonical machine-readable
# INDEX of the discipline, not the prose generator: it backs
# forbidden_phrase_examples() and the no-orphan drift guard
# (test_every_canonical_construction_is_rendered_in_some_register), which fails
# if a construction is added to the source but rendered in no register. The
# surrounding framing (vocabulary, prose-within-sections, permitted-and-encouraged)
# is synthesizer-specific register prose.

_SYNTHESIZER_FORBIDDEN_LINES = (
    "- Em-dashes. Use commas, parentheses, or two sentences. At most one "
    "em-dash per thesis if absolutely needed for a strong beat.",
    '- Padding sentences ("It is important to note that," "It is worth '
    'observing that," "This indicates that"). State the claim.',
    '- Hedging modifiers that undermine claims you have evidence for ("It '
    'could be argued that," "Some might suggest that"). If evidence supports '
    "it, say it. If it doesn't, the claim doesn't belong.",
    '- Generic enumeration tics ("Firstly," "Secondly," "Finally,").',
    "- Repetition of confidence levels in prose. The structured `confidence` "
    "field carries the confidence metadata; the prose carries the substance.",
)


def _render_synthesizer() -> str:
    forbidden = "\n".join(_SYNTHESIZER_FORBIDDEN_LINES)
    return (
        "## Voice and style — non-negotiable\n"
        "\n"
        "The thesis is read by a human trying to understand a subject, not by "
        "a downstream automated consumer. Write for engaged reading.\n"
        "\n"
        "**Absorb the source corpus's vocabulary.** If chunks use "
        '"direct-path interference suppression," do not paraphrase to "signal '
        'cancellation." If chunks use sector-specific shorthand, use it (expand '
        "on first occurrence). Generic AI vocabulary is a signal of "
        "subject-matter weakness; use the field's words.\n"
        "\n"
        "**Prose within sections, not bullets.** Top-level structure "
        "(`thesis_summary`, `thesis_components`, `falsification_conditions`, "
        "`execution_risks`) stays. Within each component's `claim` and "
        "`rationale`, write flowing paragraphs. The structured fields carry the "
        "schema; the prose carries the substance.\n"
        "\n"
        "**Forbidden constructions:**\n"
        f"{forbidden}\n"
        "\n"
        "**Permitted and encouraged:**\n"
        "- Specific numbers from the corpus in the corpus's units.\n"
        "- Sentences with internal logic, not just declarative facts. The "
        "reader should follow why one claim leads to another.\n"
        "- Naming primary sources by distinguishing feature, not just tier "
        '("the Malanowski textbook" beats "a Tier-2 source").\n'
        "- Acknowledging the boundary of what was retrieved (\"the corpus "
        'surfaced no comparative benchmark across illuminator types" beats '
        '"this question cannot be answered").'
    )


# ── Evidence-retriever register (upstream claim-text flavor) ─────────
#
# Reproduces, byte-for-byte, the addendum the evidence_retriever prompt carried
# before Sprint 11. Narrower than the synthesizer's: it governs the `claim`
# field text, adds the structured-output "context indicates" preamble ban, and
# carries the good/bad claim example pair.

_EVIDENCE_FORBIDDEN_LINES = (
    "- Em-dashes",
    '- "The context indicates that..." preamble. State the claim.',
    '- Padding clauses ("It should be noted that...", "It is worth observing '
    'that...").',
)


def _render_evidence_retriever() -> str:
    forbidden = "\n".join(_EVIDENCE_FORBIDDEN_LINES)
    return (
        "## Voice for claim text\n"
        "\n"
        "Each `claim` field is read by a synthesizer downstream AND by a human "
        "in the trajectory view. Write claim text as you would write a research "
        "note for yourself: specific, citing the source's language, avoiding "
        "generic AI vocabulary.\n"
        "\n"
        "**Forbidden in claim text:**\n"
        f"{forbidden}\n"
        "\n"
        'A good claim: *"Malanowski reports LSL and block-lattice filters '
        "achieve >40 dB sidelobe reduction relative to the DPI peak on real "
        'passive radar data."*\n'
        "\n"
        'A bad claim (current default): *"The context indicates that adaptive '
        "filtering algorithms, specifically least-squares lattice (LSL) and "
        "block lattice filters, have been reported to demonstrate sidelobe "
        "level reductions exceeding 40 dB relative to direct-path interference "
        'peaks based on real passive radar dataset evidence."*\n'
        "\n"
        "Same information; first reads like research, second reads like a "
        "parsing artifact."
    )


_RENDERERS = {
    "synthesizer": _render_synthesizer,
    "evidence_retriever": _render_evidence_retriever,
}


def render_voice_addendum(register: Register = "synthesizer") -> str:
    """Render the §5 voice/style prompt addendum for a role ``register``.

    ``register="synthesizer"`` returns the canonical full discipline
    (vocabulary + prose-within-sections + forbidden constructions +
    permitted-and-encouraged). ``register="evidence_retriever"`` returns the
    narrower upstream-claim-text flavor.

    Both reproduce, byte-for-byte, the text those prompts carried before the
    Sprint-11 de-duplication. A new role needing a different framing adds a
    register here (drawing its forbidden items from
    :data:`FORBIDDEN_CONSTRUCTIONS`) rather than re-listing the discipline in
    its own prompt file.
    """
    try:
        return _RENDERERS[register]()
    except KeyError:
        raise ValueError(
            f"unknown voice-addendum register {register!r}; "
            f"known registers: {sorted(_RENDERERS)}"
        ) from None


def forbidden_phrase_examples() -> tuple[str, ...]:
    """Flat tuple of every verbatim forbidden phrase across all constructions.

    The drift-prone payload, exposed as data so a non-prose consumer (a role
    that weaves the discipline into its own hard-constraint prose, or a
    deterministic check) can reference the same phrase list the renderer uses.
    Excludes the bare em-dash glyph (it is a character, not a phrase)."""
    out: list[str] = []
    for c in FORBIDDEN_CONSTRUCTIONS:
        for ex in c.examples:
            if ex != "—":
                out.append(ex)
    return tuple(out)
