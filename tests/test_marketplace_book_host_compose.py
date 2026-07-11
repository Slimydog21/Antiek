"""Hermetic tests for pure marketplace book host compose."""

from __future__ import annotations

import pytest

from substrate.marketplace_book_host_compose import (
    MarketplaceBookHostComposeError,
    compose_marketplace_book_host,
)


def test_free_hit_blocks_purchase() -> None:
    d = compose_marketplace_book_host(
        title="Walden",
        free_copy_available=True,
        html_projection_sha="sha:ready",
        host_requested=True,
    )
    assert d.purchase_intent_allowed is False
    assert d.purchase_executed is False
    assert d.hosted is False
    assert d.path == "html_host"
    assert d.to_dict()["purchase_executed"] is False
    assert d.to_dict()["hosted"] is False


def test_free_miss_intent() -> None:
    d = compose_marketplace_book_host(
        title="Unknown Book", free_copy_available=False
    )
    assert d.path == "purchase_intent"
    assert d.purchase_intent_allowed is True
    assert d.purchase_executed is False


def test_unknown_incomplete() -> None:
    d = compose_marketplace_book_host(
        title="Maybe Free", free_copy_available=None
    )
    assert d.path == "incomplete"
    assert d.purchase_intent_allowed is False


def test_skip_without_ack_blocked() -> None:
    d = compose_marketplace_book_host(
        title="X",
        free_copy_available=False,
        skip_free_copy=True,
        operator_skip_acknowledged=False,
    )
    assert d.path == "blocked"


def test_miss_with_sha_host() -> None:
    d = compose_marketplace_book_host(
        title="Bought Book",
        free_copy_available=False,
        html_projection_sha="sha:html",
        host_requested=True,
    )
    assert d.path == "html_host"
    assert d.purchase_executed is False
    assert d.hosted is False


def test_empty_title() -> None:
    with pytest.raises(MarketplaceBookHostComposeError, match="title"):
        compose_marketplace_book_host(title="  ", free_copy_available=False)
