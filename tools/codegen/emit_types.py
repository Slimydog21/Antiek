#!/usr/bin/env python3
"""Generate TypeScript discriminated-union types from Pydantic v2 models.

Reads ``substrate/schemas/events.py`` and emits
``apps/reading/src/generated/types.ts`` — a single self-contained
TypeScript module containing:

- ``ANTIEK_PARAM_VERSION`` + ``EVENT_SCHEMA_VERSION`` constants.
- ``ActionType`` as a ``const`` object + derived string-literal type
  (every variant from the Python enum, value-identical).
- One ``interface`` per typed payload (``DispatchCallPayload``,
  ``DocumentLoadedPayload``, etc.), with literal ``action_type``
  discriminators so TS-side narrowing works.
- ``TypedPayload`` discriminated union over every payload.
- ``Event`` envelope referencing ``TypedPayload`` as ``payload``.
- ``TYPED_PAYLOAD_ACTION_TYPES`` + ``WRESTLING_ACTION_TYPES`` as
  ``ReadonlySet<ActionType>``.
- Supporting Literal types (``ConfidenceLevel``, ``ArtifactKind``,
  ``TierClassificationMethod``, ``TierAdjustmentMethod``,
  ``StalenessResolution``).
- Nested supporting interfaces (``ContextLayer``, ``Claim``).

Discipline (architecture_notes §11.1):

- The Pydantic models are the **single source of truth**. This file
  emits; it never imports the TS side.
- The generated output is **never hand-edited**. The header makes that
  clear. ``check_staleness.py`` enforces it in CI.

Type mapping:

| Python                                  | TypeScript                |
|-----------------------------------------|---------------------------|
| str                                     | string                    |
| int, float                              | number                    |
| bool                                    | boolean                   |
| datetime                                | string  (ISO 8601)        |
| Literal["a", "b"]                       | "a" \\| "b"                |
| Literal[ActionType.X]                   | "<X.value>"               |
| Optional[T]                             | T \\| null                 |
| list[T]                                 | T[]                       |
| dict[K, V]                              | Record<K, V>              |
| tuple[T1, T2, ...]                      | [T1, T2, ...]             |
| BaseModel subclass                      | <ClassName>               |

Unhandled types fail loudly with a clear "extend emit_types.py" message.
That's the right failure mode — silent ``any`` fallbacks would erode the
contract.
"""

from __future__ import annotations

import datetime as dt
import enum
import inspect
import sys
import types
import typing
from pathlib import Path
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

# Ensure the project root is on the path so this script works from any cwd.
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from substrate.constants import ANTIEK_PARAM_VERSION  # noqa: E402
from substrate.schemas import events as schema_module  # noqa: E402
from substrate.schemas.events import (  # noqa: E402
    EVENT_SCHEMA_VERSION,
    TYPED_PAYLOAD_ACTION_TYPES,
    WRESTLING_ACTION_TYPES,
    ActionType,
    Event,
)

# ---------------------------------------------------------------------------
# Output path + header
# ---------------------------------------------------------------------------


DEFAULT_OUTPUT = _REPO / "apps" / "reading" / "src" / "generated" / "types.ts"


GENERATED_HEADER = """\
// AUTO-GENERATED — DO NOT EDIT.
//
// Generated from substrate/schemas/events.py by tools/codegen/emit_types.py.
// Re-run after any schema change:   python tools/codegen/emit_types.py
// CI gate that fails on drift:      python tools/codegen/check_staleness.py
//
// The Pydantic models in substrate/schemas/events.py are the single source
// of truth. See docs/architecture_notes.md §11.1 (polyglot seam) for the
// discipline rule that keeps this file in sync.
"""


# ---------------------------------------------------------------------------
# Models to emit, in output order. Order matters — interfaces that
# reference others must come after their referents.
# ---------------------------------------------------------------------------


