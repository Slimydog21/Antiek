"""Built-in agreement functions for ``verify_with_redispatch``.

Verbatim port of Researchmaxx ``verify.py`` (Sprint 6 day 3-4). Each
agreement function takes two parsed role outputs and returns ``True``
iff they agree on the role's load-bearing structural fields. Prose
summaries and confidence labels are deliberately NOT compared —
those are expected to vary across rephrased framings.

Three functions ship:

- ``default_agreement_synthesizer`` — implicit_recommendation must
  match exactly AND falsification-condition observables overlap with
  Jaccard ≥ 0.5.
- ``default_agreement_evidence`` — insufficient_evidence flag must
  match exactly AND cited chunk_ids overlap with Jaccard ≥ 0.5.
- ``default_agreement_strict`` — full structural equality. For
  outcome records, gating decisions, anywhere divergence is itself
  a bug.
"""

from __future__ import annotations

import json


def default_agreement_synthesizer(a: dict, b: dict) -> bool:
    """Synthesizer outputs agree iff:

    - ``implicit_recommendation`` matches exactly, AND
    - the SET of ``falsification_conditions[*].specific_observable``
      values overlaps by Jaccard ≥ 0.5.

    Both empty falsification-condition sets count as agreement;
    one empty, the other non-empty counts as disagreement (asymmetry
    is meaningful — if one pass surfaced falsifiers and the other
    didn't, that's load-bearing divergence)."""
    if a.get("implicit_recommendation") != b.get("implicit_recommendation"):
        return False
    fa = {
        (fc.get("specific_observable") or "").strip().lower()
        for fc in (a.get("falsification_conditions") or [])
        if fc.get("specific_observable")
    }
    fb = {
        (fc.get("specific_observable") or "").strip().lower()
        for fc in (b.get("falsification_conditions") or [])
        if fc.get("specific_observable")
    }
    if not fa and not fb:
        return True
    if not fa or not fb:
        return False
    overlap = len(fa & fb)
    union = len(fa | fb)
    return (overlap / union) >= 0.5


def default_agreement_evidence(a: dict, b: dict) -> bool:
    """Evidence Retriever outputs agree iff:

    - ``insufficient_evidence`` flag matches exactly, AND
    - the SET of cited chunk_ids overlaps by Jaccard ≥ 0.5.
    """
    if a.get("insufficient_evidence") != b.get("insufficient_evidence"):
        return False
    ca: set = set()
    for claim in a.get("supporting_claims") or []:
        ca.update(claim.get("chunk_ids") or [])
    cb: set = set()
    for claim in b.get("supporting_claims") or []:
        cb.update(claim.get("chunk_ids") or [])
    if not ca and not cb:
        return True
    if not ca or not cb:
        return False
    overlap = len(ca & cb)
    union = len(ca | cb)
    return (overlap / union) >= 0.5


def default_agreement_strict(a: dict, b: dict) -> bool:
    """Full structural equality via ``json.dumps(sort_keys=True)``
    fingerprint. For outcome records and gating decisions where any
    divergence is itself a bug."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
