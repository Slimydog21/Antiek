"""Evidence Retriever role prompt.

Sprint 6 day 4-5 — start of the second orchestrate.py role
extraction (the bridge handler lands in Sprint 7, building on the
seam pattern decomposer set in Day 1-2).

Verbatim port of Researchmaxx ``prompts/evidence_retriever.md``. The
system prompt is unchanged; the user template uses
``{{placeholder}}`` (double-brace) so ``render_user_template`` can
safely co-exist with the example JSON block at the tail (single-brace
``{...}``) without ``str.format`` quirks.

The five placeholders are:
- ``sub_question``       — the sub-question text from the Decomposer
- ``category``           — one of ``SubQuestionCategory`` Literals
- ``evidence_type_required`` — one of ``EvidenceTypeRequired``
- ``top_k``              — number of chunks supplied
- ``chunks_block``       — rendered chunk excerpts
- ``subgraph_block``     — rendered graph evidence

Chunks/subgraph rendering is the bridge handler's responsibility
(Sprint 7) — this module ships only the prompt-side template.
"""

from __future__ import annotations


EVIDENCE_RETRIEVER_PROMPT_VERSION = "1.0.0"
EVIDENCE_RETRIEVER_TARGET_MODEL = "deepseek/deepseek-v4-pro"
EVIDENCE_RETRIEVER_TEMPERATURE = 0.0


EVIDENCE_RETRIEVER_SYSTEM_PROMPT = """
You are an evidence analyst. You will receive a single sub-question and a context package containing:

- (a) top-k text chunks retrieved by vector similarity from the corpus, each with a stable `chunk_id` and a `source_tier` (1 = primary evidence, 5 = anonymous/aggregator)
- (b) a subgraph of knowledge-graph edges and nodes derived from those chunks, each with a stable `edge_id`

Your task is to answer the sub-question **using only the evidence in the context package**.

You must:

1. **Cite every claim by chunk_id.** Claims without chunk citations are not permitted. If you cannot answer a claim from the context, say so explicitly rather than filling gaps with general knowledge.

2. **Distinguish three evidence types per claim:**
   - `direct` — claim is stated explicitly in the cited chunks
   - `inferred` — claim follows from combining multiple cited chunks
   - `gap` — claim cannot be made from the context, recorded for completeness

3. **Assess source tier per claim.** Report `source_tier_min` — the lowest-trust tier among the chunks supporting the claim (closer to 1 = better). If a load-bearing claim rests on Tier 3 or below, raise the gap or downgrade your confidence accordingly.

4. **Do not produce confidence scores unless they have an explicit evidentiary basis.** "high confidence" because the answer feels solid is forbidden. "high confidence based on three independent primary sources, two of them SEC filings" is required.

5. **Enumerate evidentiary gaps as first-class output.** A gap is not a failure — it is information. For each gap, describe what additional retrieval would close it (a sub-query, a document type, a specific source).

6. If the context is insufficient to answer the sub-question at all, set `insufficient_evidence: true` and concentrate on enumerating the gaps that would unblock retrieval.

## Anti-patterns to suppress

Before you respond, verify your draft does **not** exhibit any of these:

1. **Confabulation to fill gaps.** If the chunks do not support a claim, the answer is "the evidence is silent on this", not a plausible-sounding fabrication. Filling gaps with general knowledge is the most damaging failure mode in this pipeline.
2. **Unjustified confidence.** Confidence is decorrelated from the model's surface fluency. `confidence_basis` must reference specific chunk counts and tiers, not the feel of the answer.
3. **Suppressing the gaps field.** Producing a complete-looking answer with `evidentiary_gaps: []` when in fact gaps exist degrades downstream constraint checking and synthesis. List the gaps even when the answer is otherwise strong.
4. **Citing chunks you did not actually use.** Every `chunk_id` in a claim must contain language that supports the claim. Pro-forma citations get caught at backtest time.
""".strip()


EVIDENCE_RETRIEVER_USER_TEMPLATE = """
Sub-question:

> {{sub_question}}

Sub-question category: `{{category}}`
Evidence type required: `{{evidence_type_required}}`

## Context package — chunks (k={{top_k}})

{{chunks_block}}

## Context package — subgraph

{{subgraph_block}}

Produce a single JSON object conforming to the output schema. No prose outside the JSON.

## Output structure (MANDATORY — use these exact field names)

```json
{
  "sub_question": "the sub-question text",
  "answer": "your evidence-grounded answer",
  "supporting_claims": [
    {
      "claim": "a specific factual claim",
      "evidence_type": "direct | inferred | gap",
      "chunk_ids": ["chunk_id_1", "chunk_id_2"],
      "edge_ids": ["edge_id_1"],
      "source_tier_min": 1,
      "confidence": "high | moderate | low | insufficient",
      "confidence_basis": "based on two independent Tier-1 SEC filings"
    }
  ],
  "evidentiary_gaps": [
    {
      "gap_description": "what is missing",
      "additional_retrieval_suggested": "what would close this gap"
    }
  ],
  "insufficient_evidence": false
}
```

Field rules:
- Top-level keys are EXACTLY `sub_question`, `answer`, `supporting_claims`, `evidentiary_gaps`, `insufficient_evidence` — nothing else.
- Claims go in `supporting_claims` (NOT `claims`).
- Each claim has EXACTLY `claim`, `evidence_type`, `chunk_ids`, `source_tier_min`, `confidence`, `confidence_basis` — plus optional `edge_ids`.
- Each gap has EXACTLY `gap_description` and optional `additional_retrieval_suggested`.
- `source_tier_min`: integer in [1,5] taken from the retrieved chunks' tiers, or `null` if no supporting chunk carries a qualifying tier. **Never use `0` — `null` is the sentinel for "below the schema floor."** The schema rejects `0`; emitting `0` will fail validation.
""".strip()


def render_user_template(
    *,
    sub_question: str,
    category: str,
    evidence_type_required: str,
    top_k: int,
    chunks_block: str,
    subgraph_block: str,
) -> str:
    """Substitute the six placeholders. ``str.replace`` (not
    ``.format``) so the JSON example block survives."""
    out = EVIDENCE_RETRIEVER_USER_TEMPLATE
    out = out.replace("{{sub_question}}", sub_question)
    out = out.replace("{{category}}", category)
    out = out.replace("{{evidence_type_required}}", evidence_type_required)
    out = out.replace("{{top_k}}", str(int(top_k)))
    out = out.replace("{{chunks_block}}", chunks_block or "(no chunks)")
    out = out.replace("{{subgraph_block}}", subgraph_block or "(no subgraph)")
    return out


def render_full_prompt(
    *,
    sub_question: str,
    category: str,
    evidence_type_required: str,
    top_k: int,
    chunks_block: str,
    subgraph_block: str,
    extra_user_prefix: str = "",
) -> str:
    """Concatenate system + user. ``extra_user_prefix`` is reserved
    for the same regeneration pattern the decomposer uses (Sprint 7
    bridge handler will wire this when it lands)."""
    user = render_user_template(
        sub_question=sub_question,
        category=category,
        evidence_type_required=evidence_type_required,
        top_k=top_k,
        chunks_block=chunks_block,
        subgraph_block=subgraph_block,
    )
    if extra_user_prefix:
        user = extra_user_prefix.strip() + "\n\n" + user
    return EVIDENCE_RETRIEVER_SYSTEM_PROMPT + "\n\n" + user
