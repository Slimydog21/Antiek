"""Golden-trace capture + replay infrastructure.

A golden trace is a captured input + output of a real Researchmaxx
investigation run end-to-end. Sprint 5's orchestrate.py extraction
uses these traces as a ratchet: each role extracted from the monolith
must replay against the captured trace and produce equivalent output.

Operator-facing entry points:

- ``tools/golden_traces/capture.py`` — run against live Researchmaxx
  to capture a trace.
- ``tools/golden_traces/replay.py`` — verify an Antiek replay against
  a captured trace.

Sprint 5 will import ``replay_trace_strict`` into per-role extraction
tests.
"""

from .replay import CallMatch, MatchReport, load_trace, replay_trace_strict
from .schema import GOLDEN_TRACE_SCHEMA_VERSION, GoldenTrace, RoleCall, stable_json_hash

__all__ = [
    "GOLDEN_TRACE_SCHEMA_VERSION",
    "GoldenTrace",
    "RoleCall",
    "stable_json_hash",
    "MatchReport",
    "CallMatch",
    "load_trace",
    "replay_trace_strict",
]
