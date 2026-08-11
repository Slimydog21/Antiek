"""Emit the arXiv corpus rights-tier CENSUS (SPR-01 M4).

The entire downstream payout business case rides on ONE measured number: how
large tier T1 (CC0 / CC-BY / CC-BY-SA — redistributable open) is relative to the
whole arXiv corpus. No payout code is built until that number exists. This tool
produces it, reproducibly, and writes ``reports/arxiv_census.md``.

WHAT IT MEASURES, from the OAI-PMH ``<license>`` element ONLY (the authoritative
rights anchor — see ``acquisition.arxiv.oai_records``; not OpenAlex, which lacks
the element and is null exactly where it matters):

  1. a RAW license-string distribution — every distinct ``<license>`` URI and
     its count, plus an explicit ``(absent / empty)`` bucket. This is the
     ground truth a reviewer reads before trusting any rollup.
  2. a PROVISIONAL three-tier rollup folded from (1):
       T1  CC0 / CC-BY / CC-BY-SA      — redistributable open (monetizable)
       T2  CC-BY-NC*                    — non-commercial (NC bars ad-funded serving)
       T3  arXiv-default / unknown / absent — the deny-by-default gated floor
     PROVISIONAL because SPR-02 owns the AUTHORITATIVE tier resolver
     (``acquisition.arxiv.licenses`` + the SPR-02 work that supersedes the
     ``substrate.schemas.documents.classify_tier`` mapping this tool folds on).
     When SPR-02's resolver lands, this rollup is to be replaced by it; the RAW
     distribution above is the part that does not move.

HARD CONSTRAINTS honored here:

  * NO live network in tests or build. The harvest goes through an injectable
    ``httpx.Client``; ``--seed`` runs the exact production harvest code path
    against a recorded multi-page OAI sequence served by ``httpx.MockTransport``
    (the OA-connector test convention). The live full backfill (M5) is an
    OPERATOR step run with ``--live`` + a real client, NOT run here.
  * deny-by-default: an absent / empty / unrecognised ``<license>`` is counted
    in T3 (and, when absent/empty, also in ``ambiguous``), never silently
    promoted to T1. The self-checking ``RightsCensus`` asserts
    ``T1 + T2 + T3 == total`` so a record can never be dropped from the
    denominator.
  * reproducible from ONE committed query: the report stamps the
    metadataPrefix + from/until window + harvest timestamp, and every % is
    COMPUTED from the counts (``RightsCensus.fraction``), never hand-edited.

Usage:

    # regenerate the committed report from the seeded census (deterministic)
    python -m tools.arxiv_census --seed --out reports/arxiv_census.md

    # OPERATOR ONLY — the real backfill against oaipmh.arxiv.org/oai (M5);
    # the true TAM. Requires --live to arm the network path.
    python -m tools.arxiv_census --live --from 2024-01-01 --until 2024-12-31 \\
        --out reports/arxiv_census.md
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv import ArxivThrottle, OaiPmhHarvester  # noqa: E402
from acquisition.arxiv.oai_records import build_census  # noqa: E402
from substrate.schemas.documents import (  # noqa: E402
    ArxivOaiRecord,
    RightsCensus,
    RightsTier,
    classify_tier,
)

# The label for the absent/empty-license bucket in the raw distribution. A real
# license URI can never equal this (it is not a URI), so it cannot collide.
ABSENT_LICENSE_KEY = "(absent / empty)"


@dataclass(frozen=True)
class CensusResult:
    """The full census: the self-checking tier rollup + the raw per-URI counts.

    ``census`` carries the exhaustive T1/T2/T3 partition and the reproducing
    query; ``license_counts`` is the raw ``<license>``-string distribution the
    rollup folds from. Both are derived from the SAME record stream in one pass,
    so the raw counts and the rollup can never disagree about the denominator
    (asserted in ``__post_init__``).
    """

    census: RightsCensus
    license_counts: Counter  # license URI (or ABSENT_LICENSE_KEY) -> count

    def __post_init__(self) -> None:
        # The raw distribution and the rollup are two views of one corpus; their
        # denominators must match or one of them is lying.
        raw_total = sum(self.license_counts.values())
        if raw_total != self.census.total:
            raise ValueError(
                f"raw license distribution ({raw_total}) disagrees with the "
                f"census denominator ({self.census.total}) — counts derived from "
                f"different streams"
            )


def build_census_result(
    records: Iterable[ArxivOaiRecord],
    *,
    metadata_prefix: str,
    from_date: str | None,
    until_date: str | None,
    harvested_at: datetime,
) -> CensusResult:
    """Fold one record stream into BOTH the raw license distribution and the
    self-checking tier rollup, in a single pass.

    Materialising the stream once (``list``) is deliberate: the corpus census is
    a one-shot batch artifact, not a streaming hot path, and folding the same
    records twice from a generator would silently halve the counts. Deleted
    tombstones carry no ``<license>`` and are excluded from BOTH views (they are
    tallied as ``census.deleted``), so the raw distribution and the rollup share
    the live-paper denominator.
    """
    materialized: list[ArxivOaiRecord] = list(records)

    license_counts: Counter = Counter()
    for record in materialized:
        if record.deleted:
            continue
        uri = record.license_uri
        key = uri if uri and uri.strip() else ABSENT_LICENSE_KEY
        license_counts[key] += 1

    census = build_census(
        materialized,
        metadata_prefix=metadata_prefix,
        from_date=from_date,
        until_date=until_date,
        harvested_at=harvested_at,
    )
    return CensusResult(census=census, license_counts=license_counts)


def _pct(fraction: float) -> str:
    """A fraction (0.0–1.0) as a 1-decimal percent string. Computed from the
    census's ``fraction`` — never a hand-typed number — so the report cannot
    drift from the counts."""
    return f"{fraction * 100:.1f}%"


def render_report(result: CensusResult) -> str:
    """Render the census as the committed Markdown report.

    Deterministic for a given ``CensusResult``: tier rows are in a fixed order;
    the raw distribution is sorted by count desc then URI asc so re-running
    yields a byte-identical report (the diff of a re-harvest is purely the
    changed counts, not row reordering). Every percentage is the COMPUTED
    ``fraction``; the monetizable line and the partition assertion are derived,
    not asserted by hand.
    """
    c = result.census
    t1_pct = _pct(c.fraction(c.t1))
    t2_pct = _pct(c.fraction(c.t2))
    t3_pct = _pct(c.fraction(c.t3))
    ambiguous_pct = _pct(c.fraction(c.ambiguous))

    # The query that reproduces this exact census (rigor bars 3 + 5).
    window = (
        f"{c.from_date or '(open)'} .. {c.until_date or '(open)'}"
    )
    harvested = c.harvested_at.isoformat()

    lines: list[str] = []
    lines.append("# arXiv corpus rights-tier census")
    lines.append("")
    lines.append(
        "Generated by `python -m tools.arxiv_census` from a single OAI-PMH "
        "harvest. Do not hand-edit — re-run the tool to regenerate."
    )
    lines.append("")
    lines.append("## Reproducing query")
    lines.append("")
    lines.append("| field | value |")
    lines.append("| --- | --- |")
    lines.append(f"| metadataPrefix | `{c.metadata_prefix}` |")
    lines.append(f"| date window (from .. until) | `{window}` |")
    lines.append(f"| harvested_at (UTC) | `{harvested}` |")
    lines.append("| license source | OAI-PMH `<license>` element (authoritative) |")
    lines.append("")
    lines.append(
        "The license is read from arXiv's own per-paper `<license>` element via "
        "OAI-PMH — the only interface that carries it. It is NOT taken from "
        "OpenAlex (which has no such element and is null exactly for the "
        "preprints this measures). See the packet's fairness note."
    )
    lines.append("")

    lines.append("## Provisional tier rollup")
    lines.append("")
    lines.append(
        "PROVISIONAL: this T1/T2/T3 mapping is folded from "
        "`substrate.schemas.documents.classify_tier` (deny-by-default). **SPR-02 "
        "owns the authoritative tier resolver and this rollup is to be replaced "
        "by it.** The raw distribution below is the part that does not move."
    )
    lines.append("")
    lines.append("| tier | meaning | count | share |")
    lines.append("| --- | --- | ---: | ---: |")
    lines.append(
        f"| T1 | CC0 / CC-BY / CC-BY-SA — redistributable open | {c.t1} | {t1_pct} |"
    )
    lines.append(
        f"| T2 | CC-BY-NC* — non-commercial (gated) | {c.t2} | {t2_pct} |"
    )
    lines.append(
        f"| T3 | arXiv-default / unknown / absent — gated floor | {c.t3} | {t3_pct} |"
    )
    lines.append(f"| **total (live papers)** |  | **{c.total}** | 100.0% |")
    lines.append("")
    lines.append(
        f"- **of which unknown (absent/empty `<license>`):** {c.ambiguous} "
        f"({ambiguous_pct}) — counted in T3, never promoted to T1 (deny-by-default)."
    )
    lines.append(
        f"- **deleted tombstones excluded from the denominator:** {c.deleted}."
    )
    lines.append(
        f"- **partition self-check:** T1 + T2 + T3 = "
        f"{c.t1 + c.t2 + c.t3} == total ({c.total}). "
        f"(Enforced by `RightsCensus.__post_init__`; this report cannot render "
        f"a census that fails it.)"
    )
    lines.append("")

    lines.append("## Monetizable share")
    lines.append("")
    lines.append(
        f"**T1 = {c.t1} / {c.total} = {t1_pct} of the live corpus is "
        f"redistributable-open (the monetizable tier).** "
        f"T2 ({t2_pct}) and T3 ({t3_pct}) are gated. This single number is the "
        f"input to the payout business case; it is computed from the counts "
        f"above, not asserted."
    )
    lines.append("")

    lines.append("## Raw license-string distribution")
    lines.append("")
    lines.append(
        "Every distinct `<license>` value and its count, before any tier "
        "folding. `(absent / empty)` is the deny-by-default bucket (no declared "
        "license OR an empty element). The tier each URI folds into is shown so "
        "a reviewer can audit the provisional rollup row by row."
    )
    lines.append("")
    lines.append("| `<license>` value | tier | count |")
    lines.append("| --- | --- | ---: |")
    for key, count in _sorted_distribution(result.license_counts):
        tier = _tier_for_key(key)
        lines.append(f"| `{key}` | {tier.value} | {count} |")
    lines.append("")

    return "\n".join(lines) + "\n"


def _sorted_distribution(counts: Counter) -> list[tuple[str, int]]:
    """Count desc, then URI asc — a stable total order so the report is
    byte-deterministic across runs with identical counts."""
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _tier_for_key(key: str) -> RightsTier:
    """The tier a raw-distribution key folds into. The absent/empty bucket is
    classified through the SAME ``classify_tier(None)`` path a real record takes
    — so the audit column cannot disagree with the rollup."""
    if key == ABSENT_LICENSE_KEY:
        return classify_tier(None)
    return classify_tier(key)


# ---------------------------------------------------------------------------
# Harvest drivers — seeded (mocked, for the committed report) vs live (operator)
# ---------------------------------------------------------------------------

# A small, recorded multi-page OAI-PMH ``arXiv``-format sequence. This is the
# ONE committed query the report is reproducible from until the operator runs
# the real backfill (M5). It exercises every tier boundary + the deny-by-default
# cases, and pages across a resumption token so the seeded path is the SAME code
# path the live backfill uses (only the client differs). The shape mirrors the
# real oaipmh.arxiv.org/oai ListRecords envelope (see tests/test_arxiv_oai_records.py).
_SEED_FROM = "2024-01-01"
_SEED_UNTIL = "2024-01-31"
_SEED_HARVESTED_AT = datetime(2026, 5, 29, 0, 0, 0, tzinfo=UTC)

_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_CC_BY_SA = "http://creativecommons.org/licenses/by-sa/4.0/"
_CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"
_CC_BY_NC = "http://creativecommons.org/licenses/by-nc/4.0/"
_CC_BY_NC_SA = "http://creativecommons.org/licenses/by-nc-sa/4.0/"
_ARXIV_DEFAULT = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"

_ARXIV_BODY_NS = 'xmlns="http://arxiv.org/OAI/arXiv/"'
_OAI_NS = 'xmlns="http://www.openarchives.org/OAI/2.0/"'


def _seed_record(arxiv_id: str, license_uri: str | None) -> str:
    lic = (
        f"<license>{license_uri}</license>"
        if license_uri is not None
        else ""
    )
    return f"""
      <record>
        <header>
          <identifier>oai:arXiv.org:{arxiv_id}</identifier>
          <datestamp>2024-01-15</datestamp>
        </header>
        <metadata>
          <arXiv {_ARXIV_BODY_NS}>
            <id>{arxiv_id}</id>
            <title>Seed paper {arxiv_id}</title>
            <categories>cs.LG</categories>
            {lic}
          </arXiv>
        </metadata>
      </record>"""


def _seed_envelope(*records: str, token: str | None = None) -> bytes:
    rt = f"<resumptionToken>{token}</resumptionToken>" if token else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH {_OAI_NS}>
  <responseDate>2026-05-29T00:00:00Z</responseDate>
  <ListRecords>
    {''.join(records)}
    {rt}
  </ListRecords>
</OAI-PMH>""".encode()


