from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal

import pytest

import substrate.midnight_oil.private_output_source_adapter_v1 as adapter
from substrate.midnight_oil.private_output_checker_v2 import (
    OwnerPrivateOverlapLedgerV2,
    OwnerPrivateOverlapPassV2,
    OwnerPrivateOverlapSourceV2,
)
from substrate.midnight_oil.private_provider_receipt_v5 import (
    OwnerPrivatePublicationSourceReceiptV5,
)
from tests.support.owner_private_v2 import (
    NOW_MS,
    PRIVATE_CANARY,
    OwnerPrivateV2Case,
    capability_registry,
    gatherer_output_bytes,
    owner_private_v2_case,
    owner_private_v2_multi_case,
    owner_private_v2_planner_case,
    planner_output_bytes,
    synthesizer_output_bytes,
    verifier_output_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
_ADAPTER_MODULE = "substrate.midnight_oil.private_output_source_adapter_v1"
_CHECKER_MODULE = "substrate.midnight_oil.private_output_checker_v2"
_POLICY_V3_MODULE = "substrate.midnight_oil.private_output_policy_v3"
_CAPABILITY_V3_MODULE = "substrate.midnight_oil.private_provider_capability_v3"
_ISOLATED_MODULES = {
    _ADAPTER_MODULE,
    _CHECKER_MODULE,
    _POLICY_V3_MODULE,
    _CAPABILITY_V3_MODULE,
}
_ALLOWED_IMPORT_DAG = {
    "substrate/midnight_oil/private_output_source_adapter_v1.py": {
        _CHECKER_MODULE: frozenset(
            {
                "PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256",
                "PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256",
                "PRIVATE_OUTPUT_CHECKER_V2_SHA256",
                "PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256",
                "PRIVATE_OUTPUT_LEDGER_V2_SHA256",
                "OwnerPrivateOverlapNotApplicableV2",
                "OwnerPrivateOverlapPassV2",
                "OwnerPrivateOverlapSourceV2",
                "check_owner_private_overlap_v2",
            }
        ),
    },
    "substrate/midnight_oil/private_output_policy_v3.py": {
        _CHECKER_MODULE: frozenset(
            {
                "PRIVATE_OUTPUT_ATTRIBUTED_NORMALIZER_V2_SHA256",
                "PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256",
                "PRIVATE_OUTPUT_CHECKER_V2_SHA256",
                "PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256",
                "PRIVATE_OUTPUT_LEDGER_V2_SHA256",
                "PRIVATE_OUTPUT_MODULE_SOURCE_V2_SHA256",
            }
        ),
        _ADAPTER_MODULE: frozenset(
            {
                "PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256",
                "PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256",
                "PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256",
            }
        ),
    },
    "substrate/midnight_oil/private_provider_capability_v3.py": {
        _CHECKER_MODULE: frozenset(
            {
                "PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256",
                "PRIVATE_OUTPUT_CHECKER_V2_SHA256",
                "PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256",
            }
        ),
        _ADAPTER_MODULE: frozenset(
            {
                "PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256",
                "PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256",
                "PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256",
            }
        ),
        _POLICY_V3_MODULE: frozenset({"OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256"}),
        "substrate.midnight_oil.private_provider_capability_v2": frozenset(
            {
                "PrivateProviderProcessingCapabilityV2",
                "private_provider_capability_v2_sha256",
                "verify_private_provider_capability_v2",
            }
        ),
        "substrate.midnight_oil.private_provider_composition": frozenset(
            {"DurablePrivateProviderRevocationHeadStore"}
        ),
        "substrate.midnight_oil.private_provider_policy": frozenset(
            {
                "MAX_PRIVATE_PROVIDER_CAPABILITIES",
                "MAX_PRIVATE_PROVIDER_REVOCATION_REFERENCE_AGE_MS",
                "private_provider_capability_sha256",
            }
        ),
    },
}
_FORBIDDEN_PUBLIC_NAMES = {
    "continuation",
    "envelope_sha256",
    "ledger",
    "ledger_bytes",
    "ledger_sha256",
    "output_bytes",
    "output_sha256",
    "pass_object",
    "private_input_commitment_sha256",
    "request_core_sha256",
    "result_sha256",
    "source_roster_sha256",
    "source_set_sha256",
    "sources",
}


class ExactReceiptResolver:
    """In-memory trusted resolver with no enumeration or fallback behavior."""

    def __init__(
        self,
        receipts: tuple[OwnerPrivatePublicationSourceReceiptV5, ...],
        *,
        substitutions: Mapping[tuple[str, str], OwnerPrivatePublicationSourceReceiptV5 | None] = {},
    ) -> None:
        self._rows = {(row.receipt_id, row.receipt_sha256): row for row in receipts}
        self._substitutions = dict(substitutions)
        self.calls: list[tuple[str, str]] = []

    def resolve_exact(
        self, *, receipt_id: str, receipt_sha256: str
    ) -> OwnerPrivatePublicationSourceReceiptV5 | None:
        key = (receipt_id, receipt_sha256)
        self.calls.append(key)
        if key in self._substitutions:
            return self._substitutions[key]
        return self._rows.get(key)


def _evaluate(
    case: OwnerPrivateV2Case,
    *,
    output: bytes | None = None,
    resolver: ExactReceiptResolver | None = None,
    now_ms: int = NOW_MS,
    registry: object | None = None,
) -> object:
    return adapter.evaluate_owner_private_output_source_adapter_v1(
        envelope=case.envelope,
        receipt_resolver=resolver or ExactReceiptResolver(case.receipts),
        capability_registry=registry or case.registry,  # type: ignore[arg-type]
        output_bytes=output or gatherer_output_bytes(),
        now_ms=now_ms,
    )


def _public_mapping(value: object) -> dict[str, Any]:
    dump = getattr(value, "model_dump", None)
    assert callable(dump), "adapter result must be a closed typed value"
    raw = dump(mode="python")
    assert isinstance(raw, dict)
    return raw


def _assert_closed_public_result(result: object, *, decision: str, sources: int) -> None:
    raw = _public_mapping(result)
    assert set(raw) == {
        "schema_version",
        "decision",
        "adapter_contract_sha256",
        "checker_v2_sha256",
        "checker_v2_contract_sha256",
        "checker_v2_corpus_sha256",
        "source_count",
        "confers_execution_authority",
        "confers_sink_authority",
        "production_consumer_enabled",
    }
    assert raw["decision"] == decision
    assert raw["source_count"] == sources
    assert raw["confers_execution_authority"] is False
    assert raw["confers_sink_authority"] is False
    assert raw["production_consumer_enabled"] is False
    assert not (_FORBIDDEN_PUBLIC_NAMES & raw.keys())
    assert not any(isinstance(value, bytes) for value in raw.values())
    assert not isinstance(result, OwnerPrivateOverlapPassV2)
    assert not isinstance(result, OwnerPrivateOverlapLedgerV2)
    assert not isinstance(result, OwnerPrivateOverlapSourceV2)
    rendered = repr(result)
    assert "redacted=True" in rendered
    assert "ledger" not in rendered.lower()


@pytest.mark.parametrize("multi", (False, True))
def test_exact_receipt_id_and_hash_resolver_passes_without_exposing_content(
    multi: bool,
) -> None:
    case = owner_private_v2_multi_case() if multi else owner_private_v2_case()
    resolver = ExactReceiptResolver(case.receipts)
    result = _evaluate(case, resolver=resolver)
    assert resolver.calls == [
        (member.receipt_id, member.receipt_sha256) for member in case.envelope.receipt_v5_roster
    ]
    _assert_closed_public_result(result, decision="pass", sources=len(case.receipts))
    rendered = repr(result)
    for source in case.source_texts:
        assert source not in rendered


def test_planner_zero_source_is_not_applicable_and_never_resolves_a_receipt() -> None:
    case = owner_private_v2_planner_case()
    resolver = ExactReceiptResolver(())
    result = _evaluate(case, output=planner_output_bytes(), resolver=resolver)
    assert resolver.calls == []
    _assert_closed_public_result(result, decision="not_applicable", sources=0)


@pytest.mark.parametrize(
    ("role", "output_factory"),
    (
        ("gatherer", gatherer_output_bytes),
        ("verifier", verifier_output_bytes),
        ("synthesizer", synthesizer_output_bytes),
    ),
)
def test_each_nonplanner_role_accepts_only_its_matching_canonical_output(
    role: Literal["gatherer", "verifier", "synthesizer"],
    output_factory: Callable[[], bytes],
) -> None:
    case = owner_private_v2_case(role=role)
    result = _evaluate(case, output=output_factory())
    _assert_closed_public_result(result, decision="pass", sources=1)


@pytest.mark.parametrize(
    ("core_role", "output_role", "output_factory"),
    (
        ("gatherer", "verifier", verifier_output_bytes),
        ("gatherer", "synthesizer", synthesizer_output_bytes),
        ("verifier", "gatherer", gatherer_output_bytes),
        ("verifier", "synthesizer", synthesizer_output_bytes),
        ("synthesizer", "gatherer", gatherer_output_bytes),
        ("synthesizer", "verifier", verifier_output_bytes),
    ),
)
def test_nonplanner_cross_role_output_substitution_rejects(
    core_role: Literal["gatherer", "verifier", "synthesizer"],
    output_role: Literal["gatherer", "verifier", "synthesizer"],
    output_factory: Callable[[], bytes],
) -> None:
    case = owner_private_v2_case(role=core_role)
    payload = output_factory()
    assert case.core.router_role == core_role
    assert f'"role":"{output_role}"'.encode() in payload
    with pytest.raises(adapter.OwnerPrivateOutputSourceAdapterRejected):
        _evaluate(case, output=payload)


def test_nonplanner_empty_source_graph_rejects() -> None:
    case = owner_private_v2_case()
    forged_core = case.core.model_copy(update={"private_sources": ()})
    forged = case.envelope.model_copy(update={"request_core": forged_core, "receipt_v5_roster": ()})
    with pytest.raises(adapter.OwnerPrivateOutputSourceAdapterRejected):
        adapter.evaluate_owner_private_output_source_adapter_v1(
            envelope=forged,
            receipt_resolver=ExactReceiptResolver(()),
            capability_registry=case.registry,
            output_bytes=gatherer_output_bytes(),
            now_ms=NOW_MS,
        )


@pytest.mark.parametrize("shape", ("missing", "extra", "reordered", "duplicate"))
def test_receipt_roster_shape_drift_rejects(shape: str) -> None:
    case = owner_private_v2_multi_case()
    roster = case.envelope.receipt_v5_roster
    if shape == "missing":
        forged_roster = roster[:1]
    elif shape == "extra":
        forged_roster = roster + (roster[-1].model_copy(update={"ordinal": 3}),)
    elif shape == "reordered":
        forged_roster = tuple(reversed(roster))
    else:
        forged_roster = (roster[0], roster[0])
    forged = case.envelope.model_copy(update={"receipt_v5_roster": forged_roster})
    with pytest.raises(adapter.OwnerPrivateOutputSourceAdapterRejected):
        adapter.evaluate_owner_private_output_source_adapter_v1(
            envelope=forged,
            receipt_resolver=ExactReceiptResolver(case.receipts),
            capability_registry=case.registry,
            output_bytes=gatherer_output_bytes(),
            now_ms=NOW_MS,
        )


def test_missing_or_substituted_exact_resolution_rejects() -> None:
    case = owner_private_v2_multi_case()
    first = case.envelope.receipt_v5_roster[0]
    missing = ExactReceiptResolver(
        case.receipts,
        substitutions={(first.receipt_id, first.receipt_sha256): None},
    )
    with pytest.raises(adapter.OwnerPrivateOutputSourceAdapterRejected):
        _evaluate(case, resolver=missing)
    substituted = ExactReceiptResolver(
        case.receipts,
        substitutions={(first.receipt_id, first.receipt_sha256): case.receipts[1]},
    )
    with pytest.raises(adapter.OwnerPrivateOutputSourceAdapterRejected):
        _evaluate(case, resolver=substituted)


def test_multi_source_exact_bytes_and_receipt_rows_cannot_be_swapped() -> None:
    case = owner_private_v2_multi_case()
    first, second = case.core.private_sources
    swapped_sources = (
        first.model_copy(update={"text": second.text}),
        second.model_copy(update={"text": first.text}),
    )
    forged_core = case.core.model_copy(update={"private_sources": swapped_sources})
    forged_envelope = case.envelope.model_copy(update={"request_core": forged_core})
    with pytest.raises(adapter.OwnerPrivateOutputSourceAdapterRejected):
        adapter.evaluate_owner_private_output_source_adapter_v1(
            envelope=forged_envelope,
            receipt_resolver=ExactReceiptResolver(case.receipts),
            capability_registry=case.registry,
            output_bytes=gatherer_output_bytes(),
            now_ms=NOW_MS,
        )
    first_member, second_member = case.envelope.receipt_v5_roster
    resolver = ExactReceiptResolver(
        case.receipts,
        substitutions={
            (first_member.receipt_id, first_member.receipt_sha256): case.receipts[1],
            (second_member.receipt_id, second_member.receipt_sha256): case.receipts[0],
        },
    )
    with pytest.raises(adapter.OwnerPrivateOutputSourceAdapterRejected):
        _evaluate(case, resolver=resolver)


@pytest.mark.parametrize(
    ("target", "field", "replacement"),
    (
        ("core", "owner_scope_sha256", "0" * 64),
        ("core", "operation_id", "other-operation"),
        ("core", "job_id", "other-job"),
        ("core", "execution_id", "other-execution"),
        ("core", "stage_key", "0" * 64),
        ("core", "provider_effect_key", "0" * 64),
        ("core", "router_role", "verifier"),
        ("core", "route_plan_sha256", "0" * 64),
        ("core", "publication_manifest_sha256", "0" * 64),
        ("core", "provider_capability_v2_sha256", "0" * 64),
        ("core", "output_policy_v2_sha256", "0" * 64),
        ("core", "checker_sha256", "0" * 64),
        ("core", "source_extractor_sha256", "0" * 64),
        ("core", "required_until_ms", 4_000),
        ("core", "provider_request_bytes", b"{}"),
        ("core", "request_core_sha256", "0" * 64),
        ("receipt", "owner_scope_sha256", "0" * 64),
        ("receipt", "operation_id", "other-operation"),
        ("receipt", "job_id", "other-job"),
        ("receipt", "execution_id", "other-execution"),
        ("receipt", "stage_key", "0" * 64),
        ("receipt", "router_role", "verifier"),
        ("receipt", "request_core_v2_sha256", "0" * 64),
        ("receipt", "provider_capability_v2_sha256", "0" * 64),
        ("receipt", "output_policy_v2_sha256", "0" * 64),
        ("receipt", "checker_sha256", "0" * 64),
        ("receipt", "source_extractor_sha256", "0" * 64),
        ("receipt", "private_source_ordinal", 2),
        ("receipt", "private_input_bytes", 1),
        ("receipt", "private_input_commitment_sha256", "0" * 64),
        ("receipt", "receipt_sha256", "0" * 64),
        ("v4", "excerpt_sha256", "0" * 64),
        ("v4", "excerpt_bytes", 1),
        ("v4", "private_source_ordinal", 2),
        ("v4", "provider_capability_sha256", "0" * 64),
        ("v4", "receipt_sha256", "0" * 64),
        ("source", "ordinal", 2),
        ("source", "alias", "private-source-0002"),
        ("source", "text", "substituted private bytes"),
    ),
)
def test_complete_authority_join_mutation_matrix_rejects(
    target: str, field: str, replacement: object
) -> None:
    case = owner_private_v2_case()
    envelope = case.envelope
    receipts = case.receipts
    if target == "core":
        core = case.core.model_copy(update={field: replacement})
        envelope = envelope.model_copy(update={"request_core": core})
    elif target == "source":
        source = case.core.private_sources[0].model_copy(update={field: replacement})
        core = case.core.model_copy(update={"private_sources": (source,)})
        envelope = envelope.model_copy(update={"request_core": core})
    else:
        receipt = receipts[0]
        if target == "v4":
            nested = receipt.source_authority_v4.model_copy(update={field: replacement})
            receipt = receipt.model_copy(update={"source_authority_v4": nested})
        else:
            receipt = receipt.model_copy(update={field: replacement})
        receipts = (receipt,)
    with pytest.raises(adapter.OwnerPrivateOutputSourceAdapterRejected):
        adapter.evaluate_owner_private_output_source_adapter_v1(
            envelope=envelope,
            receipt_resolver=ExactReceiptResolver(receipts),
            capability_registry=case.registry,
            output_bytes=gatherer_output_bytes(),
            now_ms=NOW_MS,
        )


def test_revoked_and_expired_capabilities_reject() -> None:
    case = owner_private_v2_case()
    revoked = capability_registry(case.capability, revoked=(case.capability.capability_sha256,))
    with pytest.raises(adapter.OwnerPrivateOutputSourceAdapterRejected):
        _evaluate(case, registry=revoked)
    with pytest.raises(adapter.OwnerPrivateOutputSourceAdapterRejected):
        _evaluate(case, now_ms=case.capability.expires_at_ms)


def test_checker_fail_is_one_redacted_error_with_no_log_or_source_leak(
    caplog: pytest.LogCaptureFixture,
) -> None:
    case = owner_private_v2_case(canary=True)
    copied = gatherer_output_bytes(claim=case.source_texts[0])
    with pytest.raises(adapter.OwnerPrivateOutputSourceAdapterRejected) as raised:
        _evaluate(case, output=copied)
    assert str(raised.value) == "owner-private output source adapter rejected"
    assert repr(raised.value) == "OwnerPrivateOutputSourceAdapterRejected()"
    assert raised.value.__cause__ is None
    combined = str(raised.value) + repr(raised.value) + caplog.text
    assert PRIVATE_CANARY not in combined
    assert case.source_texts[0] not in combined


def test_adapter_performs_no_file_database_network_or_process_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = owner_private_v2_case()

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("adapter attempted I/O")

    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr("pathlib.Path.open", forbidden)
    monkeypatch.setattr("pathlib.Path.read_bytes", forbidden)
    monkeypatch.setattr("sqlite3.connect", forbidden)
    monkeypatch.setattr("socket.socket", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    result = _evaluate(case)
    _assert_closed_public_result(result, decision="pass", sources=1)


def test_semantic_source_attestation_and_domain_separation_are_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert adapter._ADAPTER_DOMAIN == (
        b"antiek.midnight-oil.owner-private-checker-source-adapter.v1\x00"
    )
    assert adapter._CONTRACT_DOMAIN == (
        b"antiek.midnight-oil.owner-private-checker-source-adapter-contract.v1\x00"
    )
    assert adapter._SOURCE_SET_DOMAIN == (
        b"antiek.midnight-oil.owner-private-resolved-checker-source-set.v1\x00"
    )
    adapter.require_private_output_source_adapter_v1_implementation()
    contract = adapter.build_owner_private_output_source_adapter_contract_v1()
    assert (
        contract.implementation_sha256
        == adapter.PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256
    )
    original_read_bytes = Path.read_bytes

    def semantically_changed(path: Path) -> bytes:
        return original_read_bytes(path) + b"\nSEMANTIC_DRIFT_SENTINEL = True\n"

    monkeypatch.setattr(Path, "read_bytes", semantically_changed)
    with pytest.raises(RuntimeError, match="implementation conflicts"):
        adapter.require_private_output_source_adapter_v1_implementation()


@pytest.mark.parametrize(
    "module",
    (
        "interfaces.research.api.app",
        "substrate.midnight_oil",
        "substrate.midnight_oil.runtime",
        "substrate.midnight_oil.live",
        "substrate.midnight_oil.live_stage_engine",
    ),
)
def test_real_production_import_roots_do_not_reach_adapter_or_checker(module: str) -> None:
    script = (
        "import importlib,sys; importlib.import_module(" + repr(module) + "); "
        "forbidden={"
        + repr(_ADAPTER_MODULE)
        + ", 'substrate.midnight_oil.private_output_checker_v2', "
        + repr(_POLICY_V3_MODULE)
        + ", "
        + repr(_CAPABILITY_V3_MODULE)
        + "}; "
        "assert forbidden.isdisjoint(sys.modules), forbidden.intersection(sys.modules)"
    )
    subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT)},
        check=True,
        capture_output=True,
        text=True,
    )


