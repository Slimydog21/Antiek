"""Tests for the Sprint 11 ``style_extractor`` role + its context-pack
wiring.

The role (``roles/style_extractor/``) implements the designed-but-unbuilt
role from ``docs/strategy/voice-and-style-discipline.md`` §"Change 3":
read the top-K corpus chunks, produce a ~150-300 word JSON style guide,
and inject it into the synthesizer's context pack as a new
``kind="style_guide"`` layer — feature-flagged OFF by default and skipped
for pure-quantitative investigations.

Coverage:

A. Prompt construction (no live model — keys are operator-bound):
   1. ``render_user_template`` substitutes both placeholders.
   2. ``render_full_prompt`` = system + user, threads ``extra_user_prefix``.
   3. Empty chunks fall back to ``(no chunks)`` (no stranded ``{{...}}``).

B. Parser (against fixture JSON):
   4. Well-formed response → ``StyleGuide`` with correct shapes.
   5. ``as_layer_content`` renders deterministically (byte-stable).
   6. Garbage text → ``StyleExtractorValidationError``.
   7. Missing key rejected; extra key rejected.
   8. vocabulary count floor/ceiling enforced (8-15).
   9. forbidden_in_this_register count floor/ceiling enforced (2-4).
   10. empty string in a prose field rejected.

C. Skip heuristic (``should_run_style_extractor``):
   11. all-qualitative ⇒ run.
   12. >50% quantitative ⇒ skip.
   13. exactly 50% quantitative ⇒ run (boundary; "more than 50%" skips).
   14. empty list ⇒ run (conservative default).
   15. duck-typed inputs (object / dict / bare string) classify alike.

D. Feature flag (``style_extractor_enabled``):
   16. unset ⇒ OFF; "1"/"true"/"yes" ⇒ ON; other ⇒ OFF.

E. Injection helper (``maybe_style_guide_layer``):
   17. flag OFF ⇒ None (even with a good guide + qualitative).
   18. flag ON + qualitative + good guide ⇒ LayerSource(kind=style_guide).
   19. flag ON + quantitative ⇒ None (heuristic skip).
   20. flag ON + guide=None ⇒ None.
   21. flag ON + malformed guide object ⇒ None (graceful, no crash).

F. **Inert-by-default proof (BINDING):**
   22. With the flag OFF, an assembled context pack built through the
       real call path (heuristic → maybe_style_guide_layer → assemble)
       is BYTE-IDENTICAL to the pack assembled with no style wiring at
       all. The live synthesis path is unchanged.
   23. With the flag ON + qualitative, the same call path DOES add a
       ``style_guide`` layer (so the OFF case's inertness is meaningful,
       not vacuous).
   24. With the flag ON + quantitative, no ``style_guide`` layer appears.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from roles.style_extractor import (  # noqa: E402
    STYLE_EXTRACTOR_SYSTEM_PROMPT,
    StyleExtractorValidationError,
    StyleGuide,
    parse_style_extractor_response,
    render_full_prompt,
    render_user_template,
)
from substrate.context_pack import (  # noqa: E402
    LayerSource,
    assemble_context_pack,
    maybe_style_guide_layer,
    should_run_style_extractor,
    style_extractor_enabled,
)
from substrate.context_pack.style_guide import STYLE_EXTRACTOR_FLAG  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    """Isolate each test's event store (assembly emits a typed event)."""
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


@pytest.fixture(autouse=True)
def _flag_off_by_default(monkeypatch):
    """Belt-and-suspenders: ensure the flag is unset unless a test sets
    it, so the suite never depends on ambient env state."""
    monkeypatch.delenv(STYLE_EXTRACTOR_FLAG, raising=False)


class CharCounter:
    """1 token per character — exact budget arithmetic in tests."""

    def count(self, text: str) -> int:
        return len(text)


