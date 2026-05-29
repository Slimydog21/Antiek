"""Tests for the arXiv corpus rights-tier census (SPR-01 M4).

NO live HTTP: the seeded census drives the REAL ``OaiPmhHarvester`` paging path
through ``httpx.MockTransport`` (the OA-connector convention), and the unit
tests fold recorded ``arXiv``-format OAI XML. No test references
export.arxiv.org or opens a real socket.

The census's load-bearing properties under test:
  - the RAW license distribution and the PROVISIONAL T1/T2/T3 rollup are two
    views of ONE record stream and share a denominator;
  - deny-by-default: an absent/empty <license> is counted in T3 + ambiguous,
    never promoted to T1;
  - reproducible from one committed query: prefix + window + timestamp are
    stamped, every % is computed, and the committed report is byte-stable;
  - the live (operator) path never touches the network in the build/test.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools.arxiv_census import (  # noqa: E402
    ABSENT_LICENSE_KEY,
    CensusResult,
    build_census_result,
    live_census,
    main,
    render_report,
    seeded_census,
)
from acquisition.arxiv.oai_records import parse_records  # noqa: E402


# ---------------------------------------------------------------------------
# Recorded OAI XML (real export.arxiv.org/oai2 shape, trimmed) — local copy so
# this test is self-contained and never imports another test module.
# ---------------------------------------------------------------------------

_OAI_NS = 'xmlns="http://www.openarchives.org/OAI/2.0/"'
_ARXIV_BODY_NS = 'xmlns="http://arxiv.org/OAI/arXiv/"'

_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_CC_BY_SA = "http://creativecommons.org/licenses/by-sa/4.0/"
_CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"
_CC_BY_NC = "http://creativecommons.org/licenses/by-nc/4.0/"
_ARXIV_DEFAULT = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"


def _record(arxiv_id: str, license_uri):
    lic = f"<license>{license_uri}</license>" if license_uri is not None else ""
    return f"""
      <record>
        <header>
          <identifier>oai:arXiv.org:{arxiv_id}</identifier>
          <datestamp>2024-01-15</datestamp>
        </header>
        <metadata>
          <arXiv {_ARXIV_BODY_NS}>
            <id>{arxiv_id}</id>
            <title>Paper {arxiv_id}</title>
            <categories>cs.LG</categories>
            {lic}
          </arXiv>
        </metadata>
      </record>"""


def _envelope(*records: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH {_OAI_NS}>
  <ListRecords>
    {''.join(records)}
  </ListRecords>
</OAI-PMH>"""


def _fixed_now() -> datetime:
    return datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)


def _result_from(*records: str) -> CensusResult:
    return build_census_result(
        parse_records(_envelope(*records)),
        metadata_prefix="arXiv",
        from_date="2024-01-01",
        until_date="2024-01-31",
        harvested_at=_fixed_now(),
    )


# ---------------------------------------------------------------------------
# M4: the raw distribution + the tier rollup are two views of one stream
# ---------------------------------------------------------------------------


def test_raw_distribution_counts_each_distinct_license_string():
    result = _result_from(
        _record("a1", _CC_BY),
        _record("a2", _CC_BY),
        _record("a3", _CC0),
        _record("a4", _ARXIV_DEFAULT),
    )
    assert result.license_counts[_CC_BY] == 2
    assert result.license_counts[_CC0] == 1
    assert result.license_counts[_ARXIV_DEFAULT] == 1
    # raw distribution sums to the census denominator (asserted in __post_init__)
    assert sum(result.license_counts.values()) == result.census.total == 4


def test_absent_and_empty_license_share_one_raw_bucket_counted_in_t3():
    """Deny-by-default: a missing <license> AND an empty <license/> both land in
    the single ``(absent / empty)`` raw bucket, fold to T3, and are tallied as
    ambiguous — never as a distinct servable URI and never T1."""
    result = _result_from(
        _record("a1", None),   # no <license> element
        _record("a2", ""),     # empty <license/>
        _record("a3", _CC_BY),
    )
    assert result.license_counts[ABSENT_LICENSE_KEY] == 2
    # the absent bucket is a sentinel label, never a real (servable) URI
    assert "creativecommons" not in ABSENT_LICENSE_KEY
    assert "://" not in ABSENT_LICENSE_KEY
    assert result.census.t3 == 2
    assert result.census.ambiguous == 2
    assert result.census.t1 == 1  # only the CC-BY, never the absent ones


