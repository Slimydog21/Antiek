"""Token counting — Hook-extensible counter with len/4 fallback."""

from __future__ import annotations

from substrate.hooks import HookContext, HookRegistry

SEAM_ID = "token_count"


def _heuristic_count(*, text: str, model: str) -> int:
    return max(1, len(text) // 4)


def declare_token_count_seam(registry: HookRegistry) -> None:
    registry.declare_seam(
        SEAM_ID,
        "Count tokens in `text` for `model`. Extension hooks should raise "
        "HookShortCircuit(int) to return the count.",
    )


def count_tokens(
    registry: HookRegistry,
    *,
    text: str,
    model: str,
    project_id: str | None = None,
) -> int:
    ctx = HookContext(
        seam_id=SEAM_ID,
        extension_id="core",
        call_id=f"tc-{id(text)}",
        project_id=project_id,
    )

    def _primitive(**kwargs: object) -> int:
        return _heuristic_count(text=kwargs["text"], model=kwargs["model"])  # type: ignore[arg-type]

    return registry.dispatch(SEAM_ID, ctx, _primitive, text=text, model=model)
