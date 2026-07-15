"""Check the nightly-backup freshness marker (R1 alerting half, PR #714 review).

``infrastructure/ansible/templates/backup.sh.j2`` writes a JSON marker to
``<state dir>/backup_freshness.json`` only after a backup EXPORTed, passed the
IMPORT-verify gate, and uploaded. This tool answers ONE question — did a
verified backup land recently? — with an exit code:

  * ``0``  — marker exists, parses, and its ``completed_at`` is younger than
    the threshold (default 26h: nightly cadence + generous slack).
  * ``1``  — anything else: marker missing (no successful backup ever recorded
    on this host — treated as stale, never as "unknown"), unreadable,
    malformed, timestamp in the future (clock skew is a finding, not
    freshness), or older than the threshold. One-line reason on stdout.
  * ``2``  — usage error (argparse).

No network, no DB access, no writes — it reads one small local file.

Marker resolution order: ``--marker`` flag, ``$ANTIEK_BACKUP_MARKER``,
``$ANTIEK_STATE_DIR/backup_freshness.json``, ``~/.antiek/backup_freshness.json``
(the deployed state dir is the ``antiek`` user's ``~/.antiek``).

Operator wiring (operator-gated — this module creates NO services/timers):
the intended prod hookup is a systemd timer on the backup host running e.g.
``/opt/antiek/.venv/bin/python3 /opt/antiek/tools/backup_freshness.py`` once
or twice a day, with ``OnFailure=`` (or the cron MAILTO / journal alerting
already in place for the backup itself) carrying the alert. Until that timer
is provisioned, ad-hoc runs over SSH are the check.

``--json`` emits the full verdict as one JSON object for future wiring
(dashboards, health endpoints) without reparsing the one-line prose.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_MAX_AGE_HOURS = 26.0
MARKER_BASENAME = "backup_freshness.json"
_CORE_TABLES = frozenset({"documents", "chunks", "nodes"})

_MARKER_ENV = "ANTIEK_BACKUP_MARKER"
_STATE_DIR_ENV = "ANTIEK_STATE_DIR"


@dataclass(frozen=True)
class FreshnessVerdict:
    """The complete answer: freshness boolean + the evidence behind it.

    ``age_hours`` / ``completed_at`` / ``counts`` / ``script_version`` are
    ``None`` exactly when the marker was missing or unusable — the ``reason``
    string always says which.
    """

    fresh: bool
    reason: str
    marker_path: str
    max_age_hours: float
    age_hours: float | None
    completed_at: str | None
    counts: Mapping[str, int] | None
    script_version: str | None

    def to_json(self) -> str:
        return json.dumps(
            {
                "fresh": self.fresh,
                "reason": self.reason,
                "marker_path": self.marker_path,
                "max_age_hours": self.max_age_hours,
                "age_hours": self.age_hours,
                "completed_at": self.completed_at,
                "counts": dict(self.counts) if self.counts is not None else None,
                "script_version": self.script_version,
            },
            indent=2,
        )


def resolve_marker_path(cli_value: str | None) -> Path:
    """Resolve the marker location: flag > env marker > env state dir > ~/.antiek."""
    if cli_value:
        return Path(cli_value)
    env_marker = os.environ.get(_MARKER_ENV)
    if env_marker:
        return Path(env_marker)
    state_dir = os.environ.get(_STATE_DIR_ENV)
    if state_dir:
        return Path(state_dir) / MARKER_BASENAME
    return Path.home() / ".antiek" / MARKER_BASENAME


def _stale(
    reason: str,
    marker_path: Path,
    max_age_hours: float,
    *,
    age_hours: float | None = None,
    completed_at: str | None = None,
    counts: Mapping[str, int] | None = None,
    script_version: str | None = None,
) -> FreshnessVerdict:
    return FreshnessVerdict(
        fresh=False,
        reason=reason,
        marker_path=str(marker_path),
        max_age_hours=max_age_hours,
        age_hours=age_hours,
        completed_at=completed_at,
        counts=counts,
        script_version=script_version,
    )


def _parse_counts(raw: object) -> Mapping[str, int] | None:
    """Validate the verified backup's exact non-negative core-count manifest."""
    if not isinstance(raw, dict):
        return None
    if set(raw) != _CORE_TABLES:
        return None
    out: dict[str, int] = {}
    for key, value in raw.items():
        if (
            not isinstance(key, str)
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            return None
        out[key] = value
    return out


def evaluate(
    marker_path: Path,
    max_age_hours: float,
    now: datetime | None = None,
) -> FreshnessVerdict:
    """Read the marker and decide freshness. Pure function of file + clock."""
    reference = now if now is not None else datetime.now(UTC)
    try:
        raw_text = marker_path.read_text()
    except FileNotFoundError:
        return _stale(
            f"STALE: no marker at {marker_path} - no successful backup recorded on this host",
            marker_path,
            max_age_hours,
        )
    except OSError as exc:
        return _stale(
            f"STALE: marker at {marker_path} unreadable ({exc})",
            marker_path,
            max_age_hours,
        )

    try:
        payload = json.loads(raw_text)
    except ValueError as exc:
        return _stale(
            f"STALE: marker at {marker_path} is not valid JSON ({exc})",
            marker_path,
            max_age_hours,
        )
    if not isinstance(payload, dict):
        return _stale(
            f"STALE: marker at {marker_path} is not a JSON object",
            marker_path,
            max_age_hours,
        )

    completed_at = payload.get("completed_at")
    counts = _parse_counts(payload.get("counts"))
    script_version_raw = payload.get("script_version")
    script_version = script_version_raw if isinstance(script_version_raw, str) else None
    archive = payload.get("archive")

    if counts is None:
        return _stale(
            f"STALE: marker at {marker_path} has no valid core-table counts manifest",
            marker_path,
            max_age_hours,
            script_version=script_version,
        )
    if script_version is None or not script_version.startswith("backup.sh/"):
        return _stale(
            f"STALE: marker at {marker_path} has no valid backup script version",
            marker_path,
            max_age_hours,
            counts=counts,
            script_version=script_version,
        )
    if (
        not isinstance(archive, str)
        or not archive.startswith("antiek-")
        or not archive.endswith(".tar.gz")
        or "/" in archive
        or "\\" in archive
    ):
        return _stale(
            f"STALE: marker at {marker_path} has no valid archive identity",
            marker_path,
            max_age_hours,
            counts=counts,
            script_version=script_version,
        )

    if not isinstance(completed_at, str):
        return _stale(
            f"STALE: marker at {marker_path} has no completed_at timestamp",
            marker_path,
            max_age_hours,
            counts=counts,
            script_version=script_version,
        )
    try:
        completed = datetime.fromisoformat(completed_at)
    except ValueError:
        return _stale(
            f"STALE: marker completed_at {completed_at!r} is not an ISO timestamp",
            marker_path,
            max_age_hours,
            completed_at=completed_at,
            counts=counts,
            script_version=script_version,
        )
    if completed.tzinfo is None:
        return _stale(
            f"STALE: marker completed_at {completed_at!r} has no timezone",
            marker_path,
            max_age_hours,
            completed_at=completed_at,
            counts=counts,
            script_version=script_version,
        )

    age_hours = (reference - completed).total_seconds() / 3600.0
    if age_hours < 0:
        return _stale(
            f"STALE: marker completed_at {completed_at} is in the future "
            f"({-age_hours:.1f}h ahead) - clock skew or a forged marker, not freshness",
            marker_path,
            max_age_hours,
            age_hours=age_hours,
            completed_at=completed_at,
            counts=counts,
            script_version=script_version,
        )
    if age_hours > max_age_hours:
        return _stale(
            f"STALE: last verified backup {completed_at} is {age_hours:.1f}h old "
            f"(threshold {max_age_hours:.1f}h)",
            marker_path,
            max_age_hours,
            age_hours=age_hours,
            completed_at=completed_at,
            counts=counts,
            script_version=script_version,
        )

    return FreshnessVerdict(
        fresh=True,
        reason=(
            f"FRESH: last verified backup {completed_at} is {age_hours:.1f}h old "
            f"(threshold {max_age_hours:.1f}h)"
        ),
        marker_path=str(marker_path),
        max_age_hours=max_age_hours,
        age_hours=age_hours,
        completed_at=completed_at,
        counts=counts,
        script_version=script_version,
    )


def _threshold_hours(value: str) -> float:
    """Parse + validate ``--max-age-hours``, fail-closed at the parser.

    ``float`` alone accepts ``nan`` (every comparison against NaN is False, so
    ``age_hours > NaN`` never trips — the threshold silently disables and any
    stale marker reads FRESH) and ``inf``/negatives (a threshold that can never
    pass or never fail is a misconfiguration, not a policy). All are rejected
    here with argparse's non-zero exit + one-line reason.
    """
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError(
            f"--max-age-hours must be a finite non-negative number of hours, got {value!r} "
            "(nan/inf/negative would silently disable or invert the freshness gate)"
        )
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exit 0 iff the nightly-backup freshness marker is recent."
    )
    parser.add_argument(
        "--marker",
        help=(
            f"Path to the marker file (default: ${_MARKER_ENV}, then "
            f"${_STATE_DIR_ENV}/{MARKER_BASENAME}, then ~/.antiek/{MARKER_BASENAME})"
        ),
    )
    parser.add_argument(
        "--max-age-hours",
        type=_threshold_hours,
        default=DEFAULT_MAX_AGE_HOURS,
        help=f"Freshness threshold in hours, finite and >= 0 (default {DEFAULT_MAX_AGE_HOURS})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full verdict as JSON instead of the one-line reason",
    )
    args = parser.parse_args(argv)

    verdict = evaluate(resolve_marker_path(args.marker), args.max_age_hours)
    print(verdict.to_json() if args.json else verdict.reason)
    return 0 if verdict.fresh else 1


if __name__ == "__main__":
    sys.exit(main())
