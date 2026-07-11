"""Acquisition-cache adapters for the uniform research corpus boundary."""

from .adapter import AcquisitionCorpusAdapter
from .normalize import from_arxiv_oai, from_openalex, from_semantic_scholar, from_substack

__all__ = [
    "AcquisitionCorpusAdapter",
    "from_arxiv_oai",
    "from_openalex",
    "from_semantic_scholar",
    "from_substack",
]
