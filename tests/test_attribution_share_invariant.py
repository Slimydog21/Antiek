"""§9.3 attribution shares must be a distribution: non-negative and summing to 1.

`POST /attribution/compute` accepts `chunk_to_claim_confidence`,
`document_to_source_tier` and `claim_load_bearing_scores` in a request body with
no range validation, while the math documented — but did not enforce — their
domains. A weight below zero survives normalisation whenever the positive
weights still outweigh it, so one document received a NEGATIVE share and another
a share above 100%. A negative share is a negative payout.

Two halves are pinned here, and both matter:

* out-of-domain input can no longer leave the share set, and
* in-domain input is arithmetically UNCHANGED, which is why
  `ATTRIBUTION_ALGORITHM_VERSION` is still `attr-math-v1`. If clamping ever
  altered a schema-valid result, the stamp would have to move and every stored
  audit record would need reconstruction against different math.
"""
from itertools import product

import pytest

from substrate.ad_inventory import (
    ATTRIBUTION_ALGORITHM_VERSION,
    compute_attribution_option_a,
    compute_attribution_option_b,
    compute_attribution_option_c,
)

VALID_TIERS = (1, 2, 3, 4, 5)          # documents CHECK (source_tier BETWEEN 1 AND 5)
VALID_CONFIDENCE = (0.0, 0.2, 0.5, 0.75, 1.0)


def _shares_are_a_distribution(shares: dict[str, float]) -> None:
    assert all(value >= 0.0 for value in shares.values()), f"negative share: {shares}"
    assert all(value <= 1.0 for value in shares.values()), f"share above 100%: {shares}"
    if shares:
        assert sum(shares.values()) == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Half 1 — the defect: out-of-domain input must not escape the share set
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad_tier", [6, 7, 99, 0, -3])
def test_out_of_domain_tier_cannot_produce_a_negative_payout(bad_tier):
    shares = compute_attribution_option_b(
        page_id="page",
        chunk_to_document={"c1": "doc_good", "c2": "doc_bad"},
        chunk_to_claim_confidence={},
        document_to_source_tier={"doc_good": 1, "doc_bad": bad_tier},
    ).shares
    _shares_are_a_distribution(shares)


@pytest.mark.parametrize("bad_confidence", [-1.0, -0.25, 2.0, 1e9])
def test_out_of_domain_confidence_cannot_produce_a_negative_payout(bad_confidence):
    shares = compute_attribution_option_b(
        page_id="page",
        chunk_to_document={"c1": "doc_good", "c2": "doc_bad"},
        chunk_to_claim_confidence={"c1": 0.9, "c2": bad_confidence},
        document_to_source_tier={"doc_good": 1, "doc_bad": 3},
    ).shares
    _shares_are_a_distribution(shares)


@pytest.mark.parametrize("bad_score", [-1.0, -0.5, 4.0])
def test_out_of_domain_load_bearing_score_cannot_produce_a_negative_payout(bad_score):
    shares = compute_attribution_option_c(
        page_id="page",
        chunk_to_document={"c1": "doc_good", "c2": "doc_bad"},
        chunk_to_claim_id={"c1": "claim_good", "c2": "claim_bad"},
        claim_load_bearing_scores={"claim_good": 0.9, "claim_bad": bad_score},
    ).shares
    _shares_are_a_distribution(shares)


def test_the_exact_reported_case():
    """tier 7 alongside tier 1 produced -0.25 / +1.25 before the clamp."""
    shares = compute_attribution_option_b(
        page_id="page",
        chunk_to_document={"c1": "doc_good", "c2": "doc_bad"},
        chunk_to_claim_confidence={},
        document_to_source_tier={"doc_good": 1, "doc_bad": 7},
    ).shares
    assert shares["doc_bad"] > 0
    assert shares["doc_good"] < 1


# --------------------------------------------------------------------------
# Half 2 — no silent repricing: in-domain results are bit-identical
# --------------------------------------------------------------------------

def test_in_domain_option_b_matches_the_original_unclamped_formula():
    """Clamping must be a no-op across the whole schema-valid domain.

    The expected value is the ORIGINAL formula, written out here so the test
    fails if the clamp ever changes a legitimate payout.
    """
    for tier_a, tier_b, conf_a, conf_b in product(
        VALID_TIERS, VALID_TIERS, VALID_CONFIDENCE, VALID_CONFIDENCE
    ):
        shares = compute_attribution_option_b(
            page_id="page",
            chunk_to_document={"c1": "doc_a", "c2": "doc_b"},
            chunk_to_claim_confidence={"c1": conf_a, "c2": conf_b},
            document_to_source_tier={"doc_a": tier_a, "doc_b": tier_b},
        ).shares
        weight_a = conf_a * (6 - tier_a)          # original math, unclamped
        weight_b = conf_b * (6 - tier_b)
        total = weight_a + weight_b
        if total <= 0:
            assert shares == {}
            continue
        assert shares["doc_a"] == pytest.approx(weight_a / total)
        assert shares["doc_b"] == pytest.approx(weight_b / total)


def test_in_domain_option_c_matches_the_original_unclamped_formula():
    for score_a, score_b in product(VALID_CONFIDENCE, VALID_CONFIDENCE):
        shares = compute_attribution_option_c(
            page_id="page",
            chunk_to_document={"c1": "doc_a", "c2": "doc_b"},
            chunk_to_claim_id={"c1": "claim_a", "c2": "claim_b"},
            claim_load_bearing_scores={"claim_a": score_a, "claim_b": score_b},
        ).shares
        total = score_a + score_b
        if total <= 0:
            assert shares == {}
            continue
        assert shares["doc_a"] == pytest.approx(score_a / total)
        assert shares["doc_b"] == pytest.approx(score_b / total)


def test_math_version_stamp_is_unchanged():
    """Guards the reasoning above: the stamp moves only if valid-input math moves."""
    assert ATTRIBUTION_ALGORITHM_VERSION == "attr-math-v1"


def test_option_a_was_already_safe():
    """Option A counts citations, so it cannot go negative. Pinned so it stays so."""
    _shares_are_a_distribution(
        compute_attribution_option_a(
            page_id="page",
            chunk_to_document={"c1": "doc_a", "c2": "doc_b", "c3": "doc_a"},
        ).shares
    )
