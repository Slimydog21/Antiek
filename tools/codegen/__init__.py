"""Pydantic → TypeScript codegen for the polyglot seam (architecture_notes §11.1).

Run once after any change to ``substrate/schemas/events.py``::

    python tools/codegen/emit_types.py

CI gate that fails on drift::

    python tools/codegen/check_staleness.py
"""
