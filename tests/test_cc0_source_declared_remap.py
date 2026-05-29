"""Regression suite for the 2026-05-29 CC0 / CC-BY / CC-BY-SA remap.

The operator ruled that routing CC0 and source-declared CC-BY / CC-BY-SA into
``opt_in_licensed`` was a FALSE provenance: ``opt_in_licensed`` means EXACTLY
"a publisher claimed the work via the §9.10 opt-in flow". This suite locks the
corrected, truthful routing end to end:

  * CC0 (URI + short code)            -> public_domain
  * CC-BY / CC-BY-SA (URI + code)     -> source_declared_open (servable, NOT a
                                          §9.10 opt-in, NOT public domain)
  * deny-by-default preserved          -> CC-BY-NC / CC-BY-ND / unknown -> gated

It is NOT a gate-weakening change: every gated row stays gated and the
servability drift-guard stays coupled.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.licenses import resolve_license  # noqa: E402
from acquisition.openaccess.licenses import resolve_oa_license  # noqa: E402
from substrate.ad_inventory.attribution import monetization_eligible  # noqa: E402
from substrate.books.servability import (  # noqa: E402
    ServabilityStatus,
    is_servable_full_text,
    servability_of,
)
from substrate.collective_graph import (  # noqa: E402
    CollectiveGraphDocument,
    is_attribution_eligible,
)
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from substrate.quality_gate import (  # noqa: E402
    CheckResult,
    CheckResultKind,
    QualityGateResult,
    QualityGateVerdict,
)


# ---------------------------------------------------------------------------
# (a) CC0 -> public_domain  (URI + short code, arXiv + OA resolvers)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "resolver, value",
    [
        (resolve_license, "http://creativecommons.org/publicdomain/zero/1.0/"),
        (resolve_oa_license, "https://creativecommons.org/publicdomain/zero/1.0/"),
        (resolve_oa_license, "cc0"),
    ],
)
def test_cc0_resolves_to_public_domain(resolver, value):
    r = resolver(value)
    assert r.content_class == "public_domain"
    assert r.redistributable is True


# ---------------------------------------------------------------------------
# (b) CC-BY / CC-BY-SA -> source_declared_open  (URI + short code)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "resolver, value",
    [
        (resolve_license, "http://creativecommons.org/licenses/by/4.0/"),
        (resolve_license, "http://creativecommons.org/licenses/by-sa/4.0/"),
        (resolve_oa_license, "https://creativecommons.org/licenses/by/4.0/"),
        (resolve_oa_license, "https://creativecommons.org/licenses/by-sa/4.0/"),
        (resolve_oa_license, "cc-by"),
        (resolve_oa_license, "cc-by-sa"),
    ],
)
def test_cc_by_family_resolves_to_source_declared_open(resolver, value):
    r = resolver(value)
    assert r.content_class == "source_declared_open"
    assert r.redistributable is True


# ---------------------------------------------------------------------------
# (c) source_declared_open is servable but NOT a publisher opt-in status
# ---------------------------------------------------------------------------


def test_source_declared_open_is_servable_but_not_publisher_opted_in():
    assert "source_declared_open" in SERVABLE_CONTENT_CLASSES
    status = servability_of("source_declared_open")
    assert is_servable_full_text(status) is True
    assert status is ServabilityStatus.SOURCE_DECLARED_OPEN
    # The whole point of the remap: a source-declared open work must NOT carry
    # the §9.10 publisher-opt-in provenance.
    assert status is not ServabilityStatus.PUBLISHER_OPTED_IN


# ---------------------------------------------------------------------------
# (d) monetization (EARN gate): source_declared_open + public_domain both earn
# ---------------------------------------------------------------------------


def test_monetization_eligible_for_remapped_classes():
    assert monetization_eligible("source_declared_open") is True
    assert monetization_eligible("public_domain") is True


# ---------------------------------------------------------------------------
# (e) attribution payout gate (INNER): source_declared_open needs a claim;
#     public_domain pays out with no claim (no holder to claim).
# ---------------------------------------------------------------------------


def _passing_gate() -> QualityGateResult:
    return QualityGateResult(
        verdict=QualityGateVerdict.PASS_PUBLIC,
        checks=(
            CheckResult(check_name="verification", kind=CheckResultKind.PASS,
                        score=1.0, reasons=("ok",)),
            CheckResult(check_name="voice_style", kind=CheckResultKind.PASS,
                        score=0.9, reasons=("ok",)),
        ),
    )


def _doc(content_class: str, *, claimed: bool) -> CollectiveGraphDocument:
    return CollectiveGraphDocument(
        document_id="d", note_id="n", owner_user_id="ip-x",
        content_class=content_class,
        quality_gate_result=_passing_gate(),
        ip_holder_claimed=claimed,
    )


def test_source_declared_open_without_claim_is_attribution_ineligible():
    # Escrow, not payout: a CC-BY/CC-BY-SA holder is owed attribution but must
    # claim before any disbursement (mirrors the §9.10 escrow-not-payout gap).
    assert is_attribution_eligible(_doc("source_declared_open", claimed=False)) is False


def test_source_declared_open_with_claim_is_attribution_eligible():
    assert is_attribution_eligible(_doc("source_declared_open", claimed=True)) is True


def test_public_domain_is_attribution_eligible_without_claim():
    # CC0 lands here; public domain has no rights holder to claim.
    assert is_attribution_eligible(_doc("public_domain", claimed=False)) is True


# ---------------------------------------------------------------------------
# (f) deny-by-default preserved — NC / ND / unknown stay gated
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "resolver, value",
    [
        (resolve_license, "http://creativecommons.org/licenses/by-nc/4.0/"),
        (resolve_license, "http://creativecommons.org/licenses/by-nd/4.0/"),
        (resolve_license, "http://example.com/some-novel-license/9.9/"),
        (resolve_license, "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"),
        (resolve_oa_license, "https://creativecommons.org/licenses/by-nc/4.0/"),
        (resolve_oa_license, "https://creativecommons.org/licenses/by-nd/4.0/"),
        (resolve_oa_license, "cc-by-nc"),
        (resolve_oa_license, "cc-by-nd"),
        (resolve_oa_license, "bronze"),
        (resolve_oa_license, "https://example.com/unknown/9.9/"),
    ],
)
def test_deny_by_default_preserved(resolver, value):
    r = resolver(value)
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert r.redistributable is False
    # And a gated class is never full-text servable.
    assert is_servable_full_text(servability_of(r.content_class)) is False
