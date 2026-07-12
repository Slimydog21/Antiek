"""Antiek-bench pure substrates (ask #11 — recursive weekly self-rewriting benchmark).

A family of import-free pure-Python substrates that turn scored model runs into
the recursive loop the operator named: *run → record → learn what worked / didn't
→ re-write the benchmark (weights and task structure) → next week.* Each module
is independently bar-clean off frozen main; the route layer composes them.
"""
