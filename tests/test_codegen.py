"""Tests for tools/codegen/.

What this file proves:

1. ``check_staleness.py`` returns 0 when the committed TS file matches
   the rendered output. This is the CI invariant.
2. Every typed payload from ``substrate/schemas/events.py`` appears as
   an exported interface in the generated TS.
3. Every ActionType variant appears as both a const-object key AND an
   entry inside the TYPED_PAYLOAD_ACTION_TYPES set (where applicable).
4. The generated file declares the discriminated union over every
   payload and references it from the Event envelope.
5. Wrestling-vs-non-wrestling sets match Python source.
6. Header asserts the AUTO-GENERATED warning and the regen command.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
sys.path.insert(0, str(_REPO))

from substrate.schemas import (  # noqa: E402
    ActionType,
    TYPED_PAYLOAD_ACTION_TYPES,
    WRESTLING_ACTION_TYPES,
)
from substrate.schemas import events as schema_module  # noqa: E402
from tools.codegen.emit_types import (  # noqa: E402
    DEFAULT_OUTPUT,
    PAYLOAD_MODELS,
    render,
)


# ---------------------------------------------------------------------------
# 1. CI gate — staleness
# ---------------------------------------------------------------------------


def test_committed_ts_matches_current_schema():
    """The CI invariant: tools/codegen/check_staleness.py returns 0."""
    result = subprocess.run(
        [sys.executable, str(_REPO / "tools" / "codegen" / "check_staleness.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"check_staleness.py failed (rc={result.returncode}).\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}\n"
        f"Run: python tools/codegen/emit_types.py to regenerate."
    )


def test_render_is_deterministic():
    """Two calls in a row must produce byte-identical output. If they
    don't, codegen has nondeterminism (set iteration order, dict
    iteration order, etc.) that the CI gate cannot catch."""
    a = render()
    b = render()
    assert a == b


# ---------------------------------------------------------------------------
# 2. Every payload appears as a TS interface
# ---------------------------------------------------------------------------


def test_every_payload_has_an_emitted_interface():
    ts = render()
    for model in PAYLOAD_MODELS:
        decl = f"export interface {model.__name__} "
        assert decl in ts, f"missing interface declaration for {model.__name__}"


def test_every_payload_has_literal_action_type_discriminator():
    """Every payload's ``action_type`` field MUST be emitted as a string
    Literal matching its action_type value — that's what makes TS-side
    narrowing on the discriminated union work."""
    ts = render()
    for model in PAYLOAD_MODELS:
        # The Pydantic Literal[ActionType.X] should have emitted as
        # action_type: "x.y.z";
        at = model.model_fields["action_type"]
        # The Literal arg is the enum member; pull its string value.
        import typing as _t
        arg = _t.get_args(at.annotation)[0]
        value = arg.value if hasattr(arg, "value") else arg
        expected = f'  action_type: "{value}";'
        assert expected in ts, (
            f"{model.__name__}: missing discriminator line {expected!r}"
        )


# ---------------------------------------------------------------------------
# 3. ActionType const + type
# ---------------------------------------------------------------------------


def test_every_actiontype_variant_appears_in_const_object():
    ts = render()
    for member in ActionType:
        line = f'  {member.name}: "{member.value}",'
        assert line in ts, f"ActionType.{member.name} missing from TS const"


def test_action_type_emits_as_const_object_plus_typeof_alias():
    ts = render()
    assert "export const ActionType = {" in ts
    assert "} as const;" in ts
    assert "export type ActionType = typeof ActionType[keyof typeof ActionType];" in ts


# ---------------------------------------------------------------------------
# 4. Discriminated union + Event envelope
# ---------------------------------------------------------------------------


def test_typed_payload_union_lists_every_variant():
    ts = render()
    # The union declaration spans multiple lines after `export type
    # TypedPayload =`. Pull a slice between markers.
    start = ts.index("export type TypedPayload =")
    end = ts.index(";", start)
    union_block = ts[start:end]
    for model in PAYLOAD_MODELS:
        assert model.__name__ in union_block, (
            f"{model.__name__} missing from TypedPayload union"
        )


def test_event_envelope_references_typed_payload():
    ts = render()
    assert "export interface Event {" in ts
    # The Event.payload field must reference the alias, not an inlined
    # 26-variant union (that would mean the codegen's special-case
    # detection broke).
    assert "payload: TypedPayload;" in ts


def test_event_envelope_lists_envelope_only_fields():
    ts = render()
    # Sanity: keys that live on the envelope (not in a payload) must be
    # present in the Event interface.
    for k in (
        "event_id", "investigation_id", "synthesis_id", "phase",
        "role", "action_type", "payload", "parent_event_id",
        "policy_id", "param_version", "schema_version",
        "emitted_at", "document_id",
    ):
        assert k in ts, f"Event envelope field {k!r} missing from TS"


# ---------------------------------------------------------------------------
# 5. ReadonlySet helpers
# ---------------------------------------------------------------------------


def test_typed_payload_action_types_set_matches_python():
    ts = render()
    # Pull the set body between brackets.
    marker = "export const TYPED_PAYLOAD_ACTION_TYPES"
    start = ts.index(marker)
    end = ts.index("]);", start)
    block = ts[start:end]
    for v in TYPED_PAYLOAD_ACTION_TYPES:
        assert f'"{v}"' in block, f"action_type {v!r} missing from typed set"


def test_wrestling_action_types_set_matches_python():
    ts = render()
    marker = "export const WRESTLING_ACTION_TYPES"
    start = ts.index(marker)
    end = ts.index("]);", start)
    block = ts[start:end]
    for v in WRESTLING_ACTION_TYPES:
        assert f'"{v}"' in block, f"wrestling action_type {v!r} missing"


# ---------------------------------------------------------------------------
# 6. Header
# ---------------------------------------------------------------------------


def test_header_marks_file_as_auto_generated():
    ts = render()
    first = ts.splitlines()[0]
    assert "AUTO-GENERATED" in first
    assert "DO NOT EDIT" in first
    # And the regen command must be visible.
    assert "python tools/codegen/emit_types.py" in ts


def test_param_version_and_schema_version_are_emitted_as_constants():
    ts = render()
    assert 'export const ANTIEK_PARAM_VERSION = "' in ts
    assert "export const EVENT_SCHEMA_VERSION = " in ts


# ---------------------------------------------------------------------------
# 7. Literal type aliases
# ---------------------------------------------------------------------------


def test_literal_aliases_emitted():
    ts = render()
    for alias in (
        "ConfidenceLevel", "ArtifactKind",
        "TierClassificationMethod", "TierAdjustmentMethod",
        "StalenessResolution",
    ):
        assert f"export type {alias} =" in ts, f"missing Literal alias {alias!r}"
