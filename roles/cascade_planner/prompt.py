"""Cascade-planner prompt framing (DRW SPR-05).

The cascade planner does not re-implement decomposition — it reuses the
``roles/decomposer`` role through an injected ``Decomposer``. This prompt is
the *framing* that emphasizes the one thing the cascade adds over plain
decomposition: **focus**. A narrow sub-question yields a sharper, cheaper,
more reliable deep research than a broad one, so the planner is told to
prefer depth (split an over-broad ask) over breadth (more vague siblings).

Kept as a constant so the operator can edit the framing in one place, in the
same spirit as the decomposer's ``program.md``.
"""

CASCADE_PLANNER_FRAMING = """\
You are decomposing a problem into a tree of sub-researches that will run as
independent, focused deep researches. Optimize for FOCUS:

- Each sub-question must be answerable as one tight research, not three
  questions in a trench coat. If a sub-question bundles several asks
  ("what X and how Y and why Z"), split it into separate, narrower nodes.
- Prefer a DEEPER tree over a WIDER one: an over-broad area becomes a parent
  with focused children, not one vague leaf.
- An atomic problem that should not decompose stays a single node. Do not
  fabricate sibling questions to hit a count.
- Every node states its focus boundary (what it will and will NOT cover) so
  the researches do not overlap.
"""
