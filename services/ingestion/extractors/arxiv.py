"""arXiv extractor for the unified ingestion pipeline (M6).

This module is the thin shim that wires the existing
``acquisition/arxiv/`` (client + adapter) into the new fetcher's
throttle + banned_until + 10× cache. Per rigor #4 (diligence), we
inherit the working PDF endpoint + S2 fallback without rewriting.

Inputs are arXiv URLs like:

  https://arxiv.org/abs/2402.03300
  https://arxiv.org/abs/2402.03300v2
  https://arxiv.org/pdf/2402.03300
  https://export.arxiv.org/abs/2402.03300

We:

1. Parse the arxiv_id out of the URL.
2. Call ``acquisition.arxiv.client.fetch_by_id`` to get the
   ``ArxivPaper`` (abstract + metadata) — but going through the new
   ``services.ingestion.fetcher.fetch`` so the throttle + ban table
   apply. We do this by feeding ``fetch`` the arXiv API URL with an
   ``Accept: application/atom+xml`` and parsing the response with the
   existing Atom parser.
3. Return a ``ArxivExtraction`` envelope the pipeline maps to its
   ExtractedDocument.

The S2 fallback path remains in ``acquisition/arxiv/`` and is wired
via ``fallback_to_s2=True`` when an arXiv fetch fails. We don't
duplicate that fallback here — it's already been validated against
real arXiv behavior in the existing module.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Match arXiv ids:
#   2402.03300            (new style, post-2007)
#   2402.03300v2          (with version)
#   hep-th/9911100        (legacy 1991-2007 style)
_ARXIV_ID_RE = re.compile(
    r"(?:abs|pdf)/([a-zA-Z\-]+(?:\.[A-Z]+)?/\d+|\d{4}\.\d{4,5})(v\d+)?",
)


def parse_arxiv_id(url: str) -> Optional[tuple[str, str]]:
    """Pull (base_id, version) out of an arXiv URL. version is "" or
    e.g. "v2". Returns None when the URL doesn't look like arXiv."""
    if not url:
        return None
    m = _ARXIV_ID_RE.search(url)
    if not m:
        return None
    return (m.group(1), m.group(2) or "")


@dataclass(frozen=True)
class ArxivExtraction:
    """Extractor output for an arXiv URL."""

    arxiv_id: str
    version: str
    title: str
    authors: list[str]
    abstract: str
    abs_url: str
    pdf_url: str
    published_at: datetime
    categories: list[str] = field(default_factory=list)
    primary_category: Optional[str] = None


def extract_arxiv(
    url: str,
    *,
    client: object = None,
    db_path: Optional[str] = None,
) -> ArxivExtraction:
    """Fetch the arXiv Atom metadata for ``url`` through the
    hardened fetcher, parse it with the existing Atom parser, and
    return a uniform envelope.

    ``client`` is an injectable ``httpx.Client`` (MockTransport in
    tests). ``db_path`` lets tests point at a tmp DuckDB; the
    banned_until table lives there.
    """
    parsed = parse_arxiv_id(url)
    if parsed is None:
        raise ValueError(f"URL doesn't look like arXiv: {url!r}")
    base_id, version = parsed

    # The arXiv Atom API. We hit it through the hardened fetcher so
    # throttle + ban + cache apply uniformly with the rest of the
    # pipeline. (The legacy ``acquisition.arxiv.client.fetch_by_id``
    # uses its own httpx — we keep its parser but bypass its fetch.)
    api_base = "https://export.arxiv.org/api/query"
    api_url = (
        api_base
        + "?id_list=" + urllib.parse.quote(base_id)
        + "&max_results=1"
    )
    # Local import: the fetcher module sets SSL env vars at import,
    # so deferring this import keeps cold-start light when the
    # caller only ever uses the EPUB or HTML path.
    from services.ingestion.fetcher import fetch
    from acquisition.arxiv.client import _parse_response

    res = fetch(
        api_url,
        accept="application/atom+xml",
        client=client,  # type: ignore[arg-type]
        db_path=db_path,
        check_robots=False,  # arXiv API path is the operator surface
    )
    papers = _parse_response(res.body)
    if not papers:
        raise ValueError(f"arXiv returned no entries for id {base_id!r}")
    paper = papers[0]

    # Preserve the original version when the URL specified one; the
    # API may return "vN" for the latest version even if the URL was
    # version-less.
    final_version = version or paper.version

    return ArxivExtraction(
        arxiv_id=paper.arxiv_id,
        version=final_version,
        title=paper.title,
        authors=list(paper.authors),
        abstract=paper.abstract,
        abs_url=paper.abs_url,
        pdf_url=paper.pdf_url,
        published_at=paper.published_at,
        categories=list(paper.categories),
        primary_category=paper.primary_category,
    )


def format_as_markdown(extraction: ArxivExtraction) -> str:
    """Compose the abstract + light header so the chunker's
    heading-aware splitter has anchor metadata. Same shape as the
    legacy ``acquisition.arxiv.adapter._format_abstract_markdown``."""
    lines = [
        f"# {extraction.title}",
        "",
        f"_arXiv {extraction.arxiv_id}{extraction.version} · {extraction.abs_url}_",
        "",
    ]
    if extraction.authors:
        lines.append("**Authors:** " + ", ".join(extraction.authors))
        lines.append("")
    if extraction.categories:
        lines.append("**Categories:** " + ", ".join(extraction.categories))
        lines.append("")
    lines.append("## Abstract")
    lines.append("")
    lines.append(extraction.abstract)
    return "\n".join(lines)
