"""Knowledge-extraction prompt assembly (Phase 8).

Verbatim port of Researchmaxx ``knowledge_extraction.py`` (Sprint 6 day
2-3). The system prompt enumerates the six section names that
downstream patching keys on — the prompt and ``patch.py`` MUST agree
on the section vocabulary, so the closed set lives here as
``EXTRACTION_SECTIONS`` and is asserted equal by
``tests/test_skills_domain.py``.

Confidence vocabulary mirrors the four tiers the upstream uses
(``Measured`` / ``Calculated`` / ``Inferred`` / ``Speculated``) — same
discipline as the rest of the substrate's confidence Literals.

The system + user template are kept as separate constants so the LLM
call site can pass them through whatever dispatch shape it has
(Anthropic-style system/user separation, OpenAI-style chat
messages, prefix-and-concatenate for legacy clients).
"""

from __future__ import annotations

from typing import Any

# The closed section vocabulary. Drift between this and the prompt
# body or ``patch.py``'s section-pattern matcher is caught by tests.
EXTRACTION_SECTIONS: frozenset[str] = frozenset({
    "Domain Fundamentals",
    "Key Players",
    "Quantitative Benchmarks",
    "Competitive Dynamics",
    "Open Questions",
    "Monitoring Checklist",
})

# Finding confidence tiers. Used by the patcher to render the
# ``[Confidence]`` bullet prefix.
EXTRACTION_CONFIDENCE_TIERS: frozenset[str] = frozenset({
    "Measured", "Calculated", "Inferred", "Speculated",
})


EXTRACTION_SYSTEM_PROMPT = """\
You are a knowledge curator extracting durable findings from research syntheses.
Your job is to extract only facts that WILL still be true in 6+ months.

For each finding, classify by section and confidence level.

EXTRACTION RULES:
- Include: fundamental mechanisms, constraints, benchmarks with dates,
  competitive positions that define dynamics, strategic moats, key uncertainties
- Skip: temporary market conditions, transient news, single-customer wins,
  quarterly earnings, minor personnel changes
- When uncertain, include with [Speculated] confidence tag

SECTIONS (choose the best fit for each finding):
- Domain Fundamentals: core mechanisms, constraints, physics
- Key Players: company positions, strategies, funding, competitive stance
- Quantitative Benchmarks: numbers with dates and sources
- Competitive Dynamics: relationships between players, market structure
- Open Questions: unresolved uncertainties that structure the domain
- Monitoring Checklist: indicators to track, thresholds that change the thesis

Output structure (MANDATORY — use these exact field names):
Return a single JSON object. Keys are section names from the list above.
Values are arrays of finding objects. Each finding object MUST contain
exactly these four fields, named EXACTLY as written below — no variations,
no extra fields, no nested wrapping:
  - "text"          : string — one concise bullet point
  - "confidence"    : string — one of "Measured" | "Calculated" | "Inferred" | "Speculated"
  - "date_observed" : string — "YYYY-MM-DD" or "YYYY-MM" (use "" if unknown)
  - "source"        : string — brief source attribution (use "" if unknown)

Concrete example (illustrative shape only — your actual content will differ):
{
  "Quantitative Benchmarks": [
    {
      "text": "TSMC N2 wafer price is roughly 2x N3 at volume introduction",
      "confidence": "Inferred",
      "date_observed": "2026-04",
      "source": "industry analyst consensus"
    },
    {
      "text": "H100 peak FP8 throughput is 3958 TFLOPS per SXM module",
      "confidence": "Measured",
      "date_observed": "2024-01",
      "source": "NVIDIA H100 datasheet"
    }
  ]
}

These field names are non-negotiable. Do not rename "text" to "finding",
"confidence" to "tier", "date_observed" to "date", or "source" to "citation".
Return ONLY the JSON object — no prose, no markdown fences, no commentary."""


EXTRACTION_USER_TEMPLATE = """\
Investigation question:
{question}

Thesis summary:
{thesis_summary}

Thesis components:
{thesis_components}

Falsification conditions:
{falsification_conditions}

Extract durable findings for the {domain} knowledge skill.
Return ONLY the JSON object, no other text."""


def make_extraction_prompt(
    question: str,
    thesis: Any,
    domain: str,
) -> tuple[str, str]:
    """Build (system, user) prompts. Pure function — no I/O, no LLM
    call. The components + falsification lines are formatted from
    the thesis dict if present, ``(none)`` otherwise."""
    components_text = ""
    if isinstance(thesis, dict):
        for comp in thesis.get("thesis_components") or []:
            if isinstance(comp, dict):
                claim = comp.get("claim", "")
                conf = comp.get("confidence", "unknown")
                components_text += f"- [{conf}] {claim}\n"

    falsification_text = ""
    if isinstance(thesis, dict):
        for fc in thesis.get("falsification_conditions") or []:
            if isinstance(fc, dict):
                cond = fc.get("condition", "")
                obs = fc.get("specific_observable", "")
                falsification_text += f"- IF: {cond} → OBSERVABLE: {obs}\n"

    summary = ""
    if isinstance(thesis, dict):
        summary = thesis.get("thesis_summary", "") or ""

    user_prompt = EXTRACTION_USER_TEMPLATE.format(
        question=question,
        thesis_summary=summary,
        thesis_components=components_text or "(none)",
        falsification_conditions=falsification_text or "(none)",
        domain=domain,
    )
    return EXTRACTION_SYSTEM_PROMPT, user_prompt
