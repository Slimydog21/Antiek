"""SFT runner scaffold — autoresearch Wedge 4 pattern (master-spec §14.2).

Per integration_autoresearch.md Wedge 4: autoresearch's 5-minute
training budget + propose-execute-measure-gate loop applied to local
SFT. Sprint 30+ at earliest (Loop 3 unlock-gate dependent)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

from .unlock_gate import check_unlocked


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SFTConfig:
    """Configuration for one SFT iteration.

    Per integration_autoresearch.md Wedge 4: each iteration has a
    fixed 5-minute training budget. The runner is responsible for
    enforcing it; this struct captures the hyperparameters the
    iteration is testing."""

    base_model: str  # e.g. "qwen2.5-7b" — open-weight per criterion 4
    learning_rate: float
    batch_size: int
    lora_rank: int
    lora_target_modules: tuple[str, ...]
    training_seconds_budget: int = 300  # 5 min per Karpathy autoresearch
    seed: int = 42


@dataclass(frozen=True)
class SFTIteration:
    """Result of one SFT iteration."""

    iteration_id: str
    config: SFTConfig
    val_loss_baseline: float
    val_loss_candidate: float
    delta: float
    accepted: bool  # candidate ≤ baseline → accept (lower loss is better)
    cost_usd: Decimal
    started_at: str
    completed_at: str


@dataclass
class SFTRunner:
    """Outer loop for local SFT iterations. Mirrors
    PromptAutoresearchRunner from tools/prompt_autoresearch/ but
    targets model weights instead of prompts.

    Strictly Loop-3-gated; refuses to run without unlock."""

    baseline_val_loss: float = 1.0
    iterations: list[SFTIteration] = field(default_factory=list)
    total_cost_usd: Decimal = Decimal("0.00")

    def run_iteration(
        self,
        config: SFTConfig,
        *,
        train_fn: Callable[[SFTConfig], float],
        cost_fn: Callable[[SFTConfig], Decimal],
    ) -> SFTIteration:
        """One SFT iteration. Per Wedge 4: propose → train (5 min) →
        measure val_loss → keep if lower → revert otherwise."""
        check_unlocked()

        started = _now_iso()
        candidate_loss = train_fn(config)
        cost = cost_fn(config)
        completed = _now_iso()

        delta = candidate_loss - self.baseline_val_loss
        accepted = candidate_loss < self.baseline_val_loss

        iteration = SFTIteration(
            iteration_id=f"sft-{len(self.iterations)+1:04d}",
            config=config,
            val_loss_baseline=self.baseline_val_loss,
            val_loss_candidate=candidate_loss,
            delta=delta,
            accepted=accepted,
            cost_usd=cost,
            started_at=started,
            completed_at=completed,
        )
        self.iterations.append(iteration)
        self.total_cost_usd += cost

        if accepted:
            self.baseline_val_loss = candidate_loss

        return iteration


def run_sft_iteration(
    runner: SFTRunner,
    config: SFTConfig,
    *,
    train_fn: Callable[[SFTConfig], float],
    cost_fn: Callable[[SFTConfig], Decimal],
) -> SFTIteration:
    """Convenience wrapper."""
    return runner.run_iteration(config, train_fn=train_fn, cost_fn=cost_fn)