def _good_guide_json() -> str:
    return json.dumps({
        "vocabulary": [
            "direct-path interference suppression",
            "least-squares lattice filter",
            "block-lattice filter",
            "sidelobe reduction",
            "passive radar",
            "illuminator of opportunity",
            "clutter cancellation",
            "ambiguity function",
            "cross-ambiguity processing",
        ],
        "argumentation_pattern": (
            "Claims are anchored to specific measured numbers in dB, with "
            "hedging reserved for the comparison against prior filtering "
            "methods. Each performance assertion names the dataset it rests on."
        ),
        "sentence_rhythm": (
            "Medium-length sentences with one subordinate clause, "
            "paragraph-final declarative beats."
        ),
        "forbidden_in_this_register": [
            "first-person singular reflection",
            "marketing language",
            "vague qualitative superlatives",
        ],
        "voice_summary": (
            "Write like a radar engineer reporting measured results: name "
            "the metric, name the dataset, hedge only against prior work."
        ),
    })


def _qual_sq(et="qualitative"):
    """A duck-typed sub-question object exposing evidence_type_required."""
    class _SQ:
        evidence_type_required = et
    return _SQ()


# ===========================================================================
# A. Prompt construction
# ===========================================================================


def test_render_user_template_substitutes_both_placeholders():
    s = render_user_template(top_k=5, chunks_block="CHUNK BODY HERE")
    assert "{{top_k}}" not in s
    assert "{{chunks_block}}" not in s
    assert "top-5 chunks" in s
    assert "CHUNK BODY HERE" in s


def test_render_full_prompt_includes_system_and_threads_prefix():
    full = render_full_prompt(
        top_k=3, chunks_block="C", extra_user_prefix="REVISION NOTE",
    )
    assert STYLE_EXTRACTOR_SYSTEM_PROMPT in full
    assert "REVISION NOTE" in full
    assert full.index("REVISION NOTE") > full.index(STYLE_EXTRACTOR_SYSTEM_PROMPT)


def test_empty_chunks_block_falls_back_to_placeholder():
    s = render_user_template(top_k=0, chunks_block="")
    assert "(no chunks)" in s
    assert "{{" not in s  # no stranded template token


# ===========================================================================
# B. Parser
# ===========================================================================


def test_parser_happy_path():
    g = parse_style_extractor_response(_good_guide_json())
    assert isinstance(g, StyleGuide)
    assert len(g.vocabulary) == 9
    assert "passive radar" in g.vocabulary
    assert len(g.forbidden_in_this_register) == 3
    assert g.voice_summary.startswith("Write like a radar engineer")


def test_as_layer_content_is_deterministic_and_carries_voice_and_vocab():
    g = parse_style_extractor_response(_good_guide_json())
    c1 = g.as_layer_content()
    c2 = g.as_layer_content()
    assert c1 == c2  # byte-stable
    assert "Write like a radar engineer" in c1
    assert "passive radar" in c1
    assert "direct-path interference suppression" in c1


def test_parser_rejects_garbage():
    with pytest.raises(StyleExtractorValidationError):
        parse_style_extractor_response("this is not json at all")


def test_parser_rejects_missing_key():
    obj = json.loads(_good_guide_json())
    del obj["voice_summary"]
    with pytest.raises(StyleExtractorValidationError, match="missing required keys"):
        parse_style_extractor_response(json.dumps(obj))


def test_parser_rejects_extra_key():
    obj = json.loads(_good_guide_json())
    obj["editorial_opinion"] = "this corpus is great"
    with pytest.raises(StyleExtractorValidationError, match="unexpected keys"):
        parse_style_extractor_response(json.dumps(obj))


def test_parser_rejects_too_few_vocabulary_terms():
    obj = json.loads(_good_guide_json())
    obj["vocabulary"] = obj["vocabulary"][:7]  # 7 < floor of 8
    with pytest.raises(StyleExtractorValidationError, match="vocabulary"):
        parse_style_extractor_response(json.dumps(obj))


def test_parser_rejects_too_many_vocabulary_terms():
    obj = json.loads(_good_guide_json())
    obj["vocabulary"] = [f"term-{i}" for i in range(16)]  # 16 > ceiling 15
    with pytest.raises(StyleExtractorValidationError, match="vocabulary"):
        parse_style_extractor_response(json.dumps(obj))


def test_parser_rejects_forbidden_count_out_of_range():
    obj = json.loads(_good_guide_json())
    obj["forbidden_in_this_register"] = ["only one"]  # 1 < floor 2
    with pytest.raises(
        StyleExtractorValidationError, match="forbidden_in_this_register"
    ):
        parse_style_extractor_response(json.dumps(obj))


