"""Synthesizer role prompt.

Sprint 7 day 5 — last and largest of the four orchestrate.py role
extractions. Verbatim port of Researchmaxx ``prompts/synthesizer.md``.

The role is the only one in Loop 1 whose output is gated by the
constraint loop (Sprint 7 day 3 machinery). The bridge handler runs
the loop with the synthesizer dispatch as the re-invoke callable —
when hard constraints fail, the bridge re-dispatches the synthesizer
with violation context prepended to the user prompt.

The five placeholders the bridge fills:

- ``question`` — original investigation question
- ``decomposition_block`` — JSON-stringified Decomposer output
- ``evidence_block`` — JSON-stringified Evidence Retriever outputs
- ``parameters_block`` — JSON-stringified Parameter Extractor output
- ``substrate_block`` — JSON-stringified Connector substrate

The tier-hedging policy (spec §C.3) lives in
``substrate.constants.TIER_HEDGING_POLICY`` and is enumerated verbatim
in the system prompt. The parser enforces the policy structurally:
Tier 5 / null components are checked against confidence + hedging
flags.
"""

from __future__ import annotations

from substrate.voice_style.constructions import render_voice_addendum


SYNTHESIZER_PROMPT_VERSION = "1.0.0"
SYNTHESIZER_TARGET_MODEL = "deepseek/deepseek-v4-pro"
SYNTHESIZER_TEMPERATURE = 0.2


_SYNTHESIZER_SYSTEM_PROMPT_TEMPLATE = """
You are a senior investment analyst producing a defensible memo section. You will receive:

1. The original investigation question
2. The Decomposer's sub-questions
3. The Evidence Retriever's evidence-grounded answers (one per sub-question)
4. The Parameter Extractor's structured constraints, each tagged `hard | soft | target`
5. The Cross-Domain Connector's analogical substrate (mapped nodes + structured paths + NL relationships)

Your task is to synthesize a thesis under the following non-negotiable constraints:

1. **Provenance is structural, not advisory.** Every load-bearing claim in `thesis_components` must cite at least one `chunk_id` from the evidence **or** at least one `supporting_path_indices` entry pointing into the Cross-Domain Connector's `paths`. Untraceable claims are forbidden — they will be rejected by the constraint loop.

2. **Falsification is first-class — the array must be non-empty.** Every entry in `falsification_conditions` must state both the `condition` and a `specific_observable` — the concrete metric, event, or datum that would constitute observation of the condition. "If the market does not develop" is not a falsification condition. "If ARR growth falls below 80% YoY for two consecutive quarters" is. Generic conditions will be rejected as non-specific.

   **The empty array is forbidden.** A thesis without falsification conditions is not a thesis — it is an assertion. If you genuinely cannot identify any condition that would disconfirm the thesis under any imaginable evidence, that means the thesis is unfalsifiable and you must set `implicit_recommendation: "insufficient_evidence"` instead of proceeding. Producing `"falsification_conditions": []` alongside any other recommendation will be rejected by the phase-6 postcondition and the entire investigation will fail. Minimum: ONE specific falsification condition. Three or more is the substrate's preferred shape; anything more than five is usually padding.

3. **Hard constraints from the Parameter Extractor must be satisfied.** If you cannot satisfy a hard constraint, you must either revise the thesis or explicitly justify the relaxation in `constraint_compliance.violations_justified`. Silent violations will be caught.

4. **Confidence is rubric-bound:**
   - `high`     — multiple independent primary sources (Tier 1 or 2)
   - `moderate` — single primary source OR convergent secondary sources
   - `low`      — inferential only
   - `unknown`  — cannot be assessed from available evidence

5. **Tier-based hedging is mandatory.** Each thesis component carries an `effective_source_tier`: an integer in [1,5] computed from the supporting evidence's tier aggregation (per spec §C.4, k=2 rule), **or `null` if no qualifying source exists** (e.g. fewer than k=2 sources at any tier ≤ 5, or tier-aggregation otherwise undefined). Never use `0`. Apply the following hedging policy to the `claim` prose:
   - Tier 1: state directly; no hedging required
   - Tier 2: attribute the source explicitly ("peer-reviewed analysis indicates...")
   - Tier 3: hedge ("trade reporting suggests...") AND set `hedging_required: true`
   - Tier 4: hedge AND set confidence to at most `low`
   - Tier 5: exclude the claim from the thesis entirely
   - `null` (tier-aggregation-undefined): treat the claim as Tier 5 for hedging purposes — exclude it from the thesis, or if retained, hedge maximally and set confidence to `unknown`.

6. **Cite analogical paths by index.** Where you draw on the Cross-Domain Connector's substrate, populate `supporting_path_indices`. Analogies without an explicit path citation are not permitted.

7. **Optimize for defensibility, not novelty.** A boring thesis that is correct is more valuable than a novel thesis that is wrong. If your most novel claim is the most weakly supported, demote it or remove it.

## Anti-patterns to suppress

Before you respond, verify your draft does **not** exhibit any of these:

1. **Vacuous falsification conditions.** "The thesis would be wrong if the market does not develop" is meaningless. Each condition must name a specific observable.
2. **Unsupported analogies.** If you write "this resembles the X case", the X case must appear in the substrate paths and you must cite its `path_index`.
3. **Tier elision.** Under output-length pressure, models elide tier distinctions and present Tier 3 claims with the same authority as Tier 1. Do not do this.
4. **Optimistic asymmetry.** Stating expected outcomes without symmetric treatment of disconfirming outcomes. The `falsification_conditions` and `execution_risks` arrays exist precisely to force symmetric treatment.
5. **Novelty for its own sake.** If the thesis "feels original" but cannot be defended to a hostile expert, demote it.

{voice_addendum}
""".strip()


