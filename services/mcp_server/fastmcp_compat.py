"""FastMCP compatibility for the Antiek MCP service.

The real ``mcp`` SDK remains the production path when installed. The local
fallback keeps the read-only service importable in the default dev/test
environment, where the SDK is optional but the MCP contract tests are collected.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar


@dataclass(frozen=True)
class ResourceContent:
    """Minimal content object returned by FastMCP ``read_resource``."""

    content: str
    mimeType: str


@dataclass(frozen=True)
class ResourceTemplate:
    """Minimal resource-template object exposed by FastMCP."""

    uriTemplate: str
    name: str
    title: str | None
    description: str | None
    mimeType: str


@dataclass(frozen=True)
class Tool:
    """Minimal tool object exposed by FastMCP."""

    name: str
    description: str


_ResourceHandler = Callable[..., str]
_Handler = TypeVar("_Handler", bound=Callable[..., Any])


def _match_template(template: str, uri: str) -> dict[str, str] | None:
    template_parts = template.split("/")
    uri_parts = uri.split("/")
    if len(template_parts) != len(uri_parts):
        return None

    values: dict[str, str] = {}
    for template_part, uri_part in zip(template_parts, uri_parts, strict=True):
        if template_part.startswith("{") and template_part.endswith("}"):
            key = template_part[1:-1]
            if not key:
                return None
            values[key] = uri_part
        elif template_part != uri_part:
            return None
    return values


class LocalFastMCP:
    """Small in-process FastMCP subset used when the SDK is unavailable."""

    def __init__(self, name: str, instructions: str | None = None) -> None:
        self.name = name
        self.instructions = instructions
        self._resources: list[tuple[ResourceTemplate, _ResourceHandler]] = []
        self._tools: list[Tool] = []

    def resource(
        self,
        uri_template: str,
        *,
        name: str,
        title: str | None = None,
        description: str | None = None,
        mime_type: str = "text/plain",
    ) -> Callable[[_ResourceHandler], _ResourceHandler]:
        """Register a URI-template resource handler."""

        def decorator(handler: _ResourceHandler) -> _ResourceHandler:
            self._resources.append(
                (
                    ResourceTemplate(
                        uriTemplate=uri_template,
                        name=name,
                        title=title,
                        description=description,
                        mimeType=mime_type,
                    ),
                    handler,
                ),
            )
            return handler

        return decorator

    def tool(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable[[_Handler], _Handler]:
        """Register a tool description."""

        def decorator(handler: _Handler) -> _Handler:
            self._tools.append(
                Tool(
                    name=name or handler.__name__,
                    description=description or inspect.getdoc(handler) or "",
                ),
            )
            return handler

        return decorator

    async def list_resource_templates(self) -> list[ResourceTemplate]:
        return [template for template, _handler in self._resources]

    async def list_tools(self) -> list[Tool]:
        return list(self._tools)

    async def read_resource(self, uri: str) -> list[ResourceContent]:
        for template, handler in self._resources:
            values = _match_template(template.uriTemplate, uri)
            if values is None:
                continue
            try:
                content = handler(**values)
            except Exception as exc:
                raise ValueError(str(exc)) from exc
            return [ResourceContent(content=content, mimeType=template.mimeType)]
        raise ValueError(f"Resource not found: {uri}")

    def run(self, *, transport: str = "stdio") -> None:
        raise RuntimeError(
            "The Python 'mcp' SDK is required to run the stdio server. "
            "Install the Antiek MCP extra, for example: pip install -e '.[mcp]'."
        )


if TYPE_CHECKING:
    FastMCP = LocalFastMCP
else:
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError:
        FastMCP = LocalFastMCP


__all__ = [
    "FastMCP",
    "LocalFastMCP",
    "ResourceContent",
    "ResourceTemplate",
    "Tool",
]
