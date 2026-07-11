"""Red-proof: cascade launch gates on source-policy preflight.

Pure gate module + light HTTP surface. No live network, no paid spend.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import interfaces.research.api.cascade_routes as cr
from interfaces.research.api.cascade_routes import cascade_router
from substrate.research_sources.cascade_gate import (
    SourcePolicyLaunchBlocked,
    evaluate_source_policy_for_launch,
)
from substrate.research_sources.preflight import (
    SourcePolicyPreflight,
    SourcePreflightEntry,
)


def _receipt(
    *entries: SourcePreflightEntry,
    policy: list[str] | None = None,
) -> SourcePolicyPreflight:
    ordered = policy or [e.source for e in entries]
    return SourcePolicyPreflight(
        source_receipt_id="srcpf-test",
        source_policy=ordered,  # type: ignore[arg-type]
        gather_mode="stub",
        entries=list(entries),
        notes=["test"],
    )


def _entry(
    source: str,
    *,
    status: str = "gated",
    adapter_importable: bool = True,
    offline_probe_ok: bool = False,
    runner_consumes_today: bool = False,
) -> SourcePreflightEntry:
    return SourcePreflightEntry(
        source=source,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        runner_consumes_today=runner_consumes_today,
        external_call_would_be_required=False,
        note="test entry",
        adapter_importable=adapter_importable,
        offline_probe_ok=offline_probe_ok,
    )


# ---------------------------------------------------------------------------
# Pure gate
# ---------------------------------------------------------------------------


def test_no_policy_returns_none_without_require(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTIEK_DRW_REQUIRE_SOURCE_PREFLIGHT", raising=False)
    assert evaluate_source_policy_for_launch(None) is None
    assert evaluate_source_policy_for_launch([]) is None


def test_require_policy_blocks_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTIEK_DRW_REQUIRE_SOURCE_PREFLIGHT", raising=False)
    with pytest.raises(SourcePolicyLaunchBlocked) as ei:
        evaluate_source_policy_for_launch(None, require_policy=True)
    assert ei.value.code == "source_policy_required"
    assert ei.value.receipt is None
    detail = ei.value.http_detail()
    assert detail["code"] == "source_policy_required"
    assert "source_preflight" not in detail


def test_env_require_policy_blocks_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTIEK_DRW_REQUIRE_SOURCE_PREFLIGHT", "1")
    with pytest.raises(SourcePolicyLaunchBlocked) as ei:
        evaluate_source_policy_for_launch(None)
    assert ei.value.code == "source_policy_required"


def test_gated_importable_sources_allowed_with_receipt() -> None:
    fake = _receipt(
        _entry("arxiv", status="gated", adapter_importable=True),
        _entry("web", status="stub", adapter_importable=True),
    )

    def preflight_fn(policy: list[str], **kwargs: Any) -> SourcePolicyPreflight:
        assert policy == ["arxiv", "web"]
        assert kwargs.get("root_id") == "root-1"
        return fake

    out = evaluate_source_policy_for_launch(
        ["arxiv", "web"],
        root_id="root-1",
        preflight_fn=preflight_fn,
    )
    assert out is fake
    assert out.source_receipt_id == "srcpf-test"


def test_unavailable_source_fails_closed_with_receipt() -> None:
    fake = _receipt(
        _entry("arxiv", status="unavailable", adapter_importable=False),
        _entry("web", status="stub", adapter_importable=True),
    )

    def preflight_fn(policy: list[str], **kwargs: Any) -> SourcePolicyPreflight:
        return fake

    with pytest.raises(SourcePolicyLaunchBlocked) as ei:
        evaluate_source_policy_for_launch(["arxiv", "web"], preflight_fn=preflight_fn)
    assert ei.value.code == "source_policy_unavailable"
    assert ei.value.blocked_sources == ["arxiv"]
    assert ei.value.receipt is fake
    detail = ei.value.http_detail()
    assert detail["source_preflight"]["source_receipt_id"] == "srcpf-test"
    assert detail["blocked_sources"] == ["arxiv"]


def test_not_importable_fails_closed_even_if_status_gated() -> None:
    fake = _receipt(
        _entry("substack", status="gated", adapter_importable=False),
    )

    with pytest.raises(SourcePolicyLaunchBlocked) as ei:
        evaluate_source_policy_for_launch(
            ["substack"],
            preflight_fn=lambda *a, **k: fake,
        )
    assert ei.value.blocked_sources == ["substack"]


def test_real_preflight_web_stub_path_allows_launch() -> None:
    """Drive the real preflight composer for web (no network)."""
    receipt = evaluate_source_policy_for_launch(
        ["web"],
        problem="test problem",
        gather_mode="stub",
    )
    assert receipt is not None
    assert receipt.source_policy == ["web"]
    assert receipt.gather_mode == "stub"
    assert receipt.entries[0].adapter_importable is True
    assert receipt.entries[0].status == "stub"
    assert receipt.entries[0].runner_consumes_today is False


# ---------------------------------------------------------------------------
# HTTP launch surface (light app — cascade router only)
# ---------------------------------------------------------------------------


class _StubEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        return [0.1] * self.dimension


@pytest.fixture
def cascade_client(monkeypatch: pytest.MonkeyPatch):
    tmpdir = tempfile.mkdtemp(prefix="cascade-srcpf-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_DRW_REQUIRE_SOURCE_PREFLIGHT", raising=False)
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
    app = FastAPI()
    app.include_router(cascade_router)
    yield TestClient(app)
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()


def _approved_root(client: TestClient) -> str:
    r = client.post(
        "/research/plans",
        json={"problem": "the big problem", "sub_questions": ["a", "b"]},
    )
    assert r.status_code == 200, r.text
    root = r.json()["root_node_id"]
    ar = client.post(f"/research/plans/{root}/approve", json={"approver": "operator"})
    assert ar.status_code == 200, ar.text
    return root


def test_http_launch_without_policy_still_works(cascade_client: TestClient) -> None:
    root = _approved_root(cascade_client)
    r = cascade_client.post(
        f"/research/plans/{root}/launch",
        json={"per_research_budget_usd": 1.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"]
    assert "source_preflight" not in body


def test_http_launch_with_web_policy_attaches_receipt(
    cascade_client: TestClient,
) -> None:
    root = _approved_root(cascade_client)
    r = cascade_client.post(
        f"/research/plans/{root}/launch",
        json={
            "per_research_budget_usd": 1.0,
            "source_policy": ["web"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    pf = body["source_preflight"]
    assert pf["source_policy"] == ["web"]
    assert pf["gather_mode"] == "stub"
    assert pf["entries"][0]["runner_consumes_today"] is False
    assert pf["source_receipt_id"].startswith("srcpf-")


def test_http_launch_require_without_policy_422(
    cascade_client: TestClient,
) -> None:
    root = _approved_root(cascade_client)
    r = cascade_client.post(
        f"/research/plans/{root}/launch",
        json={
            "per_research_budget_usd": 1.0,
            "require_source_preflight": True,
        },
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "source_policy_required"
    # Must not have started a session.
    assert not cr._SESSIONS


def test_http_launch_unavailable_via_injectable_preflight(
    cascade_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed through the real evaluate_ path with a fake preflight_fn.

    Injects a receipt that marks arxiv unavailable — proves HTTP mapping and
    no session construction without network.
    """
    root = _approved_root(cascade_client)
    fake = _receipt(
        _entry("arxiv", status="unavailable", adapter_importable=False),
    )

    import substrate.research_sources.cascade_gate as gate

    real = gate.evaluate_source_policy_for_launch

    def wrapped(source_policy: list[str] | None, **kwargs: Any) -> Any:
        kwargs = dict(kwargs)
        kwargs["preflight_fn"] = lambda *a, **k: fake
        return real(source_policy, **kwargs)

    monkeypatch.setattr(gate, "evaluate_source_policy_for_launch", wrapped)

    r = cascade_client.post(
        f"/research/plans/{root}/launch",
        json={
            "per_research_budget_usd": 1.0,
            "source_policy": ["arxiv"],
        },
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "source_policy_unavailable"
    assert detail["blocked_sources"] == ["arxiv"]
    assert detail["source_preflight"]["source_receipt_id"] == "srcpf-test"
    assert not cr._SESSIONS
