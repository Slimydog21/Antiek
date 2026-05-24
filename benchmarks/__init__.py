"""Antiek performance benchmarks.

Antiek explicitly tracks ONE craft signature (per master-spec §5
voice/style discipline and the Hashimoto "love of the game" lens):
inline-rubric latency. Other dimensions stay at "good enough" by
policy — see ``docs/craft_signature.md``.

The benchmark CLI lives at ``benchmarks/rubric_latency.py``;
fixtures are deterministically generated in ``benchmarks/fixtures/``.
Baselines persist in ``benchmarks/baseline.json`` with git-SHA
provenance. CI runs ``--check-regression`` mode and fails on
>10% p95 regression against the locked baseline.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e7-craft-benchmark.html
"""