# Nested helper models (referenced by payloads). Emit first.
NESTED_MODELS: tuple[type[BaseModel], ...] = (
    schema_module.ContextLayer,
    schema_module.Claim,
    schema_module.ThesisOutcome,
    schema_module.FalsificationOutcome,
    schema_module.ExecutionRiskOutcome,
    schema_module.DecisionAlignment,
    schema_module.SubQuestion,
    schema_module.Keyword,
    schema_module.ParaphraseFlagRecord,
    schema_module.SupportingClaim,
    schema_module.EvidentiaryGap,
    schema_module.MetricValue,
    schema_module.Parameter,
    schema_module.ConstraintSpec,
    schema_module.KeywordMapping,
    schema_module.SeedPair,
    schema_module.GraphPath,
    schema_module.NaturalLanguageRelationship,
    schema_module.ThesisComponent,
    schema_module.FalsificationCondition,
    schema_module.ExecutionRisk,
    schema_module.ViolationJustification,
    schema_module.ConstraintCompliance,
    schema_module.ReasoningPathUsed,
    # Wedge 3 — sub-model for VerifierLookupPayload.results.
    schema_module.ExaLookupResult,
    # SPR-08 M4 — sub-model for ReadMetaReadingGeneratedPayload.citations.
    schema_module.MetaReadingCitation,
    schema_module.BookAnswerCitation,
    # Foundation v2 SPR-02 — sub-model for GroundednessScoredPayload.per_claim.
    schema_module.ClaimGroundednessVerdict,
)

