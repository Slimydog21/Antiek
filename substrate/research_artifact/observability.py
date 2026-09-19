"""Bounded, redacted counters for ResearchArtifact rollout evidence."""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
from pathlib import Path

from .storage import UnsafeArtifactState, _atomic_write, _private_dir, _read_regular

_ALLOWED: dict[str, dict[str, frozenset[str] | None]] = {
    "artifact_resolution_total": {"mode": frozenset({"scoped", "legacy_shadow", "denied"})},
    "artifact_migration_total": {
        "phase": frozenset(
            {"locked", "published_verified", "receipt_prepared", "tombstoned", "receipt_written"}
        ),
        "verdict": frozenset({"ok", "refused", "quarantined"}),
    },
    "artifact_owner_mismatch_total": {"surface": frozenset({"api", "storage", "event"})},
    "artifact_quarantine_total": {"reason": None},
    "artifact_event_pending_total": {"account_digest": None},
}
_SAFE_VALUE = re.compile(r"^[a-z0-9_:-]{1,64}$")


def record_counter(root: Path, name: str, **labels: str) -> None:
    """Increment a durable counter while rejecting unbounded/private label values."""
    contract = _ALLOWED.get(name)
    if contract is None or set(labels) != set(contract):
        raise ValueError("unknown ResearchArtifact metric contract")
    for key, value in labels.items():
        allowed = contract[key]
        if not _SAFE_VALUE.fullmatch(value) or (allowed is not None and value not in allowed):
            raise ValueError("unsafe ResearchArtifact metric label")
    metrics_dir = root / ".migration"
    _private_dir(root, metrics_dir)
    lock_path = metrics_dir / "metrics.lock"
    snapshot_path = metrics_dir / "metrics.json"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock_path, flags, 0o600)
    with os.fdopen(fd, "a+b") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise UnsafeArtifactState("artifact metrics lock is unsafe")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        snapshot = (
            json.loads(_read_regular(snapshot_path).decode("utf-8"))
            if snapshot_path.exists()
            else {}
        )
        label_key = ",".join(f"{key}={labels[key]}" for key in sorted(labels))
        counter_key = f"{name}{{{label_key}}}"
        snapshot[counter_key] = int(snapshot.get(counter_key, 0)) + 1
        _atomic_write(
            root,
            snapshot_path,
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode(),
        )
