"""The backfill must not stamp an identity it did not verify (audit wave 3, #3)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.backfill_embeddings_meta import _vector_matches


class _Model:
    def encode(self, text):  # deterministic 4-dim stub
        return [float(len(text)), 1.0, 2.0, 3.0]

def test_matching_vector_verifies():
    m = _Model()
    assert _vector_matches(m, "hello", m.encode("hello"))

def test_hash_derived_vector_is_rejected():
    m = _Model()
    assert not _vector_matches(m, "hello", [9.0, -1.0, 0.5, 0.0])

def test_dimension_mismatch_and_empties_are_rejected():
    m = _Model()
    assert not _vector_matches(m, "hello", [1.0, 2.0])
    assert not _vector_matches(m, "hello", None)
    assert not _vector_matches(m, None, [1.0, 1.0, 2.0, 3.0])