# Payload models, in the same order as the TypedPayload union.
PAYLOAD_MODELS: tuple[type[BaseModel], ...] = (
    schema_module.DispatchCallPayload,
    # antiek-yegge-execute SPR-01 — worker registration (future registry, SPR-04).
    schema_module.WorkerIdentityPayload,
    schema_module.LinkMonsterDigestedPayload,  # Link Monster — one digest attempt
    schema_module.ContextPackAssembledPayload,
    schema_module.KnowledgeReusedPayload,  # AFF SPR-06 — flywheel reuse half
    schema_module.ReuseGatedPayload,  # AFF SPR-08 — trust gate on reuse
    schema_module.DocumentLoadedPayload,
    schema_module.DocumentRegionSelectedPayload,
    schema_module.DistillationRequestedPayload,
    schema_module.DistillationDeliveredPayload,
    schema_module.ClaimChallengeRaisedPayload,
    schema_module.ClaimGroundingCheckPassedPayload,
    schema_module.ClaimGroundingCheckFailedPayload,
    schema_module.NoteEmergedPayload,
    schema_module.NoteRefinedPayload,
    schema_module.NoteCompressedDocWrittenPayload,
    schema_module.QuestionIdentifiedPayload,
    schema_module.QuestionEscalatedToResearchPayload,
    schema_module.QuestionResolvedByDocPayload,
    schema_module.CrossDocQuestionAnsweredPayload,
    schema_module.UserAcceptDistillationPayload,
    schema_module.UserRejectDistillationPayload,
    schema_module.UserEditDistillationPayload,
    schema_module.ArtifactGeneratedPayload,
    schema_module.ArtifactInteractedPayload,
    schema_module.ArtifactCommentCreatedPayload,
    schema_module.AgentWorkTransitionedPayload,
    schema_module.TierAssignedPayload,
    schema_module.TierOverriddenPayload,
    schema_module.TierRewriteBulkPayload,
    schema_module.StalenessFlaggedPayload,
    schema_module.StalenessResolvePayload,
    schema_module.SynthesisArchivedPayload,
    schema_module.SubstrateManifestWrittenPayload,
    schema_module.SupersessionApplyPayload,
    schema_module.SupersessionDismissPayload,
    schema_module.SupersessionCoexistPayload,
    schema_module.GraphNodeInsertedPayload,
    schema_module.GraphEdgeInsertedPayload,
    schema_module.ConstraintViolationFoundPayload,
    schema_module.ConstraintRevisionTriggeredPayload,
    schema_module.ConstraintLoopResolvedPayload,
    schema_module.OutcomeRecordedPayload,
    schema_module.RubricScoredPayload,
    # Foundation v2 SPR-02 — groundedness eval (truth axis) + the failure
    # event that replaces the Phase-6 except-pass swallow.
    schema_module.GroundednessScoredPayload,
    schema_module.GroundednessFailedPayload,
    schema_module.PhaseEnterPayload,
    schema_module.PhaseExitPayload,
    schema_module.PhaseVerifyPayload,
    schema_module.DecomposeQuestionRequestedPayload,
    schema_module.DecomposeQuestionDeliveredPayload,
    schema_module.DecomposerParaphraseFlaggedPayload,
    schema_module.DecomposerRegeneratedPayload,
    schema_module.MasterMdWrittenPayload,
    schema_module.MasterMdSkippedPayload,
    schema_module.SkillPatchGateDecidedPayload,
    schema_module.SkillPatchGateReviewedPayload,
    schema_module.AutoPatchAppliedPayload,
    schema_module.AutoPatchSkippedPayload,
    schema_module.EvidenceRetrieveRequestedPayload,
    schema_module.EvidenceRetrieveDeliveredPayload,
    schema_module.ParameterExtractRequestedPayload,
    schema_module.ParameterExtractDeliveredPayload,
    schema_module.ConnectorRequestedPayload,
    schema_module.ConnectorDeliveredPayload,
    schema_module.SynthesizeRequestedPayload,
    schema_module.SynthesizeDeliveredPayload,
    schema_module.AuditFindingPayload,
    schema_module.InvestigationStartRequestedPayload,
    schema_module.InvestigationCompletedPayload,
    schema_module.InvestigationFailedPayload,
    schema_module.InvestigationSpawnedFromPayload,
    schema_module.InvestigationChaseHaltedPayload,
    schema_module.ClaimAssertedByOperatorPayload,
    schema_module.PageAttributionComputedPayload,
    schema_module.RLMBridgeDecidedPayload,
    schema_module.QualityGateEvaluatedPayload,
    schema_module.CrossGraphCitationRecordedPayload,
    schema_module.RevShareDecidedPayload,
    schema_module.PreferenceObservationRecordedPayload,
    schema_module.SkillRulePromotedPayload,
    # Sprint 18 — Exa/Browserbase substrate-only precursor.
    # docs/integration_exa_browserbase.md §18.3.
    schema_module.DiscoveryProposedPayload,
    schema_module.DiscoverySelectedPayload,
    schema_module.FetchFallbackEscalatedPayload,
    # Wedge 3 — verifier-tier corroboration primitive.
    schema_module.VerifierLookupPayload,
    # Sprint 30+ thread 1 — federation audit trail.
    schema_module.FederationPartnerRegisteredPayload,
    schema_module.FederationPartnerTrustedPayload,
    schema_module.FederationPartnerRevokedPayload,
    schema_module.FederationOutboundCitationEmittedPayload,
    schema_module.FederationInboundCitationAcceptedPayload,
    schema_module.FederationInboundCitationRefusedPayload,
    # Sprint 30+ thread 4 — visual role audit trail.
    schema_module.VisualFrameIdentifiedPayload,
    schema_module.VisualClaimsExtractedPayload,
    schema_module.VisualRoleFailedPayload,
    # PostHog Wedge 4 — Max-style ubiquitous AI sidecar with undo
    # affordance through the event log (§5.5).
    schema_module.AIActionAppliedPayload,
    schema_module.AIActionUndonePayload,
    # Sprint 19 — DP shuffler substrate plumbing (§13.3 + §16.2).
    schema_module.DPRoutedPayload,
    # Write workflow SPR-01 — OutlineBlock composition audit trail.
    schema_module.OutlineBlockPlacedPayload,
    schema_module.OutlineBlockMovedPayload,
    schema_module.OutlineBlockRemovedPayload,
    # Write workflow SPR-02 — edit capture.
    schema_module.EditCapturedPayload,
    # Write workflow SPR-09 — draft provenance persistence (X-ray).
    schema_module.SectionDraftGeneratedPayload,
    # Read workflow SPR-01 — servable-corpus legal-gate audit trail.
    schema_module.BookServabilityChangedPayload,
    schema_module.BookTakenDownPayload,
    # Personal-Reading Lane SPR-01 — deny-by-default ingest classification.
    schema_module.DocumentContentClassDefaultedPayload,
    # antiek-unified SPR-03 — the six flywheel seams + one provisional seam.
    schema_module.SeamResearchToReadPayload,
    schema_module.SeamReadToResearchPayload,
    schema_module.SeamReadToWritePayload,
    schema_module.SeamWriteToReadPayload,
    schema_module.SeamSpeakToWritePayload,
    schema_module.SeamSpeakToReadPayload,
    schema_module.SeamWriteToSpeakPayload,
    # Living Roadmap SPR-14 — shared voice-in capture provenance.
    schema_module.VoiceCapturedPayload,
    # Living Roadmap SPR-04 — highlight → float-menu user NOTE provenance.
    schema_module.MarginaliaNotedPayload,
    # Living Roadmap SPR-03 — block-canvas position persistence (DRW organism).
    schema_module.BlockPositionPayload,
    # Living Roadmap SPR-07 — source.read → SiteSee "read" tint.
    schema_module.SourceReadPayload,
    schema_module.ReadBookAnsweredPayload,
    schema_module.ReadBookAnswerJudgedPayload,
    # Living Roadmap SPR-08 — meta-reading deliverable → re-openable Read asset.
    schema_module.ReadMetaReadingGeneratedPayload,
    # Living Roadmap SPR-13 — file a personal-space doc INTO a research project.
    schema_module.DocumentFiledIntoInvestigationPayload,
    # Own Your Mind P0 §5 — served-impression audit (v35 schema bump).
    schema_module.SurfaceServedImpressionPayload,
)