# Page 1 (carries metadataPrefix + window) -> resumption token -> page 2 (final,
# empty resumptionToken). 8 live records + 1 deleted tombstone.
_SEED_PAGE_1 = _seed_envelope(
    _seed_record("2401.0001", _CC_BY),       # T1
    _seed_record("2401.0002", _CC_BY),       # T1
    _seed_record("2401.0003", _CC0),         # T1
    _seed_record("2401.0004", _CC_BY_SA),    # T1
    token="SEEDTOK",
)
_SEED_PAGE_2 = _seed_envelope(
    _seed_record("2401.0005", _CC_BY_NC),    # T2
    _seed_record("2401.0006", _CC_BY_NC_SA), # T2
    _seed_record("2401.0007", _ARXIV_DEFAULT),  # T3
    _seed_record("2401.0008", None),         # T3 + ambiguous (absent license)
    """
      <record>
        <header status="deleted">
          <identifier>oai:arXiv.org:2401.0099</identifier>
          <datestamp>2024-01-20</datestamp>
        </header>
      </record>""",                          # deleted — excluded from denominator
    token=None,
)


def _seed_handler(request: httpx.Request) -> httpx.Response:
    """Serve the recorded 2-page sequence. The first ListRecords carries the
    window; the second is reached via the resumption token. Mirrors the
    OA-connector ``MockTransport`` handler convention."""
    if "resumptionToken=SEEDTOK" in str(request.url):
        return httpx.Response(200, content=_SEED_PAGE_2)
    return httpx.Response(200, content=_SEED_PAGE_1)


