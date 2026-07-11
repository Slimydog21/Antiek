"""Deep-research source pack builder (pure).

Turns readiness probe results + operator source selection into a human/LLM
reference pack for deep research prompts. Never opens the network. Never
claims a source is runnable today unless readiness says so honestly.

Contract (fail closed):
* Only known source names: arxiv, substack, web, operator_corpus
* A source listed as ``included`` only when status is ``ready`` or
  ``gated`` (gated = available but needs operator gate — still referenced)
* ``status=unavailable`` or ``stub`` never appear as ``ready_for_runner``
* ``runner_consumes_today`` must be a real bool from readiness; never invented
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from substrate.research_sources.readiness import SourceName, SourceReadiness

KnownSource = SourceName
PackStatus = Literal["included", "excluded", "unavailable"]

KNOWN_SOURCES: frozenset[str] = frozenset(
    {"arxiv", "substack", "web", "operator_corpus"}
)


class SourcePackError(ValueError):
    """Fail-closed validation for source packs."""


@dataclass(frozen=True)
class SourcePackEntry:
    source: str
    pack_status: PackStatus
    readiness_status: str
    adapter_importable: bool
    offline_probe_ok: bool
    runner_consumes_today: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "pack_status": self.pack_status,
            "readiness_status": self.readiness_status,
            "adapter_importable": self.adapter_importable,
            "offline_probe_ok": self.offline_probe_ok,
            "runner_consumes_today": self.runner_consumes_today,
            "note": self.note,
        }


@dataclass(frozen=True)
class SourcePack:
    selected: tuple[str, ...]
    entries: tuple[SourcePackEntry, ...]
    pack_text: str
    included_count: int
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": list(self.selected),
            "entries": [e.to_dict() for e in self.entries],
            "pack_text": self.pack_text,
            "included_count": self.included_count,
            "notes": list(self.notes),
            "authority": "advisory_preflight",
            "live_fetch_authorized": False,
        }


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise SourcePackError(f"{field} must be a boolean (got {type(value).__name__})")
    return value


def _normalize_selected(selected: Sequence[object]) -> tuple[str, ...]:
    if not isinstance(selected, (list, tuple)):
        raise SourcePackError("selected must be a list or tuple")
    if not selected:
        raise SourcePackError("selected must contain at least one source")
    out: list[str] = []
    seen: set[str] = set()
    for raw in selected:
        if not isinstance(raw, str) or not raw.strip():
            raise SourcePackError("every selected source must be a non-empty string")
        name = raw.strip().lower()
        if name not in KNOWN_SOURCES:
            raise SourcePackError(f"unknown source {name!r}; known={sorted(KNOWN_SOURCES)}")
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return tuple(out)


def _entry_from_readiness(
    source: str,
    readiness: SourceReadiness | Mapping[str, Any] | None,
    *,
    selected: bool,
) -> SourcePackEntry:
    if readiness is None:
        return SourcePackEntry(
            source=source,
            pack_status="unavailable",
            readiness_status="missing",
            adapter_importable=False,
            offline_probe_ok=False,
            runner_consumes_today=False,
            note="no readiness probe supplied for this source",
        )

    if isinstance(readiness, SourceReadiness):
        status = readiness.status
        adapter = readiness.adapter_importable
        offline = readiness.offline_probe_ok
        runner = readiness.runner_consumes_today
        note = readiness.note
    else:
        if not isinstance(readiness, Mapping):
            raise SourcePackError(f"readiness for {source} must be SourceReadiness or mapping")
        status = str(readiness.get("status") or "")
        if status not in {"ready", "gated", "stub", "unavailable"}:
            raise SourcePackError(
                f"readiness.status for {source} must be ready|gated|stub|unavailable"
            )
        adapter = _require_bool(readiness.get("adapter_importable"), field="adapter_importable")
        offline = _require_bool(readiness.get("offline_probe_ok"), field="offline_probe_ok")
        runner = _require_bool(
            readiness.get("runner_consumes_today"), field="runner_consumes_today"
        )
        note = readiness.get("note")
        if not isinstance(note, str):
            raise SourcePackError(f"readiness.note for {source} must be a string")

    if not selected:
        pack_status: PackStatus = "excluded"
    elif status in {"ready", "gated"}:
        pack_status = "included"
    else:
        pack_status = "unavailable"

    # Never claim runner_consumes_today when status is unavailable/stub.
    if status in {"unavailable", "stub"} and runner:
        raise SourcePackError(
            f"readiness for {source} claims runner_consumes_today with status={status}"
        )

    return SourcePackEntry(
        source=source,
        pack_status=pack_status,
        readiness_status=status if isinstance(readiness, SourceReadiness) else status,
        adapter_importable=adapter,
        offline_probe_ok=offline,
        runner_consumes_today=runner,
        note=note if isinstance(readiness, SourceReadiness) else note,
    )


def build_source_pack(
    selected: Sequence[object],
    readiness_by_source: Mapping[str, SourceReadiness | Mapping[str, Any]] | None = None,
) -> SourcePack:
    """Build an advisory deep-research source pack from selection + readiness."""
    sel = _normalize_selected(selected)
    readiness_by_source = readiness_by_source or {}
    # Reject unknown keys in readiness map
    for key in readiness_by_source:
        if str(key).strip().lower() not in KNOWN_SOURCES:
            raise SourcePackError(f"unknown readiness key {key!r}")

    entries: list[SourcePackEntry] = []
    notes: list[str] = [
        "live_fetch_authorized=false — pack is reference metadata only",
        "authority=advisory_preflight",
    ]
    for src in sorted(KNOWN_SOURCES):
        rd = readiness_by_source.get(src)
        entry = _entry_from_readiness(src, rd, selected=src in sel)
        entries.append(entry)
        if src in sel and entry.pack_status == "unavailable":
            notes.append(f"{src}: selected but unavailable ({entry.readiness_status})")
        if entry.pack_status == "included" and not entry.offline_probe_ok:
            notes.append(f"{src}: included without offline_probe_ok — do not overclaim")

    included = [e for e in entries if e.pack_status == "included"]
    lines = [
        "# Deep research source pack",
        f"selected: {', '.join(sel)}",
        f"included: {len(included)}",
        "",
    ]
    for e in entries:
        if e.source not in sel and e.pack_status == "excluded":
            continue
        lines.append(
            f"- {e.source}: pack={e.pack_status} readiness={e.readiness_status} "
            f"adapter={e.adapter_importable} offline_probe={e.offline_probe_ok} "
            f"runner_today={e.runner_consumes_today}"
        )
        if e.note:
            lines.append(f"  note: {e.note}")
    pack_text = "\n".join(lines) + "\n"
    if not pack_text.strip():
        raise SourcePackError("pack_text must be non-empty")

    return SourcePack(
        selected=sel,
        entries=tuple(entries),
        pack_text=pack_text,
        included_count=len(included),
        notes=tuple(notes),
    )


__all__ = [
    "KNOWN_SOURCES",
    "SourcePack",
    "SourcePackEntry",
    "SourcePackError",
    "build_source_pack",
]