def test_parser_rejects_empty_prose_field():
    obj = json.loads(_good_guide_json())
    obj["sentence_rhythm"] = "   "
    with pytest.raises(StyleExtractorValidationError, match="sentence_rhythm"):
        parse_style_extractor_response(json.dumps(obj))


# ===========================================================================
# C. Skip heuristic
# ===========================================================================


def test_heuristic_all_qualitative_runs():
    sqs = [_qual_sq("qualitative") for _ in range(4)]
    assert should_run_style_extractor(sqs) is True


def test_heuristic_majority_quantitative_skips():
    sqs = [_qual_sq("quantitative"), _qual_sq("quantitative"), _qual_sq("qualitative")]
    # 2/3 quantitative > 50% ⇒ skip
    assert should_run_style_extractor(sqs) is False


def test_heuristic_exactly_half_quantitative_runs():
    sqs = [_qual_sq("quantitative"), _qual_sq("qualitative")]
    # 50% is NOT "more than 50%" ⇒ run
    assert should_run_style_extractor(sqs) is True


def test_heuristic_empty_list_runs():
    assert should_run_style_extractor([]) is True


def test_heuristic_mixed_is_not_quantitative():
    # "mixed" must not count toward the quantitative ratio.
    sqs = [_qual_sq("mixed"), _qual_sq("mixed"), _qual_sq("quantitative")]
    assert should_run_style_extractor(sqs) is True


def test_heuristic_accepts_duck_typed_inputs():
    obj_form = [_qual_sq("quantitative"), _qual_sq("quantitative"), _qual_sq("qualitative")]
    dict_form = [
        {"evidence_type_required": "quantitative"},
        {"evidence_type_required": "quantitative"},
        {"evidence_type_required": "qualitative"},
    ]
    str_form = ["quantitative", "quantitative", "qualitative"]
    assert (
        should_run_style_extractor(obj_form)
        == should_run_style_extractor(dict_form)
        == should_run_style_extractor(str_form)
        is False
    )


# ===========================================================================
# D. Feature flag
# ===========================================================================


def test_flag_off_when_unset(monkeypatch):
    monkeypatch.delenv(STYLE_EXTRACTOR_FLAG, raising=False)
    assert style_extractor_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "Yes"])
def test_flag_on_for_truthy_values(monkeypatch, val):
    monkeypatch.setenv(STYLE_EXTRACTOR_FLAG, val)
    assert style_extractor_enabled() is True


@pytest.mark.parametrize("val", ["", "0", "false", "no", "off", "maybe"])
def test_flag_off_for_other_values(monkeypatch, val):
    monkeypatch.setenv(STYLE_EXTRACTOR_FLAG, val)
    assert style_extractor_enabled() is False


# ===========================================================================
# E. Injection helper
# ===========================================================================


def test_maybe_layer_none_when_flag_off(monkeypatch):
    monkeypatch.delenv(STYLE_EXTRACTOR_FLAG, raising=False)
    g = parse_style_extractor_response(_good_guide_json())
    layer = maybe_style_guide_layer(
        style_guide=g, sub_questions=[_qual_sq("qualitative")],
    )
    assert layer is None


def test_maybe_layer_present_when_on_and_qualitative(monkeypatch):
    monkeypatch.setenv(STYLE_EXTRACTOR_FLAG, "1")
    g = parse_style_extractor_response(_good_guide_json())
    layer = maybe_style_guide_layer(
        style_guide=g, sub_questions=[_qual_sq("qualitative")],
    )
    assert isinstance(layer, LayerSource)
    assert layer.kind == "style_guide"
    assert layer.source == "style_extractor"
    # priority equals long_term_skill (40), per the design doc.
    assert layer.effective_priority == 40
    assert "passive radar" in layer.content


def test_maybe_layer_none_when_on_but_quantitative(monkeypatch):
    monkeypatch.setenv(STYLE_EXTRACTOR_FLAG, "1")
    g = parse_style_extractor_response(_good_guide_json())
    layer = maybe_style_guide_layer(
        style_guide=g,
        sub_questions=[_qual_sq("quantitative"), _qual_sq("quantitative")],
    )
    assert layer is None


