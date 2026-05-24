"""example_uppercase_formatter — canonical post-hook worked example.

Demonstrates the minimal shape of an extension. Replace the behavior in
``_UpperCaseFormatter.__call__`` to do something useful; copy the structure
verbatim.
"""

from __future__ import annotations

from typing import Any

from substrate.hooks import HookContext, HookRegistry


class _UpperCaseFormatter:
    def __call__(self, ctx: HookContext, result: Any, **kw: Any) -> Any:
        if isinstance(result, dict) and "messages" in result:
            for m in result["messages"]:
                if isinstance(m, dict) and m.get("role") == "system":
                    m["content"] = str(m.get("content", "")).upper()
        return result


def register(registry: HookRegistry) -> None:
    registry.register_hook(
        seam_id="message_formatter",
        hook=_UpperCaseFormatter(),
        stage="post",
        extension_id="example_uppercase_formatter:v1",
        priority=100,
    )