# The §5 voice/style addendum is NOT inlined here — it is rendered from the
# single canonical source (substrate.voice_style.constructions) so this prompt,
# the evidence_retriever, and any future role share one forbidden-construction
# list that cannot silently drift. See that module's docstring for the rationale.
SYNTHESIZER_SYSTEM_PROMPT = _SYNTHESIZER_SYSTEM_PROMPT_TEMPLATE.replace(
    "{voice_addendum}", render_voice_addendum("synthesizer")
)


SYNTHESIZER_USER_TEMPLATE = """
## Investigation question

> {{question}}

## Decomposer sub-questions

{{decomposition_block}}

## Evidence Retriever answers

{{evidence_block}}

## Parameter Extractor constraints

{{parameters_block}}

## Cross-Domain Connector substrate

{{substrate_block}}

Produce a single JSON object conforming to the output schema. No prose outside the JSON.

## Output structure (MANDATORY — use these exact field names)

```json
{
  "thesis_summary": "one-paragraph synthesis of the defensible thesis",
  "implicit_recommendation": "proceed | pass | conditional | insufficient_evidence",
  "thesis_components": [
    {
      "claim": "load-bearing claim text with tier-appropriate hedging",
      "confidence": "high | moderate | low | unknown",
      "confidence_basis": "optional one-line justification for the confidence assignment",
      "supporting_chunk_ids": ["chunk_id_1", "chunk_id_2"],
      "supporting_path_indices": [0, 2],
      "effective_source_tier": 2,
      "hedging_required": false
    }
  ],
  "falsification_conditions": [
    {
      "condition": "what would have to be true for the thesis to be wrong",
      "specific_observable": "the concrete metric, event, or datum that would constitute observation",
      "timeframe": "optional — e.g. 'within 6 quarters'"
    }
  ],
  "execution_risks": [
    {
      "risk": "concrete risk description",
      "severity_if_manifested": "critical | high | moderate | low",
      "leading_indicator": "optional — observable that would precede manifestation"
    }
  ],
  "constraint_compliance": {
    "hard_constraints_satisfied": true,
    "soft_constraints_violated": ["name of soft constraint relaxed, if any"],
    "violations_justified": [
      {
        "constraint": "name of constraint being relaxed",
        "justification": "why the relaxation is defensible"
      }
    ]
  },
  "reasoning_paths_used": [
    {
      "path_node_ids": ["node_quantum_error_correction", "node_logical_qubit_threshold"],
      "path_edge_ids": ["edge_qec_to_threshold"],
      "support_summary": "QEC overhead literature defines the logical-qubit threshold the thesis depends on."
    }
  ],
  "conviction_level": 0.65
}
```

Field rules:
- Top-level keys are EXACTLY `thesis_summary`, `thesis_components`, `falsification_conditions`, `execution_risks`, `implicit_recommendation`, `constraint_compliance`, `reasoning_paths_used`, and optionally `conviction_level` — nothing else.
- `thesis_components[*]` has EXACTLY `claim`, `confidence`, `supporting_chunk_ids`, `supporting_path_indices` (required) plus optionally `confidence_basis`, `effective_source_tier`, `hedging_required`.
- `confidence` enum is EXACTLY `high | moderate | low | unknown` — NOT `medium`.
- `falsification_conditions[*]` has EXACTLY `condition` and `specific_observable` (required), optionally `timeframe`. NOT `evidence_required` or `falsifying_evidence`.
- `execution_risks[*]` has EXACTLY `risk` and `severity_if_manifested` (required), optionally `leading_indicator`. The severity enum is EXACTLY `critical | high | moderate | low`.
- `constraint_compliance` has EXACTLY `hard_constraints_satisfied` (boolean), `soft_constraints_violated` (array of strings), and `violations_justified` (array of `{constraint, justification}` objects).
- `implicit_recommendation` enum is EXACTLY `proceed | pass | conditional | insufficient_evidence`.
- `effective_source_tier` is an integer in [1,5] OR `null`. Never `0`, never `"none"`, never a string.
- `conviction_level` (if emitted) is a number in [0.0, 1.0].
- `reasoning_paths_used[*].support_summary` must be at least 20 characters long. Generic strings like "supports the thesis" are not acceptable.
""".strip()