def _forbidden_imports(source: str, *, path: str) -> tuple[str, ...]:
    tree = ast.parse(source, filename=path)
    found: list[str] = []
    allowed = _ALLOWED_IMPORT_DAG.get(path, {})
    controlled = _ISOLATED_MODULES | set(allowed)
    importlib_aliases = {"importlib"}
    import_module_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            importlib_aliases.update(
                alias.asname or alias.name for alias in node.names if alias.name == "importlib"
            )
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            import_module_aliases.update(
                alias.asname or alias.name for alias in node.names if alias.name == "import_module"
            )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _ISOLATED_MODULES:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            raw_module = node.module or ""
            target = next(
                (
                    module
                    for module in controlled
                    if raw_module == module
                    or raw_module == module.rsplit(".", 1)[1]
                    or raw_module.endswith("." + module.rsplit(".", 1)[1])
                ),
                None,
            )
            if target is not None:
                names = frozenset(alias.name for alias in node.names)
                permitted = allowed.get(target)
                if permitted is None or not names.issubset(permitted):
                    found.append(target)
            elif node.level:
                for alias in node.names:
                    target = next(
                        (
                            module
                            for module in _ISOLATED_MODULES
                            if alias.name == module.rsplit(".", 1)[1]
                        ),
                        None,
                    )
                    if target is not None:
                        found.append(target)
        elif isinstance(node, ast.Call) and node.args:
            function = node.func
            dynamic_import = (
                isinstance(function, ast.Name)
                and function.id in {"__import__", *import_module_aliases}
            ) or (
                isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id in importlib_aliases
                and function.attr == "import_module"
            )
            first = node.args[0]
            if (
                dynamic_import
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value in _ISOLATED_MODULES
            ):
                found.append(first.value)
    return tuple(found)