def test_maybe_layer_none_when_guide_is_none(monkeypatch):
    monkeypatch.setenv(STYLE_EXTRACTOR_FLAG, "1")
    layer = maybe_style_guide_layer(
        style_guide=None, sub_questions=[_qual_sq("qualitative")],
    )
    assert layer is None


def test_maybe_layer_none_when_guide_malformed(monkeypatch):
    """A malformed guide object (no usable as_layer_content) degrades to
    no injection — assembly never sees a broken layer."""
    monkeypatch.setenv(STYLE_EXTRACTOR_FLAG, "1")

    class _Broken:
        def as_layer_content(self):
            raise RuntimeError("boom")

    layer = maybe_style_guide_layer(
        style_guide=_Broken(), sub_questions=[_qual_sq("qualitative")],
    )
    assert layer is None


# ===========================================================================
# F. Inert-by-default proof (BINDING)
# ===========================================================================


def _base_layers():
    return [
        LayerSource("param_version_stamp", "v=0.1.0", "VER=0.1.0"),
        LayerSource("phase_metadata", "phase=6", "investigation=inv-x phase=6 role=synthesizer"),
        LayerSource("long_term_skill", "skill@1.0", "Background on the domain."),
        LayerSource("graph_evidence", "3 nodes", "Node A connects to Node B."),
        LayerSource("session", "task", "Synthesize the thesis from the evidence."),
    ]


def _assemble(layers, investigation_id):
    return assemble_context_pack(
        role="synthesizer",
        investigation_id=investigation_id,
        layers=layers,
        target_tokens=100_000,
        counter=CharCounter(),
    )


def test_inert_when_flag_off_pack_is_byte_identical(monkeypatch):
    """BINDING: with the flag OFF, the pack assembled through the real
    style-wiring call path is byte-identical to a pack assembled with no
    style wiring at all. ``style_guide`` adds nothing when dark."""
    monkeypatch.delenv(STYLE_EXTRACTOR_FLAG, raising=False)

    # Baseline: today's path — no style wiring whatsoever.
    baseline = _assemble(_base_layers(), "inv-baseline")

    # The wired path with the flag off: the helper returns None, so the
    # caller appends nothing.
    g = parse_style_extractor_response(_good_guide_json())
    extra = maybe_style_guide_layer(
        style_guide=g, sub_questions=[_qual_sq("qualitative")],
    )
    assert extra is None
    wired_layers = _base_layers() + ([extra] if extra else [])
    wired = _assemble(wired_layers, "inv-wired-off")

    # Byte-identical rendered text + identical layer kinds.
    assert wired.text == baseline.text
    assert [l.kind for l in wired.layers] == [l.kind for l in baseline.layers]
    assert "style_guide" not in {l.kind for l in wired.layers}
    assert wired.actual_tokens == baseline.actual_tokens


def test_flag_on_qualitative_injects_style_guide_layer(monkeypatch):
    """Counterpart to the inert proof: the OFF inertness is meaningful
    because ON+qualitative DOES inject the layer."""
    monkeypatch.setenv(STYLE_EXTRACTOR_FLAG, "1")
    g = parse_style_extractor_response(_good_guide_json())
    extra = maybe_style_guide_layer(
        style_guide=g, sub_questions=[_qual_sq("qualitative")],
    )
    assert extra is not None
    pack = _assemble(_base_layers() + [extra], "inv-wired-on")
    kinds = [l.kind for l in pack.layers]
    assert "style_guide" in kinds
    # Rendered between phase_metadata and long_term_skill (canonical order).
    assert pack.text.index("phase_metadata") < pack.text.index("style_guide")
    assert pack.text.index("style_guide") < pack.text.index("long_term_skill")
    assert "passive radar" in pack.text


def test_flag_on_quantitative_skips_layer(monkeypatch):
    monkeypatch.setenv(STYLE_EXTRACTOR_FLAG, "1")
    g = parse_style_extractor_response(_good_guide_json())
    extra = maybe_style_guide_layer(
        style_guide=g,
        sub_questions=[_qual_sq("quantitative"), _qual_sq("quantitative"), _qual_sq("qualitative")],
    )
    assert extra is None
    pack = _assemble(_base_layers() + ([extra] if extra else []), "inv-wired-quant")
    assert "style_guide" not in {l.kind for l in pack.layers}
