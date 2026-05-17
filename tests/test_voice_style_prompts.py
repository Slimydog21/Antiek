"""Lock-in tests for the voice and style discipline in the synthesizer
and evidence_retriever prompts.

These tests don't validate the LLM's actual output (that requires a real
dispatch). They lock the system prompts themselves so a future refactor
can't silently regress the discipline.

See docs/strategy/voice-and-style-discipline.md for the full discipline.
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from roles.evidence_retriever.prompt import EVIDENCE_RETRIEVER_SYSTEM_PROMPT
from roles.synthesizer.prompt import SYNTHESIZER_SYSTEM_PROMPT


# ── Synthesizer prompt ──────────────────────────────────────────────


def test_synthesizer_prompt_has_voice_and_style_section():
    assert "Voice and style" in SYNTHESIZER_SYSTEM_PROMPT


def test_synthesizer_prompt_forbids_em_dashes():
    assert "Em-dashes" in SYNTHESIZER_SYSTEM_PROMPT
    assert "at most one em-dash" in SYNTHESIZER_SYSTEM_PROMPT.lower()


def test_synthesizer_prompt_forbids_padding_constructions():
    # The forbidden-constructions list names these explicitly
    for forbidden in (
        "It is important to note",
        "It is worth observing",
        "This indicates that",
    ):
        assert forbidden in SYNTHESIZER_SYSTEM_PROMPT


def test_synthesizer_prompt_demands_sector_vocabulary():
    """Generic AI vocabulary is a signal of subject-matter weakness."""
    assert "vocabulary" in SYNTHESIZER_SYSTEM_PROMPT.lower()
    assert "field's words" in SYNTHESIZER_SYSTEM_PROMPT or \
           "corpus's vocabulary" in SYNTHESIZER_SYSTEM_PROMPT


def test_synthesizer_prompt_demands_prose_within_sections():
    """Top-level structure stays bulleted (insights vs questions),
    but within each section the body must be flowing prose."""
    assert "Prose within sections" in SYNTHESIZER_SYSTEM_PROMPT or \
           "flowing paragraphs" in SYNTHESIZER_SYSTEM_PROMPT


# ── Evidence retriever prompt ───────────────────────────────────────


def test_evidence_retriever_prompt_has_voice_section():
    assert "Voice for claim text" in EVIDENCE_RETRIEVER_SYSTEM_PROMPT


def test_evidence_retriever_prompt_forbids_em_dashes_in_claims():
    assert "Em-dashes" in EVIDENCE_RETRIEVER_SYSTEM_PROMPT


def test_evidence_retriever_prompt_forbids_context_indicates_preamble():
    """'The context indicates that...' is the classic LLM-slop opener
    for structured-output roles. Explicitly banned in the discipline."""
    assert "The context indicates that" in EVIDENCE_RETRIEVER_SYSTEM_PROMPT


def test_evidence_retriever_prompt_has_good_bad_example():
    """The prompt carries a concrete good-vs-bad claim example so the
    model has a positive target, not just a forbid list."""
    assert "Malanowski" in EVIDENCE_RETRIEVER_SYSTEM_PROMPT  # the example uses the radar source
    assert "Same information" in EVIDENCE_RETRIEVER_SYSTEM_PROMPT
