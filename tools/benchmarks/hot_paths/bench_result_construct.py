"""Bench: Ok/Err Result construction + JSON round-trip cost."""

from __future__ import annotations

from substrate.errors import BudgetExceeded
from substrate.results import Err, Ok
from tools.benchmarks.hot_paths._harness import BenchResult, measure


def _ok_int_construct() -> None:
    Ok(value=42)


def _err_substrate_construct() -> None:
    Err(error=BudgetExceeded(cap=100, attempted=150))


_PRE_BUILT_OK = Ok(value=42)
_PRE_BUILT_JSON = _PRE_BUILT_OK.model_dump_json()


def _ok_round_trip_json() -> None:
    s = _PRE_BUILT_OK.model_dump_json()
    Ok[int].model_validate_json(s)


def run() -> list[BenchResult]:
    return [
        measure("result.Ok_int_construct", _ok_int_construct, iterations=5000),
        measure("result.Err_substrate_construct",
                _err_substrate_construct, iterations=5000),
        measure("result.Ok_round_trip_json", _ok_round_trip_json,
                iterations=5000,
                metadata={"pre_built_json_bytes":
                          len(_PRE_BUILT_JSON.encode("utf-8"))}),
    ]


if __name__ == "__main__":
    for r in run():
        print(r.format_summary_line())
