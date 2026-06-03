"""Tests for OAI-PMH record parsing + the rights-tier census (SPR-01 M2).

NO live HTTP: every parse runs against RECORDED OAI-PMH ``arXiv``-format XML
(captured from the real export.arxiv.org/oai2 shape, trimmed to the load-bearing
elements). The license element is the authoritative rights anchor, so the
fixtures cover each tier boundary AND the deny-by-default cases (absent /
empty / unrecognised license) that the payout case must never inflate into T1.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.oai_records import (  # noqa: E402
    build_census,
    parse_records,
)
from substrate.schemas.documents import (  # noqa: E402
    ArxivOaiRecord,
    RightsCensus,
    RightsTier,
    classify_tier,
)

# ---------------------------------------------------------------------------
# Recorded OAI-PMH XML (real export.arxiv.org/oai2 shape, trimmed)
# ---------------------------------------------------------------------------

# The OAI envelope wraps <ListRecords>, which holds <record>s. Each live record
# is <header> (id + datestamp) + <metadata><arXiv ...> with the <license>.
_NS = (
    'xmlns="http://www.openarchives.org/OAI/2.0/"'
)
_ARXIV_BODY_NS = 'xmlns="http://arxiv.org/OAI/arXiv/"'


def _record(arxiv_id: str, datestamp: str, license_uri, *, categories="cs.LG"):
    lic = f"<license>{license_uri}</license>" if license_uri is not None else ""
    # ``license_uri is ""`` (empty string) renders an empty <license/> element.
    return f"""
      <record>
        <header>
          <identifier>oai:arXiv.org:{arxiv_id}</identifier>
          <datestamp>{datestamp}</datestamp>
        </header>
        <metadata>
          <arXiv {_ARXIV_BODY_NS}>
            <id>{arxiv_id}</id>
            <title>Paper {arxiv_id}</title>
            <categories>{categories}</categories>
            {lic}
          </arXiv>
        </metadata>
      </record>"""


def _envelope(*records: str, token: str | None = None) -> str:
    rt = f"<resumptionToken>{token}</resumptionToken>" if token else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH {_NS}>
  <responseDate>2026-05-29T00:00:00Z</responseDate>
  <ListRecords>
    {''.join(records)}
    {rt}
  </ListRecords>
</OAI-PMH>"""


_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_CC_BY_SA = "http://creativecommons.org/licenses/by-sa/4.0/"
_CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"
_CC_BY_NC = "http://creativecommons.org/licenses/by-nc/4.0/"
_CC_BY_NC_SA = "http://creativecommons.org/licenses/by-nc-sa/4.0/"
_ARXIV_DEFAULT = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"


# ---------------------------------------------------------------------------
# M2: license parse — the OAI <license> element is the authoritative anchor
# ---------------------------------------------------------------------------


def test_parse_record_lifts_license_from_oai_element():
    rec = parse_records(_envelope(_record("2401.0001", "2024-01-15", _CC_BY)))[0]
    assert rec.arxiv_id == "2401.0001"
    assert rec.datestamp == "2024-01-15"
    assert rec.license_uri == _CC_BY
    assert rec.title == "Paper 2401.0001"
    assert rec.categories == ("cs.LG",)
    assert rec.deleted is False


def test_parse_record_multiple_categories():
    rec = parse_records(
        _envelope(_record("2401.0009", "2024-01-15", _CC_BY, categories="cs.LG cs.AI math.ST"))
    )[0]
    assert rec.categories == ("cs.LG", "cs.AI", "math.ST")


def test_absent_license_element_is_none_not_empty_string():
    """A record with NO <license> element -> license_uri is None (the
    deny-by-default input), never silently a servable value."""
    rec = parse_records(_envelope(_record("2401.0002", "2024-01-16", None)))[0]
    assert rec.license_uri is None
    assert rec.tier is RightsTier.T3_DEFAULT_UNKNOWN


def test_empty_license_element_reads_as_none():
    """An empty <license/> element is ambiguous, not servable -> None -> T3."""
    rec = parse_records(_envelope(_record("2401.0003", "2024-01-16", "")))[0]
    assert rec.license_uri is None
    assert rec.tier is RightsTier.T3_DEFAULT_UNKNOWN


