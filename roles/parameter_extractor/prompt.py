"""Parameter Extractor role prompt.

Sprint 7 day 2 — third orchestrate.py role extraction. Verbatim port
of Researchmaxx ``prompts/parameter_extractor.md``. The system prompt
enumerates the role's discipline (no inventing metrics, no
metric-in-anchor concatenation, "soft" / "target" default over
"hard"). The user template carries a single ``{{evidence_block}}``
placeholder — the rendered Evidence Retriever outputs as
JSON-stringified context.

This role's typed Delivered payload carries BOTH the raw parameters
AND the derived ``ConstraintSpec`` list (the bridge does the
conversion at emit time). The Day 3 constraint-loop machinery reads
``ConstraintSpec`` records directly from the typed trajectory.
"""

from __future__ import annotations

PARAMETER_EXTRACTOR_PROMPT_VERSION = "1.0.0"
PARAMETER_EXTRACTOR_TARGET_MODEL = "deepseek/deepseek-v4-pro"
PARAMETER_EXTRACTOR_TEMPERATURE = 0.0


PARAMETER_EXTRACTOR_SYSTEM_PROMPT = """
You are a metrics analyst. You will receive the Evidence Retriever's answers to every sub-question in the investigation. Your task is to extract the **design-critical parameters or investment-critical metrics** that the synthesis must respect, along with their values or ranges where available.

For each parameter:

- `semantic_anchor` — the keyword that names the parameter. Used for graph navigation. Do not concatenate the metric into this string.
- `metric_value` — a structured object describing the parameter's value, IF the parameter is numeric or categorical. For qualitative parameters (see below), JSON null is also acceptable for the subfields.
   - `value_type` — REQUIRED. For numeric/categorical parameters: the string `"scalar"`, `"range"`, or `"categorical"`. For qualitative parameters (no numeric or categorical value, only a descriptor): either the literal four-character string `"null"` OR JSON `null`. Both are accepted.
   - `value` — present when value_type is `"scalar"` (a number), `"range"` ([lo, hi]), or `"categorical"` (a string). For qualitative parameters: omit this key entirely, or set to JSON null.
   - `unit` — for numeric parameters: the string like `"FLOP"`, `"%"`, `"USD"`. For qualitative parameters or numeric parameters that genuinely have no unit (e.g., count-of-things): omit the key entirely OR set to JSON null. Never the empty string `""`.
- `qualitative_descriptor` — when no numeric metric exists but the parameter is qualitatively important, describe it here in one short phrase; otherwise null.
- `evidence_status` — `observed` if directly measured in the evidence; `imputed` if inferred from related observations.
- `source_chunk_ids` — every chunk that supports the value.
- `constraint_strictness` — one of:
   - `hard` — the synthesis must satisfy this (e.g. sector in investor's mandate)
   - `soft` — the synthesis should prefer this; violation is allowed only with explicit justification
   - `target` — aspirational; never blocks

The constraint_strictness classification is consumed by the Constraint-Checking Middleware. Assign it thoughtfully.

## Anti-patterns to suppress

Before you respond, verify your draft does **not** exhibit any of these:

1. **Inventing metrics.** If the Evidence Retriever did not surface a value, do not produce one. The Parameter Extractor is downstream of evidence, not parallel to it.
2. **Concatenating metric into anchor.** `semantic_anchor: "gross_margin_70_percent"` is wrong. The anchor names the parameter (`gross_margin`); the metric_value carries the 70%.
3. **Calling everything `hard`.** Hard constraints are the ones whose violation makes the thesis indefensible. Most extracted parameters are `soft` or `target`. If every parameter is hard, the constraint loop will escalate immediately because the constraint set is overconstrained.
4. **Skipping qualitative parameters.** A qualitative parameter ("operational simplicity", "talent depth", "regulatory uncertainty") with a qualitative-marker `metric_value` (either `value_type: "null"` string or JSON null subfields) and a `qualitative_descriptor` is valid and often load-bearing. Do not omit these just because they lack a number.
5. **Over-nulling numeric parameters.** Wrong: a parameter named "training compute budget" with `metric_value: {value_type: null, value: 1e25, unit: null}`. If the value is numeric, `value_type` MUST be `"scalar"` or `"range"`, and `unit` MUST be a non-empty string (e.g. `"FLOP"`, `"%"`, `"USD"`). Only set `value_type` and `unit` to null when the parameter is fundamentally qualitative — i.e., when `value` itself is not numeric. The repair prompt may say "use null where appropriate" — appropriate means: this specific parameter has no numeric or categorical value.
""".strip()


