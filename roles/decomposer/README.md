# roles/decomposer/

Top-level question → sub-questions.

Input: a research question (from kanban, from a heartbeat trigger, from
the interview workflow).
Output: a tree of sub-questions, each tagged with the evidence types
needed and the constraint set that must hold for the sub-question to
be considered answered.

## Tier

Pro. Decomposition quality determines the whole investigation's shape;
reasoning depth dominates the cost calculus.

## Events emitted

- `decompose_question` — one per call
- `advance_sub_question` — one per sub-question generated