def test_deleted_record_is_a_tombstone_excluded_from_metadata():
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH {_NS}>
  <ListRecords>
    <record>
      <header status="deleted">
        <identifier>oai:arXiv.org:2401.0099</identifier>
        <datestamp>2024-02-01</datestamp>
      </header>
    </record>
  </ListRecords>
</OAI-PMH>"""
    rec = parse_records(xml)[0]
    assert rec.deleted is True
    assert rec.arxiv_id == "2401.0099"
    assert rec.license_uri is None


def test_oai_error_response_raises():
    """A protocol <error> must raise, never silently parse to an empty list
    that would understate the census."""
    xml = f"""<?xml version="1.0"?>
<OAI-PMH {_NS}>
  <error code="badArgument">from is not a valid date</error>
</OAI-PMH>"""
    with pytest.raises(ValueError, match="badArgument"):
        parse_records(xml)


def test_malformed_xml_raises():
    with pytest.raises(ValueError, match="not valid XML"):
        parse_records(b"<OAI-PMH><not closed")


def test_wrong_metadata_prefix_body_raises():
    """A live record whose body is not the <arXiv> format (e.g. oai_dc, which
    lacks <license>) must raise — silently parsing it would lose the rights
    anchor."""
    xml = f"""<?xml version="1.0"?>
<OAI-PMH {_NS}>
  <ListRecords>
    <record>
      <header><identifier>oai:arXiv.org:x</identifier><datestamp>2024-01-01</datestamp></header>
      <metadata><oai_dc xmlns="http://www.openarchives.org/OAI/2.0/oai_dc/"/></metadata>
    </record>
  </ListRecords>
</OAI-PMH>"""
    with pytest.raises(ValueError, match="metadataPrefix"):
        parse_records(xml)


# ---------------------------------------------------------------------------
# M2: tier classification — deny-by-default partition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("uri", [_CC0, _CC_BY, _CC_BY_SA])
def test_t1_is_redistributable_open(uri):
    assert classify_tier(uri) is RightsTier.T1_REDISTRIBUTABLE


@pytest.mark.parametrize("uri", [_CC_BY_NC, _CC_BY_NC_SA])
def test_t2_is_non_commercial(uri):
    assert classify_tier(uri) is RightsTier.T2_NON_COMMERCIAL


@pytest.mark.parametrize(
    "uri",
    [
        _ARXIV_DEFAULT,
        "All rights reserved",
        "http://example.com/novel-license/1.0/",
        None,
        "",
        "   ",
    ],
)
def test_t3_is_default_unknown_or_absent(uri):
    """LOAD-BEARING: arXiv-default, all-rights-reserved, unrecognised, AND
    absent/empty all land in T3 — never optimistically promoted to T1."""
    assert classify_tier(uri) is RightsTier.T3_DEFAULT_UNKNOWN


def test_nc_nd_is_t2_not_t3():
    """CC-BY-NC-ND is gated AND non-commercial -> T2 (the NC dimension wins
    the census bucket; both are gated so servability is unchanged)."""
    assert (
        classify_tier("http://creativecommons.org/licenses/by-nc-nd/4.0/")
        is RightsTier.T2_NON_COMMERCIAL
    )


def test_nd_without_nc_is_t3():
    """CC-BY-ND is gated but NOT non-commercial -> it is NOT T2; it falls to
    the T3 default bucket."""
    assert (
        classify_tier("http://creativecommons.org/licenses/by-nd/4.0/")
        is RightsTier.T3_DEFAULT_UNKNOWN
    )


# ---------------------------------------------------------------------------
# M2/rigor: the census is an exhaustive, reproducible partition
# ---------------------------------------------------------------------------


def _fixed_now() -> datetime:
    return datetime(2026, 5, 29, 12, 0, 0, tzinfo=UTC)


def test_census_counts_each_tier_and_partition_is_exhaustive():
    xml = _envelope(
        _record("a1", "2024-01-01", _CC_BY),        # T1
        _record("a2", "2024-01-01", _CC0),          # T1
        _record("a3", "2024-01-01", _CC_BY_SA),     # T1
        _record("a4", "2024-01-01", _CC_BY_NC),     # T2
        _record("a5", "2024-01-01", _ARXIV_DEFAULT),  # T3
        _record("a6", "2024-01-01", None),          # T3 + ambiguous
        _record("a7", "2024-01-01", ""),            # T3 + ambiguous
    )
    census = build_census(
        parse_records(xml),
        metadata_prefix="arXiv",
        from_date="2024-01-01",
        until_date="2024-01-31",
        harvested_at=_fixed_now(),
    )
    assert census.t1 == 3
    assert census.t2 == 1
    assert census.t3 == 3
    assert census.total == 7
    assert census.ambiguous == 2  # the absent + empty license, NOT arxiv-default
    # rigor bar 3: the partition is asserted exhaustive (RightsCensus.__post_init__)
    assert census.t1 + census.t2 + census.t3 == census.total


def test_census_records_the_reproducing_query():
    """rigor bar 5: prefix + window + timestamp are stamped on the census so a
    reviewer can re-run the exact ListRecords."""
    census = build_census(
        parse_records(_envelope(_record("a1", "2024-01-01", _CC_BY))),
        metadata_prefix="arXiv",
        from_date="2024-01-01",
        until_date="2024-01-31",
        harvested_at=_fixed_now(),
    )
    assert census.metadata_prefix == "arXiv"
    assert census.from_date == "2024-01-01"
    assert census.until_date == "2024-01-31"
    assert census.harvested_at == _fixed_now()


def test_census_fraction_is_computed_not_hand_rounded():
    census = build_census(
        parse_records(
            _envelope(
                _record("a1", "2024-01-01", _CC_BY),
                _record("a2", "2024-01-01", _ARXIV_DEFAULT),
                _record("a3", "2024-01-01", _ARXIV_DEFAULT),
                _record("a4", "2024-01-01", _ARXIV_DEFAULT),
            )
        ),
        harvested_at=_fixed_now(),
    )
    assert census.fraction(census.t1) == 0.25
    assert census.fraction(census.t3) == 0.75


def test_census_excludes_deleted_from_denominator():
    xml = f"""<?xml version="1.0"?>