def test_tier_rollup_matches_the_raw_distribution_partition():
    result = _result_from(
        _record("a1", _CC_BY),       # T1
        _record("a2", _CC0),         # T1
        _record("a3", _CC_BY_SA),    # T1
        _record("a4", _CC_BY_NC),    # T2
        _record("a5", _ARXIV_DEFAULT),  # T3
        _record("a6", None),         # T3 + ambiguous
    )
    c = result.census
    assert (c.t1, c.t2, c.t3) == (3, 1, 2)
    assert c.total == 6
    assert c.ambiguous == 1
    # rigor bar 3: the partition is exhaustive
    assert c.t1 + c.t2 + c.t3 == c.total


def test_deleted_tombstone_excluded_from_both_views():
    """A deleted record carries no license; it must not appear in the raw
    distribution NOR inflate the denominator of either view."""
    xml = f"""<?xml version="1.0"?>
<OAI-PMH {_OAI_NS}>
  <ListRecords>
    {_record("live1", _CC_BY)}
    <record>
      <header status="deleted">
        <identifier>oai:arXiv.org:dead1</identifier>
        <datestamp>2024-01-02</datestamp>
      </header>
    </record>
  </ListRecords>
</OAI-PMH>"""
    result = build_census_result(
        parse_records(xml),
        metadata_prefix="arXiv",
        from_date=None,
        until_date=None,
        harvested_at=_fixed_now(),
    )
    assert sum(result.license_counts.values()) == 1  # only the live record
    assert result.census.total == 1
    assert result.census.deleted == 1
    assert ABSENT_LICENSE_KEY not in result.license_counts


def test_census_result_rejects_mismatched_denominators():
    """The CensusResult self-check is real: if the raw distribution and the
    census denominator disagree, construction raises (a record can't be lost
    from one view but not the other)."""
    base = _result_from(_record("a1", _CC_BY))
    bad_counts = base.license_counts.copy()
    bad_counts[_CC_BY] += 5  # raw says 6, census says 1
    with pytest.raises(ValueError, match="disagrees with the census denominator"):
        CensusResult(census=base.census, license_counts=bad_counts)


def test_build_census_result_does_not_double_count_from_a_generator():
    """Folding the SAME stream into two views must not consume a generator
    twice and halve one view. A one-shot generator yields the full count to
    both."""
    records = parse_records(
        _envelope(_record("a1", _CC_BY), _record("a2", _CC0))
    )
    gen = (r for r in records)
    result = build_census_result(
        gen,
        metadata_prefix="arXiv",
        from_date=None,
        until_date=None,
        harvested_at=_fixed_now(),
    )
    assert result.census.total == 2
    assert sum(result.license_counts.values()) == 2


# ---------------------------------------------------------------------------
# M4: the seeded census drives the REAL harvester through MockTransport
# ---------------------------------------------------------------------------


def test_seeded_census_pages_through_resumption_token_no_network():
    """The committed census runs the production OaiPmhHarvester paging/throttle
    path against a recorded 2-page mock sequence — no real socket."""
    result = seeded_census()
    c = result.census
    # 4 T1 + 2 T2 + 2 T3 across the two pages; 1 deleted tombstone excluded.
    assert c.t1 == 4
    assert c.t2 == 2
    assert c.t3 == 2
    assert c.total == 8
    assert c.ambiguous == 1   # the single absent-license record
    assert c.deleted == 1
    assert c.t1 + c.t2 + c.t3 == c.total
    assert sum(result.license_counts.values()) == c.total


def test_seeded_census_is_deterministic():
    """Two runs of the seeded census produce identical counts AND an identical
    rendered report — reproducibility is the contract."""
    a = render_report(seeded_census())
    b = render_report(seeded_census())
    assert a == b


