"""Reachability probe descriptors.

Each module here exposes a module-level ``PROBE`` (a
``tools.reachability.probe_runner.Probe``). The runner discovers them via
``pkgutil.iter_modules`` over this package. A module without a ``PROBE`` is
skipped (so helper modules are allowed).

See ``../README.md`` for the descriptor contract and the
boot-via-real-factory rule.
"""
