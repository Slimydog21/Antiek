"""Prompt-level style conditioning (specs/write/ SPR-09).

The operator's thesis: a writer's last-mile edits reveal their style, so
future generation can offer a *selectable* style that produces similar
prose. Per the Q1 decision, v1 does the **capture + prompt-level
conditioning** half now and **defers training** to the gated Loop-3 track.

This module is the prompt-level half, and the honesty discipline is the
whole point:

- A style is assembled by **retrieval**, not training — a set of exemplars
  (the writer's accepted edits / prior prose, from SPR-02) plus extracted
  ``voice_style`` features. **No model weights are produced.**
- Conditioning is **prompt-level only**: the exemplars + feature summary
  are injected into ``creative_writer``'s existing ``style_guide`` field.
  The model is unchanged.
- The similarity readout is a **heuristic**, explicitly labeled — never
  "the system learned your voice." With few exemplars the signal is weak,
  and we say so.
- There is a **hard no-training guard**: this module imports nothing from
  ``sft_runner`` / ``rubric_verifier`` / any RL path. The trained per-user
  model and on-policy RL stay behind ``unlock_gate`` (G8). A test asserts
  no training path is reachable.

The ``voice_style`` anti-slop gate always wins: conditioning toward a
style can never push output below the §5.5 gate (~0.70). If a selected
style would, the gate flags it and the caller regenerates.
"""

from __future__ import annotations

import dataclasses
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional, Sequence

try:
    from ..graph.ops import content_addressed_id, new_random_id
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.graph.ops import content_addressed_id, new_random_id  # type: ignore[no-redef]

from substrate.voice_style.rubric import score_voice_style

# The §5.5 anti-slop quality gate. Conditioning can never push output
# below this — the gate wins (mirrors quality_gate.check_voice_style).
VOICE_STYLE_GATE = 0.70

# Below this many exemplars the conditioning signal is weak and we declare
# it weak rather than implying a faithful voice clone (rigor #1 + #3).
MIN_EXEMPLARS_FOR_STRONG_SIGNAL = 3

# Conditioning prompt budget (prompt-level, so token-bounded).
_DEFAULT_MAX_EXEMPLARS = 5
_DEFAULT_MAX_CHARS = 4000


# ---------------------------------------------------------------------------
# Deterministic style features (NOT learned weights)
# ---------------------------------------------------------------------------


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def extract_style_features(text: str) -> dict:
    """Extract a small, deterministic feature vector from prose. These are
    descriptive statistics + the voice_style score — NOT trained
    parameters. Same text → same features."""
    words = text.split()
    n_words = max(1, len(words))
    sents = _sentences(text)
    n_sents = max(1, len(sents))
    voice_score, _violations = score_voice_style(text)
    return {
        "voice_style_score": round(voice_score, 4),
        "mean_sentence_len_words": round(n_words / n_sents, 3),
        "em_dash_per_100w": round((text.count("—") + text.count("—")) / n_words * 100, 3),
        "comma_per_100w": round(text.count(",") / n_words * 100, 3),
        "mean_word_len_chars": round(sum(len(w) for w in words) / n_words, 3),
        "semicolon_per_100w": round(text.count(";") / n_words * 100, 3),
    }


# Feature scales used to normalize distance into a [0,1] similarity. Chosen
# as plausible spreads; documented so the heuristic is legible.
_FEATURE_SCALE = {
    "voice_style_score": 1.0,
    "mean_sentence_len_words": 20.0,
    "em_dash_per_100w": 3.0,
    "comma_per_100w": 8.0,
    "mean_word_len_chars": 3.0,
    "semicolon_per_100w": 2.0,
}


def _aggregate(features_list: Sequence[dict]) -> dict:
    if not features_list:
        return {k: 0.0 for k in _FEATURE_SCALE}
    keys = _FEATURE_SCALE.keys()
    return {
        k: round(sum(f.get(k, 0.0) for f in features_list) / len(features_list), 4)
        for k in keys
    }


def _heuristic_similarity(a: dict, b: dict) -> float:
    """1 - mean normalized absolute feature difference, clamped to [0,1].
    A bounded, deterministic heuristic — explicitly NOT ground truth."""
    diffs = []
    for k, scale in _FEATURE_SCALE.items():
        diffs.append(min(1.0, abs(a.get(k, 0.0) - b.get(k, 0.0)) / scale))
    return round(max(0.0, 1.0 - sum(diffs) / len(diffs)), 4)


# ---------------------------------------------------------------------------
# Style profile (exemplars + features — no weights)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StyleProfile:
    """A selectable style. Exemplars + extracted features, by retrieval —
    NOT a trained model. ``weak_signal`` is declared honestly when there
    are too few exemplars to imply a faithful voice."""

    profile_id: str
    name: str
    exemplars: tuple[str, ...]
    features: dict
    source: str  # 'accepted_edits' | 'prior_prose'
    weak_signal: bool
    notes: str = ""

    @property
    def exemplar_count(self) -> int:
        return len(self.exemplars)


@dataclass(frozen=True)
class StyleSimilarity:
    """A heuristic readout of how close prose is to a target style. The
    voice_style gate result is carried alongside — and the gate WINS."""

    similarity: float
    is_heuristic: bool
    weak_signal: bool
    gate_passed: bool
    gate_score: float
    detail: str


