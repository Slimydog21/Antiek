"""Twitter / X acquisition.

Sprint 14: browser-extension-driven ingest. The extension at
``apps/x-extension/`` captures a thread's DOM, POSTs it to the
substrate, and this adapter writes a ``social_thread`` document with
per-tweet chunks + nodes.

See ``acquisition/twitter/adapter.py`` for the data model and
``ingest_thread_payload`` (entry point for the API handler).
"""

from .adapter import (
    DEFAULT_TWITTER_SOURCE_TIER,
    IngestTwitterResult,
    Tweet,
    TwitterThread,
    ingest_thread_payload,
    ingest_twitter_thread,
    twitter_doc_id,
)

__all__ = [
    "DEFAULT_TWITTER_SOURCE_TIER",
    "IngestTwitterResult",
    "Tweet",
    "TwitterThread",
    "ingest_thread_payload",
    "ingest_twitter_thread",
    "twitter_doc_id",
]
