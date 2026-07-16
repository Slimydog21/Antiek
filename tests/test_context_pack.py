"""Tests for substrate/context_pack/.

What this file proves:

1. Under-budget assembly preserves every layer with no truncation.
2. Over-budget ``smart`` truncation keeps mandatory layers in full and
   drops lowest-priority optional layers first.
3. Over-budget ``head`` and ``tail`` strategies cut from the right side
   of the canonical sequence.
4. CONTEXT_PACK_ASSEMBLED events land with correct payload
   (target/actual tokens, layers list, budget_overrun, strategy applied).
5. ``synthesizer`` role uses SYNTHESIS_CONTEXT_BUDGET_TOKENS by default;
   every other role uses DEFAULT_CONTEXT_BUDGET_TOKENS.
6. Explicit ``target_tokens`` overrides the role-based default.
7. Layer rendering uses the canonical render order regardless of input
   layer order.
8. Truncated layers carry the truncation marker so downstream observers
   can spot abbreviation.
9. **Import-cycle invariant**: ``substrate.dispatch`` and
   ``substrate.context_pack`` never import each other. The seam is the
   caller's role-call site, by design (architecture_notes §11.1).

Tests inject a 1-token-per-char ``TokenCounter`` so budget arithmetic is
exact. Production uses the chars/4 heuristic in ``DefaultTokenCounter``.
"""

from __future__ import annotations

