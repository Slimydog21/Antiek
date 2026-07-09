"""Twin seed live boot wiring (residual cb)."""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.engagement_spine.twin import (  # noqa: E402
    ANTIEK_TWIN_SEED_LIVE_ENV,
    clear_twin_seed_live,
)
from substrate.engagement_spine.twin_seed_live_wiring import (  # noqa: E402
    ANTIEK_TWIN_SEED_USE_DISPATCH_ENV,
    configure_twin_seed_from_env,
)


def test_default_env_does_not_install():
    clear_twin_seed_live()
    env = {}
    report = configure_twin_seed_from_env(environ=env)
    assert report["installed"] is False
    assert report["live_env"] is False


def test_live_without_dispatch_flag_does_not_install():
    clear_twin_seed_live()
    env = {ANTIEK_TWIN_SEED_LIVE_ENV: "1"}
    report = configure_twin_seed_from_env(environ=env)
    assert report["live_env"] is True
    assert report["use_dispatch"] is False
    assert report["installed"] is False
    assert any("manually" in n.lower() or "USE_DISPATCH" in n for n in report["notes"])


def test_dual_gate_attempts_install():
    clear_twin_seed_live()
    env = {
        ANTIEK_TWIN_SEED_LIVE_ENV: "1",
        ANTIEK_TWIN_SEED_USE_DISPATCH_ENV: "1",
    }
    report = configure_twin_seed_from_env(environ=env)
    # May install or fail import — either way report is honest
    assert report["live_env"] is True
    assert report["use_dispatch"] is True
    assert report["view_format"] == "html"
    assert report["notes"]
    clear_twin_seed_live()