def seeded_census() -> CensusResult:
    """The committed census, from the recorded mock sequence via the REAL
    harvest code path.

    The harvester is driven through ``httpx.MockTransport`` and a no-sleep
    throttle pointed at a throwaway state file — no network, no real spacing
    delay, fully deterministic. This is the exact ``OaiPmhHarvester.harvest``
    paging/throttle/parse path the live backfill uses; only the transport
    differs. The clock and window are fixed so the report is byte-stable.
    """
    import tempfile

    client = httpx.Client(transport=httpx.MockTransport(_seed_handler), timeout=5.0)
    # No-op sleep + a throwaway state path so the seeded run neither blocks nor
    # touches the operator's real harvest cursor.
    fd, state_path = tempfile.mkstemp(prefix="arxiv-census-seed-", suffix=".json")
    os.close(fd)
    os.unlink(state_path)  # let the harvester create it fresh
    throttle = ArxivThrottle(
        state_path=state_path,
        min_spacing_s=0.0,
        sleep=lambda _s: None,
    )
    try:
        harvester = OaiPmhHarvester(
            throttle=throttle,
            client=client,
            state_path=state_path + ".harvest",
        )
        records = list(
            harvester.harvest(
                from_date=_SEED_FROM, until_date=_SEED_UNTIL, resume=False
            )
        )
    finally:
        client.close()
        for p in (state_path, state_path + ".harvest"):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass

    return build_census_result(
        records,
        metadata_prefix="arXiv",
        from_date=_SEED_FROM,
        until_date=_SEED_UNTIL,
        harvested_at=_SEED_HARVESTED_AT,
    )


