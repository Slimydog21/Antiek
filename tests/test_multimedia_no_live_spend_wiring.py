"""Architectural guard: multimedia live spend stays unreachable BY CONSTRUCTION.

The only spend-capable path in the multimedia subsystem is
``KreaProviderAdapter.execute()`` (``substrate/multimedia/provider_router.py``),
which raises ``ProviderUnavailable`` unless a ``transport`` is injected::

    if self._transport is None:
        raise ProviderUnavailable("Krea transport is not configured; ...")

So the "inert-until-authorized" invariant the whole media pipeline relies on holds
ONLY as long as no *shipped* (non-test) module constructs ``KreaProviderAdapter``
with a ``transport=`` argument. Today that is true (zero such call sites on main),
but it is guarded by NOTHING: a single future call site would open live provider
spend with zero change to any gate or pydantic validator. This test makes the
invariant explicit and mechanical.

Design (mirrors the repo's ``lint_tokens`` baseline idiom, not an absolutist ban):
wiring a transport in production is a legitimate *spend-authorization* event — but
it must be a deliberate, reviewed diff, never something slipped in. The guard is a
tripwire with an explicit allowlist (``AUTHORIZED_TRANSPORT_CALLSITES``, empty
today). Any authorized production wiring must add its ``path:lineno`` here in the
same PR, so live-spend authorization is auditable at review time.

Scope / intellectual honesty: tests legitimately pass a fake transport
(``tests/test_multimedia_provider_router.py``) — test files are excluded by design.
A fixture transport in a test is correct; a transport wired into a shipped route or
worker is the defect this guard catches.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_NAME = "KreaProviderAdapter"

# Explicit, reviewed authorizations of a live transport in shipped code.
# Empty by design: adding an entry here IS the spend-authorization review event.
# Format: "<repo-relative-path>:<lineno>".
AUTHORIZED_TRANSPORT_CALLSITES: frozenset[str] = frozenset()


def _is_test_module(path: Path) -> bool:
    return path.name.startswith("test_") or path.name.endswith("_test.py")


def _shipped_multimedia_files() -> list[Path]:
    """Shipped multimedia production surface: substrate/multimedia/** plus any
    interfaces/**/multimedia*.py (routes land in a later PR — guard them forward).
    Excludes test files. The adapter definition itself is safe to scan because
    this guard matches constructor calls, not function definitions.
    """
    files: list[Path] = []
    mm_root = REPO_ROOT / "substrate" / "multimedia"
    if mm_root.exists():
        files.extend(mm_root.rglob("*.py"))
    api_dir = REPO_ROOT / "interfaces" / "research" / "api"
    if api_dir.exists():
        files.extend(api_dir.glob("multimedia*.py"))

    def _keep(p: Path) -> bool:
        return not _is_test_module(p)

    return sorted({p for p in files if _keep(p)})


def _transport_wired_callsites(source: str, rel_name: str) -> list[str]:
    """Return "rel_name:lineno" for every ``KreaProviderAdapter(...)`` call that
    passes a ``transport`` keyword (covers ``transport=`` and ``**{...}`` is left
    to review — a literal keyword is the realistic wiring shape)."""
    tree = ast.parse(source, filename=rel_name)
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id if isinstance(func, ast.Name)
            else func.attr if isinstance(func, ast.Attribute)
            else None
        )
        if name != ADAPTER_NAME:
            continue
        if any(kw.arg == "transport" for kw in node.keywords):
            hits.append(f"{rel_name}:{node.lineno}")
    return hits


def test_no_shipped_multimedia_module_wires_a_live_transport() -> None:
    offenders: list[str] = []
    shipped_files = _shipped_multimedia_files()
    assert REPO_ROOT / "substrate" / "multimedia" / "provider_router.py" in shipped_files
    for path in shipped_files:
        rel = str(path.relative_to(REPO_ROOT))
        for hit in _transport_wired_callsites(path.read_text(encoding="utf-8"), rel):
            if hit not in AUTHORIZED_TRANSPORT_CALLSITES:
                offenders.append(hit)
    assert offenders == [], (
        "Multimedia live spend must be unreachable by construction. A shipped "
        "(non-test) module wired a transport into KreaProviderAdapter:\n  "
        + "\n  ".join(offenders)
        + "\n\nIf this wiring is an intentional, operator-authorized spend path, add "
        "each 'path:lineno' to AUTHORIZED_TRANSPORT_CALLSITES in this file IN THE "
        "SAME PR so the authorization is reviewed and auditable."
    )


def test_guard_detects_a_spliced_live_callsite() -> None:
    """Red-proof: the scanner MUST flag a transport-wired construction (both the
    bare-name and attribute-access call shapes)."""
    bare = (
        "from substrate.multimedia.provider_router import KreaProviderAdapter\n"
        "adapter = KreaProviderAdapter(api_key='k', transport=some_transport)\n"
    )
    attr = (
        "import substrate.multimedia.provider_router as pr\n"
        "adapter = pr.KreaProviderAdapter(transport=some_transport)\n"
    )
    assert _transport_wired_callsites(bare, "<synthetic-bare>"), (
        "guard failed to detect a bare-name transport-wired construction"
    )
    assert _transport_wired_callsites(attr, "<synthetic-attr>"), (
        "guard failed to detect an attribute-access transport-wired construction"
    )


def test_guard_ignores_dry_run_construction_without_transport() -> None:
    """A transport-less construction (dry-run only) is legitimate and must NOT trip."""
    dry = (
        "from substrate.multimedia.provider_router import KreaProviderAdapter\n"
        "adapter = KreaProviderAdapter(api_key='k')\n"
    )
    assert _transport_wired_callsites(dry, "<synthetic-dry>") == []


def test_shipped_filename_containing_test_is_not_misclassified() -> None:
    assert not _is_test_module(Path("latest_renderer.py"))
    assert _is_test_module(Path("test_provider.py"))
    assert _is_test_module(Path("provider_test.py"))
