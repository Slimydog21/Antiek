"""Twin-document substrate — insights/questions twin for every asset.

Recursive note-taker vision (operator): every information asset on the platform
can hold a twin document of LLM-proposed insights and questions. Twins are a
*substrate of information* that can be merged, referenced, and searched.

This module is the pure durable store + merge rules only:

* record / load / list by ``parent_asset_id``
* merge twins **only** when they share the same parent (cross-parent rejected)
* double-merge is stable (idempotent union by normalized text)
* no LLM dispatch, no graph writes, no engagement_spine ownership

Filesystem layout (default under ANTIEK_HOME or ``~/.antiek``)::

    twins/{safe_parent_id}.json

Override root with ``ANTIEK_TWIN_NOTES_DIR``.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class TwinNotesError(RuntimeError):
    """Base error for twin-notes substrate."""


class TwinParentMismatch(TwinNotesError):
    """Raised when merge is attempted across different parent assets."""


class TwinNotFound(TwinNotesError):
    """Raised when a twin_id is missing."""


_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


def _default_root() -> Path:
    override = os.environ.get("ANTIEK_TWIN_NOTES_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    home = os.environ.get("ANTIEK_HOME", "").strip()
    base = Path(home).expanduser() if home else Path.home() / ".antiek"
    return base / "twins"


def _safe_filename(parent_asset_id: str) -> str:
    cleaned = _SAFE_ID.sub("_", parent_asset_id.strip())[:180]
    if not cleaned:
        cleaned = "unknown"
    return f"{cleaned}.json"


def _norm_text(text: str) -> str:
    return " ".join(text.strip().split()).casefold()


@dataclass
class TwinDocument:
    twin_id: str
    parent_asset_id: str
    insights: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    source_label: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    # Provenance of merges (twin_ids absorbed).
    merged_from: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TwinDocument:
        return cls(
            twin_id=str(data["twin_id"]),
            parent_asset_id=str(data["parent_asset_id"]),
            insights=[str(x) for x in data.get("insights") or []],
            questions=[str(x) for x in data.get("questions") or []],
            source_label=str(data.get("source_label") or ""),
            created_at=float(data.get("created_at") or 0.0),
            updated_at=float(data.get("updated_at") or 0.0),
            merged_from=[str(x) for x in data.get("merged_from") or []],
        )


def _unique_preserve(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        text = str(raw).strip()
        if not text:
            continue
        key = _norm_text(text)
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


class TwinNotesStore:
    """JSON-file twin store. Process-local; house ``--workers 1`` invariant."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else _default_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for_parent(self, parent_asset_id: str) -> Path:
        return self.root / _safe_filename(parent_asset_id)

    def _read_parent_file(self, parent_asset_id: str) -> list[TwinDocument]:
        path = self._path_for_parent(parent_asset_id)
        if not path.is_file():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, dict):
            return []
        twins = raw.get("twins") or []
        out: list[TwinDocument] = []
        for row in twins:
            if not isinstance(row, dict):
                continue
            try:
                doc = TwinDocument.from_dict(row)
            except (KeyError, TypeError, ValueError):
                continue
            if doc.parent_asset_id != parent_asset_id:
                continue
            out.append(doc)
        return out

    def _write_parent_file(self, parent_asset_id: str, twins: Sequence[TwinDocument]) -> None:
        path = self._path_for_parent(parent_asset_id)
        payload = {
            "parent_asset_id": parent_asset_id,
            "twins": [t.to_dict() for t in twins],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        # Atomic replace within the parent directory.
        fd, tmp_name = tempfile.mkstemp(prefix=".twin-", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                with contextlib.suppress(OSError):
                    os.unlink(tmp_name)

    def record(
        self,
        parent_asset_id: str,
        *,
        insights: Sequence[str] | None = None,
        questions: Sequence[str] | None = None,
        source_label: str = "",
        twin_id: str | None = None,
        now: float | None = None,
    ) -> TwinDocument:
        parent = parent_asset_id.strip()
        if not parent:
            raise TwinNotesError("parent_asset_id must be non-empty")
        ts = float(now if now is not None else time.time())
        doc = TwinDocument(
            twin_id=twin_id or f"twin-{uuid.uuid4().hex[:16]}",
            parent_asset_id=parent,
            insights=_unique_preserve(insights or []),
            questions=_unique_preserve(questions or []),
            source_label=source_label.strip(),
            created_at=ts,
            updated_at=ts,
            merged_from=[],
        )
        existing = self._read_parent_file(parent)
        # Replace same twin_id if re-recording (idempotent upsert).
        kept = [t for t in existing if t.twin_id != doc.twin_id]
        kept.append(doc)
        self._write_parent_file(parent, kept)
        return doc

    def load(self, twin_id: str, *, parent_asset_id: str | None = None) -> TwinDocument:
        """Load a twin by id. Optional parent narrows the search."""
        tid = twin_id.strip()
        if not tid:
            raise TwinNotesError("twin_id must be non-empty")
        if parent_asset_id:
            for doc in self._read_parent_file(parent_asset_id.strip()):
                if doc.twin_id == tid:
                    return doc
            raise TwinNotFound(f"twin {tid!r} not found under parent {parent_asset_id!r}")
        # Linear scan of all twin files (bounded local store).
        for path in sorted(self.root.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for row in raw.get("twins") or []:
                if isinstance(row, dict) and row.get("twin_id") == tid:
                    return TwinDocument.from_dict(row)
        raise TwinNotFound(f"twin {tid!r} not found")

    def list_for_parent(self, parent_asset_id: str) -> list[TwinDocument]:
        parent = parent_asset_id.strip()
        if not parent:
            raise TwinNotesError("parent_asset_id must be non-empty")
        twins = self._read_parent_file(parent)
        twins.sort(key=lambda t: (t.created_at, t.twin_id))
        return twins

    def merge(
        self,
        twin_ids: Sequence[str],
        *,
        parent_asset_id: str | None = None,
        result_twin_id: str | None = None,
        source_label: str = "merged",
        now: float | None = None,
    ) -> TwinDocument:
        """Merge twins into one document for the same parent.

        Cross-parent merges raise :class:`TwinParentMismatch`.
        Double-merge is stable: re-merging the same set yields the same
        insight/question multiset (order-normalized unique).
        """
        if not twin_ids:
            raise TwinNotesError("twin_ids must be non-empty")
        docs: list[TwinDocument] = []
        for tid in twin_ids:
            docs.append(self.load(tid, parent_asset_id=parent_asset_id))
        parents = {d.parent_asset_id for d in docs}
        if len(parents) != 1:
            raise TwinParentMismatch(
                "cannot merge twins from different parents: " + ", ".join(sorted(parents))
            )
        parent = next(iter(parents))
        if parent_asset_id is not None and parent_asset_id.strip() != parent:
            raise TwinParentMismatch(
                f"parent_asset_id {parent_asset_id!r} does not match twin parent {parent!r}"
            )
        insights = _unique_preserve(i for d in docs for i in d.insights)
        questions = _unique_preserve(q for d in docs for q in d.questions)
        merged_from = _unique_preserve([d.twin_id for d in docs] + [m for d in docs for m in d.merged_from])
        ts = float(now if now is not None else time.time())
        # Deterministic result id for double-merge stability when caller omits id:
        # hash of sorted twin_ids so the same merge set upserts the same twin.
        if result_twin_id is None:
            key = "merge:" + "|".join(sorted({d.twin_id for d in docs}))
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
            result_twin_id = f"twin-m-{digest}"
        doc = TwinDocument(
            twin_id=result_twin_id,
            parent_asset_id=parent,
            insights=insights,
            questions=questions,
            source_label=source_label,
            created_at=ts,
            updated_at=ts,
            merged_from=merged_from,
        )
        existing = self._read_parent_file(parent)
        kept = [t for t in existing if t.twin_id != doc.twin_id]
        # Preserve earliest created_at on double-merge upsert.
        for prev in existing:
            if prev.twin_id == doc.twin_id:
                doc.created_at = prev.created_at or doc.created_at
                break
        kept.append(doc)
        self._write_parent_file(parent, kept)
        return doc


__all__ = [
    "TwinDocument",
    "TwinNotFound",
    "TwinNotesError",
    "TwinNotesStore",
    "TwinParentMismatch",
]