def test_production_ast_import_allowlist_has_teeth() -> None:
    excluded_parts = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "tests"}
    violations = {
        str(path.relative_to(ROOT)): imports
        for path in ROOT.rglob("*.py")
        if not excluded_parts.intersection(path.relative_to(ROOT).parts)
        if (
            imports := _forbidden_imports(
                path.read_text(encoding="utf-8"), path=str(path.relative_to(ROOT))
            )
        )
    }
    assert violations == {}
    planted = "from substrate.midnight_oil.private_output_source_adapter_v1 import evaluate_owner_private_output_source_adapter_v1\n"
    assert _forbidden_imports(planted, path="substrate/midnight_oil/live.py") == (_ADAPTER_MODULE,)
    planted_checker = (
        "from substrate.midnight_oil.private_output_checker_v2 import "
        "check_owner_private_overlap_v2\n"
    )
    assert _forbidden_imports(planted_checker, path="interfaces/research/api/app.py") == (
        _CHECKER_MODULE,
    )
    assert _forbidden_imports(
        "from . import private_output_source_adapter_v1\n",
        path="substrate/midnight_oil/live.py",
    ) == (_ADAPTER_MODULE,)
    assert _forbidden_imports(
        "import importlib\nimportlib.import_module(" + repr(_ADAPTER_MODULE) + ")\n",
        path="services/html_projection/worker.py",
    ) == (_ADAPTER_MODULE,)
    assert _forbidden_imports(
        "__import__(" + repr(_CHECKER_MODULE) + ")\n",
        path="middleware/worker.py",
    ) == (_CHECKER_MODULE,)
    assert _forbidden_imports(
        "import importlib as il\nil.import_module(" + repr(_ADAPTER_MODULE) + ")\n",
        path="runtime/worker.py",
    ) == (_ADAPTER_MODULE,)
    assert _forbidden_imports(
        "from importlib import import_module as load\nload(" + repr(_CHECKER_MODULE) + ")\n",
        path="orchestration/worker.py",
    ) == (_CHECKER_MODULE,)
    assert _forbidden_imports(
        "from .private_output_source_adapter_v1 import "
        "evaluate_owner_private_output_source_adapter_v1\n",
        path="substrate/midnight_oil/private_output_policy_v3.py",
    ) == (_ADAPTER_MODULE,)
    assert _forbidden_imports(
        "from .private_provider_capability_v2 import signed_private_provider_capability_v2\n",
        path="substrate/midnight_oil/private_provider_capability_v3.py",
    ) == ("substrate.midnight_oil.private_provider_capability_v2",)
    assert _forbidden_imports(
        "from substrate.midnight_oil.private_output_policy_v3 import "
        "OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256\n",
        path="interfaces/research/api/app.py",
    ) == (_POLICY_V3_MODULE,)