# Re-exported Literal aliases. Name → list of allowed values.
# Emitted as ``export type <Name> = "a" | "b";`` so the TS side can use
# them in switch narrowing and exhaustiveness checks.
LITERAL_ALIASES: dict[str, tuple[str, ...]] = {
    "ConfidenceLevel": typing.get_args(schema_module.ConfidenceLevel),
    "ArtifactKind": typing.get_args(schema_module.ArtifactKind),
    "TierClassificationMethod": typing.get_args(schema_module.TierClassificationMethod),
    "TierAdjustmentMethod": typing.get_args(schema_module.TierAdjustmentMethod),
    "StalenessResolution": typing.get_args(schema_module.StalenessResolution),
    "ThesisOutcomeStatus": typing.get_args(schema_module.ThesisOutcomeStatus),
    "ExecutionRiskSeverity": typing.get_args(schema_module.ExecutionRiskSeverity),
    "DecisionRecommendation": typing.get_args(schema_module.DecisionRecommendation),
    "ActualDecision": typing.get_args(schema_module.ActualDecision),
    "ProceedOutcome": typing.get_args(schema_module.ProceedOutcome),
    "SubQuestionCategory": typing.get_args(schema_module.SubQuestionCategory),
    "EvidenceTypeRequired": typing.get_args(schema_module.EvidenceTypeRequired),
    "EvidenceType": typing.get_args(schema_module.EvidenceType),
    "EvidenceConfidence": typing.get_args(schema_module.EvidenceConfidence),
    "MetricValueType": typing.get_args(schema_module.MetricValueType),
    "EvidenceStatus": typing.get_args(schema_module.EvidenceStatus),
    "TraversalAlgorithm": typing.get_args(schema_module.TraversalAlgorithm),
    "ThesisRiskSeverity": typing.get_args(schema_module.ThesisRiskSeverity),
    "SynthesisRecommendation": typing.get_args(schema_module.SynthesisRecommendation),
    "AuditSeverity": typing.get_args(schema_module.AuditSeverity),
    # Sprint 18 — Exa/Browserbase substrate-only precursor.
    "DiscoveryProvider": typing.get_args(schema_module.DiscoveryProvider),
    "DiscoveryDecision": typing.get_args(schema_module.DiscoveryDecision),
    # Living Roadmap SPR-14 — shared provenance vocabulary (voice-in "user",
    # TTS-out "ai", machine "system"). The voice-out builder references "ai".
    "ProvenanceSourceKind": typing.get_args(schema_module.ProvenanceSourceKind),
}


