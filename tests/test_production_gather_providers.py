from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from acquisition.arxiv.client import ArxivPaper
from acquisition.substack.client import Post, Publication
from runtime.research_runner.authorized_gather import GatherNotDispatched
from runtime.research_runner.gather_plan import GatherSource, GatherSourcePlan
from runtime.research_runner.production_gather_providers import (
    ArxivGatherProvider,
    ExaGatherProvider,
    ParallelGatherProvider,
    SubstackSubscriptionGatherProvider,
    arxiv_configuration_sha256,
    exa_configuration_sha256,
    parallel_configuration_sha256,
    substack_subscription_configuration_sha256,
)
from substrate.investigation_tenancy import InvestigationAuthority


def test_paid_configuration_fingerprint_binds_key_identity_without_disclosure() -> None:
    first = {"EXA_API_KEY": "secret-one", "PARALLEL_API_KEY": "parallel-one"}
    second = {"EXA_API_KEY": "secret-two", "PARALLEL_API_KEY": "parallel-two"}

    assert exa_configuration_sha256(first) != exa_configuration_sha256(second)
    assert parallel_configuration_sha256(first) != parallel_configuration_sha256(second)
    assert "secret-one" not in exa_configuration_sha256(first)
    assert "parallel-one" not in parallel_configuration_sha256(first)


def _authority() -> InvestigationAuthority:
    return InvestigationAuthority("acct-1", "inv-1", Path("/tmp/antiek-test"))


def _plan(
    source: GatherSource,
    *,
    results: int = 3,
    cost: int = 0,
    configuration_sha256: str | None = None,
) -> GatherSourcePlan:
    resolved = configuration_sha256
    if resolved is None:
        resolved = {
            GatherSource.EXA: exa_configuration_sha256(),
            GatherSource.PARALLEL: parallel_configuration_sha256(),
            GatherSource.ARXIV: arxiv_configuration_sha256(),
            GatherSource.SUBSTACK: "0" * 64,
        }[source]
    return GatherSourcePlan(source, results, cost, "test-v1", resolved)


@pytest.mark.parametrize(
    ("provider", "source"),
    [
        (ExaGatherProvider(legal_gate=object()), GatherSource.EXA),
        (ParallelGatherProvider(legal_gate=object()), GatherSource.PARALLEL),
    ],
)
def test_paid_provider_rejects_underfunded_plan_before_discovery(
    monkeypatch: pytest.MonkeyPatch, provider: object, source: GatherSource
) -> None:
    module = f"acquisition.search.{source.value}.adapter"
    monkeypatch.setattr(f"{module}.discover", lambda **kwargs: pytest.fail("dispatched"))
    with pytest.raises(GatherNotDispatched, match="below one search call"):
        provider.execute(
            query="question",
            source_plan=_plan(source, cost=0),
            idempotency_key="call",
            authority=_authority(),
        )


@pytest.mark.parametrize(
    ("provider", "module", "source"),
    [
        (
            ExaGatherProvider(legal_gate="gate"),
            "acquisition.search.exa.adapter",
            GatherSource.EXA,
        ),
        (
            ParallelGatherProvider(legal_gate="gate"),
            "acquisition.search.parallel.adapter",
            GatherSource.PARALLEL,
        ),
    ],
)
def test_search_providers_return_only_promoted_canonical_documents(
    monkeypatch: pytest.MonkeyPatch, provider: object, module: str, source: GatherSource
) -> None:
    proposals = [SimpleNamespace(discovery_id="a"), SimpleNamespace(discovery_id="b")]
    monkeypatch.setattr(f"{module}.discover", lambda **kwargs: proposals)

    def promote(proposal: object, **kwargs: object) -> object:
        assert kwargs["authority"] == _authority()
        return SimpleNamespace(
            decision="ingested" if proposal is proposals[0] else "rejected_by_legal_gate",
            document_id="doc-accepted" if proposal is proposals[0] else None,
        )

    monkeypatch.setattr(f"{module}.promote_discovery", promote)
    result = provider.execute(
        query="question",
        source_plan=_plan(source, cost=1_000_000),
        idempotency_key="call",
        authority=_authority(),
    )
    assert result.document_ids == ("doc-accepted",)
    assert 0 < result.actual_cost_micros <= 1_000_000


def test_parallel_rejects_client_result_limit_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "acquisition.search.parallel.adapter.discover",
        lambda **kwargs: pytest.fail("dispatched"),
    )
    with pytest.raises(GatherNotDispatched, match="at most 50"):
        ParallelGatherProvider(legal_gate=object()).execute(
            query="question",
            source_plan=_plan(GatherSource.PARALLEL, results=51, cost=1_000_000),
            idempotency_key="call",
            authority=_authority(),
        )


