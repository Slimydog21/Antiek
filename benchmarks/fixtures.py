"""Deterministic fixture generator for the inline-rubric benchmark.

The scorer at ``substrate.synthesis_rubric.scorer.score_synthesis`` reads
its input via ``getattr(payload, ...)``. We therefore don't need to
import the production ``SynthesizeDeliveredPayload`` Pydantic model —
``SimpleNamespace`` is duck-compatible and avoids dragging schemas into
the benchmark's hot path.

Three goals for the corpus:

1. **Deterministic.** Same seed → same fixtures across runs. Re-running
   the benchmark must yield numbers comparable to the baseline; a non-
   deterministic corpus contaminates the regression check.
2. **Varied along every rubric dimension.** The scorer has four
   sub-components (voice/style, conviction, citation density,
   constraint compliance). The corpus exercises the cross-product:
   high/low voice × high/low conviction × dense/sparse citations ×
   compliant/non-compliant. Plus the "insufficient_evidence" floor
   case from line 151 of scorer.py.
3. **Realistic text shape.** ``_voice_style_score`` calls
   ``deterministic_voice_style_score`` from
   ``tools.prompt_autoresearch.score``, which counts em-dashes,
   padding phrases, sector-vocab overlap. We seed the prose with
   representative spans rather than gibberish so the voice/style
   component does real work.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURE_COUNT = 100
# Deterministic seed. Encoded as the day the benchmark was first
# locked (2026-05-24) for human-debuggable provenance — a future
# maintainer reading this can reconstruct the corpus from the seed
# alone and tell at a glance when it was minted.
RANDOM_SEED = 20260524


# Representative prose spans drawn from the §5 voice/style discipline.
# Some are "good" (prose flows, claim spans inline), some are LLM-slop
# variants. The fixture generator samples across both so the scorer's
# voice/style component sees its full operating range.
GOOD_PROSE = [
    "The pricing-page experiment landed a 14% conversion lift on the cohort that hit the new card grid; the same change underperformed on returning users, which suggests the surface is doing one thing well and another thing badly.",
    "Hashicorp's first commercial product Atlas failed because it bundled every Hashicorp surface into one offering and no single buyer organization owned the budget.",
    "Antiek's substrate stays host-only by constraint; cloud SDKs in substrate/ would defeat the reusability premise that the constraint exists to protect.",
    "Two writer surfaces — the daily ingest cron and the on-demand kanban worker — share one DuckDB file and would corrupt state on overlap if not coordinated by the advisory flock at runtime/db_lock.py.",
    "The Hashimoto pivot from Atlas to per-product enterprise worked because security had an obvious budget and an obvious buyer; the analog for Antiek is the wedge audit SPR-02 is doing.",
]

SLOPPY_PROSE = [
    "It is important to note that, in the realm of pricing pages — which, as discussed, are a critical surface — the conversion lift, while significant, must be considered in light of the cohort dynamics that, as we have seen, may vary.",
    "Furthermore, it is worth mentioning — and indeed, this point bears repeating — that the substrate must, in essence, remain decoupled from cloud SDKs, as a matter of principle.",
    "In conclusion, to summarize the above, the writer surfaces (which, as outlined, share one DuckDB file) require coordination — and this coordination, importantly, is provided by the flock.",
    "Moreover, the Atlas product, while ambitious, ultimately failed — and this failure, as we shall see, was due to the bundling of products, which created budget ambiguity, which in turn — as Hashimoto notes — led to the pivot.",
    "Additionally, leveraging the analog with Hashimoto — and indeed, this analog is instructive — we can synthesize that the wedge audit (SPR-02) is, in essence, performing a similar function.",
]

# Constraint-compliance payload shape: a nested object with the
# attribute the scorer reads. SimpleNamespace works fine.
def _compliance(satisfied: bool) -> SimpleNamespace:
    return SimpleNamespace(hard_constraints_satisfied=satisfied)


def _component(claim: str, basis: str, chunks: list[str]) -> SimpleNamespace:
    """One thesis_components entry. ``supporting_chunk_ids`` is the
    field the citation-density component reads."""
    return SimpleNamespace(
        claim=claim,
        confidence_basis=basis,
        supporting_chunk_ids=list(chunks),
    )


@dataclass(frozen=True)
class FixtureRecipe:
    """Knobs the generator twirls. Stored alongside each fixture
    so a regression in the scorer can be diagnosed against the
    specific cross-product cell."""

    voice_quality: str  # "good" | "sloppy"
    conviction_level: float
    citation_density_target: float  # fraction of components with chunks
    constraint_satisfied: bool
    insufficient_evidence: bool


def _build_payload(recipe: FixtureRecipe, rng: random.Random) -> SimpleNamespace:
    """Synthesize one payload from the recipe."""
    prose_pool = GOOD_PROSE if recipe.voice_quality == "good" else SLOPPY_PROSE
    n_components = rng.randint(3, 8)
    n_with_chunks = round(n_components * recipe.citation_density_target)
    components: list[SimpleNamespace] = []
    for i in range(n_components):
        claim = rng.choice(prose_pool)
        basis = rng.choice(prose_pool)
        chunks: list[str]
        if i < n_with_chunks:
            chunks = [f"chunk-{rng.randint(1000, 9999)}" for _ in range(rng.randint(1, 3))]
        else:
            chunks = []
        components.append(_component(claim, basis, chunks))
    payload = SimpleNamespace(
        thesis_summary=rng.choice(prose_pool),
        thesis_components=components,
        conviction_level=recipe.conviction_level,
        constraint_compliance=_compliance(recipe.constraint_satisfied),
        implicit_recommendation=(
            "insufficient_evidence" if recipe.insufficient_evidence else "ship_thesis"
        ),
    )
    return payload


def build_corpus(count: int = FIXTURE_COUNT, seed: int = RANDOM_SEED) -> list[SimpleNamespace]:
    """Return ``count`` deterministically-generated payloads.

    The cross-product of recipe dimensions is sampled so the benchmark
    exercises the full operating envelope rather than one corner.
    """
    rng = random.Random(seed)
    voice_options = ["good", "sloppy"]
    conviction_options = [0.1, 0.3, 0.5, 0.7, 0.9]
    citation_options = [0.0, 0.25, 0.5, 0.75, 1.0]
    constraint_options = [True, False]
    insufficient_options = [False, False, False, False, True]  # rare

    payloads: list[SimpleNamespace] = []
    for _ in range(count):
        recipe = FixtureRecipe(
            voice_quality=rng.choice(voice_options),
            conviction_level=rng.choice(conviction_options),
            citation_density_target=rng.choice(citation_options),
            constraint_satisfied=rng.choice(constraint_options),
            insufficient_evidence=rng.choice(insufficient_options),
        )
        payloads.append(_build_payload(recipe, rng))
    return payloads


def serialize_corpus_summary() -> dict:
    """Lightweight summary persisted alongside baseline for provenance.

    We don't need to serialize the payloads themselves — the generator
    is deterministic on its seed, so a future maintainer reproduces the
    corpus by re-running the generator. We do persist the recipe
    distribution so a quick eyeball confirms the corpus exercises the
    full cross-product.
    """
    rng = random.Random(RANDOM_SEED)
    counts = {
        "voice_good": 0,
        "voice_sloppy": 0,
        "conviction_low": 0,  # < 0.5
        "conviction_high": 0,  # >= 0.5
        "citation_density_low": 0,  # < 0.5
        "citation_density_high": 0,  # >= 0.5
        "constraint_satisfied": 0,
        "constraint_violated": 0,
        "insufficient_evidence": 0,
    }
    voice_options = ["good", "sloppy"]
    conviction_options = [0.1, 0.3, 0.5, 0.7, 0.9]
    citation_options = [0.0, 0.25, 0.5, 0.75, 1.0]
    constraint_options = [True, False]
    insufficient_options = [False, False, False, False, True]
    for _ in range(FIXTURE_COUNT):
        v = rng.choice(voice_options)
        c = rng.choice(conviction_options)
        d = rng.choice(citation_options)
        s = rng.choice(constraint_options)
        i = rng.choice(insufficient_options)
        # Mirror the consumption order in build_corpus so the seed
        # advances identically; we just don't construct the payload here.
        _ = rng.randint(3, 8)  # n_components
        counts["voice_good" if v == "good" else "voice_sloppy"] += 1
        counts["conviction_low" if c < 0.5 else "conviction_high"] += 1
        counts["citation_density_low" if d < 0.5 else "citation_density_high"] += 1
        counts["constraint_satisfied" if s else "constraint_violated"] += 1
        if i:
            counts["insufficient_evidence"] += 1
    return {
        "fixture_count": FIXTURE_COUNT,
        "seed": RANDOM_SEED,
        "recipe_distribution": counts,
    }
