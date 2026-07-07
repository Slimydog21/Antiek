"""Local inbox ingestion — ``~/research/inbox/<date>/*.txt`` article dumps.

Mirrors the ``acquisition.substack`` single-writer §16 / §9.0 personal-reading
pattern. The operator's daily reading stream is personal reading (§9.0), so
every ingested document lands with ``content_class="personal_reading"`` +
``source_kind="user"``.
"""

from .ingest import InboxDayResult, InboxFileResult, ingest_inbox_day, ingest_inbox_file

__all__ = ["InboxDayResult", "InboxFileResult", "ingest_inbox_day", "ingest_inbox_file"]
