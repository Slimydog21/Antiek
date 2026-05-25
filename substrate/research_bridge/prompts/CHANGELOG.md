# research_bridge / prompts — CHANGELOG

## v1 — 2026-05-24
Initial extractor prompt. JSON object with insights + open_questions
arrays. Verbatim quotes. Calibrated confidence. "Open question" =
raised AND not answered. Empty-arrays-on-failure contract.

## cluster_v1 — 2026-05-24
Initial clustering prompt for SPR-05. At-most-7 clusters; priority
ranks unique 0..N-1; many-to-one question→cluster allowed.

## cascade_v1 — 2026-05-24
Initial cascade-generation prompt. Provider routing heuristics;
order_index global across run; ≤3 prompts per cluster;
grounding-test contract.
