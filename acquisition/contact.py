"""The one public contact URL Antiek's outbound HTTP clients advertise in their User-Agent, so a site operator (or arXiv) can reach a human before blocking the source IP. Shared by acquisition.arxiv.client and acquisition.urls.client so the two cannot drift."""
from __future__ import annotations

ANTIEK_CONTACT_URL = "https://antiek.ai/contact"

__all__ = ["ANTIEK_CONTACT_URL"]
