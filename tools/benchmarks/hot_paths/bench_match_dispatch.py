"""Benchmark: match-based dispatch vs dict-registry vs if/elif chain.

Compares three idioms for variant-typed dispatch — the ARE-03 question.
For a closed-set variant (5 cases) of string equality, measure the
per-call cost of:

  * ``match_dispatch`` — Python ``match`` over a Literal
  * ``dict_dispatch`` — ``{tier: handler_fn}[tier]()``
  * ``if_elif_dispatch`` — chain of ``if x == "a": ...``

Verdict goal: confirm that ``match`` is no slower than ``dict`` for
closed-set variants. If true, the ARE-03 conversion has zero runtime
cost — pure type-safety gain.
"""

from __future__ import annotations

import random
from typing import Literal, cast

from tools.benchmarks.hot_paths._harness import BenchResult, measure

Tier = Literal["a", "b", "c", "d", "e"]

# Pre-build a randomized but seeded sequence of tiers so each
# benchmark sees the same input distribution. Otherwise CPU branch
# prediction would help one shape over another unfairly.
_RNG = random.Random(0xCAFEBEEF)
_TIERS: list[Tier] = [cast(Tier, _RNG.choice("abcde")) for _ in range(1000)]


def _handler_a() -> int:
    return 1


def _handler_b() -> int:
    return 2


def _handler_c() -> int:
    return 3


def _handler_d() -> int:
    return 4


def _handler_e() -> int:
    return 5


_HANDLERS = {
    "a": _handler_a,
    "b": _handler_b,
    "c": _handler_c,
    "d": _handler_d,
    "e": _handler_e,
}


def _match_dispatch_one_call() -> None:
    """One match dispatch across the pre-built tier sequence."""
    total = 0
    for t in _TIERS:
        match t:
            case "a":
                total += _handler_a()
            case "b":
                total += _handler_b()
            case "c":
                total += _handler_c()
            case "d":
                total += _handler_d()
            case "e":
                total += _handler_e()
    _ = total


def _dict_dispatch_one_call() -> None:
    total = 0
    for t in _TIERS:
        total += _HANDLERS[t]()
    _ = total


def _if_elif_dispatch_one_call() -> None:
    total = 0
    for t in _TIERS:
        if t == "a":
            total += _handler_a()
        elif t == "b":
            total += _handler_b()
        elif t == "c":
            total += _handler_c()
        elif t == "d":
            total += _handler_d()
        elif t == "e":
            total += _handler_e()
    _ = total


def run() -> list[BenchResult]:
    meta = {"n_per_call": len(_TIERS), "variants": 5, "seed": "0xCAFEBEEF"}
    return [
        measure(
            "dispatch.match_per_call",
            _match_dispatch_one_call,
            iterations=200,
            metadata=meta,
        ),
        measure(
            "dispatch.dict_per_call",
            _dict_dispatch_one_call,
            iterations=200,
            metadata=meta,
        ),
        measure(
            "dispatch.if_elif_per_call",
            _if_elif_dispatch_one_call,
            iterations=200,
            metadata=meta,
        ),
    ]


if __name__ == "__main__":
    for r in run():
        print(r.format_summary_line())
