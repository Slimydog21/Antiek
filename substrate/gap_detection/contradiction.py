"""DRW SPR-07 M3 — contradiction detector (high precision).

A structural fact: two insight/claim nodes that are *about the same thing*
(high embedding similarity) yet *conflict*. Embedding similarity alone is
not enough — two similar statements usually agree — so a candidate pair is
only a contradiction if a **verification check** confirms the conflict. This
is the precision-over-recall stance the product demands: "a detector that
cries wolf is worse than none." Embedding-noise false positives are filtered
out by the verifier; we would rather miss a real contradiction than flood the
user's queue with fake ones.

The verifier is injected. The default (``negation_verifier``) is a
conservative lexical heuristic (asymmetric negation of a shared subject) —
deliberately low-recall. Production may inject an LLM verifier; either way
the verifier only *filters* the embedding-derived candidate pairs, it never
invents a pair.

Read-only; deterministic given a deterministic verifier.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Two nodes must be at least this cosine-similar to even be *considered* for
# contradiction — below it they are about different things and cannot conflict.
SIMILARITY_THRESHOLD = 0.85
# Bound the O(N^2) pair scan. Beyond this, only the most-recent nodes are
# considered (documented limitation; full scan is a future, indexed concern).
MAX_NODES_SCANNED = 500

_NEGATION = re.compile(r"\b(not|no|never|cannot|can't|isn't|aren't|doesn't|don't|fails? to|without|lacks?)\b", re.I)

# verifier(text_a, text_b) -> True if they genuinely conflict.
Verifier = Callable[[str, str], bool]


@dataclass(frozen=True)
class Contradiction:
    node_id_a: str
    node_id_b: str
    text_a: str
    text_b: str
    similarity: float


def negation_verifier(a: str, b: str) -> bool:
    """Conservative default: flag a conflict only when exactly one of the two
    similar statements carries a negation (asymmetric negation of a shared
    subject). High precision, low recall — documented as such."""
    a_neg = bool(_NEGATION.search(a))
    b_neg = bool(_NEGATION.search(b))
    return a_neg != b_neg


def _cosine(u, v) -> float:
    if not u or not v:
        return 0.0
    dot = sum(x * y for x, y in zip(u, v))
    nu = math.sqrt(sum(x * x for x in u))
    nv = math.sqrt(sum(y * y for y in v))
    return dot / (nu * nv) if nu and nv else 0.0


def find_contradictions(
    con: Any,
    *,
    verifier: Verifier | None = None,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
) -> list[Contradiction]:
    """Return verified contradictory pairs among insight/claim nodes.
    Ordered by (node_id_a, node_id_b) for determinism."""
    verify = verifier or negation_verifier
    rows = con.execute(
        """
        SELECT node_id, canonical_label, embedding
        FROM nodes
        WHERE node_type IN ('insight', 'claim') AND embedding IS NOT NULL
        ORDER BY created_at DESC, node_id
        LIMIT ?
        """,
        [MAX_NODES_SCANNED],
    ).fetchall()
    items = [(r[0], r[1], list(r[2]) if r[2] is not None else None) for r in rows]
    out: list[Contradiction] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            sim = _cosine(items[i][2], items[j][2])
            if sim < similarity_threshold:
                continue
            if verify(items[i][1], items[j][1]):
                a, b = sorted([(items[i][0], items[i][1]), (items[j][0], items[j][1])])
                out.append(Contradiction(node_id_a=a[0], node_id_b=b[0],
                                         text_a=a[1], text_b=b[1], similarity=sim))
    out.sort(key=lambda c: (c.node_id_a, c.node_id_b))
    return out
