"""Loud startup WARNING when zero providers register."""

from __future__ import annotations

import logging

from interfaces.research.api.boot_providers import log_zero_providers_warning_if_needed


def test_zero_providers_logs_warning(caplog):
    with caplog.at_level(logging.WARNING):
        log_zero_providers_warning_if_needed(set())
    assert any(
        "0 providers registered" in r.message and "source .env" in r.message
        for r in caplog.records
    )


def test_nonzero_providers_no_warning(caplog):
    with caplog.at_level(logging.WARNING):
        log_zero_providers_warning_if_needed({"openrouter"})
    assert not any("0 providers registered" in r.message for r in caplog.records)