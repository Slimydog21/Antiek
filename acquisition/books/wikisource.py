"""Wikisource public-domain connector (SPR-06 M3).

Wikisource (a MediaWiki sister project) hosts proofread transcriptions of
source texts. MOST are public domain (expired copyright), but a SMALL set carry
free licenses (CC-BY-SA) and some pages are NOT PD. So PD is established
PER ITEM from the page's **license category** (the ``PD-*`` / "no restrictions"
maintenance categories MediaWiki attaches), NOT assumed from the project.

  * a PD/PD-equivalent category (``PD-old``, ``PD-US``, ``PD-1923``,
    ``PD-self``, "No restrictions") → a CC Public-Domain-Mark URI handed to
    classify() → ``public_domain`` (servable);
  * a free-license category (``CC-BY-SA``) → the CC-BY-SA URI → classify()
    resolves ``source_declared_open`` (servable, share-alike obligation);
  * NO recognized PD/free category (or an explicit ``Copyrighted`` category) →
    license_uri=None, pd_signal=None → classify() gates it (deny-by-default).

The connector strips MediaWiki navigation chrome / templates / footnote
boilerplate before the body is rendered, so the extraction-quality gate scores
the work's body, not the sidebar. Dedup keys on the canonical page name
(source-id) + the content hash of the cleaned body.

NO raw ``requests``/``httpx``: every fetch is via the SPR-03 throttle.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .pd_connector_base import BookCandidate, ThrottledFetcher

logger = logging.getLogger("acquisition.books.wikisource")

SOURCE = "wikisource"
API_URL = "https://en.wikisource.org/w/api.php"
CC_BY_SA_URI = "https://creativecommons.org/licenses/by-sa/4.0/"

# Maintenance categories that POSITIVELY establish public-domain status. Matched
# case-insensitively as substrings of the page's category names. "No
# restrictions" is Wikisource's umbrella PD banner.
_PD_CATEGORY_TOKENS = (
    "pd-old",
    "pd-us",
    "pd-1923",
    "pd-self",
    "pd-usgov",
    "public domain",
    "no restrictions",
)
# Free-license (servable, but NOT public domain) categories.
_CC_BY_SA_CATEGORY_TOKENS = ("cc-by-sa", "cc by-sa")
# Explicit copyright/non-free signals — deny even if a PD token co-occurs.
_COPYRIGHT_CATEGORY_TOKENS = ("copyrighted", "non-free", "fair use")


def _establish_rights(categories: list[str]) -> tuple[Optional[str], Optional[str]]:
    """Map a page's categories to (license_uri, pd_signal) for classify().

    Deny-by-default: an explicit copyright/non-free category disqualifies the
    page before any PD token can accept it; a page with NO recognized PD/free
    category returns (None, None) so classify() gates it.
    """
    cats_l = [c.lower() for c in categories]
    haystack = " ".join(cats_l)
    if any(tok in haystack for tok in _COPYRIGHT_CATEGORY_TOKENS):
        return None, None
    for c in cats_l:
        if any(tok in c for tok in _PD_CATEGORY_TOKENS):
            # PD established BY the category: hand classify() a positive
            # public_domain declaration NAMING the category (no license_uri), so
            # the resulting license_basis quotes the Wikisource category that
            # established PD — not a generic PDM URI that would mask which
            # category was relied on (defensibility #5). classify() takes its
            # declared-public-domain branch and stamps "public_domain: <basis>".
            return None, f"Wikisource license category {c!r}"
    if any(tok in haystack for tok in _CC_BY_SA_CATEGORY_TOKENS):
        # A free-licensed (not PD) work: the CC-BY-SA URI resolves to
        # source_declared_open (servable, share-alike), distinct from PD.
        return CC_BY_SA_URI, None
    return None, None


# ---------------------------------------------------------------------------
# Body cleaning — strip MediaWiki chrome BEFORE extraction-quality scoring.
# ---------------------------------------------------------------------------

_TEMPLATE_RE = re.compile(r"\{\{.*?\}\}", re.DOTALL)
_TABLE_RE = re.compile(r"\{\|.*?\|\}", re.DOTALL)
_REF_RE = re.compile(r"<ref\b.*?</ref>", re.IGNORECASE | re.DOTALL)
_SELFCLOSE_REF_RE = re.compile(r"<ref\b[^>]*/>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_CATEGORY_LINK_RE = re.compile(r"\[\[Category:[^\]]*\]\]", re.IGNORECASE)
_NAV_HEADER_RE = re.compile(r"^==+\s*(navigation|footnotes?|references)\s*==+\s*$",
                            re.IGNORECASE | re.MULTILINE)
# Wikilinks: keep the display text, drop the target. [[a|b]] -> b ; [[a]] -> a
_WIKILINK_RE = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]|]+)\]\]")


def clean_wikitext(wikitext: str) -> str:
    """Strip Wikisource navigation chrome / templates / footnote boilerplate,
    leaving the work's body text. Templates ({{...}}) carry the header/sidebar
    nav and the license banner; ``<ref>`` carries footnotes; ``[[Category:...]]``
    is page-foot metadata — all removed before extraction-quality scoring."""
    text = _TEMPLATE_RE.sub(" ", wikitext)
    text = _TABLE_RE.sub(" ", text)
    text = _REF_RE.sub(" ", text)
    text = _SELFCLOSE_REF_RE.sub(" ", text)
    text = _CATEGORY_LINK_RE.sub(" ", text)
    text = _WIKILINK_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub(" ", text)
    # Drop "== Navigation ==" / "== Footnotes ==" section headers (chrome).
    text = _NAV_HEADER_RE.sub(" ", text)
    text = re.sub(r"^'{2,}|'{2,}$", "", text, flags=re.MULTILINE)  # bold/italic ticks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _categories_for(fetcher: ThrottledFetcher, pagename: str) -> list[str]:
    data = fetcher.get_json(
        API_URL,
        params={
            "action": "query",
            "prop": "categories",
            "titles": pagename,
            "cllimit": "max",
            "format": "json",
        },
    )
    pages = (data.get("query") or {}).get("pages") or {}
    cats: list[str] = []
    for page in pages.values():
        for c in page.get("categories") or []:
            title = c.get("title", "")
            cats.append(title.split(":", 1)[-1] if ":" in title else title)
    return cats


def _body_for(fetcher: ThrottledFetcher, pagename: str) -> str:
    data = fetcher.get_json(
        API_URL,
        params={
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "titles": pagename,
            "format": "json",
        },
    )
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        for rev in page.get("revisions") or []:
            slots = rev.get("slots") or {}
            main = slots.get("main") or {}
            content = main.get("*") or rev.get("*")
            if content:
                return content
    return ""


def candidate_for(
    fetcher: ThrottledFetcher, pagename: str
) -> Optional[BookCandidate]:
    """Resolve one Wikisource page to a candidate (PD established from its
    license category), or None when the page has no usable body. A non-PD page
    still returns a candidate with license_uri=None/pd_signal=None so classify()
    gates it — the caller asserts the gated branch."""
    categories = _categories_for(fetcher, pagename)
    license_uri, pd_signal = _establish_rights(categories)
    raw_wikitext = _body_for(fetcher, pagename)
    cleaned = clean_wikitext(raw_wikitext)
    if not cleaned:
        logger.info("wikisource page %r skipped: empty body after clean", pagename)
        return None
    canonical = pagename.strip().replace(" ", "_")
    return BookCandidate(
        source=SOURCE,
        source_id=f"{SOURCE}:{canonical}",
        title=pagename.strip(),
        author=None,
        source_uri=f"https://en.wikisource.org/wiki/{canonical}",
        # The cleaned body is the text we ingest; rendered to PDF at ingest. It
        # was fetched through the SPR-03 throttle here (the API revision call),
        # so it rides inline and ingest does NOT fetch download_url again.
        download_url=f"https://en.wikisource.org/wiki/{canonical}",
        download_format="text",
        inline_body=cleaned.encode("utf-8"),
        license_uri=license_uri,
        pd_signal=pd_signal,
        subjects=tuple(),
    )


def discover(
    fetcher: ThrottledFetcher, *, limit: int = 25, category: str = "Featured texts"
) -> list[BookCandidate]:
    """Enumerate candidate works from the Wikisource API category listing.

    Tested against a recorded fixture. Returns up to ``limit`` candidates with
    their license established from each page's categories; the servable/gated
    verdict is classify()'s at ingest (a non-PD page comes back gated)."""
    data = fetcher.get_json(
        API_URL,
        params={
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": str(limit),
            "cmtype": "page",
            "format": "json",
        },
    )
    members = (data.get("query") or {}).get("categorymembers") or []
    out: list[BookCandidate] = []
    for m in members:
        if len(out) >= limit:
            break
        pagename = m.get("title")
        if not pagename:
            continue
        cand = candidate_for(fetcher, pagename)
        if cand is not None:
            out.append(cand)
    return out