# ---------------------------------------------------------------------------
# Python → TypeScript type mapping
# ---------------------------------------------------------------------------


# Resolved type-name set for nested models, populated as we emit each.
# Used by the field-type renderer to know what's emitted vs unknown.
_KNOWN_NESTED_NAMES: set[str] = set()


class UnsupportedType(TypeError):
    """Raised when ``_python_to_ts`` encounters a type it cannot translate.
    The error message names the field and Python type so the operator can
    extend ``emit_types.py``."""


def _is_optional(tp: Any) -> tuple[bool, Any]:
    """If ``tp`` is ``Optional[X]`` (i.e. ``Union[X, None]``), return
    ``(True, X)``. Otherwise ``(False, tp)``."""
    origin = get_origin(tp)
    if origin is Union or origin is types.UnionType:  # py3.10+ ``X | None``
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) < len(get_args(tp)):
            inner: Any = args[0] if len(args) == 1 else Union[tuple(args)]  # type: ignore[valid-type]  # noqa: UP007  (runtime Union construction, not an annotation)
            return True, inner
    return False, tp


def _literal_value_to_ts(value: Any) -> str:
    if isinstance(value, enum.Enum):
        value = value.value
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "null"
    raise UnsupportedType(f"unsupported Literal value: {value!r} ({type(value).__name__})")


def _as_array(elem_ts: str) -> str:
    """Render ``elem_ts[]``, parenthesizing a top-level union so a union
    element type binds correctly: ``"a" | "b"`` must become ``("a" | "b")[]``,
    not the mis-parsed ``"a" | ("b"[])``. (Event payloads never hit this; the
    contract models — e.g. ``tuple[Literal[...], ...]`` — do.)"""
    return f"({elem_ts})[]" if " | " in elem_ts else f"{elem_ts}[]"


def _python_to_ts(tp: Any, *, field_name: str, model_name: str) -> str:
    """Map a Python type annotation to a TS type expression."""
    is_opt, inner = _is_optional(tp)
    ts = _python_to_ts_inner(inner, field_name=field_name, model_name=model_name)
    return f"{ts} | null" if is_opt else ts


def _payload_model_names() -> set[str]:
    return {m.__name__ for m in PAYLOAD_MODELS}


