"""PhaseLog — code-level assertions over the 9-phase autonomous-research
protocol.

State lives in one JSON file per investigation at
``$ANTIEK_RESEARCH_PHASE_LOG_DIR/{investigation_id}.json`` (default:
``~/.antiek/research_phase_logs/``). Every enter/exit/verify writes the
JSON atomically AND emits a typed PHASE_* event into the trajectory.
JSON is the live state-machine truth; the events stream is the
queryable trajectory.

Public API:

    log = PhaseLog.open(investigation_id, topic="...")
    log.enter(8, note="...")
    log.exit(8, outputs_paths=["path/to/skill.md"])
    log.verify(8, evidence="<query result or proof>")
    log.assert_phase_completed(8)   # raises PhaseAssertionError
    log.assert_ready_for_completion()
    log.snapshot()                   # for archival

The shadow DuckDB writer in upstream phase_log.py is deferred — Antiek's
``substrate/init_db.py`` hasn't migrated the ``phase_log`` table yet.
The typed event mirror is the substitute trajectory the audit tools
read until that lands.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Iterable
from datetime import UTC, datetime

try:
    from ...constants import (
        ANTIEK_PARAM_VERSION,
        AUTONOMOUS_RESEARCH_PHASES,
        AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import (  # type: ignore[no-redef]
        ANTIEK_PARAM_VERSION,
        AUTONOMOUS_RESEARCH_PHASES,
        AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION,
    )

from .events import emit_phase_enter, emit_phase_exit, emit_phase_verify
from .types import PhaseAssertionError


def default_log_dir() -> str:
    return os.environ.get(
        "ANTIEK_RESEARCH_PHASE_LOG_DIR",
        os.path.join(
            os.environ.get("ANTIEK_HOME", os.path.expanduser("~/.antiek")),
            "research_phase_logs",
        ),
    )


def _utc_iso_now() -> str:
    """ISO-8601 timestamp with the ``Z`` suffix — matches the substrate
    event-envelope timestamp format (substrate/event_log/events.py)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def hash_paths(paths: Iterable[str]) -> str:
    """SHA-256 of the concatenated file contents in sorted-path order.

    Missing files are encoded as ``<path>:MISSING\\0`` so a phase that
    referenced a deleted file produces a different hash than one that
    referenced an empty file at the same path."""
    h = hashlib.sha256()
    for p in sorted(paths):
        try:
            with open(p, "rb") as f:
                h.update(p.encode())
                h.update(b"\0")
                h.update(f.read())
                h.update(b"\0")
        except OSError:
            h.update((p + ":MISSING\0").encode())
    return h.hexdigest()


def _safe_emit(fn, **kwargs) -> None:
    """Best-effort trajectory mirror. Errors are swallowed — telemetry
    must never break a real synthesis. Mirrors the ``_phase_log_safe``
    pattern in upstream orchestrate.py."""
    try:
        fn(**kwargs)
    except Exception as e:  # pragma: no cover — diagnostic only
        print(
            f"phase_log → events mirror failed (non-fatal): {e!r}",
            file=sys.stderr,
        )