<OAI-PMH {_NS}>
  <ListRecords>
    {_record("live1", "2024-01-01", _CC_BY)}
    <record>
      <header status="deleted">
        <identifier>oai:arXiv.org:dead1</identifier>
        <datestamp>2024-01-02</datestamp>
      </header>
    </record>
  </ListRecords>
</OAI-PMH>"""
    census = build_census(parse_records(xml), harvested_at=_fixed_now())
    assert census.total == 1     # only the live record
    assert census.deleted == 1
    assert census.t1 == 1


def test_empty_census_fraction_is_zero_not_zero_division():
    census = build_census([], harvested_at=_fixed_now())
    assert census.total == 0
    assert census.fraction(0) == 0.0


def test_census_rejects_non_exhaustive_partition():
    """The self-check is real: constructing a census whose tiers don't sum to
    total raises — a record can never be silently dropped from the denominator."""
    with pytest.raises(ValueError, match="not exhaustive"):
        RightsCensus(
            t1=1, t2=1, t3=1, total=5, ambiguous=0,
            metadata_prefix="arXiv", from_date=None, until_date=None,
            harvested_at=_fixed_now(),
        )


def test_census_rejects_ambiguous_exceeding_t3():
    with pytest.raises(ValueError, match="ambiguous"):
        RightsCensus(
            t1=0, t2=0, t3=1, total=1, ambiguous=2,
            metadata_prefix="arXiv", from_date=None, until_date=None,
            harvested_at=_fixed_now(),
        )


def test_record_tier_matches_standalone_classify():
    """The record's ``.tier`` property and the standalone ``classify_tier`` are
    the same verdict — there is one tier function, not two."""
    rec = ArxivOaiRecord(arxiv_id="x", datestamp="2024-01-01", license_uri=_CC_BY_NC)
    assert rec.tier is classify_tier(_CC_BY_NC) is RightsTier.T2_NON_COMMERCIAL


def test_documents_schema_imports_without_acquisition_cycle():
    """Regression: ``substrate.schemas.documents`` sits at the bottom of the
    stack and must import with NO eager dependency on ``acquisition`` (the
    resolver is lazily imported inside ``classify_tier``). A fresh subprocess
    importing documents FIRST must not raise the partial-init ImportError that
    a top-level ``from acquisition...`` reintroduces."""
    import subprocess

    code = (
        "import substrate.schemas.documents as d; "
        "assert d.classify_tier('http://creativecommons.org/licenses/by/4.0/')"
        ".value == 'T1'; print('ok')"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=_REPO, capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"