@pytest.mark.parametrize(
    ("provider", "source", "module"),
    [
        (ExaGatherProvider(legal_gate=object()), GatherSource.EXA, "acquisition.search.exa.adapter"),
        (
            ParallelGatherProvider(legal_gate=object()),
            GatherSource.PARALLEL,
            "acquisition.search.parallel.adapter",
        ),
        (ArxivGatherProvider(), GatherSource.ARXIV, "acquisition.arxiv.client"),
    ],
)
def test_network_provider_rejects_configuration_drift_before_dispatch(
    monkeypatch: pytest.MonkeyPatch, provider: object, source: GatherSource, module: str
) -> None:
    target = "search" if source is GatherSource.ARXIV else "discover"
    monkeypatch.setattr(f"{module}.{target}", lambda **kwargs: pytest.fail("dispatched"))
    with pytest.raises(GatherNotDispatched, match="configuration differs"):
        provider.execute(
            query="question",
            source_plan=_plan(source, cost=1_000_000, configuration_sha256="f" * 64),
            idempotency_key="call",
            authority=_authority(),
        )


def test_arxiv_uses_governed_search_and_canonical_ingest_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    paper = ArxivPaper(
        "2401.00001",
        "v1",
        "Paper",
        ["A"],
        "Abstract",
        ["cs.AI"],
        "cs.AI",
        now,
        now,
        "https://arxiv.org/abs/2401.00001",
        "https://arxiv.org/pdf/2401.00001",
    )
    seen: dict[str, object] = {}

    def search(**kwargs: object) -> list[ArxivPaper]:
        seen.update(kwargs)
        return [paper]

    monkeypatch.setattr("acquisition.arxiv.client.search", search)
    monkeypatch.setattr(
        "acquisition.arxiv.adapter.ingest_paper",
        lambda paper, **kwargs: SimpleNamespace(
            document_id="doc-arxiv-2401-00001", status="ingested"
        ),
    )
    result = ArxivGatherProvider(client="client", throttle="throttle").execute(
        query="agents",
        source_plan=_plan(GatherSource.ARXIV),
        idempotency_key="call",
        authority=_authority(),
    )
    assert seen["client"] == "client"
    assert seen["throttle"] == "throttle"
    assert result.document_ids == ("doc-arxiv-2401-00001",)
    assert result.actual_cost_micros == 0


def test_arxiv_excludes_legally_denied_document_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("acquisition.arxiv.client.search", lambda **kwargs: [object()])
    monkeypatch.setattr(
        "acquisition.arxiv.adapter.ingest_paper",
        lambda paper, **kwargs: SimpleNamespace(document_id="doc-denied", status="skipped"),
    )
    result = ArxivGatherProvider().execute(
        query="agents",
        source_plan=_plan(GatherSource.ARXIV, cost=100),
        idempotency_key="call",
        authority=_authority(),
    )
    assert result.document_ids == ()


def test_substack_is_subscription_scoped_filters_query_and_honors_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relevant = Post("g1", "Agent systems", "", "Deep research agents", None)
    irrelevant = Post("g2", "Cooking", "", "Soup", None)
    calls: list[str] = []

    def fetch(feed_url: str, **kwargs: object) -> Publication:
        calls.append(feed_url)
        return Publication(feed_url, "Subscribed", [irrelevant, relevant])

    monkeypatch.setattr("acquisition.substack.client.fetch_feed", fetch)
    monkeypatch.setattr(
        "acquisition.substack.adapter.ingest_post",
        lambda post, **kwargs: SimpleNamespace(
            status="ingested", document_id=f"doc-{post.guid}"
        ),
    )
    provider = SubstackSubscriptionGatherProvider(("https://writer.example/feed",))
    configuration = substack_subscription_configuration_sha256(provider.feed_urls)
    result = provider.execute(
        query="research agents",
        source_plan=_plan(
            GatherSource.SUBSTACK, results=1, configuration_sha256=configuration
        ),
        idempotency_key="call",
        authority=_authority(),
    )
    assert calls == ["https://writer.example/feed"]
    assert result.document_ids == ("doc-g1",)


def test_substack_rejects_unreviewed_feed_scope_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "acquisition.substack.client.fetch_feed", lambda *args, **kwargs: pytest.fail("fetched")
    )
    provider = SubstackSubscriptionGatherProvider(("https://changed.example/feed",))
    reviewed = substack_subscription_configuration_sha256(("https://reviewed.example/feed",))
    with pytest.raises(GatherNotDispatched, match="differs from reviewed"):
        provider.execute(
            query="agents",
            source_plan=_plan(GatherSource.SUBSTACK, configuration_sha256=reviewed),
            idempotency_key="call",
            authority=_authority(),
        )


def test_substack_requires_explicit_unique_subscriptions() -> None:
    with pytest.raises(ValueError, match="explicit subscribed"):
        SubstackSubscriptionGatherProvider(())
    with pytest.raises(ValueError, match="unique"):
        SubstackSubscriptionGatherProvider(("https://x/feed", "https://x/feed"))
