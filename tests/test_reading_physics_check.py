from __future__ import annotations

from pathlib import Path

from tools.lint import reading_physics_check as rpc


def _point_guard_at(monkeypatch, root: Path) -> Path:
    physics = root / "apps" / "reading" / "src" / "reading-physics"
    aug = physics / "augmentations"
    facets = physics / "facets"
    canon = root / "docs" / "philosophy" / "physics-of-reading.md"

    aug.mkdir(parents=True, exist_ok=True)
    facets.mkdir(parents=True, exist_ok=True)
    canon.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(rpc, "_REPO", root)
    monkeypatch.setattr(rpc, "_PHYSICS_DIR", physics)
    monkeypatch.setattr(rpc, "_AUG_DIR", aug)
    monkeypatch.setattr(rpc, "_FACET_DIR", facets)
    monkeypatch.setattr(rpc, "_CANON", canon)
    monkeypatch.setattr(
        rpc,
        "_SUBSTRATE_READ_API",
        root / "apps" / "reading" / "src" / "lib" / "api",
    )
    return aug


def _write_canon(status: str) -> None:
    rpc._CANON.parent.mkdir(parents=True, exist_ok=True)
    rpc._CANON.write_text(
        f"---\nstatus: {status}\n---\n# Physics of Reading\n", encoding="utf-8"
    )


def _write_violating_augmentation(aug: Path) -> None:
    (aug / "bad.ts").write_text(
        'import _ from "lodash";\n'
        "export function bad() {\n"
        '  localStorage.setItem("x", "y");\n'
        "  return _;\n"
        "}\n",
        encoding="utf-8",
    )


def test_reading_physics_check_is_clean_on_current_tree() -> None:
    assert rpc.find_violations() == []


def test_draft_canon_keeps_findings_advisory(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    root = tmp_path / "tree"
    aug = _point_guard_at(monkeypatch, root)
    _write_canon("draft")
    _write_violating_augmentation(aug)

    assert rpc.main([]) == 0
    out = capsys.readouterr().out
    assert "ADVISORY" in out
    assert "canon status is 'draft'" in out
    assert "PR-2" in out
    assert "PR-8" in out


def test_missing_canon_status_defaults_to_draft(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "tree"
    _point_guard_at(monkeypatch, root)
    rpc._CANON.write_text("# Physics of Reading\n", encoding="utf-8")

    assert rpc.canon_status() == "draft"
    assert rpc.main(["--enforce"]) == 0


def test_ratified_without_enforce_stays_advisory(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    root = tmp_path / "tree"
    aug = _point_guard_at(monkeypatch, root)
    _write_canon("ratified")
    _write_violating_augmentation(aug)

    assert rpc.main([]) == 0
    out = capsys.readouterr().out
    assert "ADVISORY" in out
    assert "--enforce not set" in out
    assert "PR-2" in out
    assert "PR-8" in out


def test_ratified_with_enforce_blocks(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path / "tree"
    aug = _point_guard_at(monkeypatch, root)
    _write_canon("ratified")
    _write_violating_augmentation(aug)

    assert rpc.main(["--enforce"]) == 1
    out = capsys.readouterr().out
    assert "BLOCKING" in out
    assert "PR-2" in out
    assert "PR-8" in out


def test_same_package_helper_import_stays_clean(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "tree"
    aug = _point_guard_at(monkeypatch, root)
    _write_canon("ratified")
    package = aug / "marginalia"
    package.mkdir()
    (package / "helper.ts").write_text("export const helper = 1;\n", encoding="utf-8")
    (package / "index.ts").write_text(
        'import { helper } from "./helper";\n'
        "export const marginalia = helper;\n",
        encoding="utf-8",
    )

    assert rpc.find_violations() == []
    assert rpc.main(["--enforce"]) == 0


def test_pr2_escape_comment_suppresses_persistence_finding(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "tree"
    aug = _point_guard_at(monkeypatch, root)
    _write_canon("ratified")
    (aug / "cache.ts").write_text(
        'localStorage.setItem("view", "open"); // PR-2 escape: bounded view cache\n',
        encoding="utf-8",
    )

    assert rpc.find_violations() == []


def test_literal_boundary_patterns_are_detected(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "tree"
    aug = _point_guard_at(monkeypatch, root)
    _write_canon("ratified")
    (aug / "other.ts").write_text("export const other = 1;\n", encoding="utf-8")
    package = aug / "bad"
    package.mkdir()
    (package / "index.ts").write_text(
        'import { other } from "../other";\n'
        'import { write } from "../../lib/db_lock";\n'
        "export function bad(node: HTMLElement) {\n"
        "  node.appendChild(document.createElement('span'));\n"
        "  node.getBoundingClientRect();\n"
        "  return other + Number(Boolean(write));\n"
        "}\n",
        encoding="utf-8",
    )

    violations = "\n".join(rpc.find_violations())
    assert "PR-1" in violations
    assert "PR-3" in violations
    assert "PR-4/PR-5" in violations
    assert "PR-6" in violations
