"""Highlight -> research seed -- the pure "spin up deep research off a highlight" moment.

When the operator highlights a passage in a reading asset and wants to chase it,
the first thing the platform needs is a *question worth investigating* plus a
durable, provenance-pinned record of where that question came from. This module
is the pure, side-effect-free formulation of that record: a ``ResearchSeed``.

It is the pre-spawn half of the operator's "highlight -> floating deep-research"
flow. The post-spawn metadata (the launch event / payload the route layer emits
once an approved seed actually fires) is a different seam; importing it here would
couple this pure substrate to off-main siblings, so the types are self-contained.

Load-bearing decisions
----------------------
1. **The question is injected, not generated here.** Turning a raw highlight into
   a good question is an LLM judgment (or a human one). This module never calls a
   model -- it accepts a ``QuestionFormulator`` (a Protocol) and assembles whatever
   it returns into a validated seed. Production injects the model-backed
   formulator; tests inject a stub. There is exactly one question-framing path, so
   the pure substrate and the live model cannot drift on what a "seed" is.

2. **Seeds propose, never dispatch.** A seed leaves here in the ``proposed``
   status. Spawning the actual investigation is an operator-consent + route-layer
   concern (the floating-window bridge / launch path). The pure layer has no clock,
   no I/O, no network -- it cannot spend money or mutate the graph. ``approve_seed``
   flips status to ``approved`` but still dispatches nothing; it only records that
   consent was given. The launch gate is therefore structural, not conventional: a
   consumer that only launches ``approved`` seeds cannot be bypassed by a seed that
   skipped this module.

3. **Identity is content-addressed.** ``seed_id`` is a sha256 over the highlight
   provenance + the formulated question (canonical JSON). The same highlight + the
   same question + the same parent == the same seed. The rationale and status are
   intentionally excluded from the id: rationale is explanatory, status is
   lifecycle, neither is identity. A reformulated question is therefore a *new*
   seed (correctly), and re-approving an approved seed is a no-op (idempotent).

4. **Unknowns surface as ``None``.** A highlight may not yet have a stable
   ``highlight_id`` (before persistence), and a parent asset's title may be
   unknown. Those are ``None`` -- never fabricated to an empty string or a
   placeholder -- and ``None`` participates explicitly in the content hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Protocol

from pydantic import BaseModel

SEED_SCHEMA_VERSION: Literal[1] = 1

SeedStatus = Literal["proposed", "approved"]


class InvalidSeedError(Exception):
    """Raised when a seed cannot be formulated or transitioned from the given inputs.

    An empty highlight or question has nothing to chase; a status transition that
    violates the lifecycle has no honest result. We fail loudly rather than
    fabricate a seed around placeholder text or silently drop a transition.
    """


class Highlight(BaseModel):
    """A highlighted passage in a parent asset, with its provenance.

    ``highlight_id`` and ``scope`` are optional: a highlight exists the moment the
    operator selects text, before it has been persisted (no id yet) or pinned to a
    precise location (no scope yet). Both surface as ``None`` until known.
    """

    text: str
    parent_asset_id: str
    highlight_id: str | None = None
    scope: str | None = None


class ParentAssetContext(BaseModel):
    """The asset a highlight lives in -- minimal context for question framing."""

    asset_id: str
    title: str | None = None
    asset_kind: str | None = None


class FormulatedQuestion(BaseModel):
    """A question produced by a ``QuestionFormulator``.

    ``rationale`` is the formulator's explanation of *why this question* follows
    from the highlight. It is auditable provenance, not identity, so it does not
    participate in ``seed_id``.
    """

    question: str
    rationale: str | None = None


class QuestionFormulator(Protocol):
    """Turn a highlight + parent context into a single chasable question.

    Pure-seam contract: implementations may call a model or a human, but they must
    return a ``FormulatedQuestion`` and perform no graph mutation or dispatch. The
    pure module trusts the return shape and validates it.
    """

    def formulate(
        self, highlight: Highlight, context: ParentAssetContext
    ) -> FormulatedQuestion:
        ...


class ResearchSeed(BaseModel):
    """A chasable question pinned to the highlight that spawned it.

    Leaves the pure layer ``proposed``; the route layer is the only thing that may
    launch an investigation from an ``approved`` seed. ``rationale`` and ``status``
    are deliberately excluded from identity (see ``seed_id``): two seeds with the
    same question off the same highlight are the same seed regardless of their
    lifecycle state or explanation.
    """

    schema_version: Literal[1] = SEED_SCHEMA_VERSION
    seed_id: str
    question: str
    highlight: Highlight
    parent_asset: ParentAssetContext
    rationale: str | None = None
    status: SeedStatus = "proposed"
    superseded_by: str | None = None


def _identity_hash(highlight: Highlight, question: str) -> str:
    """Stable sha256 over the highlight provenance + the formulated question.

    ``parent_asset_id`` is part of the highlight, so a highlight reused across
    assets is correctly distinct. ``None`` fields contribute an explicit token, so
    an unknown highlight id is never silently coerced into an empty-string id.
    """
    identity = {
        "question": question,
        "highlight": {
            "text": highlight.text,
            "parent_asset_id": highlight.parent_asset_id,
            "highlight_id": highlight.highlight_id,
            "scope": highlight.scope,
        },
    }
    blob = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def formulate_research_seed(
    highlight: Highlight,
    context: ParentAssetContext,
    *,
    formulator: QuestionFormulator,
) -> ResearchSeed:
    """Formulate a ``ResearchSeed`` from a highlight via an injected formulator.

    Validates the highlight, asks the formulator for the chasable question,
    validates the question, and assembles a ``proposed`` seed with a
    content-addressed id. Performs no dispatch; the seed is inert until
    ``approve_seed`` records operator consent and the route layer launches it.
    """
    text = highlight.text.strip()
    if not text:
        raise InvalidSeedError("A seed needs non-empty highlight text to chase.")
    if highlight.parent_asset_id != context.asset_id:
        raise InvalidSeedError(
            "Highlight parent_asset_id "
            f"{highlight.parent_asset_id!r} does not match context asset_id "
            f"{context.asset_id!r}."
        )

    normalized = highlight.model_copy(update={"text": text})
    formulated = formulator.formulate(normalized, context)
    question = formulated.question.strip()
    if not question:
        raise InvalidSeedError(
            "QuestionFormulator returned an empty question; nothing to chase."
        )

    return ResearchSeed(
        seed_id="seed_" + _identity_hash(normalized, question),
        question=question,
        highlight=normalized,
        parent_asset=context,
        rationale=formulated.rationale,
        status="proposed",
        superseded_by=None,
    )


def approve_seed(seed: ResearchSeed) -> ResearchSeed:
    """Record operator consent: flip a ``proposed`` seed to ``approved``.

    Dispatches nothing -- consent is a necessary, not sufficient, condition for the
    route layer to launch. Idempotent: approving an already-approved seed returns
    it unchanged. The transition is the only way to reach ``approved``, so the
    launch gate is structural rather than conventional.
    """
    if seed.status == "approved":
        return seed
    if seed.status != "proposed":
        raise InvalidSeedError(
            f"Seed {seed.seed_id} is in status {seed.status!r}, not 'proposed'; "
            "only a proposed seed can be approved."
        )
    return seed.model_copy(update={"status": "approved"})