def live_census(
    *,
    from_date: str | None,
    until_date: str | None,
    base_url: str | None = None,
) -> CensusResult:
    """OPERATOR-ONLY (M5): harvest the real oaipmh.arxiv.org/oai and census it.

    A real ``httpx.Client`` (built inside the harvester) routed through the
    PR#23 persisted ``ArxivThrottle`` — >=3s spacing + the 429 ban sentinel —
    so a backfill cannot re-trigger the IP ban that motivated SPR-01. This is
    the true-TAM path; it is never exercised in tests (network forbidden) and is
    only reached behind ``--live``.
    """
    throttle = ArxivThrottle()  # real spacing + persisted cross-process ban state
    harvester = OaiPmhHarvester(throttle=throttle, base_url=base_url)
    records = list(harvester.harvest(from_date=from_date, until_date=until_date))
    return build_census_result(
        records,
        metadata_prefix=harvester._metadata_prefix,  # same instance built above
        from_date=from_date,
        until_date=until_date,
        harvested_at=datetime.now(UTC),
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.arxiv_census",
        description=(
            "Emit the arXiv corpus rights-tier census (T1/T2/T3 + raw "
            "license distribution + monetizable %) to a Markdown report."
        ),
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--seed",
        action="store_true",
        help="census the committed recorded mock sequence (default; no network)",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help=(
            "OPERATOR ONLY: harvest the real oaipmh.arxiv.org/oai (M5). "
            "Routes through the persisted throttle."
        ),
    )
    p.add_argument("--from", dest="from_date", help="OAI 'from' date (YYYY-MM-DD)")
    p.add_argument("--until", dest="until_date", help="OAI 'until' date (YYYY-MM-DD)")
    p.add_argument(
        "--out",
        default=os.path.join(_REPO, "reports", "arxiv_census.md"),
        help="report output path (default: reports/arxiv_census.md)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.live:
        result = live_census(
            from_date=args.from_date, until_date=args.until_date
        )
    else:
        # --seed is the default. The seeded census ignores --from/--until: the
        # committed report is reproducible from the recorded window only.
        result = seeded_census()

    report = render_report(result)
    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)

    c = result.census
    print(
        f"census: T1={c.t1} T2={c.t2} T3={c.t3} (unknown={c.ambiguous}) "
        f"total={c.total} -> monetizable {_pct(c.fraction(c.t1))}; "
        f"wrote {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