import ast
import os
import pathlib
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from substrate.constants import (  # noqa: E402
    DEFAULT_CONTEXT_BUDGET_TOKENS,
    SYNTHESIS_CONTEXT_BUDGET_TOKENS,
)
from substrate.context_pack import (  # noqa: E402
    TRUNCATION_MARKER,
    DefaultTokenCounter,
    LayerSource,
    assemble_context_pack,
    default_budget_for,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    ContextPackAssembledPayload,
    Event,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class CharCounter:
    """1 token per character. Makes budget arithmetic exact in tests."""

    def count(self, text: str) -> int:
        return len(text)


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    """Isolate each test's event store."""
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


def _layer(kind, source="src", content="x", priority=None):
    return LayerSource(kind=kind, source=source, content=content, priority=priority)


def _last_event_for(investigation_id: str) -> Event:
    rows = trajectory(investigation_id)
    assert rows, f"no events found for {investigation_id!r}"
    return Event.model_validate(rows[-1])


# ---------------------------------------------------------------------------
# 1. Under-budget assembly
# ---------------------------------------------------------------------------


def test_under_budget_assembly_preserves_every_layer():
    layers = [
        _layer("param_version_stamp", "v=0.1.0", "VER=0.1.0"),
        _layer("phase_metadata", "phase=4", "investigation=inv-1 phase=4 role=connector"),
        _layer("long_term_skill", "quantum@1.4", "Background on quantum-X."),
        _layer("graph_evidence", "3 nodes", "Node A connects to Node B."),
        _layer("session", "current_q", "What is the next sub-question?"),
    ]
    pack = assemble_context_pack(
        role="connector",
        investigation_id="inv-under",
        layers=layers,
        target_tokens=10_000,
        counter=CharCounter(),
    )

    assert pack.budget_overrun is False
    assert pack.truncation_strategy_applied is None
    assert len(pack.layers) == 5
    assert pack.actual_tokens < pack.target_tokens
    # Marker should not appear when no truncation happens.
    assert TRUNCATION_MARKER not in pack.text


def test_layers_render_in_canonical_order_regardless_of_input_order():
    """Order layers backwards on input; output must be canonical:
    param_version_stamp → phase_metadata → long_term_skill → graph_evidence → session."""
    layers = [
        _layer("session", "session", "S"),
        _layer("graph_evidence", "graph", "G"),
        _layer("long_term_skill", "skill", "K"),
        _layer("phase_metadata", "phase", "P"),
        _layer("param_version_stamp", "ver", "V"),
    ]
    pack = assemble_context_pack(
        role="connector", investigation_id="inv-order",
        layers=layers, target_tokens=10_000, counter=CharCounter(),
    )
    kinds = [a.kind for a in pack.layers]
    assert kinds == [
        "param_version_stamp",
        "phase_metadata",
        "long_term_skill",
        "graph_evidence",
        "session",
    ]
    # And the rendered text shows the same order.
    assert pack.text.index("param_version_stamp") < pack.text.index("phase_metadata")
    assert pack.text.index("phase_metadata") < pack.text.index("long_term_skill")
    assert pack.text.index("long_term_skill") < pack.text.index("graph_evidence")
    assert pack.text.index("graph_evidence") < pack.text.index("session")


def test_working_memory_renders_before_and_yields_budget_to_current_session():
    layers = [
        _layer("param_version_stamp", "v", "V" * 20),
        _layer("phase_metadata", "p", "P" * 20),
        _layer("graph_evidence", "g", "G" * 200),
        _layer("working_memory", "memory", "M" * 200),
        _layer("session", "current", "S" * 200),
    ]
    full = assemble_context_pack(
        role="connector", investigation_id="inv-working-order",
        layers=reversed(layers), target_tokens=10_000, counter=CharCounter(),
    )
    assert full.text.index("graph_evidence") < full.text.index("working_memory")
    assert full.text.index("working_memory") < full.text.index("session")

    tight = assemble_context_pack(
        role="connector", investigation_id="inv-working-priority",
        layers=layers, target_tokens=400, counter=CharCounter(),
    )
    kinds = [layer.kind for layer in tight.layers]
    assert "session" in kinds
    assert "working_memory" in kinds
    assert "graph_evidence" not in kinds


# ---------------------------------------------------------------------------
# 2. Smart truncation
# ---------------------------------------------------------------------------


def test_smart_truncation_keeps_mandatory_drops_lowest_priority():
    """With a tight budget, mandatory layers (param_version_stamp,
    phase_metadata) survive in full. The lowest-priority optional layer
    (long_term_skill, priority 40) drops before higher-priority optional
    ones (session 80, graph_evidence 60)."""
    layers = [
        # Mandatory (always kept):
        _layer("param_version_stamp", "v", "V" * 30),
        _layer("phase_metadata", "p", "P" * 30),
        # Optional in priority order: session (80) > graph_evidence (60) > long_term_skill (40)
        _layer("session", "s", "S" * 200),
        _layer("graph_evidence", "g", "G" * 200),
        _layer("long_term_skill", "k", "K" * 200),
    ]
    # Set the budget so that mandatory + session fits but
    # not graph_evidence and not long_term_skill.
    pack = assemble_context_pack(
        role="connector", investigation_id="inv-smart",
        layers=layers, target_tokens=400,
        counter=CharCounter(),
    )

    kinds = [a.kind for a in pack.layers]
    assert "param_version_stamp" in kinds
    assert "phase_metadata" in kinds
    assert "session" in kinds
    # long_term_skill (lowest optional priority) must be dropped.
    assert "long_term_skill" not in kinds
    assert pack.budget_overrun is True
    assert pack.truncation_strategy_applied == "smart"


def test_smart_truncation_truncates_boundary_layer_with_marker():
    """The layer that hits the budget edge gets truncated rather than
    dropped, and the marker appears in its rendered text."""
    layers = [
        _layer("param_version_stamp", "v", "V" * 20),
        _layer("phase_metadata", "p", "P" * 20),
        _layer("session", "s", "S" * 400),
    ]
    pack = assemble_context_pack(
        role="connector", investigation_id="inv-edge",
        layers=layers, target_tokens=300,
        counter=CharCounter(),
    )
    # All three kinds survive (session is truncated, not dropped, because
    # it's the next highest-priority and has fits-after-truncation room).
    kinds = [a.kind for a in pack.layers]
    assert kinds == ["param_version_stamp", "phase_metadata", "session"]
    # The session layer was truncated → marker present.
    session_layer = [a for a in pack.layers if a.kind == "session"][0]
    assert TRUNCATION_MARKER in session_layer.rendered
    assert pack.actual_tokens <= pack.target_tokens


def test_smart_truncation_uses_explicit_priority_override():
    """A LayerSource with explicit priority overrides the kind default.
    Useful when one specific graph-evidence layer is unusually load-bearing
    and should outrank the session for this call.

    Tight budget: after mandatory (~90 tokens), only ~110 tokens left.
    graph_evidence (promoted, ~220 tokens) gets truncated to fit, which
    stops the inclusion loop — session (demoted) drops entirely."""
    layers = [
        _layer("param_version_stamp", "v", "V" * 20),
        _layer("phase_metadata", "p", "P" * 20),
        _layer("session", "s", "S" * 200, priority=30),  # demoted below default
        _layer("graph_evidence", "g", "G" * 200, priority=85),  # promoted above session
    ]
    pack = assemble_context_pack(
        role="connector", investigation_id="inv-prio",
        layers=layers, target_tokens=200,
        counter=CharCounter(),
    )
    kinds = [a.kind for a in pack.layers]
    assert "graph_evidence" in kinds  # promoted, truncated to fit
    assert "session" not in kinds      # demoted below the cut, dropped


# ---------------------------------------------------------------------------
# 3. Head and tail truncation
# ---------------------------------------------------------------------------


def test_head_truncation_keeps_beginning_drops_session():
    """``head`` strategy preserves the head of the canonical order
    (param_version_stamp, phase_metadata, ...) and drops the tail (session
    first). Demonstrates why ``smart`` is the right default."""
    layers = [
        _layer("param_version_stamp", "v", "V" * 30),
        _layer("phase_metadata", "p", "P" * 30),
        _layer("long_term_skill", "k", "K" * 200),
        _layer("graph_evidence", "g", "G" * 200),
        _layer("session", "s", "S" * 200),
    ]
    pack = assemble_context_pack(
        role="connector", investigation_id="inv-head",
        layers=layers, target_tokens=400, truncation="head",
        counter=CharCounter(),
    )
    kinds = [a.kind for a in pack.layers]
    assert "param_version_stamp" in kinds  # head preserved
    assert "phase_metadata" in kinds
    assert "session" not in kinds  # tail dropped
    assert pack.truncation_strategy_applied == "head"


def test_tail_truncation_keeps_end_drops_skill():
    """``tail`` strategy preserves the canonical tail (session) and drops
    from the head."""
    layers = [
        _layer("param_version_stamp", "v", "V" * 30),
        _layer("phase_metadata", "p", "P" * 30),
        _layer("long_term_skill", "k", "K" * 200),
        _layer("graph_evidence", "g", "G" * 200),
        _layer("session", "s", "S" * 30),
    ]
    pack = assemble_context_pack(
        role="connector", investigation_id="inv-tail",
        layers=layers, target_tokens=200, truncation="tail",
        counter=CharCounter(),
    )
    kinds = [a.kind for a in pack.layers]
    assert "session" in kinds  # tail preserved
    assert "long_term_skill" not in kinds  # dropped from head
    assert pack.truncation_strategy_applied == "tail"


# ---------------------------------------------------------------------------
# 4. Event emission
# ---------------------------------------------------------------------------


def test_context_pack_assembled_event_lands_with_correct_payload():
    layers = [
        _layer("param_version_stamp", "v=0.1.0", "VER=0.1.0"),
        _layer("session", "current", "Decompose this question."),
    ]
    pack = assemble_context_pack(
        role="decomposer", investigation_id="inv-evt",
        layers=layers, target_tokens=10_000,
        counter=CharCounter(),
    )

    event = _last_event_for("inv-evt")
    assert event.action_type == ActionType.CONTEXT_PACK_ASSEMBLED.value
    assert isinstance(event.payload, ContextPackAssembledPayload)
    p = event.payload
    assert p.target_role == "decomposer"
    assert p.target_tokens == 10_000
    assert p.actual_tokens == pack.actual_tokens
    assert p.budget_overrun is False
    assert p.truncation_strategy_applied is None
    assert {layer.kind for layer in p.layers} == {"param_version_stamp", "session"}
    # pack.event_id matches the event written.
    assert event.event_id == pack.event_id


def test_event_records_strategy_when_truncated():
    layers = [
        _layer("param_version_stamp", "v", "V" * 20),
        _layer("session", "s", "S" * 1000),
        _layer("long_term_skill", "k", "K" * 1000),
    ]
    pack = assemble_context_pack(
        role="connector", investigation_id="inv-event-trunc",
        layers=layers, target_tokens=300,
        counter=CharCounter(),
    )
    event = _last_event_for("inv-event-trunc")
    assert event.payload.budget_overrun is True
    assert event.payload.truncation_strategy_applied == "smart"
    # The event's layers list reports POST-truncation token counts.
    total_from_event = sum(layer.tokens for layer in event.payload.layers)
    assert total_from_event == pack.actual_tokens


# ---------------------------------------------------------------------------
# 5. Budget selection by role
# ---------------------------------------------------------------------------


def test_synthesizer_role_uses_synthesis_budget():
    assert default_budget_for("synthesizer") == SYNTHESIS_CONTEXT_BUDGET_TOKENS


def test_non_synthesizer_roles_use_default_budget():
    for role in ("decomposer", "evidence_retriever", "connector", "note_taker", "grounder"):
        assert default_budget_for(role) == DEFAULT_CONTEXT_BUDGET_TOKENS


def test_explicit_target_tokens_overrides_role_default():
    layers = [_layer("session", "s", "S" * 50)]
    pack = assemble_context_pack(
        role="synthesizer", investigation_id="inv-override",
        layers=layers, target_tokens=5_000,
        counter=CharCounter(),
    )
    assert pack.target_tokens == 5_000  # not SYNTHESIS_CONTEXT_BUDGET_TOKENS


# ---------------------------------------------------------------------------
# 6. DefaultTokenCounter sanity
# ---------------------------------------------------------------------------


def test_default_counter_is_roughly_chars_over_4():
    c = DefaultTokenCounter()
    assert c.count("") == 0
    assert c.count("a") == 1
    assert c.count("a" * 4) == 1
    assert c.count("a" * 8) == 2
    assert c.count("a" * 1000) == 250


# ---------------------------------------------------------------------------
# 7. THE IMPORT-CYCLE INVARIANT
# ---------------------------------------------------------------------------


def _imports_in_module(module_dir: pathlib.Path) -> list[tuple[pathlib.Path, str]]:
    """Walk every .py under module_dir; return (file, imported_module) pairs
    for every import statement."""
    pairs: list[tuple[pathlib.Path, str]] = []
    for f in module_dir.rglob("*.py"):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    pairs.append((f, alias.name))
            elif isinstance(node, ast.ImportFrom):
                # Handle relative imports — node.module may be None for
                # "from . import X"; node.level is the dot count.
                module = node.module or ""
                if node.level > 0:
                    # Convert relative import to its substrate.* form.
                    parts = f.relative_to(module_dir.parent.parent).with_suffix("").parts
                    # parts looks like ('substrate', 'context_pack', 'assembler')
                    base = parts[:-1]  # drop the file name
                    up = node.level
                    # Going UP `up` levels from the current package.
                    ancestor = base[: len(base) - up + 1] if up <= len(base) else ()
                    module = ".".join((*ancestor, module)) if module else ".".join(ancestor)
                pairs.append((f, module))
    return pairs


def test_dispatch_does_not_import_context_pack():
    """The polyglot-seam discipline plus the architectural rule in §2.5
    requires dispatch and context_pack to be independent. This test fails
    loudly if a future change introduces a back-channel."""
    root = pathlib.Path(__file__).parent.parent
    dispatch_dir = root / "substrate" / "dispatch"
    pairs = _imports_in_module(dispatch_dir)
    offenders = [(p, m) for p, m in pairs if "context_pack" in m]
    assert not offenders, (
        f"substrate.dispatch must not import substrate.context_pack. "
        f"Offenders: {offenders}"
    )


def test_context_pack_does_not_import_dispatch():
    root = pathlib.Path(__file__).parent.parent
    cp_dir = root / "substrate" / "context_pack"
    pairs = _imports_in_module(cp_dir)
    offenders = [(p, m) for p, m in pairs if "dispatch" in m]
    assert not offenders, (
        f"substrate.context_pack must not import substrate.dispatch. "
        f"Offenders: {offenders}"
    )


# ---------------------------------------------------------------------------
# 8. Sanity / robustness
# ---------------------------------------------------------------------------


def test_empty_layer_list_produces_empty_pack_with_event():
    """Edge case: a role calls assemble with no layers. The pack should be
    empty but still emit a CONTEXT_PACK_ASSEMBLED event so the trajectory
    records the assembly attempt."""
    pack = assemble_context_pack(
        role="decomposer", investigation_id="inv-empty",
        layers=[], target_tokens=1000, counter=CharCounter(),
    )
    assert pack.text == ""
    assert pack.layers == ()
    assert pack.actual_tokens == 0
    assert pack.budget_overrun is False
    event = _last_event_for("inv-empty")
    assert isinstance(event.payload, ContextPackAssembledPayload)
    assert event.payload.layers == []


def test_kept_layer_token_counts_match_rendered_text():
    """Sanity: the tokens recorded for each AssembledLayer equal the
    tokens counted from its rendered text. If these drift, the budget
    accounting in the event becomes a lie."""
    layers = [
        _layer("param_version_stamp", "v", "V" * 20),
        _layer("session", "s", "S" * 50),
    ]
    counter = CharCounter()
    pack = assemble_context_pack(
        role="connector", investigation_id="inv-sanity",
        layers=layers, target_tokens=10_000, counter=counter,
    )
    for a in pack.layers:
        assert a.tokens == counter.count(a.rendered)
    assert pack.actual_tokens == sum(a.tokens for a in pack.layers)
