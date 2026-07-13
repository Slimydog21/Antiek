"""Antiek-bench — recursive, weekly, self-rewriting model-quality benchmark (ask #11).

This package is the **run + record + score** half of the recursive loop the operator named:
*run → record → learn weights → re-write the benchmark*. It is the namespace
``bench_presentation.view`` defers to ("does not own ``substrate/antiek_bench``").

Submodules are intentionally offline / pure: they never call model providers in the pure layer.
``scorer`` is the honesty keystone (harness spec §6) — it turns one captured run into a dual-output
(finite float ``score`` for the view + real-bool ``success`` for usage-learn) with self-grade
mechanically impossible.
"""
