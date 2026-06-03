"""Style-guide context-pack wiring (Sprint 11).

This module is the single home for the three things that gate the
``style_extractor`` role's output into the synthesizer's context pack:

1. **The feature flag** — ``ANTIEK_STYLE_EXTRACTOR_ENABLED``, DEFAULT
   OFF. ``style_extractor_enabled()`` reads it with the same
   ``("1", "true", "yes")`` convention the rest of the substrate uses.

2. **The skip heuristic** — ``should_run_style_extractor(...)`` returns
   ``False`` (skip) when more than 50% of the decomposer's sub-questions
   are pure-quantitative. Per ``docs/strategy/voice-and-style-discipline.md``
   the extractor adds nothing to "find me the number" investigations.

   *Heuristic note (intellectual honesty):* the design doc names
   hypothetical sub-question categories ``parameter_extraction`` /
   ``quantitative_metric``. Those are NOT members of the substrate's
   actual ``SubQuestionCategory`` enum (which is investment-thesis
   oriented: ``market_sizing``, ``defensibility``, …). The realizable
   quantitative signal that DOES exist per sub-question is the
   decomposer's ``evidence_type_required`` field
   (``quantitative | qualitative | mixed``). The heuristic therefore
   keys off ``evidence_type_required == "quantitative"``. This is a
   faithful realization of the doc's intent against the schema that
   exists; if a future schema adds explicit quantitative categories,
   ``_is_quantitative`` is the one place to extend.

3. **The injection helper** — ``maybe_style_guide_layer(...)`` returns a
   ``LayerSource`` (``kind="style_guide"``, priority equal to
   ``long_term_skill``) when, and ONLY when, the flag is ON, the
   investigation is qualitative, and a parseable ``StyleGuide`` is
   supplied. Otherwise it returns ``None``.

**Inert-by-default invariant (binding):** with the flag OFF,
``maybe_style_guide_layer`` returns ``None`` for every input, so no
``style_guide`` layer is ever constructed, the caller's layer list is
unchanged, and the assembled pack is byte-identical to today's. The live
synthesis path is untouched. ``tests/test_style_extractor.py`` asserts
this.

This module is import-light by design. It does NOT import ``roles`` (that
would invert the substrate→roles layering); the parsed ``StyleGuide`` is
passed in by the caller (the future bridge handler), and the heuristic
accepts duck-typed sub-questions (any object exposing
``evidence_type_required``, or a bare string) so it can be unit-tested
without the decomposer.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable

try:
    from .assembler import DEFAULT_KIND_PRIORITY, LayerSource
except ImportError:  # pragma: no cover — direct-script fallback
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.context_pack.assembler import (  # type: ignore[no-redef]
        DEFAULT_KIND_PRIORITY,
        LayerSource,
    )


# The feature flag. DEFAULT OFF — the whole role is dark until the
# operator exports this and (per program.md) wires `style_extractor` to a
# flash tier in dispatch/config.yaml.
STYLE_EXTRACTOR_FLAG = "ANTIEK_STYLE_EXTRACTOR_ENABLED"

# The skip threshold: strictly MORE THAN this fraction of quantitative
# sub-questions ⇒ skip the extractor (design doc: ">50%").
QUANTITATIVE_SKIP_THRESHOLD = 0.5

# The kind + default source label for the injected layer.
STYLE_GUIDE_LAYER_KIND = "style_guide"
STYLE_GUIDE_LAYER_SOURCE = "style_extractor"


@runtime_checkable
class _HasEvidenceType(Protocol):
    evidence_type_required: str


def style_extractor_enabled() -> bool:
    """Read the feature flag. DEFAULT OFF.

    Matches the substrate's env-flag convention
    (``substrate/speak/gate_status.py``): truthy iff the value is one of
    ``"1" | "true" | "yes"`` (case-insensitive, trimmed)."""
    return os.environ.get(STYLE_EXTRACTOR_FLAG, "").strip().lower() in (
        "1", "true", "yes",
    )


def _evidence_type_of(sub_question: Any) -> str | None:
    """Extract the ``evidence_type_required`` from a duck-typed
    sub-question. Accepts:

    - an object with an ``evidence_type_required`` attribute
      (e.g. the decomposer's ``ParsedSubQuestion`` or the schema's
      ``SubQuestion``),
    - a mapping with an ``"evidence_type_required"`` key,
    - a bare string (already the evidence type).

    Returns the lowercased evidence type, or ``None`` if it cannot be
    determined (such a sub-question is treated as non-quantitative —
    the conservative default keeps the extractor running rather than
    silently skipping)."""
    if isinstance(sub_question, str):
        return sub_question.strip().lower() or None
    if isinstance(sub_question, _HasEvidenceType):
        val = sub_question.evidence_type_required
        return val.strip().lower() if isinstance(val, str) else None
    if isinstance(sub_question, dict):
        val = sub_question.get("evidence_type_required")
        return val.strip().lower() if isinstance(val, str) else None
    return None


def _is_quantitative(sub_question: Any) -> bool:
    """A sub-question is pure-quantitative iff its
    ``evidence_type_required == "quantitative"``. ``mixed`` and
    ``qualitative`` are NOT counted as quantitative — only a sub-question
    that asks purely for a number contributes to the skip ratio."""
    return _evidence_type_of(sub_question) == "quantitative"


def should_run_style_extractor(sub_questions: Iterable[Any]) -> bool:
    """The qualitative/quantitative skip heuristic.

    Returns ``True`` (run the extractor) unless MORE THAN
    ``QUANTITATIVE_SKIP_THRESHOLD`` (50%) of the sub-questions are
    pure-quantitative, in which case it returns ``False`` (skip).

    An empty sub-question list returns ``True`` — absent evidence that
    an investigation is quantitative, default to running the extractor
    (the conservative choice; the flag still gates the whole thing OFF).

    This function does NOT consult the feature flag — it is a pure
    classifier so it can be tested in isolation. ``maybe_style_guide_layer``
    combines it with the flag."""
    items = list(sub_questions)
    if not items:
        return True
    quantitative = sum(1 for sq in items if _is_quantitative(sq))
    fraction = quantitative / len(items)
    return fraction <= QUANTITATIVE_SKIP_THRESHOLD


def maybe_style_guide_layer(
    *,
    style_guide: Any,
    sub_questions: Iterable[Any],
) -> LayerSource | None:
    """Return the ``style_guide`` ``LayerSource`` to inject into the
    synthesizer's context pack, or ``None`` to inject nothing.

    Returns ``None`` (inject nothing) when ANY of the following hold:

    - the feature flag is OFF (the inert-by-default case),
    - the skip heuristic says the investigation is pure-quantitative,
    - ``style_guide`` is ``None`` (the extractor was not run / its
      output was malformed and the bridge passed ``None``),
    - ``style_guide`` does not expose an ``as_layer_content()`` that
      returns a non-empty string (defensive: a malformed object never
      crashes assembly — it degrades to no injection).

    Returns a ``LayerSource`` (``kind="style_guide"``, priority equal to
    ``long_term_skill``) only when the flag is ON, the investigation is
    qualitative, and a usable guide is supplied.

    The priority is pulled from ``DEFAULT_KIND_PRIORITY["style_guide"]``
    (== the ``long_term_skill`` priority) so the layer truncates like
    background conditioning, never displacing evidence or the session
    task."""
    if not style_extractor_enabled():
        return None
    if style_guide is None:
        return None
    if not should_run_style_extractor(sub_questions):
        return None

    content = _render_guide_content(style_guide)
    if not content:
        return None

    return LayerSource(
        kind=STYLE_GUIDE_LAYER_KIND,  # type: ignore[arg-type]
        source=STYLE_GUIDE_LAYER_SOURCE,
        content=content,
        priority=DEFAULT_KIND_PRIORITY[STYLE_GUIDE_LAYER_KIND],
    )


def _render_guide_content(style_guide: Any) -> str | None:
    """Render the guide body, defending against a malformed object.

    Prefers ``style_guide.as_layer_content()`` (the ``StyleGuide``
    dataclass). Falls back to a bare string. Any exception or empty
    result yields ``None`` so the caller skips injection rather than
    propagating a failure into assembly."""
    if isinstance(style_guide, str):
        return style_guide.strip() or None
    render = getattr(style_guide, "as_layer_content", None)
    if callable(render):
        try:
            out = render()
        except Exception:  # pragma: no cover — defensive; malformed guide
            return None
        if isinstance(out, str) and out.strip():
            return out.strip()
    return None
