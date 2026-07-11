"""Hermetic tests for pure source publication registry."""

from __future__ import annotations

import pytest

from substrate.source_publication_registry import (
    SourcePublicationRegistryError,
    select_publication_sources,
)


def test_select_arxiv_substack_fetched_false() -> None:
    pack = select_publication_sources(
        requested_families=["arxiv", "substack"],
        enabled_only=True,
    )
    assert pack.fetched is False
    assert pack.to_dict()["fetched"] is False
    assert sorted(s.family for s in pack.sources) == ["arxiv", "substack"]
    assert pack.authority == "source_publication_registry_advisory"


def test_rejects_empty_families() -> None:
    with pytest.raises(SourcePublicationRegistryError, match="non-empty"):
        select_publication_sources(requested_families=[], enabled_only=True)


def test_custom_when_requested() -> None:
    pack = select_publication_sources(
        requested_families=["custom"],
        custom_sources=[
            {
                "source_id": "my-blog",
                "family": "custom",
                "label": "My Research Blog",
                "enabled": True,
            }
        ],
        enabled_only=True,
    )
    assert len(pack.sources) == 1
    assert pack.sources[0].source_id == "my-blog"
    assert pack.fetched is False


def test_skips_disabled_custom() -> None:
    pack = select_publication_sources(
        requested_families=["custom"],
        custom_sources=[
            {
                "source_id": "off",
                "family": "custom",
                "label": "Off",
                "enabled": False,
            }
        ],
        enabled_only=True,
    )
    assert pack.sources == ()


def test_rejects_non_custom_in_custom_sources() -> None:
    with pytest.raises(SourcePublicationRegistryError, match="must be custom"):
        select_publication_sources(
            requested_families=["arxiv"],
            custom_sources=[
                {
                    "source_id": "x",
                    "family": "arxiv",
                    "label": "x",
                    "enabled": True,
                }
            ],
            enabled_only=True,
        )


def test_strict_enabled_only_bool() -> None:
    with pytest.raises(SourcePublicationRegistryError, match="enabled_only"):
        select_publication_sources(
            requested_families=["arxiv"],
            enabled_only="true",  # type: ignore[arg-type]
        )
