"""Red-proofs: preflight consumer wires to real probe_source path."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from acquisition.arxiv.throttle import ArxivThrottle
from interfaces.research.api.source_readiness_routes import (
    register_source_readiness_routes,
)
from substrate.research_sources.preflight import run_source_policy_preflight


def _arxiv_atom(arxiv_id: str = "2402.03300") -> bytes:
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/{arxiv_id}v1</id>
    <updated>2024-02-15T12:00:00Z</updated>
    <published>2024-02-05T09:15:33Z</published>
    <title>Paper {arxiv_id}</title>
    <summary>Abstract for {arxiv_id}.</summary>
    <author><name>Jane Doe</name></author>
    <arxiv:primary_category term="cs.AI"/>
    <category term="cs.AI"/>
  </entry>
</feed>
"""
    return xml.encode()


def _substack_rss() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Substack</title>
    <link>https://example.substack.com</link>
    <item>
      <title>Hello research</title>
      <link>https://example.substack.com/p/hello</link>
      <guid>hello-1</guid>
      <description>Body of the post for offline parse.</description>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


@pytest.fixture
def isolated_arxiv_governor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ArxivThrottle:
    lock = tmp_path / "arxiv_throttle.json.governor.lock"
    state = tmp_path / "arxiv_throttle.json"
    monkeypatch.setenv("ANTIEK_ARXIV_GOVERNOR_LOCK_PATH", str(lock))
    clock = {"t": 1_000_000.0}

    def now() -> float:
        return clock["t"]

    def sleep(dt: float) -> None:
        clock["t"] += float(dt)

    return ArxivThrottle(
        state_path=str(state),
        min_spacing_s=0.0,
        now=now,
        sleep=sleep,
    )


def _mock_client(body: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def test_preflight_empty_policy_fails_closed() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        run_source_policy_preflight([])


def test_preflight_dedupes_and_probes_arxiv_substack_offline(
    isolated_arxiv_governor: ArxivThrottle,
) -> None:
    with _mock_client(_arxiv_atom()) as a_client, _mock_client(_substack_rss()) as s_client:
        result = run_source_policy_preflight(
            ["arxiv", "substack", "arxiv"],  # dedupe
            problem="What is the scaling limit?",
            arxiv_client=a_client,
            arxiv_throttle=isolated_arxiv_governor,
            substack_client=s_client,
        )
    assert result.source_policy == ["arxiv", "substack"]
    assert result.source_receipt_id.startswith("srcpf-")
    by_src = {e.source: e for e in result.entries}
    assert by_src["arxiv"].offline_probe_ok is True
    assert by_src["arxiv"].runner_consumes_today is False
    assert by_src["arxiv"].adapter_importable is True
    assert by_src["substack"].offline_probe_ok is True
    assert by_src["substack"].runner_consumes_today is False
    assert any("offline" in n.lower() or "probe" in n.lower() for n in result.notes)


def test_preflight_import_only_does_not_claim_offline_ok() -> None:
    result = run_source_policy_preflight(["arxiv", "substack"])
    by_src = {e.source: e for e in result.entries}
    assert by_src["arxiv"].adapter_importable is True
    assert by_src["arxiv"].offline_probe_ok is False
    assert by_src["arxiv"].status == "gated"
    assert by_src["substack"].offline_probe_ok is False


def test_http_route_uses_real_preflight_composer(
    isolated_arxiv_governor: ArxivThrottle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP layer must call run_source_policy_preflight (not invent entries)."""
    import interfaces.research.api.source_readiness_routes as routes
    from substrate.research_sources.preflight import SourcePolicyPreflight, SourcePreflightEntry

    calls: list[list[str]] = []

    def fake_run(source_policy, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(source_policy))
        return SourcePolicyPreflight(
            source_receipt_id="srcpf-test",
            source_policy=list(source_policy),
            gather_mode="stub",
            entries=[
                SourcePreflightEntry(
                    source=s,  # type: ignore[arg-type]
                    status="ready",
                    runner_consumes_today=False,
                    external_call_would_be_required=True,
                    note=f"wired:{s}",
                    adapter_importable=True,
                    offline_probe_ok=True,
                )
                for s in source_policy
            ],
            notes=["test"],
        )

    monkeypatch.setattr(routes, "run_source_policy_preflight", fake_run)

    app = FastAPI()
    register_source_readiness_routes(app)
    with TestClient(app) as client:
        res = client.post(
            "/research/source-policy/preflight",
            json={"source_policy": ["arxiv", "substack"], "problem": "p"},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert calls == [["arxiv", "substack"]]
    assert body["source_receipt_id"] == "srcpf-test"
    assert body["entries"][0]["note"] == "wired:arxiv"
    assert body["entries"][0]["runner_consumes_today"] is False


def test_http_route_end_to_end_offline_arxiv(
    isolated_arxiv_governor: ArxivThrottle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E2E without network: inject MockTransport into the pure composer via patch."""
    import substrate.research_sources.preflight as preflight_mod

    real_run = preflight_mod.run_source_policy_preflight

    def run_with_mock(source_policy, **kwargs):  # type: ignore[no-untyped-def]
        with _mock_client(_arxiv_atom()) as a_client, _mock_client(
            _substack_rss()
        ) as s_client:
            return real_run(
                source_policy,
                arxiv_client=a_client,
                arxiv_throttle=isolated_arxiv_governor,
                substack_client=s_client,
                root_id=kwargs.get("root_id"),
                problem=kwargs.get("problem"),
            )

    monkeypatch.setattr(
        "interfaces.research.api.source_readiness_routes.run_source_policy_preflight",
        run_with_mock,
    )

    app = FastAPI()
    register_source_readiness_routes(app)
    with TestClient(app) as client:
        res = client.post(
            "/research/source-policy/preflight",
            json={"source_policy": ["arxiv", "substack"]},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    by_src = {e["source"]: e for e in body["entries"]}
    assert by_src["arxiv"]["offline_probe_ok"] is True
    assert by_src["substack"]["offline_probe_ok"] is True
    assert by_src["arxiv"]["runner_consumes_today"] is False


def test_gather_mode_arg_overrides_env_for_web_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Receipt gather_mode and web entry must share one authoritative mode.

    Regression (codex): gather_mode='stub' with env exa produced stub header
    but runner_consumes_today=True from probe_source re-reading env.
    """
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "exa")
    result = run_source_policy_preflight(
        ["web"],
        gather_mode="stub",
    )
    assert result.gather_mode == "stub"
    web = result.entries[0]
    assert web.source == "web"
    assert web.status == "stub"
    assert web.runner_consumes_today is False
    assert web.external_call_would_be_required is False

    result_exa = run_source_policy_preflight(["web"], gather_mode="exa")
    assert result_exa.gather_mode == "exa"
    assert result_exa.entries[0].runner_consumes_today is True
    assert result_exa.entries[0].status == "gated"


def test_register_function_mounts_preflight_path() -> None:
    app = FastAPI()
    register_source_readiness_routes(app)
    # Starlette/FastAPI may store path without methods until first request on some versions;
    # OpenAPI paths are the stable product contract.
    schema = app.openapi()
    assert "/research/source-policy/preflight" in schema.get("paths", {})
