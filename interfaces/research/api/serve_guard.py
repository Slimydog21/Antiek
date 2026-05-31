"""Thin re-export shim for the serving-boundary guard (SPR-02 M2 named path).

The REAL home of the guard is ``substrate.books.serve_guard`` — it is pure
substrate logic (imports only ``substrate.books.serve`` + ``substrate.rights``)
and belongs adjacent to ``serve.py`` in the same layer. This module exists only
to preserve the SPR-02-spec'd ``interfaces/research/api/serve_guard.py`` import
path for the interfaces-layer caller (``interfaces.research.api.books``) without
re-introducing a ``substrate -> interfaces`` import inversion. It re-exports the
guarded serve function and nothing else.
"""

from __future__ import annotations

from substrate.books.serve_guard import serve_full_text_guarded

__all__ = ["serve_full_text_guarded"]
