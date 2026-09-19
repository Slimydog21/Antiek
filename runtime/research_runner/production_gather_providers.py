"""Production acquisition wrappers for authorized multi-source gather.

These wrappers do not create a second ingestion path.  They translate the
reviewed gather protocol into the existing discovery/admission adapters and
return only canonical document IDs.  Substack is intentionally subscription
scoped: Antiek has an RSS connector, not a global Substack search API.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from runtime.research_runner.authorized_gather import (
    GatherNotDispatched,
    GatherProviderResult,
)
from runtime.research_runner.gather_plan import GatherSource, GatherSourcePlan
from substrate.investigation_tenancy import InvestigationAuthority


def _cost_micros(value: object) -> int:
    amount = Decimal(str(value))
    micros = amount * 1_000_000
    if not amount.is_finite() or amount < 0 or micros != micros.to_integral_value():
        raise RuntimeError("provider cost is not representable as exact non-negative micros")
    return int(micros)


def _require_plan(source_plan: GatherSourcePlan, source: GatherSource) -> None:
    if source_plan.source is not source:
        raise GatherNotDispatched("source plan does not match provider")


def substack_subscription_configuration_sha256(feed_urls: tuple[str, ...]) -> str:
    """Fingerprint the exact ordered subscription scope reviewed for dispatch."""
    normalized = tuple(url.strip() for url in feed_urls)
    encoded = json.dumps(normalized, ensure_ascii=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _configuration_sha256(source: str, values: dict[str, object]) -> str:
    encoded = json.dumps(
        {"source": source, **values}, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def exa_configuration_sha256(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    return _configuration_sha256(
        "exa",
        {
            "base_url": str(env.get("EXA_BASE_URL", "https://api.exa.ai")).rstrip("/"),
            "search_path": "/search",
            "cost_micros": 5_000,
            "api_key_sha256": hashlib.sha256(
                str(env.get("EXA_API_KEY", "")).encode()
            ).hexdigest(),
        },
    )


def parallel_configuration_sha256(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    return _configuration_sha256(
        "parallel",
        {
            "base_url": str(env.get("PARALLEL_BASE_URL", "https://api.parallel.ai")).rstrip(
                "/"
            ),
            "search_path": "/v1/search",
            "mode": "basic",
            "cost_micros": 10_000,
            "api_key_sha256": hashlib.sha256(
                str(env.get("PARALLEL_API_KEY", "")).encode()
            ).hexdigest(),
        },
    )


def arxiv_configuration_sha256(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    return _configuration_sha256(
        "arxiv",
        {
            "base_url": str(
                env.get("ANTIEK_ARXIV_BASE_URL", "https://export.arxiv.org/api/query")
            ),
            "sort": "relevance",
            "content": "abstract",
        },
    )


@dataclass(slots=True)
class ExaGatherProvider:
    """Search Exa and promote accepted discoveries through ``ingest_url``."""

    legal_gate: Any
    db_path: str | None = None
    client: Any = None
    embedder: Any = None
    events_dir: str | None = None
    source: GatherSource = GatherSource.EXA
    configuration_sha256: str | None = None

    def execute(
        self,
        *,
        query: str,
        source_plan: GatherSourcePlan,
        idempotency_key: str,
        authority: InvestigationAuthority,
    ) -> GatherProviderResult:
        del idempotency_key
        _require_plan(source_plan, self.source)
        configuration = self.configuration_sha256 or exa_configuration_sha256()
        if source_plan.source_configuration_sha256 != configuration:
            raise GatherNotDispatched("Exa execution configuration differs from reviewed plan")
        from acquisition.search.exa.adapter import discover, promote_discovery
        from acquisition.search.exa.client import COST_PER_SEARCH_USD

        known_cost = _cost_micros(COST_PER_SEARCH_USD)
        if known_cost > source_plan.max_cost_micros:
            raise GatherNotDispatched("reviewed Exa cap is below one search call")
        proposals = discover(
            query=query,
            investigation_id=authority.investigation_id,
            num_results=source_plan.max_results,
            client=self.client,
            events_dir=self.events_dir,
            db_path=self.db_path,
        )
        documents: list[str] = []
        for proposal in proposals[: source_plan.max_results]:
            promoted = promote_discovery(
                proposal,
                investigation_id=authority.investigation_id,
                legal_gate=self.legal_gate,
                db_path=self.db_path,
                embedder=self.embedder,
                events_dir=self.events_dir,
                authority=authority,
            )
            if (
                promoted.decision == "ingested"
                and promoted.document_id
                and promoted.document_id not in documents
            ):
                documents.append(promoted.document_id)
        return GatherProviderResult(tuple(documents), known_cost)


@dataclass(slots=True)
class ParallelGatherProvider:
    """Search Parallel and promote accepted discoveries through ``ingest_url``."""

    legal_gate: Any
    db_path: str | None = None
    client: Any = None
    embedder: Any = None
    events_dir: str | None = None
    session_id: str | None = None
    source: GatherSource = GatherSource.PARALLEL
    configuration_sha256: str | None = None

    def execute(
        self,
        *,
        query: str,
        source_plan: GatherSourcePlan,
        idempotency_key: str,
        authority: InvestigationAuthority,
    ) -> GatherProviderResult:
        _require_plan(source_plan, self.source)
        configuration = self.configuration_sha256 or parallel_configuration_sha256()
        if source_plan.source_configuration_sha256 != configuration:
            raise GatherNotDispatched("Parallel execution configuration differs from reviewed plan")
        from acquisition.search.parallel.adapter import discover, promote_discovery
        from acquisition.search.parallel.client import COST_PER_SEARCH_USD

        known_cost = _cost_micros(COST_PER_SEARCH_USD)
        if known_cost > source_plan.max_cost_micros:
            raise GatherNotDispatched("reviewed Parallel cap is below one search call")
        if source_plan.max_results > 50:
            raise GatherNotDispatched("Parallel production search supports at most 50 results")
        proposals = discover(
            query=query,
            investigation_id=authority.investigation_id,
            num_results=source_plan.max_results,
            client=self.client,
            events_dir=self.events_dir,
            session_id=self.session_id or idempotency_key,
        )
        documents: list[str] = []
        for proposal in proposals[: source_plan.max_results]:
            promoted = promote_discovery(
                proposal,
                investigation_id=authority.investigation_id,
                legal_gate=self.legal_gate,
                db_path=self.db_path,
                embedder=self.embedder,
                events_dir=self.events_dir,
                authority=authority,
            )
            if (
                promoted.decision == "ingested"
                and promoted.document_id
                and promoted.document_id not in documents
            ):
                documents.append(promoted.document_id)
        return GatherProviderResult(tuple(documents), known_cost)


@dataclass(slots=True)
class ArxivGatherProvider:
    """Query governed arXiv search and admit abstract documents."""

    db_path: str | None = None
    client: Any = None
    throttle: Any = None
    embedder: Any = None
    source: GatherSource = GatherSource.ARXIV
    configuration_sha256: str | None = None
    base_url: str | None = None

    def execute(
        self,
        *,
        query: str,
        source_plan: GatherSourcePlan,
        idempotency_key: str,
        authority: InvestigationAuthority,
    ) -> GatherProviderResult:
        del idempotency_key
        _require_plan(source_plan, self.source)
        configuration = self.configuration_sha256 or arxiv_configuration_sha256()
        if source_plan.source_configuration_sha256 != configuration:
            raise GatherNotDispatched("arXiv execution configuration differs from reviewed plan")
        from acquisition.arxiv.adapter import ingest_paper
        from acquisition.arxiv.client import search

        papers = search(
            query=query,
            max_results=source_plan.max_results,
            client=self.client,
            base_url=self.base_url,
            throttle=self.throttle,
        )
        documents: list[str] = []
        for paper in papers[: source_plan.max_results]:
            result = ingest_paper(
                paper,
                investigation_id=authority.investigation_id,
                db_path=self.db_path,
                embedder=self.embedder,
                authority=authority,
            )
            if result.status != "skipped" and result.document_id not in documents:
                documents.append(result.document_id)
        return GatherProviderResult(tuple(documents), 0)


@dataclass(slots=True)
class SubstackSubscriptionGatherProvider:
    """Search posts in explicit subscribed RSS feeds; never global Substack."""

    feed_urls: tuple[str, ...]
    db_path: str | None = None
    client: Any = None
    embedder: Any = None
    source: GatherSource = GatherSource.SUBSTACK

    def __post_init__(self) -> None:
        normalized = tuple(url.strip() for url in self.feed_urls)
        if not normalized or any(not url for url in normalized):
            raise ValueError("Substack gather requires explicit subscribed feed URLs")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Substack subscribed feed URLs must be unique")
        self.feed_urls = normalized

    def execute(
        self,
        *,
        query: str,
        source_plan: GatherSourcePlan,
        idempotency_key: str,
        authority: InvestigationAuthority,
    ) -> GatherProviderResult:
        del idempotency_key
        _require_plan(source_plan, self.source)
        expected_configuration = substack_subscription_configuration_sha256(self.feed_urls)
        if source_plan.source_configuration_sha256 != expected_configuration:
            raise GatherNotDispatched("Substack subscription scope differs from reviewed plan")
        from acquisition.substack.adapter import ingest_post
        from acquisition.substack.client import fetch_feed

        terms = tuple(part.casefold() for part in query.split() if part.strip())
        documents: list[str] = []
        for feed_url in self.feed_urls:
            if len(documents) >= source_plan.max_results:
                break
            publication = fetch_feed(
                feed_url,
                max_posts=source_plan.max_results,
                client=self.client,
            )
            for post in publication.posts:
                haystack = f"{post.title}\n{post.body_markdown}".casefold()
                if terms and not all(term in haystack for term in terms):
                    continue
                result = ingest_post(
                    post,
                    publication=publication,
                    investigation_id=authority.investigation_id,
                    db_path=self.db_path,
                    embedder=self.embedder,
                    authority=authority,
                )
                if result.status != "skipped" and result.document_id not in documents:
                    documents.append(result.document_id)
                if len(documents) >= source_plan.max_results:
                    break
        return GatherProviderResult(tuple(documents), 0)


__all__ = [
    "ArxivGatherProvider",
    "ExaGatherProvider",
    "ParallelGatherProvider",
    "SubstackSubscriptionGatherProvider",
    "arxiv_configuration_sha256",
    "exa_configuration_sha256",
    "parallel_configuration_sha256",
    "substack_subscription_configuration_sha256",
]
