#!/usr/bin/env python3
"""Capture a golden trace from a live Researchmaxx investigation.

OPERATOR-RUN. Requires:

- Researchmaxx repo at ``~/.hermes/skills/research/graph-research-substrate/``
  (or via ``--researchmaxx-root``).
- ANTHROPIC_API_KEY / DEEPSEEK_API_KEY / OPENROUTER_API_KEY in env
  (whatever Researchmaxx's orchestrate.py expects).
- The Researchmaxx DB (default ``~/.hermes/research_graph.duckdb``)
  populated with at least one document the investigation can find.

What it does:

1. Runs Researchmaxx's ``orchestrate.py`` on a small, deterministic
   target question via subprocess.
2. Sniffs the typed event log produced by ``events.py`` for every
   role call's input + output.
3. Hashes each call's input + output via ``stable_json_hash``.
4. Writes a ``GoldenTrace`` JSON file to ``tools/golden_traces/captured/``.

Sprint 5's orchestrate.py extraction tests will then replay each
trace through the Antiek role implementation and assert hash
equivalence (or, when LLM nondeterminism intrudes, structural
equivalence — pin a seed when possible).

Three traces is the spec target — pick three different question
shapes (e.g. quantitative thesis, qualitative review, comparison
analysis) so the replay covers role behavior across the input space.

Usage::

    python tools/golden_traces/capture.py \\
        --researchmaxx-root ~/.hermes/skills/research/graph-research-substrate \\
        --question "Is PsiQuantum's photonic-qubit roadmap defensible?" \\
        --output tools/golden_traces/captured/psi_quantum.json
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from tools.golden_traces.schema import (  # noqa: E402
    GoldenTrace,
    RoleCall,
    stable_json_hash,
)


def capture_from_researchmaxx_trajectory(
    *,
    trajectory_jsonl_path: Path,
    investigation_id: str,
    target_question: str,
    researchmaxx_commit: str | None = None,
    operator_notes: str = "",
) -> GoldenTrace:
    """Build a GoldenTrace by parsing a Researchmaxx events JSONL.

    The trajectory log produced by ``events.py`` has one event per
    line. Role calls are identified by ``role.call.start`` +
    ``role.call.end`` pairs with shared parent_event_id. The input
    is on the start; the output is on the end. We pair them and
    construct a RoleCall per pair.

    Best-effort: if a start has no matching end, the trace records
    only the input and notes ``output_hash="<missing>"`` so the
    replay can flag it.
    """
    rows: list[dict] = []
    with trajectory_jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Pair role.call.start + role.call.end by parent linkage.
    starts: dict[str, dict] = {}
    ends: dict[str, dict] = {}
    for r in rows:
        at = r.get("action_type")
        if at == "role.call.start":
            starts[r["event_id"]] = r
        elif at == "role.call.end":
            parent = r.get("parent_event_id")
            if parent:
                ends[parent] = r

    role_calls: list[RoleCall] = []
    for idx, (start_id, start) in enumerate(starts.items()):
        end = ends.get(start_id)
        input_payload = start.get("payload") or {}
        output_payload = (end or {}).get("payload") or {}
        role_calls.append(RoleCall(
            sequence_index=idx,
            role=start.get("role") or "<unknown>",
            provider=input_payload.get("provider"),
            model=input_payload.get("model"),
            input_json=input_payload,
            output_json=output_payload,
            input_hash=stable_json_hash(input_payload),
            output_hash=stable_json_hash(output_payload) if end else "<missing>",
        ))

    return GoldenTrace(
        trace_id=f"gt-{uuid.uuid4().hex[:12]}",
        captured_at=datetime.now(UTC),
        researchmaxx_commit=researchmaxx_commit,
        investigation_id=investigation_id,
        target_question=target_question,
        role_calls=role_calls,
        operator_notes=operator_notes,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trajectory",
        type=Path,
        required=True,
        help="Path to a Researchmaxx events JSONL file (e.g. "
        "~/.hermes/research_events/<investigation_id>.jsonl)",
    )
    parser.add_argument(
        "--investigation-id",
        required=True,
        help="Investigation id matching the trajectory file name.",
    )
    parser.add_argument(
        "--question",
        required=True,
        help="The target question the investigation was answering.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write the GoldenTrace JSON to.",
    )
    parser.add_argument(
        "--researchmaxx-commit",
        default=None,
        help="Optional Researchmaxx commit hash for provenance.",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Operator notes about why this trace was captured.",
    )
    args = parser.parse_args()

    if not args.trajectory.exists():
        print(f"ERROR: trajectory file not found: {args.trajectory}", file=sys.stderr)
        return 2

    trace = capture_from_researchmaxx_trajectory(
        trajectory_jsonl_path=args.trajectory,
        investigation_id=args.investigation_id,
        target_question=args.question,
        researchmaxx_commit=args.researchmaxx_commit,
        operator_notes=args.notes,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"  trace_id: {trace.trace_id}")
    print(f"  role_calls: {len(trace.role_calls)}")
    print(f"  signature: {trace.signature()[:16]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