def test_package_exports_and_application_routes_do_not_publish_adapter() -> None:
    import substrate.midnight_oil as package
    from interfaces.research.api.app import create_app

    assert not hasattr(package, "evaluate_owner_private_output_source_adapter_v1")
    assert not hasattr(package, "OwnerPrivateOutputPolicyV3")
    assert not hasattr(package, "PrivateProviderProcessingCapabilityV3")
    assert not hasattr(package, "PrivateProviderCapabilityV3CurrentResolver")
    paths = {route.path for route in create_app().routes if hasattr(route, "path")}
    assert not any(
        "private-output" in path
        or "source-adapter" in path
        or "capability-v3" in path
        or "policy-v3" in path
        for path in paths
    )


def test_contract_and_source_identity_drift_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = adapter.build_owner_private_output_source_adapter_contract_v1()
    raw = contract.model_dump(mode="python")
    raw["contract_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        adapter.OwnerPrivateOutputSourceAdapterContractV1.model_validate(raw)
    monkeypatch.setattr(adapter, "PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256", "0" * 64)
    with pytest.raises(RuntimeError, match="implementation conflicts"):
        adapter.require_private_output_source_adapter_v1_implementation()


def test_result_json_repr_and_error_surfaces_contain_no_canary() -> None:
    case = owner_private_v2_case(canary=True)
    result = _evaluate(case)
    rendered = repr(result) + json.dumps(_public_mapping(result), sort_keys=True)
    assert PRIVATE_CANARY not in rendered
    for source in case.source_texts:
        assert source not in rendered
