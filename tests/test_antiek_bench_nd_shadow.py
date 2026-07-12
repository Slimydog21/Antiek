from __future__ import annotations

import ast
import fcntl
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from substrate.antiek_bench.live.journal import Journal
from substrate.antiek_bench.live.nd_shadow import (
    NDShadowConfig,
    NDShadowJournal,
    NDShadowJournalCorruptionError,
    NDShadowRecord,
    NDShadowResponse,
)
from substrate.antiek_bench.live.nd_shadow import (
    collect_nd_shadow as _collect_nd_shadow,
)
from substrate.antiek_bench.store import InMemoryBenchStore
from substrate.model_registration import (
    ModelRegistry,
    add_model,
    get_decision_tree_model_id,
    get_decision_tree_registry,
    set_decision_tree_registry,
)


class FakeClient:
    def __init__(self, recommendation: str = "model-a") -> None:
        self.recommendation = recommendation
        self.calls: list[dict] = []

    def model_select(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        return NDShadowResponse(self.recommendation, "session-1", 19)


class DirectShadowTimeout:
    def run(self, fn, timeout_s):  # type: ignore[no-untyped-def]
        del timeout_s
        return fn()


def collect_nd_shadow(**kwargs):  # type: ignore[no-untyped-def]
    kwargs.setdefault("timeout_runner", DirectShadowTimeout())
    return _collect_nd_shadow(**kwargs)


def config(enabled: bool = True) -> NDShadowConfig:
    return NDShadowConfig(
        enabled=enabled,
        week_id="2026-W28",
        suite_version="suite-live-v1",
        candidates=("model-a", "model-b"),
    )


@pytest.fixture(autouse=True)
def restore_registry():  # type: ignore[no-untyped-def]
    previous_registry = get_decision_tree_registry()
    previous_model = get_decision_tree_model_id()
    yield
    set_decision_tree_registry(previous_registry, model_id=previous_model)


def test_double_gate_makes_zero_calls_and_writes(tmp_path: Path) -> None:
    for enabled, environ in ((False, {"ANTIEK_NOTDIAMOND": "1"}), (True, {})):
        client = FakeClient()
        journal = NDShadowJournal(tmp_path / f"{enabled}.jsonl")
        assert (
            collect_nd_shadow(
                config=config(enabled),
                items=(("item", "distill", "private prompt"),),
                client=client,
                journal=journal,
                environ=environ,
            )
            == ()
        )
        assert client.calls == []
        assert journal.list_records() == []


def test_shadow_uses_hash_content_and_persists_no_prompt(tmp_path: Path) -> None:
    client = FakeClient()
    journal = NDShadowJournal(tmp_path / "shadow.jsonl")
    records = collect_nd_shadow(
        config=config(),
        items=(("private-item sk-ITEM123", "distill", "private-sentinel sk-ABC123"),),
        client=client,
        journal=journal,
        environ={"ANTIEK_NOTDIAMOND": "true"},
    )
    assert records[0].recommendation == "model-a"
    assert client.calls[0]["hash_content"] is True
    assert client.calls[0]["llm_providers"] == ("model-a", "model-b")
    persisted = journal.path.read_text()
    assert "private-sentinel" not in persisted
    assert "sk-ABC123" not in persisted
    assert "sk-ITEM123" not in persisted
    assert "sha256:" in persisted

    replay_client = FakeClient("model-b")
    replay = collect_nd_shadow(
        config=config(),
        items=(("private-item sk-ITEM123", "distill", "private-sentinel sk-ABC123"),),
        client=replay_client,
        journal=journal,
        environ={"ANTIEK_NOTDIAMOND": "true"},
    )
    assert replay == records
    assert replay_client.calls == []


def test_failure_timeout_and_invalid_choice_are_nonfatal_and_bounded(tmp_path: Path) -> None:
    class FailureClient:
        def __init__(self, error):  # type: ignore[no-untyped-def]
            self.error = error

        def model_select(self, **kwargs):  # type: ignore[no-untyped-def]
            raise self.error

    for index, (error, status) in enumerate(
        ((TimeoutError("secret"), "timeout"), (RuntimeError("secret"), "failed"))
    ):
        journal = NDShadowJournal(tmp_path / f"failure-{index}.jsonl")
        row = collect_nd_shadow(
            config=config(),
            items=(("item", "distill", "prompt"),),
            client=FailureClient(error),
            journal=journal,
            environ={"ANTIEK_NOTDIAMOND": "1"},
        )[0]
        assert row.status == status
        assert "secret" not in journal.path.read_text()

    invalid = collect_nd_shadow(
        config=config(),
        items=(("item", "distill", "prompt"),),
        client=FakeClient("model-c"),
        journal=NDShadowJournal(tmp_path / "invalid.jsonl"),
        environ={"ANTIEK_NOTDIAMOND": "1"},
    )[0]
    assert invalid.status == "failed"
    assert invalid.recommendation == ""


def test_blocking_shadow_client_is_actually_time_bounded(tmp_path: Path) -> None:
    class BlockingClient:
        def model_select(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            time.sleep(0.2)
            return NDShadowResponse("model-a", "late", 200)

    bounded = NDShadowConfig(
        enabled=True,
        week_id="2026-W28",
        suite_version="suite-live-v1",
        candidates=("model-a", "model-b"),
        timeout_s=0.01,
    )
    started = time.monotonic()
    record = _collect_nd_shadow(
        config=bounded,
        items=(("item", "distill", "prompt"),),
        client=BlockingClient(),
        journal=NDShadowJournal(tmp_path / "blocking.jsonl"),
        environ={"ANTIEK_NOTDIAMOND": "1"},
    )[0]
    assert time.monotonic() - started < 0.1
    assert record.status == "timeout"
    assert record.failure_code == "notdiamond_timeout"


def test_untrusted_session_identifier_is_hashed(tmp_path: Path) -> None:
    class SessionClient(FakeClient):
        def model_select(self, **kwargs):  # type: ignore[no-untyped-def]
            return NDShadowResponse("model-a", "private-sentinel sk-ABC123", 1)

    journal = NDShadowJournal(tmp_path / "session.jsonl")
    row = collect_nd_shadow(
        config=config(),
        items=(("item", "distill", "prompt"),),
        client=SessionClient(),
        journal=journal,
        environ={"ANTIEK_NOTDIAMOND": "1"},
    )[0]
    assert row.session_id.startswith("session_sha256:")
    assert "private-sentinel" not in journal.path.read_text()


def test_claim_is_concurrency_safe_and_tradeoff_is_identity_bound(tmp_path: Path) -> None:
    class SlowClient(FakeClient):
        def model_select(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls.append(kwargs)
            time.sleep(0.05)
            return NDShadowResponse("model-a", "session", 2)

    client = SlowClient()
    journal = NDShadowJournal(tmp_path / "concurrent.jsonl")

    def collect():  # type: ignore[no-untyped-def]
        return collect_nd_shadow(
            config=config(),
            items=(("item", "distill", "prompt"),),
            client=client,
            journal=journal,
            environ={"ANTIEK_NOTDIAMOND": "1"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: collect(), range(2)))
    assert len(client.calls) == 1
    assert len(journal.list_records()) == 1
    assert journal.list_records()[0].status == "ok"

    balanced = NDShadowConfig(
        enabled=True,
        week_id="2026-W28",
        suite_version="suite-live-v1",
        candidates=("model-a", "model-b"),
        tradeoff="balanced",
    )
    collect_nd_shadow(
        config=balanced,
        items=(("item", "distill", "prompt"),),
        client=client,
        journal=journal,
        environ={"ANTIEK_NOTDIAMOND": "1"},
    )
    assert len(client.calls) == 2
    assert len(journal.list_records()) == 2


def test_crashed_pending_claim_becomes_honest_terminal_without_retry(tmp_path: Path) -> None:
    class CrashClient:
        def model_select(self, **kwargs):  # type: ignore[no-untyped-def]
            raise KeyboardInterrupt

    journal = NDShadowJournal(tmp_path / "crash.jsonl")
    with pytest.raises(KeyboardInterrupt):
        collect_nd_shadow(
            config=config(),
            items=(("item", "distill", "prompt"),),
            client=CrashClient(),
            journal=journal,
            environ={"ANTIEK_NOTDIAMOND": "1"},
            now_ms=1_000,
        )
    assert journal.list_records()[0].status == "pending"

    client = FakeClient()
    recovered = collect_nd_shadow(
        config=config(),
        items=(("item", "distill", "prompt"),),
        client=client,
        journal=journal,
        environ={"ANTIEK_NOTDIAMOND": "1"},
        now_ms=301_000,
    )
    assert recovered[0].status == "failed"
    assert recovered[0].failure_code == "abandoned_shadow_claim"
    assert client.calls == []


def test_shadow_cannot_mutate_driver_scores_or_budget(tmp_path: Path) -> None:
    registry = ModelRegistry()
    add_model(registry, "model-a", provider_id="provider-a", select=True)
    set_decision_tree_registry(registry, model_id="model-a")
    store = InMemoryBenchStore()
    store.put_run("run", {"mean_score": 0.75})
    budget_journal = Journal(tmp_path / "budget.jsonl")
    before = (
        tuple(sorted(registry.models.items())),
        registry.selected_model_id,
        get_decision_tree_model_id(),
        store.list_runs(),
        budget_journal.replay(),
    )
    collect_nd_shadow(
        config=config(),
        items=(("item", "distill", "prompt"),),
        client=FakeClient("model-b"),
        journal=NDShadowJournal(tmp_path / "shadow.jsonl"),
        environ={"ANTIEK_NOTDIAMOND": "1"},
    )
    after = (
        tuple(sorted(registry.models.items())),
        registry.selected_model_id,
        get_decision_tree_model_id(),
        store.list_runs(),
        budget_journal.replay(),
    )
    assert after == before


def test_module_has_no_execution_authority_surface() -> None:
    path = Path("substrate/antiek_bench/live/nd_shadow.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_modules = {"substrate.dispatch", "substrate.model_registration"}
    forbidden_callables = {"dispatch", "install", "select_driver", "as_dispatch_kwargs"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(
                not any(alias.name.startswith(module) for module in forbidden_modules)
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            assert not any((node.module or "").startswith(module) for module in forbidden_modules)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in forbidden_callables


def _pending(shadow_id: str = "nds_test") -> NDShadowRecord:
    return NDShadowRecord(
        shadow_id=shadow_id,
        week_id="2026-W28",
        suite_version="suite-live-v1",
        item_id_hash="sha256:item",
        task_class="distill",
        prompt_hash="sha256:prompt",
        candidates=("model-a", "model-b"),
        tradeoff="quality",
        status="pending",
        claimed_at_ms=1,
    )


def test_shadow_journal_recovers_torn_tail_before_append(tmp_path: Path) -> None:
    path = tmp_path / "torn.jsonl"
    journal = NDShadowJournal(path)
    first = _pending("nds_first")
    assert journal.claim(first)
    with path.open("ab") as handle:
        handle.write(b'{"torn":')

    assert journal.claim(_pending("nds_second"))
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    assert b'"torn"' not in raw
    assert {row.shadow_id for row in journal.list_records()} == {
        "nds_first",
        "nds_second",
    }


def test_shadow_journal_interior_corruption_is_typed(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.jsonl"
    path.write_bytes(b'{"broken":true}\n{"also":')
    journal = NDShadowJournal(path)

    with pytest.raises(NDShadowJournalCorruptionError, match="row 1"):
        journal.list_records()
    with pytest.raises(NDShadowJournalCorruptionError, match="row 1"):
        journal.claim(_pending())


def test_shadow_journal_completes_short_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = NDShadowJournal(tmp_path / "short.jsonl")
    real_write = os.write
    writes: list[int] = []

    def short_write(fd: int, payload: bytes | memoryview) -> int:
        chunk = bytes(payload[: max(1, len(payload) // 3)])
        writes.append(len(chunk))
        return real_write(fd, chunk)

    monkeypatch.setattr(os, "write", short_write)
    assert journal.claim(_pending())
    assert len(writes) > 1
    assert journal.list_records() == [_pending()]


def test_shadow_journal_zero_progress_write_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = NDShadowJournal(tmp_path / "zero-write.jsonl")
    monkeypatch.setattr(os, "write", lambda _fd, _payload: 0)

    with pytest.raises(OSError, match="no progress"):
        journal.claim(_pending())


def test_shadow_journal_short_reads_never_trigger_false_tail_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "short-read.jsonl"
    journal = NDShadowJournal(path)
    assert journal.claim(_pending("nds_first"))
    assert journal.claim(_pending("nds_second"))
    before = path.read_bytes()
    real_read = os.read

    def short_read(fd: int, _size: int) -> bytes:
        return real_read(fd, 17)

    monkeypatch.setattr(os, "read", short_read)
    assert {row.shadow_id for row in journal.list_records()} == {
        "nds_first",
        "nds_second",
    }
    assert not journal.claim(_pending("nds_first"))
    assert path.read_bytes() == before


def test_shadow_journal_snapshot_read_takes_shared_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = NDShadowJournal(tmp_path / "locked-read.jsonl")
    assert journal.claim(_pending())
    real_flock = fcntl.flock
    operations: list[int] = []

    def recording_flock(fd: int, operation: int) -> None:
        operations.append(operation)
        real_flock(fd, operation)

    monkeypatch.setattr(fcntl, "flock", recording_flock)
    assert journal.list_records() == [_pending()]
    assert fcntl.LOCK_SH in operations
    assert operations[-1] == fcntl.LOCK_UN


def test_shadow_journal_rejects_sequence_and_identity_tampering(tmp_path: Path) -> None:
    path = tmp_path / "identity.jsonl"
    pending = _pending()
    terminal = NDShadowRecord(
        **{
            **pending.to_dict(),
            "status": "ok",
            "recommendation": "model-a",
            "tradeoff": "tampered",
        }
    )
    path.write_text(
        json.dumps(pending.to_dict()) + "\n" + json.dumps(terminal.to_dict()) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(NDShadowJournalCorruptionError, match="identity mismatch"):
        NDShadowJournal(path).list_records()

    terminal_only = tmp_path / "terminal-only.jsonl"
    terminal_only.write_text(json.dumps(terminal.to_dict()) + "\n", encoding="utf-8")
    with pytest.raises(NDShadowJournalCorruptionError, match="without claim"):
        NDShadowJournal(terminal_only).list_records()