def _python_to_ts_inner(tp: Any, *, field_name: str, model_name: str) -> str:
    if tp is str:
        return "string"
    if tp is int or tp is float:
        return "number"
    if tp is bool:
        return "boolean"
    if tp is dt.datetime:
        return "string"  # ISO 8601
    if tp is type(None):
        return "null"
    # ``Any`` → TS ``unknown`` (safer than ``any`` — forces the
    # consumer to narrow before use). Required for heterogeneous
    # JSON-shaped fields the schema cannot tighten further
    # (e.g. parameter_extractor's ``metric_value.value`` is one of
    # number/string/array, and constraint ``config`` is a small
    # kind-specific dict the substrate-side validator interprets).
    if tp is Any:
        return "unknown"

    # Bare Enum class (e.g. ``ActionType`` on Event.action_type) — emit the
    # enum's class name, which we also emit as a TS type alias in
    # _emit_action_type. Only ActionType is supported today; other enums
    # would need explicit handling.
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        if tp is ActionType:
            return "ActionType"
        raise UnsupportedType(
            f"{model_name}.{field_name}: bare enum {tp.__name__!r} has no "
            "registered TS emission. Add a case to _python_to_ts_inner."
        )

    if isinstance(tp, type) and issubclass(tp, BaseModel):
        name = tp.__name__
        if name not in _KNOWN_NESTED_NAMES and name not in _payload_model_names():
            raise UnsupportedType(
                f"{model_name}.{field_name}: nested model {name!r} not in the "
                "emit list. Add it to NESTED_MODELS in tools/codegen/emit_types.py."
            )
        return name

    # Bare ``dict`` (no type args) — opaque JSON snapshots like
    # AIActionAppliedPayload.prev_state/next_state. JSON object keys
    # are strings; value type is unknown by design.
    if tp is dict:
        return "Record<string, unknown>"

    origin = get_origin(tp)
    args = get_args(tp)

    if origin is typing.Literal:
        return " | ".join(_literal_value_to_ts(a) for a in args)

    if origin is list:
        (elem,) = args
        return _as_array(_python_to_ts(elem, field_name=field_name, model_name=model_name))

    if origin is tuple:
        # Variable-length tuple ``tuple[T, ...]`` not used by the event
        # payloads, but used by the contract models (substrate/contracts/).
        if len(args) == 2 and args[1] is Ellipsis:
            elem = _python_to_ts(args[0], field_name=field_name, model_name=model_name)
            return _as_array(elem)
        parts = ", ".join(
            _python_to_ts(a, field_name=field_name, model_name=model_name) for a in args
        )
        return f"[{parts}]"

    if origin is dict:
        if len(args) != 2:
            raise UnsupportedType(f"{model_name}.{field_name}: dict without key+value args: {tp!r}")
        k_ts = _python_to_ts(args[0], field_name=field_name, model_name=model_name)
        v_ts = _python_to_ts(args[1], field_name=field_name, model_name=model_name)
        # ``Record<K, V>`` requires K to be string/number/symbol-assignable.
        # For our schema (int keys in by_tier, str keys elsewhere), this works.
        return f"Record<{k_ts}, {v_ts}>"

    if origin is Union or origin is types.UnionType:
        # Special case: the discriminated union over every payload variant
        # (Event.payload) — emit the TypedPayload alias rather than the
        # inlined Union of 26 names. Detect by comparing the arg-name set
        # to the known PAYLOAD_MODELS set.
        non_none_args = [a for a in args if a is not type(None)]
        arg_names = {
            a.__name__ for a in non_none_args if isinstance(a, type) and issubclass(a, BaseModel)
        }
        if arg_names == _payload_model_names():
            return "TypedPayload"
        return " | ".join(
            _python_to_ts(a, field_name=field_name, model_name=model_name) for a in non_none_args
        )

    raise UnsupportedType(
        f"{model_name}.{field_name}: unsupported type {tp!r} (origin={origin!r}, "
        f"args={args!r}). Extend tools/codegen/emit_types.py to handle it."
    )


# ---------------------------------------------------------------------------
# Interface emission
# ---------------------------------------------------------------------------


def _emit_interface(model: type[BaseModel], lines: list[str]) -> None:
    name = model.__name__
    # inspect.cleandoc, not .strip(): Python 3.13+ auto-dedents docstrings
    # at compile time, so bare .strip() emits indented continuation lines
    # on ≤3.12 but dedented ones on 3.13+ — 1,700+ lines of whitespace-only
    # divergence that reds check_staleness whenever the generator and CI
    # run different interpreters. cleandoc normalizes both to the same text.
    docstring = inspect.cleandoc(model.__doc__ or "")
    lines.append("")
    if docstring:
        lines.append("/**")
        for d_line in docstring.splitlines():
            lines.append(f" * {d_line.rstrip()}")
        lines.append(" */")
    lines.append(f"export interface {name} {{")
    for field_name, field in model.model_fields.items():
        annotation = field.annotation
        is_opt, _ = _is_optional(annotation)
        ts_type = _python_to_ts(annotation, field_name=field_name, model_name=name)
        # In TS we use a trailing `?` to indicate optional. Combined
        # with the `| null` we emit for Optional, the field both accepts
        # null AND can be omitted entirely on the JSON wire.
        suffix = "?" if (is_opt or field.default is not None and not field.is_required()) else ""
        # Special case: discriminator literal — always required, no suffix.
        if field_name == "action_type":
            suffix = ""
        lines.append(f"  {field_name}{suffix}: {ts_type};")
    lines.append("}")


