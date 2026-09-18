"""Stranded dispatch.call recovery closes open role requests."""

from __future__ import annotations

import json
import time
from pathlib import Path

from interfaces.research.api.stranded_dispatch_recovery import (
    find_stranded_investigations,
    recover_stranded_investigation,
)
from substrate.event_log.events import iter_physical_events


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _evt(
    inv: str,
    action: str,
    *,
    n: int = 0,
    emitted_at: str | None = None,
    **payload,
) -> dict:
    return {
        "event_id": f"evt-{action}-{n}",
        "investigation_id": inv,
        "action_type": action,
        "role": "test",
        "payload": {"action_type": action, **payload},
        "emitted_at": emitted_at or "2020-01-01T00:00:00.000000Z",
        "schema_version": 40,
        "param_version": "0.2.0",
    }


def test_find_stranded_after_error_dispatch(tmp_path: Path) -> None:
    events = tmp_path / "events"
    inv = "inv-strand-a"
    old = "2020-01-01T00:00:00.000000Z"
    _write_jsonl(
        events / f"{inv}.jsonl",
        [
            _evt(inv, "phase.enter", n=1, emitted_at=old),
            _evt(inv, "decompose.requested", n=2, emitted_at=old),
            _evt(
                inv,
                "dispatch.call",
                n=3,
                emitted_at=old,
                provider="zai",
                model="glm-5.2",
                finish_reason="error",
                target_role="decomposer",
            ),
        ],
    )
    found = find_stranded_investigations(
        events_dir=str(events), min_age_s=60, now=time.time()
    )
    assert len(found) == 1
    assert found[0].investigation_id == inv
    assert found[0].pending_request == "decompose.requested"
    assert found[0].phase == 1


def test_skip_when_delivered_present(tmp_path: Path) -> None:
    events = tmp_path / "events"
    inv = "inv-ok"
    old = "2020-01-01T00:00:00.000000Z"
    _write_jsonl(
        events / f"{inv}.jsonl",
        [
            _evt(inv, "decompose.requested", n=1, emitted_at=old),
            _evt(inv, "dispatch.call", n=2, emitted_at=old, finish_reason="error"),
            _evt(inv, "decompose.delivered", n=3, emitted_at=old),
        ],
    )
    assert (
        find_stranded_investigations(
            events_dir=str(events), min_age_s=0, now=time.time()
        )
        == []
    )


def test_skip_when_already_failed(tmp_path: Path) -> None:
    events = tmp_path / "events"
    inv = "inv-failed"
    old = "2020-01-01T00:00:00.000000Z"
    _write_jsonl(
        events / f"{inv}.jsonl",
        [
            _evt(inv, "decompose.requested", n=1, emitted_at=old),
            _evt(inv, "dispatch.call", n=2, emitted_at=old, finish_reason="error"),
            _evt(
                inv,
                "investigation.failed",
                n=3,
                emitted_at=old,
                phase=1,
                reason="x",
            ),
        ],
    )
    assert find_stranded_investigations(events_dir=str(events), min_age_s=0) == []


def test_recover_emits_investigation_failed(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "events"
    inv = "inv-recover"
    old = "2020-01-01T00:00:00.000000Z"
    _write_jsonl(
        events / f"{inv}.jsonl",
        [
            _evt(inv, "decompose.requested", n=1, emitted_at=old),
            _evt(inv, "dispatch.call", n=2, emitted_at=old, finish_reason="error"),
        ],
    )
    import substrate.event_log.events as evmod

    monkeypatch.setattr(evmod, "default_events_dir", lambda: str(events))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    eid = recover_stranded_investigation(
        inv,
        pending_request="decompose.requested",
        phase=1,
        events_dir=str(events),
    )
    assert eid
    rows = list(
        iter_physical_events(inv, events_dir=str(events), _lock_already_held=True)
    )
    assert rows[-1]["action_type"] == "investigation.failed"
    assert "stranded" in (rows[-1].get("payload") or {}).get("reason", "")


def test_decomposer_dispatch_catches_generic_exception(monkeypatch) -> None:
    from interfaces.research.api import decomposer as dec
    from substrate.schemas import Event
    import interfaces.research.api.research_owner_dispatch as rod

    class Boom(RuntimeError):
        pass

    def _boom(*a, **k):
        raise Boom("owner_byot_outcome_unknown")

    monkeypatch.setattr(dec, "dispatch", _boom)
    monkeypatch.setattr(rod, "dispatch_loop_one", lambda *a, **k: None)

    event = Event.model_validate(
        {
            "event_id": "evt-req",
            "investigation_id": "inv-x",
            "action_type": "decompose.requested",
            "payload": {
                "action_type": "decompose.requested",
                "question": "What is liberty?",
                "context": "",
            },
            "emitted_at": "2026-09-18T10:00:00.000000Z",
            "schema_version": 40,
            "param_version": "0.2.0",
        }
    )
    result, policy = dec._dispatch_and_parse("prompt", event, label="test")
    assert result is None
    assert policy == "decomposer-fallback/no-provider"
