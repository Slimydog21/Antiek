"""Compose floating deep-research sessions into reading workspace windows.

Pure adapter between:

* ``substrate.floating_session`` (Python session substrate)
* reading ``windowsStore`` contract (TS: kind/mode/payload/title/id)

Does **not** reimplement z-order, MAX_WINDOWS, or spawn/merge. Maps session
identity → window open descriptor; maps floating⇄full to the same mode names
used by ``windowsStore`` (expand/restore).

Payload shape (handoff to TS ``open(kind, payload, opts)``)::

    kind: "deep_research_session"
    payload: {
      session_id, spawn_id, investigation_id, parent_asset_id,
      model_id?, selection_text, region_id?, goal?, status
    }
    opts: { id: "wdr-<session_id>", title, mode: "floating"|"full" }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from .session import FloatingSession, SessionStore, ViewMode, get_session, set_view_mode

# Matches apps/reading WindowMode
WindowMode = Literal["floating", "full"]

# Window-native kind for openWindow WINDOW_PAGES registration (TS side).
DEEP_RESEARCH_WINDOW_KIND = "deep_research_session"

# windowsStore.MAX_WINDOWS
DEFAULT_MAX_WINDOWS = 8


@dataclass(frozen=True)
class WindowOpenDescriptor:
    """Descriptor ready for windowsStore.open(kind, payload, opts)."""

    kind: str
    mode: WindowMode
    title: str
    payload: dict[str, Any]
    window_id: str
    session_id: str
    parent_asset_id: str
    spawn_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "mode": self.mode,
            "title": self.title,
            "payload": dict(self.payload),
            "id": self.window_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "spawn_id": self.spawn_id,
        }

    def open_options(self) -> dict[str, Any]:
        """opts fragment for windowsStore.open(..., opts)."""
        return {
            "id": self.window_id,
            "title": self.title,
            "mode": self.mode,
        }


def window_id_for_session(session_id: str) -> str:
    """Stable window id so reopening the same session focuses, not duplicates."""
    sid = (session_id or "").strip()
    if not sid:
        raise ValueError("session_id is required")
    return f"wdr_{sid}"


def map_session_mode_to_window_mode(view_mode: ViewMode) -> WindowMode:
    if view_mode not in ("floating", "full"):
        raise ValueError(f"invalid session view_mode: {view_mode!r}")
    return view_mode


def map_window_mode_to_session_mode(mode: WindowMode) -> ViewMode:
    if mode not in ("floating", "full"):
        raise ValueError(f"invalid window mode: {mode!r}")
    return mode


def session_to_window_descriptor(
    session: FloatingSession,
    *,
    title: str | None = None,
) -> WindowOpenDescriptor:
    """Map a floating session to a windowsStore-compatible open descriptor."""
    mode = map_session_mode_to_window_mode(session.view_mode)
    sel = session.selection_text.strip()
    short = sel if len(sel) <= 48 else sel[:45] + "..."
    resolved_title = title or f"Deep research: {short or session.session_id}"
    payload: dict[str, Any] = {
        "session_id": session.session_id,
        "spawn_id": session.spawn_id,
        "investigation_id": session.investigation_id,
        "parent_asset_id": session.parent_asset_id,
        "selection_text": session.selection_text,
        "status": session.status,
        "view_format": "html",
    }
    if session.model_id:
        payload["model_id"] = session.model_id
    if session.region_id:
        payload["region_id"] = session.region_id
    if session.goal:
        payload["goal"] = session.goal
    return WindowOpenDescriptor(
        kind=DEEP_RESEARCH_WINDOW_KIND,
        mode=mode,
        title=resolved_title,
        payload=payload,
        window_id=window_id_for_session(session.session_id),
        session_id=session.session_id,
        parent_asset_id=session.parent_asset_id,
        spawn_id=session.spawn_id,
    )


@runtime_checkable
class WindowStore(Protocol):
    """Minimal protocol matching windowsStore open/expand/restore/list surface."""

    def open(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        opts: dict[str, Any] | None = None,
    ) -> str: ...
    def expand(self, window_id: str) -> None: ...
    def restore(self, window_id: str) -> None: ...
    def toggle_mode(self, window_id: str) -> str: ...
    def get(self, window_id: str) -> dict[str, Any] | None: ...
    def list_for_parent(self, parent_asset_id: str) -> list[dict[str, Any]]: ...


@dataclass
class InMemoryWindowStore:
    """Injectable store for tests — mirrors MAX_WINDOWS + mode semantics only."""

    max_windows: int = DEFAULT_MAX_WINDOWS
    _windows: dict[str, dict[str, Any]] = field(default_factory=dict)
    _order: list[str] = field(default_factory=list)

    def open(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        opts: dict[str, Any] | None = None,
    ) -> str:
        opts = opts or {}
        payload = dict(payload or {})
        wid = str(opts.get("id") or f"win_{len(self._windows) + 1}")
        mode = opts.get("mode") or "floating"
        if mode not in ("floating", "full"):
            raise ValueError(f"invalid mode: {mode!r}")
        if wid in self._windows:
            # Focus existing — same as cap/focus semantics at store layer
            if wid in self._order:
                self._order.remove(wid)
            self._order.append(wid)
            return wid
        if len(self._windows) >= self.max_windows:
            # Focus oldest (matches windowsStore cap behavior)
            oldest = self._order[0] if self._order else next(iter(self._windows))
            if oldest in self._order:
                self._order.remove(oldest)
            self._order.append(oldest)
            return oldest
        self._windows[wid] = {
            "id": wid,
            "kind": kind,
            "mode": mode,
            "title": opts.get("title") or kind,
            "payload": payload,
        }
        self._order.append(wid)
        return wid

    def expand(self, window_id: str) -> None:
        w = self._windows.get(window_id)
        if w is None:
            raise KeyError(window_id)
        w["mode"] = "full"

    def restore(self, window_id: str) -> None:
        w = self._windows.get(window_id)
        if w is None:
            raise KeyError(window_id)
        w["mode"] = "floating"

    def toggle_mode(self, window_id: str) -> str:
        w = self._windows.get(window_id)
        if w is None:
            raise KeyError(window_id)
        w["mode"] = "full" if w["mode"] == "floating" else "floating"
        return str(w["mode"])

    def get(self, window_id: str) -> dict[str, Any] | None:
        row = self._windows.get(window_id)
        return dict(row) if row is not None else None

    def list_for_parent(self, parent_asset_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for wid in self._order:
            w = self._windows[wid]
            if w.get("payload", {}).get("parent_asset_id") == parent_asset_id:
                out.append(dict(w))
        return out


def open_session_as_window(
    session: FloatingSession,
    *,
    window_store: WindowStore,
    title: str | None = None,
) -> WindowOpenDescriptor:
    """Open (or focus) a workspace window for a deep-research session."""
    desc = session_to_window_descriptor(session, title=title)
    opened_id = window_store.open(
        desc.kind,
        desc.payload,
        desc.open_options(),
    )
    # If cap returned a different id, still return the intended descriptor
    # but note the opened id in a copy for callers that need it.
    if opened_id != desc.window_id:
        return WindowOpenDescriptor(
            kind=desc.kind,
            mode=desc.mode,
            title=desc.title,
            payload=desc.payload,
            window_id=opened_id,
            session_id=desc.session_id,
            parent_asset_id=desc.parent_asset_id,
            spawn_id=desc.spawn_id,
        )
    return desc


def sync_session_window_mode(
    session_id: str,
    mode: WindowMode,
    *,
    session_store: SessionStore,
    window_store: WindowStore,
) -> FloatingSession:
    """Set floating⇄full on both session substrate and window store."""
    session_mode = map_window_mode_to_session_mode(mode)
    session = set_view_mode(session_id, session_mode, session_store=session_store)
    wid = window_id_for_session(session_id)
    existing = window_store.get(wid)
    if existing is not None:
        if mode == "full":
            window_store.expand(wid)
        else:
            window_store.restore(wid)
    return session


def list_session_window_descriptors(
    parent_asset_id: str,
    *,
    session_store: SessionStore,
) -> list[WindowOpenDescriptor]:
    """Build window descriptors for all sessions on a parent asset (no open)."""
    from .session import list_sessions_for_asset

    sessions = list_sessions_for_asset(parent_asset_id, session_store=session_store)
    return [session_to_window_descriptor(s) for s in sessions]


def open_sessions_as_windows(
    parent_asset_id: str,
    *,
    session_store: SessionStore,
    window_store: WindowStore,
    session_ids: list[str] | tuple[str, ...] | None = None,
) -> list[WindowOpenDescriptor]:
    """Open distinct windows for one or more sessions on a parent asset."""
    from .session import list_sessions_for_asset

    if session_ids is None:
        sessions = list_sessions_for_asset(parent_asset_id, session_store=session_store)
    else:
        sessions = []
        for sid in session_ids:
            s = get_session(sid, session_store=session_store)
            if s is None:
                raise KeyError(f"unknown session_id: {sid}")
            if s.parent_asset_id != parent_asset_id:
                raise ValueError(
                    f"session {sid} parent is {s.parent_asset_id}, not {parent_asset_id}"
                )
            sessions.append(s)
    return [open_session_as_window(s, window_store=window_store) for s in sessions]
