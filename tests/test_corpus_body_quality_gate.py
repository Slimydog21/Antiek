"""SPR-03 M6 (corpus path) — the extraction-quality gate is LOAD-BEARING in
the corpus-ingest path, not only in the §13.9 public-notes pipeline.

The bulk arXiv body arrives as a PDF fetched at ingest, NOT as discovery-time
text — so ``acquisition.corpus_quality``'s discovery-time checks ran
metadata-only on it (``assess_body=False``). The body's quality is gated inside
the bulk ingest thunk by ``tools.run_corpus_ingest._assert_pdf_body_quality``,
which extracts the real PDF text with the same ``read_pdf`` the ingest uses and
runs ``substrate.quality_gate.assess_extraction_quality`` BEFORE
``ingest_paper_with_rights`` writes anything. These tests prove that gate
rejects OCR garbage / near-empty bodies as a COUNTED per-item failure on the
corpus path, and that a clean body passes — exercising the corpus ingest seam,
not the public-notes gate.

NO live HTTP, NO DB write: the PDF body is built in-process by ``text_to_pdf``
and the gate is asserted before any ingest call.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.books.public_domain import text_to_pdf  # noqa: E402
from tools.run_corpus_ingest import (  # noqa: E402
    BodyQualityRejected,
    _assert_pdf_body_quality,
)

_CLEAN_BODY = (
    "The transformer architecture replaced recurrent layers with attention. "
    "Each token attends to every other token in the sequence, and the model "
    "learns position through added encodings. This parallelism is why training "
    "scales across many accelerators where recurrent models could not. "
    "The result reshaped natural language processing over the following years. "
) * 4

# OCR garble — the same shape the public-notes gate test uses; low alpha-char
# ratio, single-char speckle, vowel-free runs — carried through a real PDF so
# the corpus path's read_pdf -> assess_extraction_quality bites on extracted
# bytes, not on a hand-fed string.
_OCR_GARBAGE_BODY = (
    "rn cl l l 1 1 0 // \\ |  rn  vv  l  l  9 8 7 ~ ` ^ %% $$ ## @@ "
    "l rn cl ii 1l 0O  \\/  |_|  rn rn rn  l l l l  cl cl  9 0 1 2 3 4 5 "
) * 6


def test_clean_pdf_body_passes_corpus_gate():
    """A clean prose PDF body extracts to real text and passes the corpus
    body-quality gate (no raise) — the gate does not block a real document."""
    pdf = text_to_pdf(_CLEAN_BODY, title="Clean Paper")
    # No exception == accepted.
    _assert_pdf_body_quality(pdf, ref_id="arxiv:test.clean")


def test_ocr_garbage_pdf_body_rejected_before_ingest():
    """An OCR-garbage PDF body is rejected by the corpus gate as a
    BodyQualityRejected (a ValueError subclass execute_plan counts as a per-item
    failure) — OCR garbage never enters the corpus."""
    pdf = text_to_pdf(_OCR_GARBAGE_BODY, title="Garbled Scan")
    with pytest.raises(BodyQualityRejected) as exc:
        _assert_pdf_body_quality(pdf, ref_id="arxiv:test.garbage")
    assert "arxiv:test.garbage" in str(exc.value)
    assert "quality gate" in str(exc.value)


def test_body_quality_rejection_is_counted_per_item_not_a_crash():
    """BodyQualityRejected is a ValueError, so execute_plan's per-item
    try/except treats it as a counted failure (the batch continues) rather than
    an uncaught crash — the rigor-card 'counted per-item rejection' contract."""
    assert issubclass(BodyQualityRejected, ValueError)


def test_corpus_gate_uses_the_shared_assess_function():
    """The corpus body gate is the SAME assess_extraction_quality the
    public-notes gate uses — one home for the three signals, not a parallel
    re-implementation (defends against the M6-wired-to-wrong-gate defect)."""
    import inspect

    import tools.run_corpus_ingest as orch

    src = inspect.getsource(orch._assert_pdf_body_quality)
    assert "assess_extraction_quality" in src
    assert "read_pdf" in src