def assemble_style_profile(
    *,
    exemplars: Sequence[str],
    name: str,
    source: str = "accepted_edits",
    profile_id: Optional[str] = None,
) -> StyleProfile:
    """Assemble a style profile by retrieval from exemplars. No training,
    no weights — the profile is the exemplar set + aggregated voice_style
    features. Declares a weak signal when exemplars are too few."""
    clean = tuple(e.strip() for e in exemplars if e and e.strip())
    feats = _aggregate([extract_style_features(e) for e in clean]) if clean else _aggregate([])
    weak = len(clean) < MIN_EXEMPLARS_FOR_STRONG_SIGNAL
    notes = (
        f"weak signal: only {len(clean)} exemplar(s) (< {MIN_EXEMPLARS_FOR_STRONG_SIGNAL}); "
        "conditioning will shift output only slightly — this is prompt-level "
        "conditioning, not a learned voice."
        if weak else
        f"{len(clean)} exemplars; prompt-level conditioning (not a trained model)."
    )
    pid = profile_id or content_addressed_id("style", name + "|" + "|".join(clean))
    return StyleProfile(
        profile_id=pid, name=name, exemplars=clean, features=feats,
        source=source, weak_signal=weak, notes=notes,
    )


def assemble_from_authoring_trajectory(traj, *, name: str) -> StyleProfile:
    """Assemble a profile from a writer's *accepted edits* — the after-text
    of non-reverted replace/insert edits in an authoring trajectory
    (SPR-02). These are what the writer settled on, hence exemplary of
    their style. Reverted edits are excluded (a revert is not an
    endorsement)."""
    exemplars: list[str] = []
    for step in traj.signal_steps:  # signal_steps already excludes reverts
        if step.kind != "edit":
            continue
        if step.payload.get("edit_kind") in ("replace", "insert"):
            after = step.payload.get("after_text")
            if after and after.strip():
                exemplars.append(after)
    return assemble_style_profile(exemplars=exemplars, name=name, source="accepted_edits")


# ---------------------------------------------------------------------------
# Prompt-level conditioning (the model is unchanged)
# ---------------------------------------------------------------------------


def build_conditioning_prompt(
    profile: StyleProfile,
    *,
    max_exemplars: int = _DEFAULT_MAX_EXEMPLARS,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str:
    """Build the ``style_guide`` fragment to inject into the
    ``creative_writer`` prompt. Prompt-level only — no model change.
    Token-budget bounded (rigor #3 long-exemplar-set case)."""
    header = (
        f"Style: \"{profile.name}\" — match the voice and rhythm of the "
        "exemplars below. This is prompt-level conditioning on the writer's "
        "accepted edits, NOT a separate trained model. Honor the substrate "
        "voice/style discipline above all (it wins over style)."
    )
    if profile.weak_signal:
        header += (
            f" NOTE: only {profile.exemplar_count} exemplar(s) — the style "
            "signal is weak; lean on the substrate discipline when unsure."
        )
    feat = profile.features
    feat_line = (
        "Observed style features (descriptive, not prescriptive): "
        f"~{feat.get('mean_sentence_len_words', 0):.0f}-word sentences, "
        f"{feat.get('comma_per_100w', 0):.1f} commas / 100 words, "
        f"voice_style baseline {feat.get('voice_style_score', 0):.2f}."
    )
    parts = [header, "", feat_line, "", "Exemplars:"]
    budget = max_chars
    for i, ex in enumerate(profile.exemplars[:max_exemplars]):
        snippet = ex.strip()
        if len(snippet) > budget:
            snippet = snippet[: max(0, budget - 1)].rstrip() + "…"
        if not snippet:
            break
        parts.append(f"{i + 1}. {snippet}")
        budget -= len(snippet)
        if budget <= 0:
            break
    return "\n".join(parts)


def condition_context(ctx, profile: StyleProfile, **kwargs):
    """Return a COPY of a ``CreativeWriterContext`` with its ``style_guide``
    set to the conditioning prompt. The context's blocks and the model are
    unchanged — this is purely prompt-level. (Typed loosely to avoid a
    hard import of the role at module load.)"""
    return dataclasses.replace(ctx, style_guide=build_conditioning_prompt(profile, **kwargs))


def score_style_similarity(text: str, profile: StyleProfile) -> StyleSimilarity:
    """Heuristic similarity of ``text`` to a target style, plus the
    voice_style gate result. The similarity is explicitly heuristic
    (descriptive feature distance), and the gate WINS — sub-gate output is
    flagged regardless of how 'similar' it looks."""
    feats = extract_style_features(text)
    sim = _heuristic_similarity(feats, profile.features)
    gate_score, violations = score_voice_style(text)
    gate_passed = gate_score >= VOICE_STYLE_GATE
    detail = (
        f"heuristic feature similarity {sim:.2f} "
        f"({profile.exemplar_count} exemplar(s)"
        + (", WEAK signal" if profile.weak_signal else "")
        + f"); voice_style gate {'PASS' if gate_passed else 'FAIL'} "
        f"(score {gate_score:.2f}, threshold {VOICE_STYLE_GATE})"
    )
    if not gate_passed:
        detail += " — gate wins: regenerate, do not ship sub-gate prose."
    return StyleSimilarity(
        similarity=sim, is_heuristic=True, weak_signal=profile.weak_signal,
        gate_passed=gate_passed, gate_score=round(gate_score, 4), detail=detail,
    )
