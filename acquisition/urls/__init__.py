"""URL acquisition path — HTML → markdown → graph.

Sprint 10 day 3-4. Operator runs
``pip install -e '.[urls]'`` once to pick up
``html2text`` + ``beautifulsoup4`` if they don't already have them.
"""

from .adapter import IngestUrlResult, ingest_url, url_doc_id
from .client import FetchedHtml, fetch
from .extract import MarkdownDoc, html_to_markdown

__all__ = [
    "FetchedHtml",
    "IngestUrlResult",
    "MarkdownDoc",
    "fetch",
    "html_to_markdown",
    "ingest_url",
    "url_doc_id",
]
