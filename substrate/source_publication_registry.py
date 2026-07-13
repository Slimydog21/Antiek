"""Knowledge-dense publication registry for deep research (pure).

Operator vision: reference arxiv, substack, and other knowledge-dense
publications when running deep research. This pure layer catalogs known
source families and builds a selection pack — never invents live fetch hits.

fetched is always False here (selection / policy only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

PublicationFamily = Literal["arxiv", "substack", "openalex", "web", "custom"]

VALID_FAMILIES = frozenset({"arxiv", "substack", "openalex", "web", "custom"})


class SourcePublicationRegistryError(ValueError):
    """Fail-closed validation for source publication registry."""


@dataclass(frozen=True)
class PublicationSource:
    source_id: str
    family: PublicationFamily
    label: str
    host: str | None
    enabled: bool

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "source_id": self.source_id,
            "family": self.family,
            "label": self.label,
            "enabled": self.enabled,
        }
        if self.host is not None:
            out["host"] = self.host
        return out


@dataclass(frozen=True)
class SourceSelectionPack:
    sources: tuple[PublicationSource, ...]
    families: tuple[PublicationFamily, ...]
    fetched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": [s.to_dict() for s in self.sources],
            "families": list(self.families),
            "fetched": False,
            "notes": list(self.notes),
            "authority": "source_publication_registry_advisory",
        }


DEFAULT_PUBLICATION_CATALOG: tuple[PublicationSource, ...] = (
    PublicationSource(
        source_id="arxiv",
        family="arxiv",
        label="arXiv",
        host="arxiv.org",
        enabled=True,
    ),
    PublicationSource(
        source_id="substack",
        family="substack",
        label="Substack",
        host="substack.com",
        enabled=True,
    ),
    PublicationSource(
        source_id="openalex",
        family="openalex",
        label="OpenAlex",
        host="openalex.org",
        enabled=True,
    ),
    PublicationSource(
        source_id="web",
        family="web",
        label="General web",
        host=None,
        enabled=True,
    ),
)


def _require_family(value: object, *, field: str) -> PublicationFamily:
    if not isinstance(value, str) or value not in VALID_FAMILIES:
        raise SourcePublicationRegistryError(
            f"{field} must be arxiv|substack|openalex|web|custom"
        )
    return value  # type: ignore[return-value]


def select_publication_sources(
    *,
    requested_families: object,
    custom_sources: object | None = None,
    enabled_only: object = True,
    catalog: tuple[PublicationSource, ...] | list[PublicationSource] | None = None,
) -> SourceSelectionPack:
    """Build a source selection pack. Never invents live fetch results."""
    if not isinstance(requested_families, list):
        raise SourcePublicationRegistryError("requested_families must be an array")
    if len(requested_families) == 0:
        raise SourcePublicationRegistryError("requested_families must be non-empty")

    if not isinstance(enabled_only, bool):
        # Match TS: enabled_only !== false means default filter-on
        # Accept explicit bool only for honesty
        raise SourcePublicationRegistryError(
            "enabled_only must be an explicit boolean"
        )
    filter_enabled = enabled_only is True

    notes: list[str] = [
        "fetched=false — selection pack only (no live arxiv/substack/web fetch)",
    ]
    requested: set[PublicationFamily] = set()
    for i, fam in enumerate(requested_families):
        requested.add(_require_family(fam, field=f"requested_families[{i}]"))

    cat = tuple(catalog) if catalog is not None else DEFAULT_PUBLICATION_CATALOG
    sources: list[PublicationSource] = []
    for entry in cat:
        if entry.family not in requested:
            continue
        if filter_enabled and not entry.enabled:
            notes.append(f"catalog {entry.source_id} skipped (disabled)")
            continue
        sources.append(entry)

    if custom_sources is not None:
        if not isinstance(custom_sources, list):
            raise SourcePublicationRegistryError(
                "custom_sources must be an array or null"
            )
        for i, c in enumerate(custom_sources):
            if not isinstance(c, dict):
                raise SourcePublicationRegistryError(
                    f"custom_sources[{i}] must be an object"
                )
            family = _require_family(c.get("family"), field=f"custom_sources[{i}].family")
            if family != "custom":
                raise SourcePublicationRegistryError(
                    f"custom_sources[{i}].family must be custom (use catalog for built-ins)"
                )
            sid = c.get("source_id")
            if not isinstance(sid, str) or not sid.strip():
                raise SourcePublicationRegistryError(
                    f"custom_sources[{i}].source_id required"
                )
            label = c.get("label")
            if not isinstance(label, str) or not label.strip():
                raise SourcePublicationRegistryError(
                    f"custom_sources[{i}].label required"
                )
            enabled = c.get("enabled")
            if not isinstance(enabled, bool):
                raise SourcePublicationRegistryError(
                    f"custom_sources[{i}].enabled must be boolean"
                )
            if filter_enabled and not enabled:
                notes.append(f"custom {sid.strip()} skipped (disabled)")
                continue
            if "custom" not in requested:
                notes.append(
                    f"custom {sid.strip()} skipped (custom not in requested_families)"
                )
                continue
            host_raw = c.get("host")
            host: str | None
            if host_raw is None:
                host = None
            elif isinstance(host_raw, str):
                host = host_raw
            else:
                raise SourcePublicationRegistryError(
                    f"custom_sources[{i}].host must be string or null"
                )
            sources.append(
                PublicationSource(
                    source_id=sid.strip(),
                    family="custom",
                    label=label.strip(),
                    host=host,
                    enabled=enabled,
                )
            )

    families = tuple(dict.fromkeys(s.family for s in sources))
    notes.append(
        f"selected={len(sources)} sources across {len(families)} families"
    )
    notes.append("fetched=false")

    return SourceSelectionPack(
        sources=tuple(sources),
        families=families,
        fetched=False,
        notes=tuple(notes),
        authority="source_publication_registry_advisory",
    )


__all__ = [
    "DEFAULT_PUBLICATION_CATALOG",
    "PublicationSource",
    "SourcePublicationRegistryError",
    "SourceSelectionPack",
    "select_publication_sources",
]
