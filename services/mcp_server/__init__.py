"""Antiek MCP server — exposes substrate resources over Model Context Protocol.

Serves private notes via ``antiek://private/notes/{user_id}/{note_id}``
from the DuckDB substrate, read-only. Single-writer invariant respected:
this server opens only read-only connections through
``runtime.db_lock.connect_read``.
"""

from __future__ import annotations
