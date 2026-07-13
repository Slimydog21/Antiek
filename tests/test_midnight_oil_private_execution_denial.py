from __future__ import annotations

import ast
from pathlib import Path

from tests.test_midnight_oil_private_provider_authority import (
    test_consent_route_denies_complete_private_carrier_before_issue_or_enqueue as _api_denial,
)
from tests.test_midnight_oil_private_provider_authority import (
    test_internal_persistence_entry_replays_and_reopens_complete_v2 as _worker_denial,
)

ROOT = Path(__file__).parents[1]
DISPATCH_MODULE = ROOT / "substrate/midnight_oil/private_provider_dispatch.py"


def test_private_dispatch_production_module_has_no_transport_or_router_callback() -> None:
    source = DISPATCH_MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "RouterSwarmDispatch" not in source
    assert "substrate.dispatch" not in source
    assert "Callable" not in source
    assert "transport:" not in source
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"dispatch", "send", "complete", "respond"}
        for node in ast.walk(tree)
    )


def test_prepared_envelope_has_no_production_consumer() -> None:
    consumers: list[Path] = []
    for path in ROOT.rglob("*.py"):
        if "tests" in path.parts or path == DISPATCH_MODULE:
            continue
        if "PreparedOwnerPrivateDispatchV1" in path.read_text(encoding="utf-8"):
            consumers.append(path)
    assert consumers == []


def test_current_worker_and_authority_literals_remain_disabled() -> None:
    worker = (ROOT / "substrate/midnight_oil/worker_cli.py").read_text(encoding="utf-8")
    authority = (
        ROOT / "substrate/midnight_oil/private_provider_authority.py"
    ).read_text(encoding="utf-8")
    assert "owner-private execution remains disabled" in worker
    assert "consent_enabled: Literal[False] = False" in authority
    assert "delivery_enabled: Literal[False] = False" in authority


def test_real_api_path_denies_before_issue_or_enqueue(tmp_path: Path) -> None:
    _api_denial(tmp_path)


def test_synthetic_worker_path_denies_before_execution(tmp_path: Path) -> None:
    _worker_denial(tmp_path)
