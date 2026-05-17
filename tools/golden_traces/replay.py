#!/usr/bin/env python3
"""Replay a captured golden trace against the Antiek role
implementation. Sprint 5's orchestrate.py extraction tests use this
as a ratchet.

Returns:

- ``MatchReport.exact_signature_match`` → True when the trace
  signature is bit-identical between capture and replay.
- ``MatchReport.per_call_match`` → list of bool per role call,
  ordered by sequence_index. Lets the extraction PR show which
  specific role's output drifted.

Replay can be strict (hash-equal) or lenient (structural equivalence,
allowing LLM nondeterminism inside structural fields). Default is
strict for non-LLM roles, lenient for LLM roles — extraction tests
override per-call.

Sprint 4 day 4-5 ships:

- ``MatchReport`` dataclass.
- ``replay_trace_strict`` — hash-equal comparison.
- Loading + saving GoldenTrace JSON.

Deferred (Sprint 5 when extraction starts):

- Lenient structural comparator. Needs role-specific equivalence
  helpers (a Decomposer output is equivalent if the sub_question
  set + keyword set match, regardless of ordering or paraphrase;
  a Synthesizer output is harder).
- Wire into Sprint 5's per-role extraction tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from tools.golden_traces.schema import GoldenTrace, RoleCall, stable_json_hash  # noqa: E402


@dataclass(frozen=True)
class CallMatch:
    sequence_index: int
    role: str
    input_match: bool
    output_match: bool
    note: str = ""


@dataclass(frozen=True)
class MatchReport:
    trace_id: str
    exact_signature_match: bool
    per_call: tuple[CallMatch, ...]

    @property
    def passed(self) -> bool:
        return self.exact_signature_match


def load_trace(path: Path) -> GoldenTrace:
    text = path.read_text(encoding="utf-8")
    return GoldenTrace.model_validate_json(text)


def replay_trace_strict(
    captured: GoldenTrace,
    replayed_calls: list[RoleCall],
) -> MatchReport:
    """Compare captured vs replayed role-by-role on hash equality.

    Two traces are an EXACT match iff:
    1. Same number of role calls in the same order.
    2. Every (input_hash, output_hash) pair agrees.

    Strict equality is the right default for non-LLM roles
    (deterministic code paths). LLM roles will need a lenient
    structural comparator in Sprint 5; this strict path stays as the
    fast happy-path check + the diagnostic when lenience isn't
    available yet.
    """
    matches: list[CallMatch] = []
    by_index_cap = {c.sequence_index: c for c in captured.role_calls}
    by_index_rep = {c.sequence_index: c for c in replayed_calls}

    all_indices = sorted(set(by_index_cap) | set(by_index_rep))
    for idx in all_indices:
        cap = by_index_cap.get(idx)
        rep = by_index_rep.get(idx)
        if cap is None:
            matches.append(CallMatch(
                sequence_index=idx, role=rep.role if rep else "<missing>",
                input_match=False, output_match=False,
                note="present in replay but not capture (extra role call)",
            ))
            continue
        if rep is None:
            matches.append(CallMatch(
                sequence_index=idx, role=cap.role,
                input_match=False, output_match=False,
                note="present in capture but not replay (missing role call)",
            ))
            continue
        matches.append(CallMatch(
            sequence_index=idx, role=cap.role,
            input_match=(cap.input_hash == rep.input_hash),
            output_match=(cap.output_hash == rep.output_hash),
        ))

    # Recompute the replay signature from the matches we got.
    replay_signature_parts = [
        f"{c.sequence_index}:{c.role}:{c.input_hash}:{c.output_hash}"
        for c in replayed_calls
    ]
    replay_signature = stable_json_hash(replay_signature_parts)
    exact = replay_signature == captured.signature()

    return MatchReport(
        trace_id=captured.trace_id,
        exact_signature_match=exact,
        per_call=tuple(matches),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--captured",
        type=Path,
        required=True,
        help="Path to a captured GoldenTrace JSON file.",
    )
    parser.add_argument(
        "--replayed",
        type=Path,
        required=True,
        help="Path to a replayed GoldenTrace JSON file from the Antiek run.",
    )
    args = parser.parse_args()

    cap = load_trace(args.captured)
    rep = load_trace(args.replayed)
    report = replay_trace_strict(cap, rep.role_calls)

    print(f"trace_id: {report.trace_id}")
    print(f"exact_signature_match: {report.exact_signature_match}")
    print(f"per_call: {len(report.per_call)} role calls compared")
    drift = [c for c in report.per_call if not (c.input_match and c.output_match)]
    if drift:
        print(f"\nDrift in {len(drift)} role calls:")
        for c in drift:
            print(f"  - seq={c.sequence_index} role={c.role} "
                  f"input_match={c.input_match} output_match={c.output_match}"
                  + (f" — {c.note}" if c.note else ""))
        return 1
    print("OK: every role call matches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
