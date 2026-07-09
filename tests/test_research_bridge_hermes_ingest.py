"""Read-only Hermes research-event ingest bridge (hardened).

Pins parse tolerance, investigation grouping, deterministic rendering, live-path
ingest via ``ingest_file``, content-addressed idempotency, honest skip/error
statuses, AND the trust boundary: allowed-root path enforcement, symlink
escape rejection, payload secret redaction, and size caps. No network.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from runtime.db_lock import connect_read, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.research_bridge.hermes_ingest import (
    HERMES_INGEST_VERSION,
    HermesEventsDirError,
    HermesIngestBatch,
    HermesIngestResult,
    _render_payload,
    group_investigations,
    ingest_hermes_events,
    ingest_hermes_investigation,
    iter_hermes_events,
    parse_hermes_event_line,
    render_investigation_text,
    resolve_allowed_events_dir,
)


class _FakeEmbedding:
    dimension = 8

    def encode(self, text):
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def env(monkeypatch):
    d = tempfile.mkdtemp()
    db = os.path.join(d, "g.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    import substrate.graph.insight_question as iq
    monkeypatch.setattr(iq, "graph_db_path", lambda: db)
    init_database_at_path(db)
    return {"db": db, "events": ev, "root": d, "allowed": [Path(ev)]}


def _event(
    event_id: str,
    investigation_id: str = "inv-1",
    *,
    emitted_at: str | None = "2026-07-01T00:00:00Z",
    phase: str = "research",
    role: str = "note_taker",
    action_type: str = "synthesize",
    payload: dict | None = None,
    schema_version: int = 31,
) -> dict:
    return {
        "event_id": event_id,
        "investigation_id": investigation_id,
        "phase": phase,
        "role": role,
        "action_type": action_type,
        "emitted_at": emitted_at,
        "schema_version": schema_version,
        "payload": payload if payload is not None else {"text": "a finding"},
    }


def _write_events(env, events, filename="trace.jsonl"):
    path = os.path.join(env["events"], filename)
    with open(path, "w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")
    return path


# --------------------------------------------------------------------------
# parse tolerance
# --------------------------------------------------------------------------


def test_parse_valid_line_captures_fields():
    record = parse_hermes_event_line(json.dumps(_event("e1", schema_version=31)))
    assert record is not None
    assert record.event_id == "e1"
    assert record.investigation_id == "inv-1"
    assert record.schema_version == 31
    assert record.payload == {"text": "a finding"}


def test_parse_blank_line_returns_none():
    assert parse_hermes_event_line("   \n") is None
    assert parse_hermes_event_line("") is None


def test_parse_malformed_json_returns_none():
    assert parse_hermes_event_line("{not json") is None
    assert parse_hermes_event_line("[1, 2, 3]") is None


def test_parse_missing_required_keys_returns_none():
    no_event = {"investigation_id": "inv-1"}
    assert parse_hermes_event_line(json.dumps(no_event)) is None
    no_inv = {"event_id": "e1"}
    assert parse_hermes_event_line(json.dumps(no_inv)) is None


def test_parse_non_string_ids_returns_none():
    bad = _event("e1")
    bad["event_id"] = 123
    assert parse_hermes_event_line(json.dumps(bad)) is None
    bad2 = _event("e1")
    bad2["investigation_id"] = None
    assert parse_hermes_event_line(json.dumps(bad2)) is None


def test_iter_skips_blank_and_malformed_lines(env):
    path = os.path.join(env["events"], "mixed.jsonl")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n")
        handle.write(json.dumps(_event("e1")) + "\n")
        handle.write("{bad\n")
        handle.write(json.dumps(_event("e2")) + "\n")
    records = list(iter_hermes_events(env["events"], allowed_roots=env["allowed"]))
    assert [r.event_id for r in records] == ["e1", "e2"]


def test_iter_missing_dir_yields_nothing(env):
    missing = os.path.join(env["events"], "does-not-exist")
    # Missing path under allowed root → empty, not an error.
    assert list(iter_hermes_events(missing, allowed_roots=env["allowed"])) == []


def test_group_two_investigations_sorted_by_time():
    events = [
        parse_hermes_event_line(json.dumps(_event("e2", "inv-a", emitted_at="2026-07-02T00:00:00Z"))),
        parse_hermes_event_line(json.dumps(_event("e1", "inv-a", emitted_at="2026-07-01T00:00:00Z"))),
        parse_hermes_event_line(json.dumps(_event("e3", "inv-b", emitted_at="2026-07-01T12:00:00Z"))),
    ]
    assert all(e is not None for e in events)
    groups = group_investigations(e for e in events if e is not None)
    assert list(groups) == ["inv-a", "inv-b"]
    assert [e.event_id for e in groups["inv-a"].events] == ["e1", "e2"]


def test_group_events_without_timestamp_sort_stably():
    e1 = parse_hermes_event_line(json.dumps(_event("e1", emitted_at=None)))
    e2 = parse_hermes_event_line(json.dumps(_event("e2", emitted_at=None)))
    assert e1 is not None and e2 is not None
    groups = group_investigations([e1, e2])
    assert [e.event_id for e in groups["inv-1"].events] == ["e1", "e2"]


def test_render_is_deterministic_and_carries_provenance():
    e = parse_hermes_event_line(json.dumps(_event("e1", payload={"text": "finding"})))
    assert e is not None
    inv = group_investigations([e])["inv-1"]
    a = render_investigation_text(inv)
    b = render_investigation_text(inv)
    assert a == b
    assert "hermes" in a.lower()
    assert "inv-1" in a
    assert f"ingest version: {HERMES_INGEST_VERSION}" in a
    assert "finding" in a


def test_ingest_one_investigation_writes_new_document(env):
    e = parse_hermes_event_line(json.dumps(_event("e1")))
    assert e is not None
    inv = group_investigations([e])["inv-1"]
    with connect_write(env["db"]) as con:
        result = ingest_hermes_investigation(con, inv)
    assert result.status == "ok"
    assert result.was_new is True
    assert result.document_id is not None
    with connect_read(env["db"]) as con:
        n = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    assert n == 1


def test_ingest_is_idempotent_cache_hit(env):
    e = parse_hermes_event_line(json.dumps(_event("e1")))
    assert e is not None
    inv = group_investigations([e])["inv-1"]
    with connect_write(env["db"]) as con:
        first = ingest_hermes_investigation(con, inv)
        second = ingest_hermes_investigation(con, inv)
    assert first.status == "ok"
    assert second.status == "cache_hit"
    assert second.was_new is False
    assert second.document_id == first.document_id


def test_ingest_hermes_events_batch_rollup(env):
    _write_events(
        env,
        [
            _event("e1", "inv-a"),
            _event("e2", "inv-b"),
        ],
    )
    with connect_write(env["db"]) as con:
        batch = ingest_hermes_events(
            con, env["events"], allowed_roots=env["allowed"]
        )
    assert isinstance(batch, HermesIngestBatch)
    assert batch.new_count == 2
    assert batch.cache_hit_count == 0
    assert batch.error_count == 0
    assert len(batch.results) == 2


def test_ingest_hermes_events_limit_caps_investigations(env):
    _write_events(
        env,
        [
            _event("e1", "inv-a"),
            _event("e2", "inv-b"),
            _event("e3", "inv-c"),
        ],
    )
    with connect_write(env["db"]) as con:
        batch = ingest_hermes_events(
            con, env["events"], limit=1, allowed_roots=env["allowed"]
        )
    assert batch.new_count == 1
    assert len(batch.results) == 1


def test_batch_counts_malformed_lines_honestly(env):
    path = os.path.join(env["events"], "messy.jsonl")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(_event("e1")) + "\n")
        handle.write("{not-json\n")
        handle.write("[]\n")
    with connect_write(env["db"]) as con:
        batch = ingest_hermes_events(
            con, env["events"], allowed_roots=env["allowed"]
        )
    assert batch.malformed_lines == 2
    assert batch.new_count == 1


def test_invalid_utf8_does_not_abort_sweep(env):
    path = os.path.join(env["events"], "binaryish.jsonl")
    with open(path, "wb") as handle:
        handle.write(b'{"event_id":"e1","investigation_id":"inv-1","payload":{}}\n')
        handle.write(b"\xff\xfe not json \n")
        handle.write(b'{"event_id":"e2","investigation_id":"inv-1","payload":{}}\n')
    with connect_write(env["db"]) as con:
        batch = ingest_hermes_events(
            con, env["events"], allowed_roots=env["allowed"]
        )
    assert batch.new_count == 1
    assert batch.malformed_lines >= 1


def test_oversized_line_is_bounded_and_next_event_survives(env):
    path = os.path.join(env["events"], "oversized.jsonl")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write('{"event_id":"too-big","investigation_id":"skip","payload":"')
        handle.write("x" * 80_000)
        handle.write('"}\n')
        handle.write(json.dumps(_event("e1", "kept")) + "\n")
    with connect_write(env["db"]) as con:
        batch = ingest_hermes_events(
            con, env["events"], allowed_roots=env["allowed"]
        )
    assert batch.malformed_lines == 1
    assert [r.investigation_id for r in batch.results] == ["kept"]


def test_result_is_frozen_dataclass():
    r = HermesIngestResult(
        investigation_id="i",
        document_id=None,
        status="skipped_empty",
        events_count=0,
        was_new=False,
        source_label="hermes:i",
        document_type=None,
    )
    with pytest.raises(FrozenInstanceError):
        r.status = "ok"  # type: ignore[misc]


# --------------------------------------------------------------------------
# trust boundary (codex #351 BLOCKING fixes)
# --------------------------------------------------------------------------


def test_resolve_rejects_path_outside_allowed_roots(env, tmp_path):
    outsider = tmp_path / "not-hermes"
    outsider.mkdir()
    with pytest.raises(HermesEventsDirError):
        resolve_allowed_events_dir(outsider, allowed_roots=env["allowed"])


def test_ingest_rejects_path_outside_allowed_roots(env, tmp_path):
    outsider = tmp_path / "not-hermes"
    outsider.mkdir()
    (outsider / "evil.jsonl").write_text(
        json.dumps(_event("evil", "steal")) + "\n", encoding="utf-8"
    )
    with connect_write(env["db"]) as con, pytest.raises(HermesEventsDirError):
        ingest_hermes_events(con, outsider, allowed_roots=env["allowed"])
    with connect_read(env["db"]) as con:
        n = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    assert n == 0


def test_symlink_escape_file_is_skipped(env, tmp_path):
    # Outside file with a secret-looking event.
    outside = tmp_path / "outside.jsonl"
    outside.write_text(
        json.dumps(
            _event(
                "esc",
                "escape-inv",
                payload={"api_key": "sk-live-should-not-ingest"},
            )
        )
        + "\n",
        encoding="utf-8",
    )
    link = Path(env["events"]) / "escape.jsonl"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink not permitted in this environment")
    # Also write a legitimate local file so the batch is non-empty if escape skipped.
    _write_events(env, [_event("local", "local-inv")], filename="local.jsonl")
    with connect_write(env["db"]) as con:
        batch = ingest_hermes_events(
            con, env["events"], allowed_roots=env["allowed"]
        )
    labels = {r.investigation_id for r in batch.results}
    assert "escape-inv" not in labels
    assert "local-inv" in labels


def test_payload_redacts_secret_keys():
    rendered = _render_payload(
        {
            "model": "deepseek-v4",
            "api_key": "sk-live-secret",
            "Authorization": "Bearer abc",
            "nested": {"password": "hunter2", "ok": "keep"},
        }
    )
    assert "sk-live-secret" not in rendered
    assert "Bearer abc" not in rendered
    assert "hunter2" not in rendered
    assert "[redacted]" in rendered
    assert "deepseek-v4" in rendered
    assert "keep" in rendered


def test_payload_size_cap_truncates_huge_strings():
    huge = "x" * 50_000
    rendered = _render_payload({"blob": huge})
    assert len(rendered) <= 8_192 + 16  # small slack for JSON quoting
    assert "…" in rendered
    assert huge not in rendered


def test_render_does_not_embed_raw_secrets_in_document():
    e = parse_hermes_event_line(
        json.dumps(
            _event(
                "e1",
                payload={"client_secret": "super-secret-value", "n_chunks": 3},
            )
        )
    )
    assert e is not None
    text = render_investigation_text(group_investigations([e])["inv-1"])
    assert "super-secret-value" not in text
    assert "[redacted]" in text
    assert "n_chunks" in text


def test_meta_fields_are_capped():
    huge_id = "i" * 500
    record = parse_hermes_event_line(
        json.dumps(_event("e" * 400, huge_id, phase="p" * 1000))
    )
    assert record is not None
    assert len(record.investigation_id) <= 128
    assert len(record.event_id) <= 128
    assert len(record.phase or "") <= 256
    groups = group_investigations([record])
    text = render_investigation_text(groups[record.investigation_id])
    assert "i" * 500 not in text


def test_payload_node_budget_stops_huge_object():
    # 10k keys would OOM without a walk budget; ensure we truncate early.
    huge = {f"k{i}": "v" for i in range(10_000)}
    rendered = _render_payload(huge)
    assert len(rendered) <= 8_192 + 32
    assert "truncated" in rendered or "…" in rendered


def test_meta_secret_values_are_redacted():
    record = parse_hermes_event_line(
        json.dumps(
            _event(
                "sk-live-abcdefghijklmnopqrstuvwxyz",
                "inv-with-Bearer abcdefghijklmnop",
                phase="Bearer supersecrettokenvalue",
                role="note_taker",
            )
        )
    )
    assert record is not None
    assert record.event_id == "[redacted]"
    # investigation_id may be truncated/filename-safe but secret-shaped → redacted
    assert "Bearer" not in (record.investigation_id or "")
    assert "sk-live" not in (record.event_id or "")
    text = render_investigation_text(
        group_investigations([record])[record.investigation_id]
    )
    assert "sk-live" not in text
    assert "supersecrettokenvalue" not in text


def test_payload_string_secret_values_redacted():
    rendered = _render_payload({"note": "token is sk-live-abcdefghijklmnopqrstuvwxyz ok"})
    assert "sk-live" not in rendered
    assert "[redacted]" in rendered
