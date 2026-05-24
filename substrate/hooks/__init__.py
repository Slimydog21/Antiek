"""Hook registry substrate (Pi-pattern extensibility)."""

from substrate.hooks.contract import (
    HookContext,
    HookShortCircuit,
    OnErrorHook,
    PostCallHook,
    PreCallHook,
)
from substrate.hooks.loader import ExtensionLoadResult, load_extensions
from substrate.hooks.registry import HookRegistry

__all__ = [
    "ExtensionLoadResult",
    "HookContext",
    "HookRegistry",
    "HookShortCircuit",
    "OnErrorHook",
    "PostCallHook",
    "PreCallHook",
    "load_extensions",
]
