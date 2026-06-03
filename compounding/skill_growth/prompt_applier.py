"""Apply GEPA-approved prompt variants to versioned role-prompt files.

Per master-spec §13.6: the canonical Python prompt-composer for each
role (e.g. ``roles/synthesizer/prompt.py``) is stable; the variable
piece is the SYSTEM PROMPT TEXT, which the GEPA → Phase 8 bridge can
swap when a variant clears the gate.

This module is the writer. It:

  1. Validates the variant against the bridge outcome (must be
     ``PatchDecision.ACCEPT`` — refuses SHADOW or REJECT).
  2. Writes the variant text to a versioned file under
     ``compounding/applied_prompts/<role>/<variant_id>.md``.
  3. Updates the per-role pointer
     ``compounding/applied_prompts/<role>/current.json`` so role
     modules that opt into "load from applied" resolve to the new text
     on next read.
  4. Returns an ``AppliedPromptRecord`` describing what landed.

The pointer file is the substrate's single source of truth for
"which variant is currently live for this role" — production role
modules that want to consume applied prompts read `current.json` to
get the path; role modules that prefer their hard-coded prompts
ignore the directory entirely. Opt-in by design.

Files NEVER overwrite by ``variant_id`` (the id is content-derived
upstream so re-runs are idempotent); the pointer file overwrites by
necessity.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .gate import PatchDecision
from .gepa_bridge import BridgeOutcome

# Resolution path for applied prompts. The repo root is the parent of
# this module's package (``compounding/skill_growth/``).
DEFAULT_APPLIED_PROMPTS_DIR: Path = (
    Path(__file__).resolve().parent.parent / "applied_prompts"
)


class PromptApplyError(Exception):
    """Raised on attempts to apply a non-ACCEPTED variant or on
    role/variant-id sanitization failures."""


_SAFE_ROLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SAFE_VARIANT_ID_RE = re.compile(r"^gepa-[a-z0-9_]+-[a-f0-9]+$")


@dataclass(frozen=True)
class AppliedPromptRecord:
    """Outcome of one apply call."""

    role: str
    variant_id: str
    variant_path: str
    pointer_path: str
    applied_at: str
    baseline_score: float
    candidate_score: float
    delta: float


def _validate_role(role: str) -> None:
    if not _SAFE_ROLE_RE.match(role):
        raise PromptApplyError(
            f"role {role!r} must match [a-z][a-z0-9_]* — used as path component"
        )


def _validate_variant_id(variant_id: str) -> None:
    if not _SAFE_VARIANT_ID_RE.match(variant_id):
        raise PromptApplyError(
            f"variant_id {variant_id!r} doesn't match the GEPA naming "
            f"convention 'gepa-<role>-<hex>' — used as path component"
        )


def apply_prompt_variant(
    *,
    role: str,
    bridge_outcome: BridgeOutcome,
    base_dir: Path | None = None,
) -> AppliedPromptRecord:
    """Land the accepted variant on disk + update the per-role pointer.

    Args:
      role: e.g. ``"synthesizer"`` or ``"parameter_extractor"``. Used
        as a path component; sanitized against ``[a-z][a-z0-9_]*``.
      bridge_outcome: from ``GepaToPhase8Bridge.bridge()``. Must carry
        a ``PatchDecision.ACCEPT`` verdict — SHADOW (calibration data
        only) and REJECT (variant failed the gate) raise
        ``PromptApplyError``.
      base_dir: override the default ``compounding/applied_prompts``
        location (used by tests for isolation).

    Returns an ``AppliedPromptRecord`` describing what was written.
    """
    _validate_role(role)
    _validate_variant_id(bridge_outcome.variant_id)

    decision = bridge_outcome.patch_outcome.decision
    if decision != PatchDecision.ACCEPT:
        raise PromptApplyError(
            f"refuse to apply {bridge_outcome.variant_id!r} for "
            f"role {role!r}: decision={decision.value!r} (only ACCEPT "
            "lands on disk; SHADOW/REJECT are observation-only)"
        )

    root = (base_dir or DEFAULT_APPLIED_PROMPTS_DIR)
    role_dir = root / role
    role_dir.mkdir(parents=True, exist_ok=True)

    variant_path = role_dir / f"{bridge_outcome.variant_id}.md"
    pointer_path = role_dir / "current.json"

    # Idempotent variant write: if the file already exists with the
    # same content, leave it alone. Content-addressing means a
    # re-application of the same prompt text → same variant_id, so
    # repeats are deterministic.
    if variant_path.exists():
        existing = variant_path.read_text(encoding="utf-8")
        if existing != bridge_outcome.variant_prompt:
            raise PromptApplyError(
                f"variant_path {variant_path} exists with different "
                "content — variant_id collision is impossible under "
                "content-addressing; check upstream"
            )
    else:
        variant_path.write_text(
            bridge_outcome.variant_prompt, encoding="utf-8",
        )

    applied_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    pointer = {
        "role": role,
        "variant_id": bridge_outcome.variant_id,
        "variant_path": str(variant_path),
        "applied_at": applied_at,
        "baseline_backtest_score": bridge_outcome.patch_outcome.baseline_backtest_score,
        "candidate_backtest_score": bridge_outcome.patch_outcome.candidate_backtest_score,
        "delta": bridge_outcome.patch_outcome.delta,
        "epsilon_required": bridge_outcome.patch_outcome.epsilon_required,
        "cohort_size": bridge_outcome.patch_outcome.cohort_size,
        "rationale": bridge_outcome.variant_rationale,
        "notes": bridge_outcome.patch_outcome.notes,
    }
    pointer_path.write_text(
        json.dumps(pointer, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return AppliedPromptRecord(
        role=role,
        variant_id=bridge_outcome.variant_id,
        variant_path=str(variant_path),
        pointer_path=str(pointer_path),
        applied_at=applied_at,
        baseline_score=bridge_outcome.patch_outcome.baseline_backtest_score,
        candidate_score=bridge_outcome.patch_outcome.candidate_backtest_score,
        delta=bridge_outcome.patch_outcome.delta,
    )


def load_active_variant(
    role: str,
    *,
    base_dir: Path | None = None,
) -> str | None:
    """Read the currently-active variant's prompt text for ``role``.

    Returns the prompt text if a pointer exists, or None if no
    variant has been applied. Role modules that opt into "load from
    applied" call this; modules that prefer their hard-coded prompts
    ignore this surface entirely.
    """
    _validate_role(role)
    root = (base_dir or DEFAULT_APPLIED_PROMPTS_DIR)
    pointer_path = root / role / "current.json"
    if not pointer_path.exists():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        variant_path = Path(pointer["variant_path"])
        if not variant_path.exists():
            return None
        return variant_path.read_text(encoding="utf-8")
    except (json.JSONDecodeError, KeyError, OSError):
        return None


__all__ = [
    "AppliedPromptRecord",
    "DEFAULT_APPLIED_PROMPTS_DIR",
    "PromptApplyError",
    "apply_prompt_variant",
    "load_active_variant",
]
