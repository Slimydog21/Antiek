"""Golden-trace schema (Pydantic models).

A golden trace is the captured input + output of a real Researchmaxx
investigation run end-to-end. Sprint 5's orchestrate.py extraction
uses these traces as a ratchet: each role extracted from the monolith
must replay against the captured trace and produce equivalent output.

Structure:

```
GoldenTrace(
    trace_id="...",
    captured_at=...,
    researchmaxx_commit="...",
    investigation_id="...",
    target_question="...",
    role_calls=[
        RoleCall(role="decomposer", input_hash=..., output_hash=...,
                 input_json={...}, output_json={...}),
        RoleCall(role="evidence_retriever", ...),
        ...
    ],
    final_synthesis_id="...",
)
```

The hashes let us detect drift without storing the full transcripts
twice; the JSON blobs let us replay if hash equivalence fails (the
common case for LLM nondeterminism is a textual diff with the same
structural meaning).

Discipline:

- Every field that's not strictly necessary is Optional. Real captures
  are noisy and we'd rather record a partial trace than reject it.
- ``role_calls`` are appended in invocation order. Replay walks them
  in order so the new implementation sees the same sequence the
  monolith did.
- ``input_hash`` and ``output_hash`` use SHA-256 hex over a stable
  JSON serialization (sort_keys=True, ensure_ascii=False).
- Schema lives in ``tools/golden_traces/`` not ``substrate/schemas/``
  because it's developer-facing, not part of the typed event log.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


GOLDEN_TRACE_SCHEMA_VERSION: int = 1


def stable_json_hash(obj: Any) -> str:
    """SHA-256 hex over a stable JSON serialization. Same input →
    same hash, deterministically. Used to detect drift between the
    Researchmaxx monolith's output and the Antiek extraction's
    output for each role call."""
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RoleCall(BaseModel):
    """One LLM call made by a role during the investigation. Captures
    the input prompt + model + provider, the parsed output JSON, and
    hashes of both for fast drift detection on replay."""

    model_config = ConfigDict(extra="allow")  # capture-time noise tolerated

    sequence_index: int = Field(ge=0)
    role: str
    provider: Optional[str] = None
    model: Optional[str] = None
    # The prompt sent to the model and the parsed structured output.
    # ``input_json`` is a structured representation of the inputs
    # (sub_question, context_pack layers, etc.); ``input_text`` is the
    # full string actually sent. Both are stored so a replay can use
    # whichever representation is more stable.
    input_json: dict[str, Any] = Field(default_factory=dict)
    input_text: Optional[str] = None
    output_json: dict[str, Any] = Field(default_factory=dict)
    output_text: Optional[str] = None
    input_hash: str
    output_hash: str
    latency_ms: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class GoldenTrace(BaseModel):
    """One full investigation captured end-to-end."""

    model_config = ConfigDict(extra="allow")

    trace_id: str
    captured_at: datetime
    schema_version: int = GOLDEN_TRACE_SCHEMA_VERSION
    researchmaxx_commit: Optional[str] = None
    investigation_id: str
    target_question: str
    role_calls: list[RoleCall] = Field(default_factory=list)
    # Final outputs the extraction must reproduce.
    final_synthesis_id: Optional[str] = None
    final_thesis_text: Optional[str] = None
    final_thesis_hash: Optional[str] = None
    # Operator notes — non-structural, free-form context for the
    # reviewer comparing replay output to capture output.
    operator_notes: str = ""

    def signature(self) -> str:
        """Stable hash over the role-call ordering + per-call hashes.
        A replay produces the same signature iff every role call had
        equivalent input + output. Drift surfaces as a signature
        mismatch + a per-call breakdown."""
        parts = [
            f"{c.sequence_index}:{c.role}:{c.input_hash}:{c.output_hash}"
            for c in self.role_calls
        ]
        return stable_json_hash(parts)
