"""Backend grounder bridge — the proto-grounder (Sprint 3 day 3-4).

Subscribes to ``claim.challenge_raised`` events. For each challenge:

1. Resolves the document scope from the envelope's ``document_id``.
2. Runs ``substrate.graph.search.search()`` against the chunks scoped
   to that document, using the claim text as the semantic query.
   Returns top-K most-relevant chunks (default K=5).
3. Builds a context pack: param_version_stamp + phase_metadata +
   graph_evidence (the retrieved chunks) + session (the claim text +
   user's challenge question).
4. Dispatches a ``grounder`` role call asking the model to decide:
   - GROUNDED  → which chunk + confidence?
   - NOT GROUNDED → which of 4 reason categories?
5. Emits ``claim.grounding_check_passed`` with the located region id
   when grounded, or ``claim.grounding_check_failed`` with a closed
   reason Literal when not.

The proto-grounder uses the chunks the wrestling bridge populates from
region selections (Sprint 3 day 2-3). When the user challenges a claim
sourced from regions they highlighted, the grounder gets a real
chance to confirm or refute against the document the user is
actually wrestling with.

Mirrors the structure of ``wrestling.py`` (the proto-note_taker):
async handler closed over the broadcaster, registered against
``ActionType.CLAIM_CHALLENGE_RAISED``. The real ``grounder`` role
(skills/verification/) arrives in Sprint 4-5 when the role catalog
matures.
"""

from __future__ import annotations

import os
import sys

# Direct import — interfaces/research/api/ depends on substrate.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from processing.embedding import (  # noqa: E402
    EmbeddingProvider,
    default_embedding_provider,
)
from roles.grounder import (  # noqa: E402
    GROUNDER_ROLE_PROMPT,
    parse_grounder_response,
)
from runtime.db_lock import connect_read  # noqa: E402
from substrate.constants import ANTIEK_PARAM_VERSION  # noqa: E402
from substrate.context_pack import LayerSource, assemble_context_pack  # noqa: E402
from substrate.dispatch import ProviderError, dispatch  # noqa: E402
from substrate.dispatch.session_routing import dispatch_routing_kwargs  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized, search  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    ClaimChallengeRaisedPayload,
    ClaimGroundingCheckFailedPayload,
    ClaimGroundingCheckPassedPayload,
    Event,
)

from .broadcast import EventBroadcaster  # noqa: E402

# Top-K chunks to surface to the grounder. 5 is enough for a tight
# decision; more dilutes the prompt and increases cost.
GROUNDING_SEARCH_TOP_K = 5


# ---------------------------------------------------------------------------
# Region-id helpers
# ---------------------------------------------------------------------------


def _chunk_to_region_id(chunk_id: str) -> str:
    """Reverse of ``wrestling._region_to_chunk_id``. Lets the grounder
    map a located chunk back to the region_id the surface knows about
    so the UI can highlight the source passage."""
    suffix = chunk_id[len("chunk-"):] if chunk_id.startswith("chunk-") else chunk_id
    return f"r-{suffix}"


# ---------------------------------------------------------------------------
# Search + format helpers
# ---------------------------------------------------------------------------


def _search_chunks_for_claim(
    db_path: str,
    *,
    document_id: str | None,
    claim_text: str,
    embedder: EmbeddingProvider,
    top_k: int = GROUNDING_SEARCH_TOP_K,
) -> list[dict]:
    """Read-side query against ``substrate.graph.search``. Scoped to
    ``document_id`` when set; spanning all chunks otherwise (the
    wrestling bridge always sets document_id, but the grounder
    handles None defensively in case a future caller doesn't)."""
    ensure_initialized(db_path)
    con = connect_read(db_path)
    try:
        result = search(
            con, claim_text, model=embedder,
            top_k=top_k, document_id=document_id,
        )
    finally:
        con.close()
    return result["results"]


def _render_chunks_for_prompt(chunks: list[dict]) -> str:
    """Format the search results for the grounder prompt. Each chunk
    gets a numbered entry with its chunk_id and full text excerpt so
    the model can quote it back."""
    if not chunks:
        return "(no chunks in the source document yet)"
    lines = []
    for i, c in enumerate(chunks, start=1):
        lines.append(
            f"[{i}] chunk_id={c['chunk_id']} "
            f"(similarity={c['similarity']:.3f}, tier={c['source_tier']}):\n"
            f"  \"{c['chunk_text']}\""
        )
    return "\n\n".join(lines)


