from __future__ import annotations

import ast
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from substrate.antiek_bench.live.journal import Journal
from substrate.antiek_bench.live.nd_shadow import (
    NDShadowConfig,
    NDShadowJournal,
    NDShadowResponse,
    collect_nd_shadow,
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
        assert collect_nd_shadow(
            config=config(enabled),
            items=(("item", "distill", "private prompt"),),
            client=client,
            journal=journal,
            environ=environ,
        ) == ()
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