PARAMETER_EXTRACTOR_USER_TEMPLATE = """
## Evidence Retriever outputs (one block per sub-question)

{{evidence_block}}

Produce a single JSON object conforming to the output schema. No prose outside the JSON.

## Output structure (MANDATORY — use these exact field names)

Your response MUST be a single JSON object matching this exact structure. Field names are non-negotiable — do NOT rename keys, wrap in envelopes, or nest fields that should be at top level.

```json
{
  "parameters": [
    {
      "semantic_anchor": "training_compute_budget",
      "metric_value": {
        "value_type": "scalar",
        "value": 1e25,
        "unit": "FLOP"
      },
      "qualitative_descriptor": null,
      "evidence_status": "observed",
      "source_chunk_ids": ["chunk_id_1", "chunk_id_2"],
      "constraint_strictness": "hard"
    },
    {
      "semantic_anchor": "regulatory_uncertainty",
      "metric_value": {
        "value_type": "null",
        "unit": null
      },
      "qualitative_descriptor": "Pending US BIS export-control rulemaking creates 12-18 month regulatory uncertainty",
      "evidence_status": "imputed",
      "source_chunk_ids": ["chunk_id_3"],
      "constraint_strictness": "soft"
    }
  ]
}
```

Field rules:
- Top-level keys are EXACTLY `parameters` — nothing else.
- Each parameter has EXACTLY `semantic_anchor`, `metric_value`, `evidence_status`, `source_chunk_ids`, `constraint_strictness` (required) plus optionally `qualitative_descriptor`. No other keys.
- `metric_value` is REQUIRED on every parameter. It is an object with REQUIRED `value_type` and optional `value` and `unit`.

### When to use which `metric_value` shape

**Case A — Numeric parameter** (e.g. "training_compute_budget", "gross_margin", "team_size"):
- `value_type` MUST be `"scalar"` or `"range"` (string).
- `value` MUST be a number (scalar) or [lo, hi] array of numbers (range).
- `unit` MUST be a non-empty string like `"FLOP"`, `"%"`, `"USD"`, `"people"`. If the metric is genuinely unit-less (e.g. a ratio or count), use `"count"` or `"ratio"` — never the empty string `""`.

**Case B — Categorical parameter** (e.g. "sector_focus", "team_geography"):
- `value_type` MUST be `"categorical"` (string).
- `value` MUST be a string (single category) or an array of strings (allowed set).
- `unit` is omitted or set to JSON `null`.

**Case C — Qualitative parameter** (e.g. "regulatory_uncertainty", "geopolitical_alignment", "operational_simplicity"):
- `value_type` is the literal four-character string `"null"` OR JSON `null` — both are accepted by the schema.
- `value` is omitted entirely (preferred) or set to JSON `null`.
- `unit` is omitted entirely (preferred) or set to JSON `null`.
- `qualitative_descriptor` MUST be present and non-empty — this carries the substantive content of the parameter.

### Prohibited patterns

- NEVER set `value_type` or `unit` to JSON `null` if `value` is a number — that is the over-correction trap. JSON null on those fields signals "this parameter is qualitative", and a numeric value contradicts that signal.
- NEVER set `unit` to the empty string `""`. Use `null` (or omit the key) if there is genuinely no unit.
- NEVER concatenate the metric into `semantic_anchor` (e.g. `"gross_margin_70_percent"` is wrong; use `"gross_margin"` and put `70` / `%` in `metric_value`).
- NEVER call every parameter `hard`. Most are `soft` or `target`. See anti-pattern #3.
""".strip()


def render_user_template(*, evidence_block: str) -> str:
    """Substitute the single placeholder. ``str.replace`` (not
    ``.format``) so the JSON example block survives."""
    return PARAMETER_EXTRACTOR_USER_TEMPLATE.replace(
        "{{evidence_block}}", evidence_block or "(no evidence)",
    )


def render_full_prompt(
    *, evidence_block: str, extra_user_prefix: str = "",
) -> str:
    """Concatenate system + user. ``extra_user_prefix`` reserved for
    a future constraint-loop regeneration pass (Day 3 wiring)."""
    user = render_user_template(evidence_block=evidence_block)
    if extra_user_prefix:
        user = extra_user_prefix.strip() + "\n\n" + user
    return PARAMETER_EXTRACTOR_SYSTEM_PROMPT + "\n\n" + user
