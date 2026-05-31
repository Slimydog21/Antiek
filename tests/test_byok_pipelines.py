"""M2 tests — per-account BYOK pipeline configuration.

Offline + deterministic (a temp config path, no network, no daemon). Validates
the pipeline_kind frozenset, coexisting pipelines per account, and that the
record carries the cred_id (a reference) but never the plaintext key."""

from __future__ import annotations

import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402

from runtime.byok.pipelines import (  # noqa: E402
    PIPELINE_KINDS,
    get_pipeline,
    list_pipelines,
    register_pipeline,
)


def test_pipeline_kinds_frozenset():
    assert PIPELINE_KINDS == frozenset({"general_feed", "thread_specific"})


def test_register_both_kinds_and_reject_unknown():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = os.path.join(tmp, "pipelines.json")
        gf = register_pipeline(
            "@dhh", "cred-x-abc", "general_feed", config_path=cfg,
        )
        assert gf.pipeline_kind == "general_feed"
        assert gf.account_handle == "dhh"  # @ stripped
        ts = register_pipeline(
            "dhh", "cred-x-abc", "thread_specific", seed="1759999", config_path=cfg,
        )
        assert ts.pipeline_kind == "thread_specific"
        assert ts.seed == "1759999"
        # a third, unknown kind is rejected
        with pytest.raises(ValueError):
            register_pipeline("dhh", "cred-x-abc", "firehose", config_path=cfg)


def test_two_pipelines_same_account_listed_with_cred_no_key():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = os.path.join(tmp, "pipelines.json")
        register_pipeline("dhh", "cred-x-abc", "general_feed", config_path=cfg)
        register_pipeline(
            "dhh", "cred-x-abc", "thread_specific", seed="1759999", config_path=cfg,
        )
        pls = list_pipelines(config_path=cfg)
        assert len(pls) == 2
        kinds = {p.pipeline_kind for p in pls}
        assert kinds == {"general_feed", "thread_specific"}
        for p in pls:
            assert p.cred_id == "cred-x-abc"
            # the config dataclass never carries the plaintext key — only cred_id
            assert not hasattr(p, "secret")
            assert not hasattr(p, "key")


def test_list_filter_by_account():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = os.path.join(tmp, "pipelines.json")
        register_pipeline("dhh", "cred-x-abc", "general_feed", config_path=cfg)
        register_pipeline("patio11", "cred-x-def", "general_feed", config_path=cfg)
        only_dhh = list_pipelines(account_handle="dhh", config_path=cfg)
        assert len(only_dhh) == 1
        assert only_dhh[0].account_handle == "dhh"


def test_get_pipeline_roundtrip_and_unknown():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = os.path.join(tmp, "pipelines.json")
        pl = register_pipeline("dhh", "cred-x-abc", "general_feed", config_path=cfg)
        fetched = get_pipeline(pl.pipeline_id, config_path=cfg)
        assert fetched.pipeline_id == pl.pipeline_id
        assert fetched.cred_id == "cred-x-abc"
        with pytest.raises(KeyError):
            get_pipeline("pl-x-nope", config_path=cfg)
