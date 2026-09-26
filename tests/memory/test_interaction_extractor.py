"""Interaction extraction and the Thought Partner memory boundary.

The substrate half (a-c) runs the extractor and the reconciler against a real
graph: one stable fact is exactly one ADD, its restatement is a NOOP that
writes nothing, and a contradiction is a SUPERSEDE that keeps the original row
reachable with ``include_invalidated=True``. The interface half (d, flag) goes
through the real ``/thought-partner`` route. Raw prompts never authorize a
durable write, and legacy unconfirmed extracts never enter provider context.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from runtime.db_lock import LockedConnection, connect_write
from substrate.auth import mint_session_cookie
from substrate.dispatch import (
    NormalizedUsage,
    RawProviderResponse,
    register_provider,
    reset_provider_registry,
)
from substrate.graph.schema import init_database_at_path
from substrate.memory import list_memory, write_memory_item
from substrate.memory.interaction_extractor import (
    EXTRACTOR_VERSION,
    INTERACTION_MEMORY_FLAG,
    OWNER_SUBJECT,
    extract_memory_candidates,
    record_interaction_memory,
)

_SECRET = "interaction-extractor-test-" + "x" * 48
_EMAIL = "owner@example.test"
_T0 = datetime(2026, 9, 1, 9, 0)


@pytest.fixture
def memory_con(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LockedConnection:
    db_path = str(tmp_path / "interaction.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    init_database_at_path(db_path)
    con = connect_write(db_path, purpose="test-interaction-extractor")
    try:
        yield con
    finally:
        con.close()


def _turn(con: LockedConnection, prompt: str, *, at: datetime, owner: str = "owner-a"):
    candidates = extract_memory_candidates(
        owner_user_id=owner, prompt=prompt, valid_from=at, investigation_id="inv-42"
    )
    return candidates, record_interaction_memory(con, candidates)


# ── (a) a stable fact is exactly one ADD ────────────────────────────


def test_stable_fact_produces_exactly_one_add(memory_con: LockedConnection) -> None:
    candidates, decisions = _turn(memory_con, "I prefer vim for editing. Can you help?", at=_T0)

    assert [decision.action for decision in decisions] == ["ADD"]
    rows = list_memory(memory_con, "owner-a")
    assert len(rows) == 1
    assert (rows[0].subject, rows[0].predicate, rows[0].object) == (
        OWNER_SUBJECT,
        "prefers",
        "vim for editing",
    )
    assert rows[0].provenance["source"] == "thought_partner"
    assert rows[0].provenance["investigation_id"] == "inv-42"
    assert rows[0].provenance["excerpt"] == "I prefer vim for editing"
    assert candidates[0].valid_from == _T0


# ── (b) the same fact restated is a NOOP and writes nothing ─────────


def test_restated_fact_is_noop_and_writes_nothing(memory_con: LockedConnection) -> None:
    _turn(memory_con, "I prefer vim for editing.", at=_T0)
    before = list_memory(memory_con, "owner-a", include_invalidated=True)

    _, decisions = _turn(memory_con, "Well, I prefer Vim for editing!", at=_T0 + timedelta(hours=1))

    assert [decision.action for decision in decisions] == ["NOOP"]
    assert list_memory(memory_con, "owner-a", include_invalidated=True) == before


# ── (c) a contradiction supersedes and keeps the original reachable ──


def test_contradicting_restatement_supersedes_and_keeps_the_original(
    memory_con: LockedConnection,
) -> None:
    _turn(memory_con, "I prefer vim for editing.", at=_T0)
    original = list_memory(memory_con, "owner-a")[0]

    _, decisions = _turn(
        memory_con, "Actually I prefer emacs for editing.", at=_T0 + timedelta(days=1)
    )

    assert [decision.action for decision in decisions] == ["SUPERSEDE"]
    current = list_memory(memory_con, "owner-a")
    assert [item.object for item in current] == ["emacs for editing"]
    history = {
        item.edge_id: item for item in list_memory(memory_con, "owner-a", include_invalidated=True)
    }
    assert set(history) == {original.edge_id, current[0].edge_id}
    retained = history[original.edge_id]
    assert retained.object == "vim for editing"
    assert retained.valid_to == _T0 + timedelta(days=1)
    assert retained.superseded_by == current[0].edge_id


def test_negated_restatement_is_a_supersede_too(memory_con: LockedConnection) -> None:
    _turn(memory_con, "I use vim.", at=_T0)
    _, decisions = _turn(memory_con, "I don't use vim anymore.", at=_T0 + timedelta(days=1))

    assert [decision.action for decision in decisions] == ["SUPERSEDE"]
    assert [item.object for item in list_memory(memory_con, "owner-a")] == ["not vim"]


# ── extraction quality: what is refused ─────────────────────────────


@pytest.mark.parametrize(
    "prompt",
    [
        "Do I prefer vim?",
        "I prefer that you answer briefly.",
        "I use this to track my reading.",
        "I am a bit confused about the second chapter.",
        "Summarise the paper on quantum error correction.",
        "My colleague prefers vim.",
        "I prefer " + "a very long phrase " * 6,
    ],
)
def test_low_confidence_shapes_produce_no_candidates(prompt: str) -> None:
    assert extract_memory_candidates(owner_user_id="owner-a", prompt=prompt, valid_from=_T0) == []


def test_one_turn_yields_one_candidate_per_key_and_reads_only_the_prompt() -> None:
    candidates = extract_memory_candidates(
        owner_user_id="owner-a",
        prompt="I live in Berlin and I work at Antiek, but I prefer tea. No, I prefer coffee.",
        valid_from=_T0,
    )
    assert {(c.predicate, c.object) for c in candidates} == {
        ("lives_in", "Berlin"),
        ("works_at", "Antiek"),
        ("prefers", "coffee"),
    }
    for candidate in candidates:
        assert candidate.owner_user_id == "owner-a"
        assert candidate.valid_to is None and candidate.superseded_by is None
        assert "investigation_id" not in candidate.provenance


# ── (d) + flag: through the real /thought-partner route ────────────


class _CannedProvider:
    name = "zai"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({"model": model, "prompt": prompt})
        return RawProviderResponse(
            text='{"shape":"synthesis","synthesis_text":"noted"}',
            raw_usage={},
            finish_reason="stop",
            latency_ms=1,
            request_id="interaction-extractor-test",
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(input_tokens=0, output_tokens=0)


@pytest.fixture(autouse=True)
def _providers() -> None:
    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = str(tmp_path / "memory.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _EMAIL)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    monkeypatch.delenv(INTERACTION_MEMORY_FLAG, raising=False)
    init_database_at_path(db_path)
    app_module = importlib.import_module("interfaces.research.api.app")

    monkeypatch.setattr(
        app_module,
        "_retrieve_thought_partner_context",
        lambda *a, **k: ([], "duckdb — brute_force_kind", None),
    )
    app = app_module.create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app), db_path


def _post(client: TestClient, *, owner: str = "owner-a") -> Any:
    register_provider(_CannedProvider())
    response = client.post(
        "/thought-partner",
        cookies={"ANTIEK_SESSION": mint_session_cookie(user_id=owner, email=_EMAIL)},
        json={
            "prompt": "I prefer vim for editing. What should I read next?",
            "investigation_id": "inv-7",
        },
    )
    assert response.status_code == 200, response.text
    return response


def _owner_rows(db_path: str, owner: str = "owner-a"):
    with connect_write(db_path, purpose="read-back") as con:
        return list_memory(con, owner, include_invalidated=True)


def test_untyped_writeback_does_not_change_response_or_store(
    app_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db_path = app_client
    baseline = _post(client).json()

    monkeypatch.setenv(INTERACTION_MEMORY_FLAG, "1")

    response = _post(client)

    assert response.json() == baseline
    assert _owner_rows(db_path) == []


def test_flag_off_writes_nothing(app_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, db_path = app_client
    monkeypatch.delenv(INTERACTION_MEMORY_FLAG, raising=False)

    _post(client)

    assert _owner_rows(db_path) == []


def test_quoted_source_not_promoted_to_owner_fact(
    app_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db_path = app_client
    monkeypatch.setenv(INTERACTION_MEMORY_FLAG, "1")
    register_provider(_CannedProvider())
    response = client.post(
        "/thought-partner",
        cookies={"ANTIEK_SESSION": mint_session_cookie(user_id="owner-a", email=_EMAIL)},
        json={
            "prompt": "Please summarize this quoted source:\nI work at ExampleCo.",
            "investigation_id": "inv-7",
        },
    )
    assert response.status_code == 200, response.text
    assert _owner_rows(db_path) == []


def test_signed_raw_turn_cannot_write_memory_even_with_flag_on(
    app_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db_path = app_client
    monkeypatch.setenv(INTERACTION_MEMORY_FLAG, "1")

    _post(client)
    _post(client)
    assert _owner_rows(db_path) == []

    _post(client, owner="__operator__")
    assert _owner_rows(db_path, "__operator__") == []


def test_legacy_unconfirmed_extract_is_quarantined_from_provider_context(
    app_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db_path = app_client
    monkeypatch.setenv(INTERACTION_MEMORY_FLAG, "1")
    with connect_write(db_path, purpose="seed-legacy-unconfirmed-memory") as con:
        _turn(con, "I work at ExampleCo.", at=_T0)
    assert len(_owner_rows(db_path)) == 1

    provider = _CannedProvider()
    register_provider(provider)
    response = client.post(
        "/thought-partner",
        cookies={"ANTIEK_SESSION": mint_session_cookie(user_id="owner-a", email=_EMAIL)},
        json={"prompt": "What should I read next?", "investigation_id": "inv-7"},
    )

    assert response.status_code == 200, response.text
    assert len(provider.calls) == 1
    assert "ExampleCo" not in provider.calls[0]["prompt"]
    assert len(_owner_rows(db_path)) == 1


def test_legacy_extracts_cannot_crowd_out_valid_recall(app_client) -> None:
    client, db_path = app_client
    with connect_write(db_path, purpose="seed-recall-crowd-out") as con:
        write_memory_item(
            con,
            owner_user_id="owner-a",
            subject="owner",
            predicate="prefers",
            object="manual-entry-coffee",
            provenance={"source": "account_memory_test", "event_id": "manual-1"},
            valid_from=_T0,
        )
        for index in range(8):
            write_memory_item(
                con,
                owner_user_id="owner-a",
                subject="owner",
                predicate=f"legacy_{index}",
                object=f"unconfirmed-{index}",
                provenance={
                    "source": "thought_partner",
                    "extractor": EXTRACTOR_VERSION,
                    "event_id": f"legacy-{index}",
                },
                valid_from=_T0 + timedelta(days=index + 1),
            )
    assert len(_owner_rows(db_path)) == 9

    provider = _CannedProvider()
    register_provider(provider)
    response = client.post(
        "/thought-partner",
        cookies={"ANTIEK_SESSION": mint_session_cookie(user_id="owner-a", email=_EMAIL)},
        json={"prompt": "What should I read next?"},
    )

    assert response.status_code == 200, response.text
    assert len(provider.calls) == 1
    assert "manual-entry-coffee" in provider.calls[0]["prompt"]
    assert "unconfirmed-" not in provider.calls[0]["prompt"]
    assert len(_owner_rows(db_path)) == 9
