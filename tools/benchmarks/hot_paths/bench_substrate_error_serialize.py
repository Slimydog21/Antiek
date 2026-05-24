"""Bench: SubstrateError union serialization + variant resolution cost."""

from __future__ import annotations

from pydantic import TypeAdapter

from substrate.errors import (
    BudgetExceeded,
    SchemaMismatch,
    SubstrateError,
    UpstreamUnavailable,
    VerifierTimeout,
    WriterContended,
)
from tools.benchmarks.hot_paths._harness import BenchResult, measure

_ADAPTER: TypeAdapter[SubstrateError] = TypeAdapter(SubstrateError)
_SAMPLES: list[SubstrateError] = [
    BudgetExceeded(cap=100, attempted=150),
    SchemaMismatch(field="foo", expected_type="int",
                   actual_repr="'bar'", schema_version=3),
    UpstreamUnavailable(upstream="openai", status_code=429, reason="rate-limit"),
    VerifierTimeout(verifier="legal_gate", elapsed_s=12.5, timeout_s=10.0),
    WriterContended(resource="syntheses", holder_pid=4242, timeout_s=300.0),
]
_PAYLOADS: list[bytes] = [_ADAPTER.dump_json(s) for s in _SAMPLES]


def _dump_each() -> None:
    for s in _SAMPLES:
        _ADAPTER.dump_json(s)


def _validate_each() -> None:
    for p in _PAYLOADS:
        _ADAPTER.validate_json(p)


def _round_trip_each() -> None:
    for s in _SAMPLES:
        _ADAPTER.validate_json(_ADAPTER.dump_json(s))


def run() -> list[BenchResult]:
    meta = {"variants": 5}
    return [
        measure("errors.union_dump_5_variants", _dump_each,
                iterations=2000, metadata=meta),
        measure("errors.union_validate_5_variants", _validate_each,
                iterations=2000, metadata=meta),
        measure("errors.union_round_trip_5_variants", _round_trip_each,
                iterations=2000, metadata=meta),
    ]


if __name__ == "__main__":
    for r in run():
        print(r.format_summary_line())
