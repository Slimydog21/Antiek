"""BYOK X pipeline runner (Personal-Reading Lane SPR-08, M3).

Given a registered :class:`~runtime.byok.pipelines.BYOKPipeline`, decrypt the
operator's own X key in-process (M1), pull tweets/threads with the BYOK X API v2
client within the key's OWN tier limits, map them through the EXISTING
``acquisition/twitter`` adapter, and write them as ``content_class='personal_
reading'`` / ``document_type='social_thread'`` through the single box-bounded
writer.

§16 BOX-BOUNDED / single-writer. The runner adds NO second connection and NO
second runtime: every DB write funnels through
``acquisition.twitter.adapter.ingest_twitter_thread`` →
``runtime.db_lock.connect_write(purpose="acquisition/twitter")``. The runner is
OPERATOR-INVOKED — there is NO scheduler, NO daemon, NO polling loop here (the
"make the feed live" cadence is SPR-09's operator-invoked refresh, deliberately
out of scope; adding it here would recreate the §16 second-runtime hazard).

NEVER LOGS THE KEY. The runner never reveals, logs, prints, or emits the
decrypted key — it hands the ``cred_id`` to the client, which decrypts behind a
:class:`SecretStr` and reads ``.reveal()`` only to set the auth header. There are
zero ``logging`` / ``print`` / ``emit_typed`` call sites in this module that
receive the key or the SecretStr.

The X API client is INJECTABLE (``client=...``) so the deterministic test drives
a fixture-backed fake with NO network; the live path is the operator's own smoke.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from acquisition.twitter.adapter import (
    IngestTwitterResult,
    ingest_twitter_thread,
)
from acquisition.twitter.api_client import XApiClient, to_thread
from runtime.byok.pipelines import BYOKPipeline, get_pipeline
from substrate.constants import PERSONAL_READING_CONTENT_CLASS


class _ClientLike(Protocol):
    """The slice of XApiClient the runner uses (so a test fake can stand in)."""

    def recent_search(self, query: str) -> list[dict]: ...
    def user_timeline(self, user_id: str) -> list[dict]: ...
    def conversation(self, conversation_id: str) -> list[dict]: ...


@dataclass(frozen=True)
class RunPipelineResult:
    """What a run produced: the per-thread ingest results + a count."""

    pipeline_id: str
    threads_ingested: int
    results: tuple[IngestTwitterResult, ...]


def _fetch_for_pipeline(client: _ClientLike, pipeline: BYOKPipeline) -> list[dict]:
    """Pull the raw tweet dicts for a pipeline kind. ``general_feed`` uses
    recent-search over the account handle (or a query seed if present);
    ``thread_specific`` uses a conversation lookup keyed on the seed (a
    conversation/tweet id) or a recent-search if the seed is a query."""
    if pipeline.pipeline_kind == "general_feed":
        query = pipeline.seed or f"from:{pipeline.account_handle}"
        return client.recent_search(query)
    if pipeline.pipeline_kind == "thread_specific":
        seed = pipeline.seed or ""
        if seed.isdigit():
            return client.conversation(seed)
        return client.recent_search(seed)
    # pipelines.register_pipeline already validates the kind, so this is defensive.
    raise ValueError(f"unsupported pipeline_kind: {pipeline.pipeline_kind}")


def run_pipeline(
    pipeline_id: str,
    *,
    db_path: str | None = None,
    config_path: str | None = None,
    artifact_path: str | None = None,
    key_bytes: bytes | None = None,
    key_file: str | None = None,
    client: _ClientLike | None = None,
    embedder: Any = None,
) -> RunPipelineResult:
    """Run a registered pipeline → ingest its threads as ``personal_reading``.

    Resolves the pipeline config (M2), builds (or accepts an injected) BYOK X API
    client bound to the pipeline's ``cred_id`` (M1), fetches tweets for the
    pipeline kind, groups them into threads by ``conversation_id``, maps each to a
    ``TwitterThread`` (reusing the adapter model), and ingests each through
    ``ingest_twitter_thread(content_class=PERSONAL_READING_CONTENT_CLASS)`` — so
    every resulting row is ``document_type='social_thread'`` AND
    ``content_class='personal_reading'``.

    The content_class is the IMPORTED CONSTANT (never the string literal), passed
    explicitly so the lane is auditable at this call site.
    """
    pipeline = get_pipeline(pipeline_id, config_path=config_path)
    investigation_id = pipeline.investigation_id or f"byok-x-{pipeline.account_handle}"

    api: _ClientLike = client or XApiClient(
        cred_id=pipeline.cred_id,
        artifact_path=artifact_path,
        key_bytes=key_bytes,
        key_file=key_file,
    )

    tweets = _fetch_for_pipeline(api, pipeline)
    threads = _group_into_threads(tweets, default_handle=pipeline.account_handle)

    results: list[IngestTwitterResult] = []
    for thread in threads:
        result = ingest_twitter_thread(
            thread,
            investigation_id=investigation_id,
            # The Personal-Reading Lane: X content lands personal_reading
            # (owner-only, never served / attributed / trained). The IMPORTED
            # CONSTANT is passed — never the "personal_reading" literal.
            content_class=PERSONAL_READING_CONTENT_CLASS,
            db_path=db_path,
            embedder=embedder,
        )
        results.append(result)

    return RunPipelineResult(
        pipeline_id=pipeline_id,
        threads_ingested=len(results),
        results=tuple(results),
    )


def _group_into_threads(tweets: list[dict], *, default_handle: str) -> list[Any]:
    """Group flat tweet dicts into ``TwitterThread`` objects by conversation_id.

    The root of each thread is the conversation_id; tweets with no conversation_id
    fall back to grouping by their own tweet_id (a standalone tweet = a one-tweet
    thread)."""
    by_conv: dict[str, list[dict]] = {}
    for tw in tweets:
        conv = str(tw.get("conversation_id") or tw.get("tweet_id") or "")
        if not conv:
            continue
        by_conv.setdefault(conv, []).append(tw)

    threads: list[Any] = []
    for conv_id, group in by_conv.items():
        # Order by tweet_id ascending as a stable proxy for chronology when
        # created_at is absent; the adapter renders them in this order.
        group_sorted = sorted(group, key=lambda t: str(t.get("tweet_id", "")))
        root_handle = group_sorted[0].get("author_handle") or default_handle
        root_id = conv_id
        thread_url = f"https://x.com/{root_handle.lstrip('@')}/status/{root_id}"
        thread = to_thread(
            group_sorted,
            thread_url=thread_url,
            root_tweet_id=root_id,
            author_handle=root_handle or default_handle,
        )
        threads.append(thread)
    return threads


__all__ = [
    "RunPipelineResult",
    "run_pipeline",
]
