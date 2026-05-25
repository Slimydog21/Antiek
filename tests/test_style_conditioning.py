"""Tests for prompt-level style conditioning (specs/write/ SPR-09).

The spine is honesty: this is conditioning, not a learned model, and a
maintainer must be able to confirm NO training path is reachable.

M1 style exemplar set — assembled by retrieval; no weights; weak signal
   declared when exemplars are few.
M2 prompt conditioning — exemplars injected into creative_writer's
   style_guide; the model/blocks are unchanged; the prompt observably
   changes (the testable proxy for "shifts generation").
M3 scoring — heuristic similarity labeled as heuristic; the voice_style
   gate still applies and WINS.
M4 no-training guard — the module imports no trainer/RL path; conditioning
   works with the Loop-3 gate closed.
"""

from __future__ import annotations

import ast
import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from roles.creative_writer.prompt import CreativeWriterBlock, CreativeWriterContext
from substrate.edit.authoring_trajectory import reconstruct_from_events
from substrate.write.style_profile import (
    MIN_EXEMPLARS_FOR_STRONG_SIGNAL,
    VOICE_STYLE_GATE,
    StyleProfile,
    assemble_from_authoring_trajectory,
    assemble_style_profile,
    build_conditioning_prompt,
    condition_context,
    extract_style_features,
    score_style_similarity,
)

# A few terse, flowing exemplars (in the operator's anti-slop register).
_EXEMPLARS = [
    "The thesis holds because the mechanism is load-bearing, not decorative.",
    "Capital intensity rises with scale; the moat is the data, not the model.",
    "Provenance is the product. Strip it and you have a worse chatbot.",
    "The edit is the writing. The draft is just where editing starts.",
]


# ── M1 — exemplar set, by retrieval, no weights ────────────────────


def test_assemble_profile_from_exemplars():
    profile = assemble_style_profile(exemplars=_EXEMPLARS, name="operator-voice")
    assert isinstance(profile, StyleProfile)
    assert profile.exemplar_count == 4
    assert not profile.weak_signal
    # Features are descriptive stats, not weights.
    assert "voice_style_score" in profile.features
    assert "mean_sentence_len_words" in profile.features


def test_weak_signal_declared_with_few_exemplars():
    profile = assemble_style_profile(exemplars=_EXEMPLARS[:1], name="thin")
    assert profile.weak_signal
    assert profile.exemplar_count < MIN_EXEMPLARS_FOR_STRONG_SIGNAL
    assert "weak signal" in profile.notes.lower()


def test_assemble_from_accepted_edits_excludes_reverts():
    events = [
        {"action_type": "edit.captured", "event_id": "e1", "emitted_at": "t1",
         "payload": {"deliverable_id": "d1", "edit_kind": "replace",
                     "after_text": "kept this sentence", "reverted": False}},
        {"action_type": "edit.captured", "event_id": "e2", "emitted_at": "t2",
         "payload": {"deliverable_id": "d1", "edit_kind": "replace",
                     "after_text": "reverted this one", "reverted": True}},
    ]
    traj = reconstruct_from_events(events, "d1")
    profile = assemble_from_authoring_trajectory(traj, name="from-edits")
    assert "kept this sentence" in profile.exemplars
    assert "reverted this one" not in profile.exemplars


# ── M2 — prompt-level conditioning ─────────────────────────────────


def test_conditioning_changes_the_prompt_not_the_model():
    profile = assemble_style_profile(exemplars=_EXEMPLARS, name="operator-voice")
    ctx = CreativeWriterContext(
        deliverable_title="T", deliverable_kind="research_memo",
        section_title="S", section_index=0, section_count=1,
        blocks=[CreativeWriterBlock(block_id="b1", block_kind="insight",
                                    label="x", body="y")],
    )
    conditioned = condition_context(ctx, profile)
    # The prompt observably shifts toward the style (the testable proxy).
    assert conditioned.style_guide != ctx.style_guide
    assert profile.exemplars[0][:20] in conditioned.style_guide
    # Blocks (the substrate) are unchanged — conditioning is prompt-only.
    assert conditioned.blocks == ctx.blocks


def test_conditioning_prompt_respects_budget():
    long_ex = ["word " * 5000]
    profile = assemble_style_profile(exemplars=long_ex * 3, name="huge")
    prompt = build_conditioning_prompt(profile, max_exemplars=5, max_chars=500)
    assert len(prompt) < 2000  # header + budgeted exemplars, bounded


def test_conditioning_prompt_declares_weak_signal():
    profile = assemble_style_profile(exemplars=_EXEMPLARS[:1], name="thin")
    prompt = build_conditioning_prompt(profile)
    assert "weak" in prompt.lower()
    assert "not a separate trained model" in prompt.lower()


# ── M3 — heuristic scoring; the gate wins ──────────────────────────


def test_similarity_is_labeled_heuristic():
    profile = assemble_style_profile(exemplars=_EXEMPLARS, name="operator-voice")
    sim = score_style_similarity(_EXEMPLARS[0], profile)
    assert sim.is_heuristic is True
    assert 0.0 <= sim.similarity <= 1.0
    assert "heuristic" in sim.detail.lower()


def test_gate_wins_over_style():
    """Slop-laden prose fails the voice_style gate regardless of how it
    scores on similarity — the gate wins."""
    profile = assemble_style_profile(exemplars=_EXEMPLARS, name="operator-voice")
    slop = (
        "Key takeaways: let me explain. Moreover, furthermore, additionally, "
        "it could be argued that perhaps possibly this is — arguably — in some "
        "sense worth noting. In conclusion, to summarize, all in all.\n"
        "- bullet one\n- bullet two\n- bullet three\n- bullet four\n"
        "- bullet five\n- bullet six\n- bullet seven\n"
    )
    sim = score_style_similarity(slop, profile)
    assert sim.gate_passed is False
    assert sim.gate_score < VOICE_STYLE_GATE
    assert "gate wins" in sim.detail.lower()


def test_features_are_deterministic():
    a = extract_style_features(_EXEMPLARS[0])
    b = extract_style_features(_EXEMPLARS[0])
    assert a == b


# ── M4 — the no-training guard ─────────────────────────────────────


def test_no_training_path_reachable():
    """The hard guard: style_profile must import NO trainer / RL path.
    AST-level so prose mentions in docstrings don't falsely trip it."""
    import substrate.write.style_profile as sp

    tree = ast.parse(open(sp.__file__).read())
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
            imported.extend(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
    for forbidden in ("sft_runner", "rubric_verifier", "prime", "verifiers_env"):
        assert not any(forbidden in name for name in imported), (
            f"style_profile must not import {forbidden} — conditioning is "
            "prompt-only; training stays gated on Loop-3/G8"
        )


def test_conditioning_works_with_gate_closed(monkeypatch):
    """Conditioning does not depend on the Loop-3 unlock gate at all."""
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)
    profile = assemble_style_profile(exemplars=_EXEMPLARS, name="operator-voice")
    prompt = build_conditioning_prompt(profile)  # must not raise
    assert profile.name in prompt