def _parse_grounder_response(
    text: str,
) -> tuple[bool, str | None, float, str | None]:
    """Back-compat shim. The real parser lives at
    ``roles.grounder.parse_grounder_response`` (Sprint 4 day 4-5
    extraction). Existing tests import this name + the tuple shape;
    keep the wrapper to avoid disturbing the test suite during the
    role-module promotion."""
    v = parse_grounder_response(text)
    return v.grounded, v.located_chunk_id, v.confidence, v.reason


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------


def make_grounding_handler(
    broadcaster: EventBroadcaster,
    *,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
):
    """Build the handler closed over a broadcaster + db path +
    embedder. Registered against ``ActionType.CLAIM_CHALLENGE_RAISED``;
    on fire it produces a passed/failed event and broadcasts it."""
    resolved_db = db_path or default_db_path()

    async def handle_claim_challenge_raised(event: Event) -> None:
        if not isinstance(event.payload, ClaimChallengeRaisedPayload):
            return  # defensive — handler keyed on action_type
        if not event.document_id:
            return  # wrestling validator requires document_id; defensive

        challenge = event.payload
        claim_text = challenge.claim_text.strip()
        if not claim_text:
            return  # nothing to ground

        # Resolve the embedder lazily so env-var overrides + test
        # injection both take effect.
        emb = embedder if embedder is not None else default_embedding_provider()

        # 1. Search chunks scoped to the document being challenged.
        try:
            chunks = _search_chunks_for_claim(
                resolved_db,
                document_id=event.document_id,
                claim_text=claim_text,
                embedder=emb,
            )
        except Exception as exc:  # pragma: no cover — diagnostic
            print(
                f"grounding.handle: chunk search failed — {exc!r}",
                flush=True,
            )
            chunks = []

        searched_chunk_ids = [c["chunk_id"] for c in chunks]
        searched_region_ids = [_chunk_to_region_id(cid) for cid in searched_chunk_ids]

        # 2. Build context pack.
        pack = assemble_context_pack(
            role="grounder",
            investigation_id=event.investigation_id,
            layers=[
                LayerSource(
                    kind="param_version_stamp",
                    source="antiek",
                    content=f"ANTIEK_PARAM_VERSION={ANTIEK_PARAM_VERSION}",
                ),
                LayerSource(
                    kind="phase_metadata",
                    source="loop2.grounding",
                    content=(
                        f"loop=wrestling.grounding investigation={event.investigation_id} "
                        f"document={event.document_id} "
                        f"challenged_claim_id={challenge.challenged_claim_id or '<external>'} "
                        f"anchor_region={challenge.anchor_region_id or '<none>'}"
                    ),
                ),
                LayerSource(
                    kind="graph_evidence",
                    source=f"chunks:{len(chunks)}",
                    content=_render_chunks_for_prompt(chunks),
                ),
                LayerSource(
                    kind="session",
                    source="claim_challenge",
                    content=(
                        f"Claim being checked:\n\"{claim_text}\"\n\n"
                        f"User's challenge:\n{challenge.user_question}"
                    ),
                ),
            ],
            parent_event_id=event.event_id,
        )

        full_prompt = pack.text + "\n\n" + GROUNDER_ROLE_PROMPT

        # 3. Dispatch grounder role.
        try:
            result = dispatch(
                full_prompt,
                "grounder",
                investigation_id=event.investigation_id,
                context_pack_event_id=pack.event_id,
                parent_event_id=event.event_id,
                **dispatch_routing_kwargs(event.investigation_id),
            )
            response_text = result.text
            policy_id = f"{result.provider}/{result.model}"
        except (ProviderError, KeyError) as exc:
            # Surface the failure as an ambiguous-grounding-check-failed
            # so the user sees something rather than silence. The
            # wrestling-fallback policy_id stamp marks it as a synthetic
            # event for the RL trajectory consumer to filter.
            response_text = (
                "Could not dispatch a grounder call: "
                f"{type(exc).__name__}: {exc}"
            )
            policy_id = "grounding-fallback/no-provider"
            # Skip the LLM parse path; emit ambiguous fail directly.
            _emit_grounding_failed(
                event,
                challenge=challenge,
                reason="ambiguous",
                searched_region_ids=searched_region_ids,
                policy_id=policy_id,
                broadcaster=broadcaster,
            )
            return

        # 4. Parse + emit.
        grounded, chunk_id, confidence, reason = _parse_grounder_response(response_text)

        if grounded and chunk_id and chunk_id in searched_chunk_ids:
            await _emit_grounding_passed(
                event,
                challenge=challenge,
                located_chunk_id=chunk_id,
                confidence=confidence,
                policy_id=policy_id,
                broadcaster=broadcaster,
            )
        else:
            # If the model said grounded=true but with a chunk_id not in
            # our search results, that's a hallucination — treat as
            # ambiguous (the model picked an id that didn't exist).
            final_reason = reason or ("ambiguous" if grounded else "absent_from_source")
            await _emit_grounding_failed_async(
                event,
                challenge=challenge,
                reason=final_reason,
                searched_region_ids=searched_region_ids,
                policy_id=policy_id,
                broadcaster=broadcaster,
            )

    return handle_claim_challenge_raised


