"""Tests for substrate/harness_diff -- snapshot capture, save/load, semantic diff."""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.harness_diff import (
    HarnessSnapshot,
    capture_snapshot,
    diff_snapshots,
    load_snapshot,
    save_snapshot,
)
from substrate.harness_diff.snapshot import list_snapshots
from substrate.hooks import HookRegistry


def test_capture_empty_registry_produces_minimal_snapshot(tmp_path: Path) -> None:
    snap = capture_snapshot(tag="empty", registry=None, project_root=tmp_path)
    assert snap.tag == "empty"
    assert snap.hook_seams == {}
    assert snap.hooks == []


def test_capture_includes_seams_and_hooks(tmp_path: Path) -> None:
    reg = HookRegistry()
    reg.declare_seam("seam_a", "description A")
    reg.declare_seam("seam_b")

    class _H:
        def __call__(self, ctx, **kw):
            return None

    reg.register_hook("seam_a", _H(), "pre", "ext-1", priority=5)
    snap = capture_snapshot(tag="v1", registry=reg, project_root=tmp_path)
    assert snap.hook_seams == {"seam_a": "description A", "seam_b": ""}
    assert len(snap.hooks) == 1


def test_capture_includes_model_config_and_tools_and_prompt_digest(tmp_path: Path) -> None:
    snap = capture_snapshot(
        tag="v1",
        model_config={"primary_model": "claude-opus-4-7", "context_window": 1_000_000},
        tools=[{"name": "run_script", "description": "Execute TS in deno sandbox"}],
        system_prompt="You are a research assistant.",
        project_root=tmp_path,
    )
    assert snap.model_config == {"primary_model": "claude-opus-4-7", "context_window": 1_000_000}
    assert snap.system_prompt_digest is not None and len(snap.system_prompt_digest) == 64


def test_capture_reads_substrate_version_from_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="9.9.9"\n')
    snap = capture_snapshot(tag="v1", project_root=tmp_path)
    assert snap.substrate_version == "9.9.9"


def test_capture_handles_missing_pyproject(tmp_path: Path) -> None:
    snap = capture_snapshot(tag="v1", project_root=tmp_path)
    assert snap.substrate_version == "unknown"


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    snap = capture_snapshot(tag="v1.2.3", model_config={"k": "v"}, project_root=tmp_path)
    path = save_snapshot(snap, tmp_path)
    assert path.exists()
    loaded = load_snapshot("v1.2.3", tmp_path)
    assert loaded == snap


def test_save_sanitizes_dangerous_tag(tmp_path: Path) -> None:
    snap = HarnessSnapshot(tag="../escape", captured_at="t", substrate_version="x")
    path = save_snapshot(snap, tmp_path)
    assert path.parent == tmp_path / ".antiek" / "harness" / "snapshots"
    assert ".." not in path.name


def test_save_rejects_all_unsafe_tag(tmp_path: Path) -> None:
    snap = HarnessSnapshot(tag="///", captured_at="t", substrate_version="x")
    with pytest.raises(ValueError):
        save_snapshot(snap, tmp_path)


def test_load_missing_tag_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_snapshot("never-saved", tmp_path)


def test_list_snapshots_returns_sorted(tmp_path: Path) -> None:
    s1 = HarnessSnapshot(tag="a", captured_at="2026-01-01T00:00:00+00:00", substrate_version="x")
    s2 = HarnessSnapshot(tag="b", captured_at="2026-01-02T00:00:00+00:00", substrate_version="x")
    save_snapshot(s2, tmp_path)
    save_snapshot(s1, tmp_path)
    listed = list_snapshots(tmp_path)
    assert [s.tag for s in listed] == ["a", "b"]


def test_diff_identical_is_empty() -> None:
    s = HarnessSnapshot(tag="v1", captured_at="t", substrate_version="1.0.0")
    d = diff_snapshots(s, s)
    assert d.is_empty()


def test_diff_detects_added_and_removed_seams() -> None:
    a = HarnessSnapshot(tag="a", captured_at="t", substrate_version="x", hook_seams={"keep": "k", "old": "o"})
    b = HarnessSnapshot(tag="b", captured_at="t", substrate_version="x", hook_seams={"keep": "k", "new": "n"})
    d = diff_snapshots(a, b)
    assert d.seams_added == ("new",)
    assert d.seams_removed == ("old",)


def test_diff_detects_changed_seam_description() -> None:
    a = HarnessSnapshot(tag="a", captured_at="t", substrate_version="x", hook_seams={"s": "old desc"})
    b = HarnessSnapshot(tag="b", captured_at="t", substrate_version="x", hook_seams={"s": "new desc"})
    d = diff_snapshots(a, b)
    assert d.seams_changed == (("s", "old desc", "new desc"),)


def test_diff_detects_added_hook() -> None:
    a = HarnessSnapshot(tag="a", captured_at="t", substrate_version="x", hooks=[])
    b_hook = {"seam_id": "s", "extension_id": "ext", "stage": "pre", "priority": 0}
    b = HarnessSnapshot(tag="b", captured_at="t", substrate_version="x", hooks=[b_hook])
    d = diff_snapshots(a, b)
    assert len(d.hooks_added) == 1


def test_diff_detects_model_config_changes() -> None:
    a = HarnessSnapshot(tag="a", captured_at="t", substrate_version="x",
                        model_config={"model": "claude-opus-4-6", "ctx": 1_000_000})
    b = HarnessSnapshot(tag="b", captured_at="t", substrate_version="x",
                        model_config={"model": "claude-opus-4-7", "ctx": 1_000_000, "temp": 0.5})
    d = diff_snapshots(a, b)
    assert d.model_config_changes == {
        "model": ("claude-opus-4-6", "claude-opus-4-7"),
        "temp": (None, 0.5),
    }


def test_diff_detects_tools_changes() -> None:
    a = HarnessSnapshot(tag="a", captured_at="t", substrate_version="x",
                        tools=[{"name": "old_tool", "description": "x"},
                               {"name": "kept", "description": "v1"}])
    b = HarnessSnapshot(tag="b", captured_at="t", substrate_version="x",
                        tools=[{"name": "new_tool", "description": "y"},
                               {"name": "kept", "description": "v2"}])
    d = diff_snapshots(a, b)
    assert d.tools_added == ("new_tool",)
    assert d.tools_removed == ("old_tool",)
    assert d.tools_changed == (("kept", "v1", "v2"),)


def test_diff_detects_system_prompt_changed() -> None:
    a = HarnessSnapshot(tag="a", captured_at="t", substrate_version="x", system_prompt_digest="a" * 64)
    b = HarnessSnapshot(tag="b", captured_at="t", substrate_version="x", system_prompt_digest="b" * 64)
    d = diff_snapshots(a, b)
    assert d.system_prompt_changed


def test_diff_detects_substrate_version_change() -> None:
    a = HarnessSnapshot(tag="a", captured_at="t", substrate_version="1.0.0")
    b = HarnessSnapshot(tag="b", captured_at="t", substrate_version="1.1.0")
    d = diff_snapshots(a, b)
    assert d.substrate_version_changed == ("1.0.0", "1.1.0")


def test_diff_is_empty_helper_negative_when_anything_changed() -> None:
    a = HarnessSnapshot(tag="a", captured_at="t", substrate_version="1.0.0")
    b = HarnessSnapshot(tag="b", captured_at="t", substrate_version="1.0.0", hook_seams={"x": "y"})
    assert not diff_snapshots(a, b).is_empty()
