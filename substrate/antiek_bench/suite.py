"""Suite definition: versioned items keyed by task class."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TaskClass = Literal["distill", "synthesize", "wrestle", "book_qa"]


@dataclass(frozen=True)
class SuiteItem:
    item_id: str
    task_class: TaskClass
    prompt: str
    # Offline expected tokens for stub scoring (not live answers).
    expected_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class SuiteDefinition:
    suite_version: str
    items: tuple[SuiteItem, ...]
    label: str = "antiek-bench-core"

    def task_classes(self) -> tuple[TaskClass, ...]:
        seen: list[TaskClass] = []
        for it in self.items:
            if it.task_class not in seen:
                seen.append(it.task_class)
        return tuple(seen)

    def items_for(self, task_class: TaskClass) -> tuple[SuiteItem, ...]:
        return tuple(i for i in self.items if i.task_class == task_class)


@dataclass
class SuiteRegistry:
    """Active suite pointer + versioned suite map. Promote is the only mutator of active."""

    suites: dict[str, SuiteDefinition] = field(default_factory=dict)
    active_version: str | None = None

    def register(self, suite: SuiteDefinition) -> None:
        if not suite.suite_version.strip():
            raise ValueError("suite_version is required")
        if not suite.items:
            raise ValueError("suite must contain at least one item")
        classes = {i.task_class for i in suite.items}
        if len(classes) < 1:
            raise ValueError("suite must declare task classes")
        self.suites[suite.suite_version] = suite
        if self.active_version is None:
            self.active_version = suite.suite_version

    def get(self, version: str) -> SuiteDefinition | None:
        return self.suites.get(version)

    def active(self) -> SuiteDefinition:
        if self.active_version is None or self.active_version not in self.suites:
            raise RuntimeError("no active suite registered")
        return self.suites[self.active_version]

    def promote(self, version: str) -> SuiteDefinition:
        if version not in self.suites:
            raise KeyError(f"unknown suite_version: {version}")
        self.active_version = version
        return self.suites[version]


# Process-local default registry (tests inject their own).
_DEFAULT_REGISTRY = SuiteRegistry()


def default_core_suite() -> SuiteDefinition:
    """Frozen core suite v1 — ≥2 task classes (distill + synthesize)."""
    return SuiteDefinition(
        suite_version="suite-v1",
        label="antiek-bench-core",
        items=(
            SuiteItem(
                item_id="distill-01",
                task_class="distill",
                prompt="Distill the key claim from: Attention is content-addressable memory.",
                expected_keywords=("attention", "memory", "claim"),
            ),
            SuiteItem(
                item_id="distill-02",
                task_class="distill",
                prompt="Distill: Retrieval-augmented generation grounds answers in sources.",
                expected_keywords=("retrieval", "sources", "generation"),
            ),
            SuiteItem(
                item_id="synth-01",
                task_class="synthesize",
                prompt="Synthesize a comparison of vector indexes for RAG latency.",
                expected_keywords=("vector", "index", "latency", "rag"),
            ),
            SuiteItem(
                item_id="synth-02",
                task_class="synthesize",
                prompt="Synthesize how twin notes feed recursive research prompts.",
                expected_keywords=("twin", "notes", "research"),
            ),
        ),
    )


def register_suite(
    suite: SuiteDefinition,
    *,
    registry: SuiteRegistry | None = None,
    make_active: bool = False,
) -> SuiteDefinition:
    reg = registry if registry is not None else _DEFAULT_REGISTRY
    reg.register(suite)
    if make_active:
        reg.promote(suite.suite_version)
    return suite


def get_suite(version: str, *, registry: SuiteRegistry | None = None) -> SuiteDefinition | None:
    reg = registry if registry is not None else _DEFAULT_REGISTRY
    return reg.get(version)


def active_suite(*, registry: SuiteRegistry | None = None) -> SuiteDefinition:
    reg = registry if registry is not None else _DEFAULT_REGISTRY
    if reg.active_version is None and "suite-v1" not in reg.suites:
        reg.register(default_core_suite())
    return reg.active()
