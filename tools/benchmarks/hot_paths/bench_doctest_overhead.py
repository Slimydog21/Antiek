"""Benchmark: doctest execution overhead vs regular test.

Measures the per-doctest-block execution overhead. Relevant to whether
running ``pytest --doctest-modules`` on the substrate floor (ARE-06)
adds non-trivial CI time. We expect ~100 µs per doctest block — fine
for a floor of ~10 doctests.
"""

from __future__ import annotations

import doctest

from tools.benchmarks.hot_paths._harness import BenchResult, measure

# A representative doctest block — the same shape as the exemplars
# added to substrate/results.py.
_DOCTEST_SOURCE = """
    >>> 1 + 1
    2
    >>> sum(range(10))
    45
    >>> sorted([3, 1, 2])
    [1, 2, 3]
"""


def _run_one_doctest() -> None:
    """Parse + execute one DocTestExample-shaped block."""
    parser = doctest.DocTestParser()
    examples = parser.get_examples(_DOCTEST_SOURCE)
    runner = doctest.DocTestRunner(verbose=False)
    fake_test = doctest.DocTest(
        examples=examples,
        globs={},
        name="bench-doctest",
        filename=None,
        lineno=None,
        docstring=_DOCTEST_SOURCE,
    )
    runner.run(fake_test, clear_globs=False)


def run() -> list[BenchResult]:
    return [
        measure(
            "doctest.parse_and_run_3_examples",
            _run_one_doctest,
            iterations=1000,
            metadata={"examples_per_block": 3},
        ),
    ]


if __name__ == "__main__":
    for r in run():
        print(r.format_summary_line())
