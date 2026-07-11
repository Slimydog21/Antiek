"""Durable CORE metadata corpus boundary."""

from .adapter import CoreCorpusAdapter
from .client import CachedCoreSearch, SearchWorks
from .store import CoreSnapshotError, CoreSnapshotStore

__all__ = [
    "CachedCoreSearch",
    "CoreCorpusAdapter",
    "CoreSnapshotError",
    "CoreSnapshotStore",
    "SearchWorks",
]