def test_seeded_census_stamps_the_reproducing_query():
    c = seeded_census().census
    assert c.metadata_prefix == "arXiv"
    assert c.from_date == "2024-01-01"
    assert c.until_date == "2024-01-31"
    assert c.harvested_at == datetime(2026, 5, 29, 0, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# M4: the rendered report — computed %, no hand-rounding, deny-by-default visible
# ---------------------------------------------------------------------------


def test_report_percentages_are_computed_not_hand_rounded():
    # 1 T1 of 4 -> exactly 25.0%; 3 T3 of 4 -> 75.0%.
    result = _result_from(
        _record("a1", _CC_BY),
        _record("a2", _ARXIV_DEFAULT),
        _record("a3", _ARXIV_DEFAULT),
        _record("a4", _ARXIV_DEFAULT),
    )
    report = render_report(result)
    assert "25.0%" in report   # T1 share / monetizable
    assert "75.0%" in report   # T3 share
    # the monetizable line states the T1 count/total it was computed from
    assert "T1 = 1 / 4 = 25.0%" in report


def test_report_lists_all_required_sections_and_counts():
    result = _result_from(
        _record("a1", _CC_BY),
        _record("a2", _CC_BY_NC),
        _record("a3", _ARXIV_DEFAULT),
        _record("a4", None),
    )
    report = render_report(result)
    # acceptance: exact counts for T1/T2/T3/unknown + monetizable %
    assert "Provisional tier rollup" in report
    assert "Monetizable share" in report
    assert "Raw license-string distribution" in report
    assert "Reproducing query" in report
    # SPR-02 ownership of the authoritative resolver is called out
    assert "SPR-02" in report
    # the OpenAlex refutation is recorded in the report
    assert "OpenAlex" in report
    # absent/empty bucket is surfaced as unknown, with its count
    assert ABSENT_LICENSE_KEY in report
    # the four tier counts are present: T1=1, T2=1, T3=2 (arxiv-default + absent)
    assert "| T1 | CC0 / CC-BY / CC-BY-SA — redistributable open | 1 |" in report
    assert "of which unknown (absent/empty `<license>`):** 1" in report


def test_report_marks_the_rollup_provisional_and_names_the_resolver_owner():
    report = render_report(_result_from(_record("a1", _CC_BY)))
    assert "PROVISIONAL" in report
    assert "authoritative tier resolver" in report


def test_report_states_the_partition_self_check():
    report = render_report(
        _result_from(_record("a1", _CC_BY), _record("a2", _ARXIV_DEFAULT))
    )
    # the report asserts T1+T2+T3==total inline, derived from the census
    assert "T1 + T2 + T3 = 2 == total (2)" in report


def test_report_raw_distribution_is_sorted_deterministically():
    """Count desc, URI asc — so a re-harvest's diff is the changed counts, not
    row reordering."""
    result = _result_from(
        _record("a1", _CC_BY),
        _record("a2", _CC_BY),
        _record("a3", _CC0),
        _record("a4", _ARXIV_DEFAULT),
    )
    report = render_report(result)
    # CC-BY (count 2) appears before CC0 and arxiv-default (count 1 each)
    by_pos = report.index(_CC_BY)
    cc0_pos = report.index(_CC0)
    arxiv_pos = report.index(_ARXIV_DEFAULT)
    assert by_pos < cc0_pos
    assert by_pos < arxiv_pos
    # the two count-1 URIs are in URI-ascending order (arxiv.org < creativecommons)
    assert arxiv_pos < cc0_pos


def test_empty_census_report_renders_zero_percent_not_zero_division():
    result = build_census_result(
        [], metadata_prefix="arXiv", from_date=None, until_date=None,
        harvested_at=_fixed_now(),
    )
    report = render_report(result)
    assert "0.0%" in report
    assert "total (live papers)** |  | **0**" in report


# ---------------------------------------------------------------------------
# M4: the CLI writes the committed report
# ---------------------------------------------------------------------------


def test_main_seed_writes_report(tmp_path):
    out = tmp_path / "census.md"
    rc = main(["--seed", "--out", str(out)])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "# arXiv corpus rights-tier census" in text
    # the seeded monetizable share is 4/8 = 50.0%
    assert "T1 = 4 / 8 = 50.0%" in text


def test_main_defaults_to_seed_when_no_mode_given(tmp_path):
    out = tmp_path / "census.md"
    rc = main(["--out", str(out)])
    assert rc == 0
    assert out.read_text(encoding="utf-8").startswith("# arXiv corpus rights-tier census")


# ---------------------------------------------------------------------------
# Hard constraint 2: the LIVE (operator) path uses a real client + persisted
# throttle and is NEVER hit in tests. We assert its WIRING without a network
# call by intercepting the harvester it builds.
# ---------------------------------------------------------------------------


def test_live_census_routes_through_a_real_persisted_throttle(monkeypatch):
    """``live_census`` must build an OaiPmhHarvester whose throttle is the
    PR#23 persisted ArxivThrottle (not a no-op), and harvest through it. We
    stub the harvest() at the seam so no socket opens, and assert the throttle
    type + that the window flows through."""
    import tools.arxiv_census as mod
    from acquisition.arxiv import ArxivThrottle

    seen = {}

    class _SpyHarvester:
        def __init__(self, *, throttle, base_url=None, **kw):
            seen["throttle_type"] = type(throttle)
            seen["base_url"] = base_url
            self._metadata_prefix = "arXiv"

        def harvest(self, *, from_date=None, until_date=None, resume=True):
            seen["from_date"] = from_date
            seen["until_date"] = until_date
            return iter([])  # no records, no network

    monkeypatch.setattr(mod, "OaiPmhHarvester", _SpyHarvester)
    result = live_census(from_date="2024-03-01", until_date="2024-03-31")

    assert seen["throttle_type"] is ArxivThrottle  # persisted, real spacing
    assert seen["from_date"] == "2024-03-01"
    assert seen["until_date"] == "2024-03-31"
    assert result.census.total == 0
    assert result.census.metadata_prefix == "arXiv"
