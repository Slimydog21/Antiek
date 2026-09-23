"""A stale ad-ranker artifact must degrade LOUDLY, not invisibly.

``_load_model_from_env`` returns None on any artifact problem by design — an
ad slot must never be blanked because a model file is missing or stale. That
contract is correct and is unchanged here.

What was wrong is that it degraded with NO log, NO event and NO /health field.
A stale artifact silently downgraded every auction to rule-based ranking, so
ranking quality could regress indefinitely with nothing to notice it. The
operator runbook compounded it by saying to grep the service logs for
``refusing to load stale coefficients`` — a message this handler swallowed, so
it could never be emitted.

Degrading gracefully and degrading invisibly are different things.
"""
from __future__ import annotations

import json
import logging

from substrate.ad_inventory import auction_ranker as ar
from substrate.ad_inventory.auction_model import FEATURE_SCHEMA_VERSION


def test_a_stale_schema_artifact_still_returns_none(tmp_path, monkeypatch, caplog):
    """The contract: degrade to rule-based, never raise."""
    artifact = tmp_path / "model.json"
    artifact.write_text(json.dumps({
        "feature_schema_version": "definitely-not-" + str(FEATURE_SCHEMA_VERSION),
        "weights": [0.1, 0.2],
    }))
    monkeypatch.setenv(ar.MODEL_PATH_ENV, str(artifact))
    with caplog.at_level(logging.WARNING, logger=ar.__name__):
        assert ar._load_model_from_env() is None


def test_a_stale_schema_artifact_is_logged_with_the_reason(tmp_path, monkeypatch, caplog):
    """The fix: the operator can now see WHY ranking quality dropped."""
    artifact = tmp_path / "model.json"
    artifact.write_text(json.dumps({
        "feature_schema_version": "stale-vX",
        "weights": [0.1, 0.2],
    }))
    monkeypatch.setenv(ar.MODEL_PATH_ENV, str(artifact))
    with caplog.at_level(logging.WARNING, logger=ar.__name__):
        ar._load_model_from_env()
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "rule-based" in text, f"fallback not announced; got: {text!r}"
    assert "stale coefficients" in text, (
        "the underlying ValueError's reason was not surfaced — this is the "
        "exact message the runbook told the operator to grep for"
    )
    assert str(artifact) in text, "the log does not say WHICH artifact failed"


def test_a_missing_artifact_is_also_logged(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(ar.MODEL_PATH_ENV, str(tmp_path / "nope.json"))
    with caplog.at_level(logging.WARNING, logger=ar.__name__):
        assert ar._load_model_from_env() is None
    assert any("rule-based" in r.getMessage() for r in caplog.records)


def test_an_unset_env_var_is_NOT_logged(monkeypatch, caplog):
    """Control: no artifact configured is the NORMAL state, not a degradation.

    Without this, the warning would fire on every call in the default
    configuration and be tuned out — the classic way a real signal is buried.
    """
    monkeypatch.delenv(ar.MODEL_PATH_ENV, raising=False)
    with caplog.at_level(logging.WARNING, logger=ar.__name__):
        assert ar._load_model_from_env() is None
    assert caplog.records == [], (
        f"warned on the default no-artifact path: {[r.getMessage() for r in caplog.records]}"
    )


def test_the_warning_is_warning_not_error(tmp_path, monkeypatch, caplog):
    """The system is working as designed, just worse. ERROR would be wrong."""
    artifact = tmp_path / "bad.json"
    artifact.write_text("{not json")
    monkeypatch.setenv(ar.MODEL_PATH_ENV, str(artifact))
    with caplog.at_level(logging.DEBUG, logger=ar.__name__):
        ar._load_model_from_env()
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
