"""Declarative, versioned benchmark task registry.

A task is DATA, not code. The registry is the single source of truth for "what
the benchmark measures": a versioned set of ``(task_id, family, prompt,
scoring method, expected/rubric)`` definitions. Weekly runs are comparable only
within a fixed task version; a version bump invalidates cross-week score
comparability and is recorded.

Hard-to-vary invariants (each is a test):

- **Deterministic load.** ``load_default_registry()`` returns the same tasks in
  the same order every run — no filesystem/network/dict-ordering nondeterminism.
- **Stable ``task_id``** of the form ``{family}::{slug}``, matching the
  ``{task}::edge_cases`` convention the usage-learn lane expects.
- **No silent overwrite.** A duplicate ``task_id`` raises ``TaskRegistryError``;
  an unknown lookup raises rather than returning ``None`` (fail-closed, never a
  silent miss that inflates coverage).
- **Families mirror the platform surface** so usage-learn can up-weight
  failure-heavy families as the product expands.

This module holds no scoring logic and no provider calls — it is pure data plus
deterministic validation.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field, model_validator

TaskFamily = Literal[
    "reasoning",
    "retrieval",
    "writing",
    "deep_research",
    "code",
    "reading_comprehension",
]

ScoringMethod = Literal["exact", "rubric", "human"]


class _SlugChecker(Protocol):
    """Minimal protocol reused by the model validator (keeps mypy --strict happy)."""

    task_id: str

    def slug(self) -> str: ...


class BenchTask(BaseModel):
    """One declarative benchmark task.

    ``expected`` is required for ``exact`` scoring; ``rubric`` for ``rubric``
    scoring; both are ``None`` for ``human`` scoring (the operator supplies the
    verdict asynchronously). These constraints are enforced by a model
    validator so a malformed task can never enter a registry.
    """

    task_id: str = Field(min_length=3)
    family: TaskFamily
    prompt: str = Field(min_length=1)
    scoring: ScoringMethod
    expected: str | None = None
    rubric: str | None = None
    version: int = Field(default=1, ge=1)
    model_cost_class: str = Field(default="standard")
    notes: str | None = None

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def _enforce_scoring_payload(self) -> BenchTask:
        if self.scoring == "exact" and not (self.expected and self.expected.strip()):
            raise ValueError(f"task {self.task_id}: exact scoring requires non-empty 'expected'")
        if self.scoring == "rubric" and not (self.rubric and self.rubric.strip()):
            raise ValueError(f"task {self.task_id}: rubric scoring requires non-empty 'rubric'")
        if self.scoring == "human" and (self.expected or self.rubric):
            raise ValueError(
                f"task {self.task_id}: human scoring takes neither 'expected' nor 'rubric'"
            )
        return self

    @model_validator(mode="after")
    def _enforce_task_id_shape(self) -> BenchTask:
        if "::" not in self.task_id:
            raise ValueError(
                f"task_id must be '{{family}}::{{slug}}' (got {self.task_id!r})"
            )
        family_part, _, slug = self.task_id.partition("::")
        if family_part != self.family:
            raise ValueError(
                f"task_id family prefix {family_part!r} must match family {self.family!r}"
            )
        if not slug:
            raise ValueError(f"task_id {self.task_id!r} has an empty slug")
        return self


class TaskRegistryError(ValueError):
    """Fail-closed registry error: duplicate id or unknown lookup."""


class TaskRegistry:
    """An ordered, immutable collection of benchmark tasks.

    Construction validates determinism and uniqueness. Lookups are fail-closed.
    """

    __slots__ = ("_tasks", "_by_id")

    def __init__(self, tasks: list[BenchTask]) -> None:
        seen: dict[str, BenchTask] = {}
        ordered: list[BenchTask] = []
        for task in tasks:
            if task.task_id in seen:
                raise TaskRegistryError(f"duplicate task_id {task.task_id!r}")
            seen[task.task_id] = task
            ordered.append(task)
        self._tasks: tuple[BenchTask, ...] = tuple(ordered)
        self._by_id: dict[str, BenchTask] = seen

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._tasks)

    def __len__(self) -> int:
        return len(self._tasks)

    def __contains__(self, task_id: object) -> bool:
        return isinstance(task_id, str) and task_id in self._by_id

    def task_ids(self) -> list[str]:
        return [t.task_id for t in self._tasks]

    def families(self) -> list[TaskFamily]:
        """Families present, in first-appearance order (stable)."""
        seen: list[TaskFamily] = []
        for t in self._tasks:
            if t.family not in seen:
                seen.append(t.family)
        return seen

    def get(self, task_id: str) -> BenchTask:
        """Fail-closed lookup. Unknown id raises, never returns None."""
        try:
            return self._by_id[task_id]
        except KeyError:
            raise TaskRegistryError(f"unknown task_id {task_id!r}") from None


def _default_tasks() -> list[BenchTask]:
    """The seed registry. Deterministic and minimal (2-3 per family).

    These are deliberately simple, single-shot tasks. The recursive loop
    (usage-learn) up-weights failure-heavy families over time; the seed just
    needs enough breadth to differentiate model quality across the platform's
    core surface.
    """

    return [
        BenchTask(
            task_id="reasoning::two_step_inference",
            family="reasoning",
            prompt="If A implies B and B implies C, and A is true, what is C? Answer in one sentence.",
            scoring="exact",
            expected="C is true.",
        ),
        BenchTask(
            task_id="reasoning::counterfactual",
            family="reasoning",
            prompt="Explain in one sentence why a counterfactual is not directly observable.",
            scoring="rubric",
            rubric="PASS if the answer names a difference from the actual world; FAIL otherwise.",
        ),
        BenchTask(
            task_id="retrieval::citation_from_excerpt",
            family="retrieval",
            prompt="Given a source excerpt, identify the single most relevant citation anchor.",
            scoring="rubric",
            rubric="PASS if the anchor is a real claim grounded in the excerpt; FAIL if invented.",
        ),
        BenchTask(
            task_id="writing::one_paragraph_summary",
            family="writing",
            prompt="Summarize the provided document in exactly one coherent paragraph.",
            scoring="rubric",
            rubric="PASS if the summary covers the document's thesis without fabrication; FAIL otherwise.",
        ),
        BenchTask(
            task_id="deep_research::conflict_surface",
            family="deep_research",
            prompt="Given two sources that disagree, name the conflict in one sentence.",
            scoring="rubric",
            rubric="PASS if a concrete disagreement is identified (not papered over); FAIL otherwise.",
        ),
        BenchTask(
            task_id="code::fix_off_by_one",
            family="code",
            prompt="Fix the off-by-one bug in the provided loop. Return the corrected line only.",
            scoring="exact",
            expected="for i in range(len(xs)):",
        ),
        BenchTask(
            task_id="reading_comprehension::main_claim",
            family="reading_comprehension",
            prompt="State the main claim of the provided passage in one sentence.",
            scoring="human",
        ),
    ]


_DEFAULT_REGISTRY: TaskRegistry | None = None


def load_default_registry() -> TaskRegistry:
    """Return the seed registry, deterministically.

    Cached after first construction; the seed list is a module-level literal so
    repeated calls are byte-identical across runs.
    """

    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = TaskRegistry(_default_tasks())
    return _DEFAULT_REGISTRY
