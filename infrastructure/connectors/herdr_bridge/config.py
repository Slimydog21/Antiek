"""Private, fail-closed bridge configuration."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class WorkerSelector:
    agent: str
    cwd: str
    preferred_pane_id: str | None = None


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    source_path: Path
    antiek_base_url: str
    credential_id: str
    credential_secret: str = field(repr=False)
    bridge_instance_id: str
    journal_path: Path
    result_cli: str
    workers: dict[str, WorkerSelector]
    lease_seconds: int = 120
    poll_seconds: float = 5.0


def _private_regular(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
        raise PermissionError(f"{path} must be an owner-controlled regular file")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError(f"{path} must have mode 0600")


def _required_string(body: dict[str, object], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def load_config(path: str | Path) -> BridgeConfig:
    config_path = Path(path).expanduser()
    _private_regular(config_path)
    raw = json.loads(config_path.read_text())
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("bridge config must use schema_version 1")
    allowed = {
        "schema_version",
        "antiek_base_url",
        "credential_id",
        "credential_secret_file",
        "bridge_instance_id",
        "journal_path",
        "result_cli",
        "workers",
        "lease_seconds",
        "poll_seconds",
    }
    if not set(raw) <= allowed:
        raise ValueError("bridge config has unknown fields")
    base_url = _required_string(raw, "antiek_base_url").rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("antiek_base_url must be an HTTPS origin without userinfo")
    secret_path = Path(_required_string(raw, "credential_secret_file")).expanduser()
    _private_regular(secret_path)
    secret = secret_path.read_text().strip()
    if len(secret) < 8:
        raise ValueError("bridge credential secret is missing or too short")
    workers_raw = raw.get("workers")
    if not isinstance(workers_raw, dict) or not workers_raw:
        raise ValueError("workers must be a non-empty object")
    workers: dict[str, WorkerSelector] = {}
    for logical_worker_id, selector_raw in workers_raw.items():
        if not isinstance(logical_worker_id, str) or not logical_worker_id:
            raise ValueError("logical worker IDs must be non-empty strings")
        if not isinstance(selector_raw, dict):
            raise ValueError("worker selector must be an object")
        allowed = {"agent", "cwd", "preferred_pane_id"}
        if not set(selector_raw) <= allowed:
            raise ValueError("worker selector has unknown fields")
        preferred = selector_raw.get("preferred_pane_id")
        if preferred is not None and (not isinstance(preferred, str) or not preferred):
            raise ValueError("preferred_pane_id must be a non-empty string")
        workers[logical_worker_id] = WorkerSelector(
            agent=_required_string(selector_raw, "agent"),
            cwd=str(Path(_required_string(selector_raw, "cwd")).expanduser().resolve()),
            preferred_pane_id=preferred,
        )
    lease_seconds = raw.get("lease_seconds", 120)
    poll_seconds = raw.get("poll_seconds", 5.0)
    if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 300:
        raise ValueError("lease_seconds must be an integer from 1 through 300")
    if not isinstance(poll_seconds, int | float) or isinstance(poll_seconds, bool) or not 0.25 <= poll_seconds <= 300:
        raise ValueError("poll_seconds must be from 0.25 through 300")
    return BridgeConfig(
        source_path=config_path.resolve(),
        antiek_base_url=base_url,
        credential_id=_required_string(raw, "credential_id"),
        credential_secret=secret,
        bridge_instance_id=_required_string(raw, "bridge_instance_id"),
        journal_path=Path(_required_string(raw, "journal_path")).expanduser(),
        result_cli=_required_string(raw, "result_cli"),
        workers=workers,
        lease_seconds=lease_seconds,
        poll_seconds=float(poll_seconds),
    )