def _emit_action_type(lines: list[str]) -> None:
    lines.append("")
    lines.append("// Stable action vocabulary. Values are persisted to the trajectory")
    lines.append("// store and MUST match substrate.schemas.events.ActionType exactly.")
    lines.append("export const ActionType = {")
    for member in ActionType:
        # Build a TS-safe identifier: enum member name (already SCREAMING_SNAKE).
        lines.append(f'  {member.name}: "{member.value}",')
    lines.append("} as const;")
    lines.append("export type ActionType = typeof ActionType[keyof typeof ActionType];")


def _emit_literal_aliases(lines: list[str]) -> None:
    for alias_name, values in LITERAL_ALIASES.items():
        ts_values = " | ".join(_literal_value_to_ts(v) for v in values)
        lines.append("")
        lines.append(f"export type {alias_name} = {ts_values};")


def _emit_typed_payload_union(lines: list[str]) -> None:
    lines.append("")
    lines.append("/**")
    lines.append(" * Discriminated union over every typed payload. TS narrowing on")
    lines.append(" * ``payload.action_type`` selects the right variant.")
    lines.append(" */")
    parts = "\n  | ".join(m.__name__ for m in PAYLOAD_MODELS)
    lines.append(f"export type TypedPayload =\n  | {parts};")


def _emit_action_set(name: str, values: frozenset[str], lines: list[str]) -> None:
    """Emit a ``const X: ReadonlySet<ActionType> = new Set([...])``."""
    lines.append("")
    lines.append(f"export const {name}: ReadonlySet<ActionType> = new Set<ActionType>([")
    # One per line for diff legibility.
    for v in sorted(values):
        lines.append(f'  "{v}",')
    lines.append("]);")


# ---------------------------------------------------------------------------
# Top-level emit
# ---------------------------------------------------------------------------


def render() -> str:
    """Render the complete TS file as a string. Pure function — useful
    for the staleness check, which compares this output against the
    on-disk file without touching the filesystem."""
    lines: list[str] = []
    lines.append(GENERATED_HEADER)
    lines.append(f'export const ANTIEK_PARAM_VERSION = "{ANTIEK_PARAM_VERSION}";')
    lines.append(f"export const EVENT_SCHEMA_VERSION = {EVENT_SCHEMA_VERSION};")

    _emit_action_type(lines)
    _emit_literal_aliases(lines)

    # Nested helper models first.
    for model in NESTED_MODELS:
        _emit_interface(model, lines)
        _KNOWN_NESTED_NAMES.add(model.__name__)

    # Payload interfaces.
    for model in PAYLOAD_MODELS:
        _emit_interface(model, lines)

    # The discriminated union over payloads.
    _emit_typed_payload_union(lines)

    # The Event envelope.
    _emit_interface(Event, lines)

    # The ReadonlySet helpers.
    _emit_action_set("TYPED_PAYLOAD_ACTION_TYPES", TYPED_PAYLOAD_ACTION_TYPES, lines)
    _emit_action_set("WRESTLING_ACTION_TYPES", WRESTLING_ACTION_TYPES, lines)

    # Trailing newline so editors don't complain.
    return "\n".join(lines) + "\n"


def write(output_path: Path | None = None) -> Path:
    """Render and write to ``output_path`` (defaults to
    ``apps/reading/src/generated/types.ts``). Creates parent dirs."""
    out = output_path or DEFAULT_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8")
    return out


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Emit TypeScript types from Pydantic schemas")
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Print to stdout instead of writing.",
    )
    args = p.parse_args()
    if args.stdout:
        print(render(), end="")
        return 0
    written = write(args.output)
    print(f"wrote {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
