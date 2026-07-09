"""Offline suite runner with injectable stub providers."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .store import BenchStore
from .suite import SuiteDefinition, SuiteRegistry, TaskClass, active_suite

# model_id → callable(prompt, item) -> response text
ProviderFn = Callable[[str, str], str]
ProviderMap = Mapping[str, ProviderFn]


@dataclass(frozen=True)
class TaskScore:
    item_id: str
    task_class: TaskClass
    model_id: str
    score: float
    hit_keywords: tuple[str, ...]
    response_preview: str


@dataclass(frozen=True)
class BenchRunResult:
    run_id: str
    week_id: str
    suite_version: str
    model_id: str
    scores: tuple[TaskScore, ...]
    mean_score: float
    by_task_class: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "week_id": self.week_id,
            "suite_version": self.suite_version,
            "model_id": self.model_id,
            "mean_score": self.mean_score,
            "by_task_class": dict(self.by_task_class),
            "scores": [
                {
                    "item_id": s.item_id,
                    "task_class": s.task_class,
                    "model_id": s.model_id,
                    "score": s.score,
                    "hit_keywords": list(s.hit_keywords),
                    "response_preview": s.response_preview,
                }
                for s in self.scores
            ],
            "view_format": "html",
        }


def keyword_stub_provider(model_id: str, quality: float = 0.8) -> ProviderFn:
    """Deterministic offline provider: echoes prompt keywords with model tag.

    ``quality`` in [0,1] controls fraction of expected keywords echoed (stub
    performance differentiation across models without network).
    """
    q = max(0.0, min(1.0, quality))

    def _fn(prompt: str, item_id: str) -> str:
        # Stable pseudo-response from model + item
        seed = hashlib.sha256(f"{model_id}:{item_id}:{prompt}".encode()).hexdigest()
        words = re.findall(r"[A-Za-z0-9_]+", prompt.lower())
        keep_n = max(1, int(len(words) * q))
        kept = words[:keep_n]
        return f"[{model_id}] " + " ".join(kept) + f" seed={seed[:8]}"

    return _fn


def _score_response(response: str, expected: tuple[str, ...]) -> tuple[float, tuple[str, ...]]:
    if not expected:
        return (1.0 if response.strip() else 0.0, ())
    text = response.lower()
    hits = tuple(k for k in expected if k.lower() in text)
    return (len(hits) / float(len(expected)), hits)


def _run_id(week_id: str, suite_version: str, model_id: str) -> str:
    digest = hashlib.sha256(
        f"run:v1:{week_id}:{suite_version}:{model_id}".encode()
    ).hexdigest()[:16]
    return f"brun_{digest}"


def run_suite(
    *,
    model_id: str,
    week_id: str,
    store: BenchStore,
    suite: SuiteDefinition | None = None,
    providers: ProviderMap | None = None,
    registry: SuiteRegistry | None = None,
    provider_fn: ProviderFn | None = None,
) -> BenchRunResult:
    """Run the active (or given) suite offline for one model.

    Requires either ``provider_fn`` or ``providers[model_id]``. Never hits the network.
    """
    mid = (model_id or "").strip()
    if not mid:
        raise ValueError("model_id is required")
    wid = (week_id or "").strip()
    if not wid:
        raise ValueError("week_id is required")

    suite_def = suite if suite is not None else active_suite(registry=registry)
    if provider_fn is not None:
        fn = provider_fn
    elif providers is not None and mid in providers:
        fn = providers[mid]
    else:
        raise ValueError(
            f"no provider for model_id={mid!r}; pass provider_fn or providers map"
        )

    scores: list[TaskScore] = []
    class_buckets: dict[str, list[float]] = {}
    for item in suite_def.items:
        response = fn(item.prompt, item.item_id)
        if not isinstance(response, str):
            raise TypeError("provider must return str")
        score, hits = _score_response(response, item.expected_keywords)
        scores.append(
            TaskScore(
                item_id=item.item_id,
                task_class=item.task_class,
                model_id=mid,
                score=round(score, 6),
                hit_keywords=hits,
                response_preview=response[:160],
            )
        )
        class_buckets.setdefault(item.task_class, []).append(score)

    by_class = {
        tc: round(sum(vs) / len(vs), 6) for tc, vs in sorted(class_buckets.items())
    }
    mean = round(sum(s.score for s in scores) / len(scores), 6) if scores else 0.0
    rid = _run_id(wid, suite_def.suite_version, mid)
    result = BenchRunResult(
        run_id=rid,
        week_id=wid,
        suite_version=suite_def.suite_version,
        model_id=mid,
        scores=tuple(scores),
        mean_score=mean,
        by_task_class=by_class,
    )
    store.put_run(rid, result.to_dict())
    return result
