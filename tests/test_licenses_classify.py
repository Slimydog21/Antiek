"""Tests for the rights-classification chokepoint (SPR-02 M2 + M3).

``acquisition.licenses_core.classify`` is the ONE deny-by-default function that
maps a work's license + source declaration to a content_class and the
gated-mass-ingest-vs-skip decision. These tests pin:

  - deny-by-default: unknown / garbage / None / missing license -> gated,
    never a servable class (the load-bearing safety branch);
  - the positive branches (PD, CC-BY/-SA, CC0, publisher grant) classify
    correctly and carry a non-empty license_basis;
  - a servable result can NEVER carry an empty basis (impossible by construction);
  - the legitimacy policy: in-copyright + legitimate -> gated INGEST;
    + illegitimate -> SKIP; omitting legitimate_source is a TypeError.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.licenses_core import (  # noqa: E402
    ClassificationResult,
    classify,
)
from substrate.books.ingest import _VALID_BOOK_CONTENT_CLASSES  # noqa: E402
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)

_CC_BY = "https://creativecommons.org/licenses/by/4.0/"
_CC_BY_SA = "https://creativecommons.org/licenses/by-sa/4.0/"
_CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"
_CC_BY_NC = "https://creativecommons.org/licenses/by-nc/4.0/"


# ---------------------------------------------------------------------------
# M2 — deny-by-default
# ---------------------------------------------------------------------------


def test_none_license_is_gated_by_default():
    """The deny-by-default branch: no license, no signal -> gated."""
    r = classify(None, {}, legitimate_source=True)
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert r.servable is False


@pytest.mark.parametrize(
    "garbage",
    [
        "blah",
        "license: open",  # weak signal, no recognizable CC code
        "all rights reserved",
        "https://example.com/novel-license/9.9/",
        "   ",
    ],
)
def test_garbage_license_is_gated_never_servable(garbage):
    """An unrecognized / ambiguous license string NEVER resolves servable —
    the intellectual-honesty branch: 'we couldn't tell' gates, it does not
    upgrade to a hopeful servable class."""
    r = classify(garbage, {}, legitimate_source=True)
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert r.servable is False
    assert r.content_class not in SERVABLE_CONTENT_CLASSES


def test_classify_never_invents_a_content_class():
    """Every branch resolves to a class the substrate's book vocabulary
    accepts — no new content_class string is invented."""
    samples = [
        classify(None, {}, legitimate_source=True),
        classify(_CC_BY, {}, legitimate_source=True),
        classify(_CC_BY_SA, {}, legitimate_source=True),
        classify(_CC0, {}, legitimate_source=True),
        classify(_CC_BY_NC, {}, legitimate_source=True),
        classify(None, {"publisher_grant": {"rights_holder": "MIT Press"}}, legitimate_source=True),
        classify(None, {"public_domain": True}, legitimate_source=True),
    ]
    for r in samples:
        assert r.content_class in _VALID_BOOK_CONTENT_CLASSES


# ---------------------------------------------------------------------------
# M2 — the positive (servable) branches
# ---------------------------------------------------------------------------


def test_public_domain_signal_classifies_public_domain():
    r = classify(None, {"public_domain": "US pre-1929"}, legitimate_source=True)
    assert r.content_class == "public_domain"
    assert r.servable is True
    assert "US pre-1929" in r.license_basis


@pytest.mark.parametrize("uri", [_CC_BY, _CC_BY_SA, "cc-by"])
def test_cc_by_family_classifies_source_declared_open(uri):
    r = classify(uri, {}, legitimate_source=True)
    assert r.content_class == "source_declared_open"
    assert r.servable is True


def test_cc0_classifies_public_domain():
    r = classify(_CC0, {}, legitimate_source=True)
    assert r.content_class == "public_domain"
    assert r.servable is True


def test_publisher_grant_classifies_opt_in_licensed():
    r = classify(
        None,
        {"publisher_grant": {"rights_holder": "MIT Press"}},
        legitimate_source=True,
    )
    assert r.content_class == "opt_in_licensed"
    assert r.servable is True
    assert "MIT Press" in r.license_basis


def test_restrictive_cc_license_is_gated_with_named_basis():
    """A recognised-but-restrictive CC license (NC) gates, and the basis NAMES
    why — not a bare 'unrecognised'. NC is an in-copyright restriction with a
    rights holder, so it is accrual-eligible."""
    r = classify(_CC_BY_NC, {}, legitimate_source=True)
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert r.servable is False
    assert "commercial" in r.license_basis.lower()
    assert r.accrual_eligible is True


# ---------------------------------------------------------------------------
# M2 — every servable result carries a non-empty basis
# ---------------------------------------------------------------------------


def test_every_servable_result_has_nonempty_basis():
    """A servable result with an empty basis is impossible by construction:
    the audit (M5) fails the batch on a servable work without a basis, so the
    classifier must never produce one."""
    servable_samples = [
        classify(_CC_BY, {}, legitimate_source=True),
        classify(_CC_BY_SA, {}, legitimate_source=True),
        classify(_CC0, {}, legitimate_source=True),
        classify(None, {"public_domain": True}, legitimate_source=True),
        classify(None, {"publisher_grant": {"rights_holder": "MIT Press"}}, legitimate_source=True),
    ]
    for r in servable_samples:
        assert r.servable is True
        assert r.license_basis and r.license_basis.strip(), r


def test_gated_results_also_carry_a_basis():
    """Even a gated work carries a basis that states WHY it gated (the
    audit + a lawyer read it)."""
    for r in (
        classify(None, {}, legitimate_source=True),
        classify(_CC_BY_NC, {}, legitimate_source=True),
        classify("garbage", {}, legitimate_source=True),
    ):
        assert r.license_basis and r.license_basis.strip()


# ---------------------------------------------------------------------------
# M3 — gated-mass-ingest vs never-ingest (legitimacy policy)
# ---------------------------------------------------------------------------


def test_in_copyright_legitimate_source_is_gated_ingest():
    """An in-copyright work from a legitimate source is ingested GATED — body
    stored, withheld, graph-resident — rather than skipped."""
    r = classify(None, {"rights_holder": "Elsevier"}, legitimate_source=True)
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert r.ingest is True
    assert r.servable is False
    assert r.skipped is False


def test_in_copyright_illegitimate_source_is_skip():
    """The SAME work from an illegitimate (circumvented-access) source is NEVER
    ingested — no body stored, no escrow."""
    r = classify(None, {"rights_holder": "Elsevier"}, legitimate_source=False)
    assert r.ingest is False
    assert r.skipped is True
    assert r.servable is False
    assert r.accrual_eligible is False
    assert "circumvented" in r.license_basis.lower()


def test_legitimate_source_is_keyword_only_no_default():
    """Omitting legitimate_source is a TypeError, proving a connector cannot
    silently omit the legitimacy judgment."""
    with pytest.raises(TypeError):
        classify(None, {})  # type: ignore[call-arg]


def test_legitimate_source_cannot_be_positional():
    """It is keyword-only — a positional third arg is a TypeError, so a caller
    cannot accidentally pass it by position and transpose the judgment."""
    with pytest.raises(TypeError):
        classify(None, {}, True)  # type: ignore[misc]


def test_servable_work_ingested_regardless_of_legitimacy_flag():
    """A positively-licensed servable work (a public-domain text) is lawful
    from any legitimate fetch and is ingested servable regardless of the
    legitimacy flag — legitimacy only gates the non-servable case."""
    for legit in (True, False):
        r = classify(_CC0, {}, legitimate_source=legit)
        assert r.content_class == "public_domain"
        assert r.servable is True
        assert r.ingest is True


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_result_is_classification_result():
    assert isinstance(classify(None, {}, legitimate_source=True), ClassificationResult)