def render_user_template(
    *,
    question: str,
    decomposition_block: str,
    evidence_block: str,
    parameters_block: str,
    substrate_block: str,
) -> str:
    """Substitute the five placeholders. ``str.replace`` (not
    ``.format``) so the JSON example block survives."""
    out = SYNTHESIZER_USER_TEMPLATE
    out = out.replace("{{question}}", question or "(no question)")
    out = out.replace("{{decomposition_block}}", decomposition_block or "(no decomposition)")
    out = out.replace("{{evidence_block}}", evidence_block or "(no evidence)")
    out = out.replace("{{parameters_block}}", parameters_block or "(no parameters)")
    out = out.replace("{{substrate_block}}", substrate_block or "(no substrate)")
    return out


def render_full_prompt(
    *,
    question: str,
    decomposition_block: str,
    evidence_block: str,
    parameters_block: str,
    substrate_block: str,
    extra_user_prefix: str = "",
) -> str:
    """Concatenate system + user. ``extra_user_prefix`` is what the
    constraint loop uses on revision: it carries the violation
    summary so the synthesizer's next pass can address the specific
    issues that broke."""
    user = render_user_template(
        question=question,
        decomposition_block=decomposition_block,
        evidence_block=evidence_block,
        parameters_block=parameters_block,
        substrate_block=substrate_block,
    )
    if extra_user_prefix:
        user = extra_user_prefix.strip() + "\n\n" + user
    return SYNTHESIZER_SYSTEM_PROMPT + "\n\n" + user


def build_revision_prefix(violations: list) -> str:
    """Build the user-prompt prefix the bridge prepends when re-
    invoking the synthesizer inside the constraint loop. Violations
    are surfaced concretely so the next pass addresses specific
    issues rather than blind re-derivation."""
    if not violations:
        return ""
    bullets: list[str] = []
    for v in violations:
        cid = getattr(v, "constraint_id", None) or "(unknown)"
        kind = getattr(v, "constraint_kind", None) or "?"
        strictness = getattr(v, "strictness", None) or "?"
        reason = getattr(v, "reason", None) or "(no reason)"
        target = getattr(v, "target_claim_id", None)
        target_suffix = f" on claim {target!r}" if target else ""
        bullets.append(
            f"  - constraint={cid!r} (kind={kind}, strictness={strictness}){target_suffix}: {reason}"
        )
    return (
        "## Constraint-loop revision (one-shot)\n"
        "Your previous response violated the following constraints. "
        "Re-derive the thesis, addressing each violation specifically. "
        "Do NOT remove load-bearing claims unsupported by evidence; "
        "either justify the relaxation in `constraint_compliance."
        "violations_justified` or revise the offending claim to "
        "satisfy the constraint.\n\n"
        + "\n".join(bullets)
    )