class PhaseLog:
    """State machine over the 9-phase protocol for one investigation.

    Construction always goes through ``PhaseLog.open`` so the JSON file
    is created on first use and re-loaded on subsequent opens — callers
    never instantiate ``PhaseLog`` directly with raw data.
    """

    def __init__(self, path: str, data: dict):
        self.path = path
        self.data = data

    @classmethod
    def open(
        cls,
        investigation_id: str,
        *,
        topic: str = "",
        log_dir: str | None = None,
    ) -> PhaseLog:
        d = log_dir or default_log_dir()
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{investigation_id}.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
        else:
            data = {
                "investigation_id": investigation_id,
                "topic": topic,
                "created_at": _utc_iso_now(),
                "param_version": ANTIEK_PARAM_VERSION,
                "phases": {},
            }
        return cls(path, data)

    @property
    def investigation_id(self) -> str:
        return self.data["investigation_id"]

    def _save(self) -> None:
        """Atomic write — temp file + os.replace so a crash mid-write
        leaves the prior valid snapshot, not a half-written file."""
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)

    def _phase_key(self, phase_id: int) -> str:
        if phase_id not in AUTONOMOUS_RESEARCH_PHASES:
            raise ValueError(
                f"Phase {phase_id} is not in AUTONOMOUS_RESEARCH_PHASES "
                f"({AUTONOMOUS_RESEARCH_PHASES})"
            )
        return str(phase_id)

    def enter(
        self,
        phase_id: int,
        note: str | None = None,
        *,
        metadata_json: str | None = None,
    ) -> None:
        """Mark a phase entered.

        Re-entering an already-entered phase OVERWRITES ``entered_at``
        (a re-run is a valid trajectory; the prior exit / verify
        records are preserved so the audit tool can see both attempts)."""
        k = self._phase_key(phase_id)
        existing = self.data["phases"].get(k, {})
        existing["entered_at"] = _utc_iso_now()
        if "verified" not in existing:
            existing["verified"] = False
        if note is not None:
            existing["enter_note"] = note
        if metadata_json is not None:
            existing["enter_metadata_json"] = metadata_json
        self.data["phases"][k] = existing
        self._save()
        _safe_emit(
            emit_phase_enter,
            investigation_id=self.investigation_id,
            phase=phase_id,
            entered_at=existing["entered_at"],
            note=note,
            metadata_json=metadata_json,
        )

    def exit(
        self,
        phase_id: int,
        *,
        outputs_hash: str | None = None,
        outputs_paths: Iterable[str] | None = None,
    ) -> None:
        """Mark a phase exited. If ``outputs_paths`` is provided the
        hash is computed from sorted-path file contents (see
        ``hash_paths``); ``outputs_hash`` overrides when both are
        passed (matches upstream precedence)."""
        k = self._phase_key(phase_id)
        rec = self.data["phases"].setdefault(k, {})
        rec["exited_at"] = _utc_iso_now()
        if outputs_hash:
            rec["outputs_hash"] = outputs_hash
        elif outputs_paths:
            paths_list = list(outputs_paths)
            rec["outputs_hash"] = hash_paths(paths_list)
            rec["outputs_paths"] = paths_list
        self._save()
        _safe_emit(
            emit_phase_exit,
            investigation_id=self.investigation_id,
            phase=phase_id,
            exited_at=rec["exited_at"],
            outputs_hash=rec.get("outputs_hash"),
        )

    def verify(self, phase_id: int, *, evidence: str) -> None:
        """Mark a phase verified. ``evidence`` is freeform — path,
        query result, SHA-256, or 1-line proof — stored verbatim so a
        reviewer can audit *why* verify was called."""
        if not evidence:
            raise ValueError(
                "evidence is required: verify() without a proof string "
                "defeats the purpose (Phase 8 compounding gate)."
            )
        k = self._phase_key(phase_id)
        rec = self.data["phases"].setdefault(k, {})
        rec["verified"] = True
        rec["verified_at"] = _utc_iso_now()
        rec["verification_evidence"] = evidence
        self._save()
        _safe_emit(
            emit_phase_verify,
            investigation_id=self.investigation_id,
            phase=phase_id,
            verified_at=rec["verified_at"],
            verification_evidence=evidence,
        )

    def is_verified(self, phase_id: int) -> bool:
        k = self._phase_key(phase_id)
        return bool(self.data["phases"].get(k, {}).get("verified"))

    def assert_phase_completed(self, phase_id: int) -> None:
        """Raise ``PhaseAssertionError`` if the phase did not pass
        verification. Used by Phase 9 to gate completion."""
        k = self._phase_key(phase_id)
        rec = self.data["phases"].get(k)
        if not rec:
            raise PhaseAssertionError(
                f"Phase {phase_id} was never entered for investigation "
                f"{self.investigation_id!r}. Skipping phases is a "
                f"protocol violation."
            )
        if not rec.get("exited_at"):
            raise PhaseAssertionError(
                f"Phase {phase_id} was entered but never exited for "
                f"investigation {self.investigation_id!r}."
            )
        if not rec.get("verified"):
            raise PhaseAssertionError(
                f"Phase {phase_id} exited but verify() was never called. "
                f"Phase 8 in particular MUST be verified — that is what "
                f"makes the system compound. Did you actually merge "
                f"findings into the knowledge graph?"
            )

    def assert_ready_for_completion(self) -> None:
        """Phase 9 gate. Raises on any required phase that did not verify."""
        missing = []
        for phase_id in AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION:
            try:
                self.assert_phase_completed(phase_id)
            except PhaseAssertionError as e:
                missing.append(str(e))
        if missing:
            raise PhaseAssertionError(
                "Investigation is not ready for completion. Required "
                f"phases failed: "
                f"{AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION}\n\n"
                + "\n".join(f"  - {m}" for m in missing)
            )

    def snapshot(self) -> dict:
        """Deep copy of the JSON state — safe to hand to archive code
        without worrying about subsequent mutation."""
        return json.loads(json.dumps(self.data))
