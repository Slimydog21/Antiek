"""Antiek-bench pure substrates (ask #11 — the recursive weekly self-rewriting benchmark).

Each module is independently bar-clean off main. The authorized-run orchestrator
(:mod:`authorized_run`) composes the gate -> run -> record sequence behind injectable
protocols so it stays pure and import-free of the sibling runner/recorder modules.
"""
