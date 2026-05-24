"""HarnessSnapshot -- captured externally-visible substrate surface."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore[import-not-found]
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found]

from substrate.hooks import HookRegistry


@dataclass(frozen=True)
class HarnessSnapshot:
    tag: str
    captured_at: str
    substrate_version: str
    hook_seams: dict[str, str] = field(default_factory=dict)
    hooks: list[dict[str, Any]] = field(default_factory=list)
    model_config: dict[str, Any] = field(default_factory=dict)
    tools: list[dict[str, str]] = field(default_factory=list)
    system_prompt_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HarnessSnapshot":
        return cls(**data)


def _read_substrate_version(project_root: Path) -> str:
    pp = project_root / "pyproject.toml"
    if not pp.exists():
        return "unknown"
    try:
        data = tomllib.loads(pp.read_text())
        return str(data.get("project", {}).get("version", "unknown"))
    except Exception:
        return "unknown"


def _digest(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def capture_snapshot(
    *,
    tag: str,
    registry: HookRegistry | None = None,
    model_config: dict[str, Any] | None = None,
    tools: list[dict[str, str]] | None = None,
    system_prompt: str | None = None,
    project_root: Path | None = None,
) -> HarnessSnapshot:
    return HarnessSnapshot(
        tag=tag,
        captured_at=datetime.now(timezone.utc).isoformat(),
        substrate_version=_read_substrate_version(project_root or Path.cwd()),
        hook_seams=dict(registry.seams()) if registry else {},
        hooks=registry.list_hooks() if registry else [],
        model_config=dict(model_config) if model_config else {},
        tools=[dict(t) for t in (tools or [])],
        system_prompt_digest=_digest(system_prompt),
    )


def _snapshots_dir(project_root: Path) -> Path:
    return project_root / ".antiek" / "harness" / "snapshots"


def _sanitize_tag(tag: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in tag)
    while ".." in safe:
        safe = safe.replace("..", "_")
    if not any(c.isalnum() for c in safe):
        raise ValueError(
            f"snapshot tag {tag!r} has no alphanumeric characters after sanitization"
        )
    if safe.startswith("."):
        safe = "_" + safe.lstrip(".")
    return safe


def save_snapshot(snapshot: HarnessSnapshot, project_root: Path) -> Path:
    d = _snapshots_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    safe = _sanitize_tag(snapshot.tag)
    out = d / f"{safe}.json"
    out.write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
    return out


def load_snapshot(tag: str, project_root: Path) -> HarnessSnapshot:
    try:
        safe = _sanitize_tag(tag)
    except ValueError as exc:
        raise FileNotFoundError(str(exc)) from exc
    p = _snapshots_dir(project_root) / f"{safe}.json"
    if not p.exists():
        raise FileNotFoundError(f"no snapshot at {p}")
    return HarnessSnapshot.from_dict(json.loads(p.read_text()))


def list_snapshots(project_root: Path) -> list[HarnessSnapshot]:
    d = _snapshots_dir(project_root)
    if not d.is_dir():
        return []
    snaps = [HarnessSnapshot.from_dict(json.loads(p.read_text())) for p in d.glob("*.json")]
    return sorted(snaps, key=lambda s: s.captured_at)
