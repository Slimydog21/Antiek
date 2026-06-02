"""Lock-in tests for the canonical §5 voice/style source (Sprint 11 M2).

`substrate.voice_style.constructions` is the SINGLE source the role prompts
reference instead of inlining their own forbidden-construction lists. These
tests pin:

1. the rendered addendum text is byte-identical to what the synthesizer and
   evidence_retriever prompts carried before the de-duplication (equivalence —
   this is a refactor, not a discipline change);
2. the canonical forbidden items are present in the rendered text;
3. the roles that weave the discipline into bespoke prose (creative_writer,
   interviewer) still ban the canonical constructions, so their
   register-specific framing cannot silently relax (drift guard).

See docs/strategy/voice-and-style-discipline.md (design authority) and the
constructions.py module docstring (rationale).
"""

from __future__ import annotations

import pytest

from roles.creative_writer.prompt import CREATIVE_WRITER_SYSTEM_PROMPT
from roles.evidence_retriever.prompt import EVIDENCE_RETRIEVER_SYSTEM_PROMPT
from roles.interviewer.prompt import INTERVIEWER_SYSTEM_PROMPT
from roles.synthesizer.prompt import SYNTHESIZER_SYSTEM_PROMPT
from substrate.voice_style import (
    FORBIDDEN_CONSTRUCTIONS,
    forbidden_phrase_examples,
    render_voice_addendum,
)
from substrate.voice_style.constructions import (
    CONFIDENCE_REPETITION,
    CONTEXT_PREAMBLE,
    EM_DASH,
    ENUMERATION_TICS,
    HEDGING,
    PADDING,
)

# ── Canonical data ──────────────────────────────────────────────────


def test_canonical_list_covers_the_slop_pattern():
    """Every §5.1 forbidden construction is present in the canonical list."""
    keys = {c.key for c in FORBIDDEN_CONSTRUCTIONS}
    assert keys == {
        "em_dash",
        "padding",
        "hedging",
        "enumeration_tics",
        "confidence_repetition",
        "context_preamble",
    }


def test_forbidden_phrase_examples_are_flat_and_drop_the_glyph():
    phrases = forbidden_phrase_examples()
    assert "—" not in phrases  # the em-dash glyph is a character, not a phrase
    assert "It is important to note that" in phrases
    assert "Firstly," in phrases
    assert "The context indicates that" in phrases


# ── render_voice_addendum — equivalence ─────────────────────────────


def test_synthesizer_addendum_equivalent_to_inline_block():
    """Byte-for-byte equal to the block the synthesizer prompt embeds."""
    rendered = render_voice_addendum("synthesizer")
    inline = SYNTHESIZER_SYSTEM_PROMPT[
        SYNTHESIZER_SYSTEM_PROMPT.index("## Voice and style") :
    ]
    assert rendered == inline


def test_evidence_retriever_addendum_equivalent_to_inline_block():
    rendered = render_voice_addendum("evidence_retriever")
    inline = EVIDENCE_RETRIEVER_SYSTEM_PROMPT[
        EVIDENCE_RETRIEVER_SYSTEM_PROMPT.index("## Voice for claim text") :
    ]
    assert rendered == inline


def test_default_register_is_synthesizer():
    assert render_voice_addendum() == render_voice_addendum("synthesizer")


def test_unknown_register_raises():
    with pytest.raises(ValueError, match="unknown voice-addendum register"):
        render_voice_addendum("does_not_exist")  # type: ignore[arg-type]


# ── render_voice_addendum — canonical items present ─────────────────


def test_synthesizer_addendum_names_every_forbidden_construction():
    """The rendered synthesizer text must carry each canonical construction —
    the assertion that catches a future edit that drops one from the canonical
    source. The em-dash / padding / hedging / enumeration constructions quote
    their example phrases verbatim in the addendum; the confidence-repetition
    construction is described by its rule (its '(high confidence)' marker is
    illustrative data, not quoted in the synthesizer prose)."""
    text = render_voice_addendum("synthesizer")
    for c in (PADDING, HEDGING, ENUMERATION_TICS):
        for ex in c.examples:
            assert ex in text, f"{c.key} example {ex!r} missing from synthesizer addendum"
    # Em-dash and confidence-repetition are present by rule, not example phrase.
    assert "Em-dashes" in text
    assert "confidence levels in prose" in text  # CONFIDENCE_REPETITION rule
    # Sanity: the canonical confidence marker exists as data even if not quoted.
    assert CONFIDENCE_REPETITION.examples == ("(high confidence)",)
    assert EM_DASH.examples == ("—",)


def test_evidence_addendum_carries_context_preamble_ban():
    text = render_voice_addendum("evidence_retriever")
    assert CONTEXT_PREAMBLE.examples[0] in text  # "The context indicates that"
    assert "Em-dashes" in text


def test_every_canonical_construction_is_rendered_in_some_register():
    """No canonical construction may be defined-but-never-surfaced.

    The "single source, no drift" guarantee (M2) is that the rendered prose and
    the machine-readable index cannot diverge silently. The byte-equivalence
    tests pin the prose; this pins the other direction: every item in
    FORBIDDEN_CONSTRUCTIONS must appear — by its rule wording or an example
    phrase — in at least one rendered register. Add a construction to the source
    but wire it into no prompt and this fails. (Per-register wording is bespoke,
    so the signal is "rule OR example present somewhere," not a uniform format.)
    """
    rendered = "\n".join(
        render_voice_addendum(r) for r in ("synthesizer", "evidence_retriever")
    )
    for c in FORBIDDEN_CONSTRUCTIONS:
        signals = [c.rule, *(ex for ex in c.examples if ex != "—")]
        assert any(s and s in rendered for s in signals), (
            f"canonical construction {c.key!r} is defined in the source but "
            f"rendered in no register — wire it into a prompt or remove it"
        )


# ── Drift guard for the woven-prose roles ───────────────────────────


def test_creative_writer_still_bans_canonical_constructions():
    """creative_writer weaves a STRICTER register into its hard constraints;
    the discipline must still ban em-dashes, padding, and hedging so the
    register cannot silently relax below the canonical bar."""
    p = CREATIVE_WRITER_SYSTEM_PROMPT
    assert "No em-dashes" in p
    assert "No padding" in p
    assert "No hedging modifiers" in p


def test_interviewer_still_bans_hedging():
    """interviewer addresses a real person; its register is conversational,
    but the hedging ban (a canonical construction) must remain."""
    assert "No hedging modifiers" in INTERVIEWER_SYSTEM_PROMPT


def test_woven_roles_point_to_the_canonical_source():
    """Defensibility: both woven roles name the canonical module so a future
    maintainer adds itself to the source rather than copy-pasting."""
    assert "substrate.voice_style.constructions" in CREATIVE_WRITER_SYSTEM_PROMPT or \
        "constructions" in _module_doc("roles.creative_writer.prompt")
    assert "constructions" in _module_doc("roles.interviewer.prompt")


def _module_doc(modname: str) -> str:
    import importlib

    mod = importlib.import_module(modname)
    return mod.__doc__ or ""