async def _emit_grounding_passed(
    event: Event,
    *,
    challenge: ClaimChallengeRaisedPayload,
    located_chunk_id: str,
    confidence: float,
    policy_id: str,
    broadcaster: EventBroadcaster,
) -> None:
    located_region = _chunk_to_region_id(located_chunk_id)
    eid = emit_typed(
        event.investigation_id,
        ClaimGroundingCheckPassedPayload(
            claim_id=challenge.challenged_claim_id,
            claim_text=challenge.claim_text,
            located_region_id=located_region,
            confidence=confidence,
        ),
        parent_event_id=event.event_id,
        role="grounder",
        document_id=event.document_id,
        policy_id=policy_id,
    )
    await _broadcast_emitted(event, eid, broadcaster)


def _emit_grounding_failed(
    event: Event,
    *,
    challenge: ClaimChallengeRaisedPayload,
    reason: str,
    searched_region_ids: list[str],
    policy_id: str,
    broadcaster: EventBroadcaster,
) -> str | None:
    """Synchronous variant — used by the provider-failure branch which
    needs to bail without awaiting the broadcast (handler still runs
    inside an async function, but the caller has already decided to
    skip the LLM parse path)."""
    return emit_typed(
        event.investigation_id,
        ClaimGroundingCheckFailedPayload(
            claim_id=challenge.challenged_claim_id,
            claim_text=challenge.claim_text,
            reason=reason,  # type: ignore[arg-type]
            searched_regions=searched_region_ids,
        ),
        parent_event_id=event.event_id,
        role="grounder",
        document_id=event.document_id,
        policy_id=policy_id,
    )
    # Note: provider-failure path doesn't broadcast — the WS client
    # will see the event on the next trajectory fetch. Acceptable
    # because this path is rare and adding await machinery here would
    # complicate the early-return.


async def _emit_grounding_failed_async(
    event: Event,
    *,
    challenge: ClaimChallengeRaisedPayload,
    reason: str,
    searched_region_ids: list[str],
    policy_id: str,
    broadcaster: EventBroadcaster,
) -> None:
    eid = emit_typed(
        event.investigation_id,
        ClaimGroundingCheckFailedPayload(
            claim_id=challenge.challenged_claim_id,
            claim_text=challenge.claim_text,
            reason=reason,  # type: ignore[arg-type]
            searched_regions=searched_region_ids,
        ),
        parent_event_id=event.event_id,
        role="grounder",
        document_id=event.document_id,
        policy_id=policy_id,
    )
    await _broadcast_emitted(event, eid, broadcaster)


async def _broadcast_emitted(
    event: Event,
    emitted_event_id: str | None,
    broadcaster: EventBroadcaster,
) -> None:
    """Look up the just-emitted event in the trajectory and broadcast
    it so subscribed WS clients see the grounder's verdict in real
    time. Cheap: trajectory walk + one model_validate."""
    if emitted_event_id is None:
        return
    for row in reversed(trajectory(event.investigation_id)):
        if row.get("event_id") == emitted_event_id:
            try:
                emitted = Event.model_validate(row)
                await broadcaster.broadcast(emitted)
            except Exception:  # pragma: no cover — never block on broadcast
                pass
            return


def register_handlers(
    broadcaster: EventBroadcaster,
    *,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
) -> None:
    """Wire every grounding handler into the broadcaster. Called once
    at app startup from ``app.create_app``."""
    broadcaster.register_handler(
        ActionType.CLAIM_CHALLENGE_RAISED.value,
        make_grounding_handler(broadcaster, db_path=db_path, embedder=embedder),
    )
