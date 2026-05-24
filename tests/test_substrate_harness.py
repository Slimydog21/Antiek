"""Tests for substrate/harness -- fork creation + apply composition + CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.cli.harness import main as harness_cli
from substrate.harness.apply import apply_harness
from substrate.harness.fork import ForkAlreadyExists, create_fork, list_forks
from substrate.harness_diff import HarnessSnapshot, load_snapshot, save_snapshot
from substrate.observability.burn import BurnRecorder
from substrate.queue import get_registry as get_queue_registry


@pytest.fixture(autouse=True)
def _reset_singletons():
    BurnRecorder._reset_instances()
    get_queue_registry().reset()
    yield
    BurnRecorder._reset_instances()
    get_queue_registry().reset()


def test_create_fork_scaffolds_full_layout(tmp_path: Path) -> None:
    fork = create_fork("autoresearch", tmp_path)
    assert fork.path.is_dir()
    assert (fork.path / "extension.py").is_file()
    assert (fork.path / "config.toml").is_file()
    assert (fork.path / "README.md").is_file()
    for sub in ("hooks", "tools", "prompts", "adapters"):
        assert (fork.path / sub).is_dir()


def test_create_fork_extension_loads_cleanly(tmp_path: Path) -> None:
    create_fork("mojojojo", tmp_path)
    result = apply_harness(project_root=tmp_path)
    by_id = {r.extension_id: r for r in result.extension_results}
    assert by_id["project:mojojojo"].status == "loaded"


def test_create_fork_refuses_overwrite(tmp_path: Path) -> None:
    create_fork("dup", tmp_path)
    with pytest.raises(ForkAlreadyExists):
        create_fork("dup", tmp_path)


def test_create_fork_rejects_unsafe_name(tmp_path: Path) -> None:
    for name in ("", "/escape", "..parent", ".hidden"):
        with pytest.raises(ValueError):
            create_fork(name, tmp_path)


def test_list_forks_empty_when_no_extensions_dir(tmp_path: Path) -> None:
    assert list_forks(tmp_path) == []


def test_list_forks_returns_all(tmp_path: Path) -> None:
    create_fork("a", tmp_path)
    create_fork("b", tmp_path)
    forks = list_forks(tmp_path)
    assert {f.name for f in forks} == {"a", "b"}


def test_apply_loads_all_forks_by_default(tmp_path: Path) -> None:
    create_fork("a", tmp_path)
    create_fork("b", tmp_path)
    result = apply_harness(project_root=tmp_path)
    statuses = {r.extension_id: r.status for r in result.extension_results}
    assert statuses == {"project:a": "loaded", "project:b": "loaded"}


def test_apply_with_fork_name_loads_only_that_fork(tmp_path: Path) -> None:
    create_fork("kept", tmp_path)
    create_fork("ignored", tmp_path)
    result = apply_harness(project_root=tmp_path, fork_name="kept")
    assert len(result.extension_results) == 1
    assert result.extension_results[0].extension_id == "project:kept"


def test_apply_reads_compaction_config_from_fork(tmp_path: Path) -> None:
    create_fork("rsearch", tmp_path)
    cfg = tmp_path / "antiek_extensions" / "rsearch" / "config.toml"
    cfg.write_text(
        '[fork]\nname = "rsearch"\n'
        '[compaction]\npolicy = "lossy"\nthreshold_pct = 0.7\nkeep_first_n = 2\nkeep_last_n = 4\n'
    )
    result = apply_harness(project_root=tmp_path, fork_name="rsearch")
    assert result.compaction_config.policy.value == "lossy"
    assert result.compaction_config.threshold_pct == 0.7


def test_apply_registers_queues_from_config(tmp_path: Path) -> None:
    create_fork("rsearch", tmp_path)
    cfg = tmp_path / "antiek_extensions" / "rsearch" / "config.toml"
    cfg.write_text(
        '[queues]\n'
        '"autoresearch.fanout" = { capacity = 20, watermark_pct = 0.7 }\n'
        '"dispatch.batch" = { capacity = 50 }\n'
    )
    result = apply_harness(project_root=tmp_path, fork_name="rsearch")
    assert set(result.queue_names) == {"autoresearch.fanout", "dispatch.batch"}
    reg = get_queue_registry()
    assert reg.get("autoresearch.fanout").capacity == 20


def test_apply_builds_adapter_import_map(tmp_path: Path) -> None:
    create_fork("rsearch", tmp_path)
    adapter_dir = tmp_path / "antiek_extensions" / "rsearch" / "adapters" / "exa"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "index.ts").write_text("export const search = () => null;")
    result = apply_harness(project_root=tmp_path, fork_name="rsearch")
    assert "exa" in result.import_map["imports"]


def test_apply_with_capture_tag_saves_snapshot(tmp_path: Path) -> None:
    create_fork("rsearch", tmp_path)
    result = apply_harness(project_root=tmp_path, fork_name="rsearch", capture_tag="v0.1.0")
    assert result.snapshot_path is not None
    assert result.snapshot_path.exists()
    loaded = load_snapshot("v0.1.0", tmp_path)
    assert loaded.tag == "v0.1.0"


def test_apply_declares_standard_seams(tmp_path: Path) -> None:
    create_fork("rsearch", tmp_path)
    result = apply_harness(project_root=tmp_path, fork_name="rsearch")
    seams = result.registry.seams()
    for s in ("token_count", "edit_validator", "message_formatter", "model_select",
              "tool_dispatch", "run_script_dispatch", "compaction_summarize"):
        assert s in seams


def test_apply_missing_fork_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        apply_harness(project_root=tmp_path, fork_name="nonexistent")


def test_real_hook_registered_through_fork_changes_token_count(tmp_path: Path) -> None:
    create_fork("counter", tmp_path)
    ext_py = tmp_path / "antiek_extensions" / "counter" / "extension.py"
    ext_py.write_text(
        "from substrate.hooks import HookContext, HookRegistry, HookShortCircuit\n"
        "\n"
        "class _Fixed:\n"
        "    def __call__(self, ctx: HookContext, **kw):\n"
        "        raise HookShortCircuit(result=42)\n"
        "\n"
        "def register(registry: HookRegistry) -> None:\n"
        "    registry.register_hook(\n"
        "        seam_id='token_count', hook=_Fixed(), stage='pre',\n"
        "        extension_id='counter:v1', priority=0,\n"
        "    )\n"
    )
    result = apply_harness(project_root=tmp_path, fork_name="counter")
    from substrate.conversation.token_counter import count_tokens
    n = count_tokens(result.registry, text="anything goes here at all", model="m")
    assert n == 42


def test_cli_fork_creates_directory(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = harness_cli(["--project-root", str(tmp_path), "fork", "test_fork"])
    assert rc == 0
    assert (tmp_path / "antiek_extensions" / "test_fork" / "extension.py").exists()


def test_cli_fork_duplicate_returns_nonzero(tmp_path: Path) -> None:
    create_fork("dup", tmp_path)
    rc = harness_cli(["--project-root", str(tmp_path), "fork", "dup"])
    assert rc == 2


def test_cli_apply_with_capture_writes_snapshot(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    create_fork("rsearch", tmp_path)
    rc = harness_cli(
        ["--project-root", str(tmp_path), "apply", "--fork", "rsearch", "--capture", "v0", "--json"]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["snapshot_tag"] == "v0"


def test_cli_diff_between_snapshots(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    s1 = HarnessSnapshot(tag="v1", captured_at="t1", substrate_version="1.0.0")
    s2 = HarnessSnapshot(tag="v2", captured_at="t2", substrate_version="1.1.0", hook_seams={"new": ""})
    save_snapshot(s1, tmp_path)
    save_snapshot(s2, tmp_path)
    rc = harness_cli(["--project-root", str(tmp_path), "diff", "v1", "v2"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "substrate version: 1.0.0 -> 1.1.0" in out
    assert "+ new" in out


def test_cli_status_lists_forks_and_snapshots(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    create_fork("a", tmp_path)
    save_snapshot(HarnessSnapshot(tag="v0", captured_at="t", substrate_version="1.0.0"), tmp_path)
    rc = harness_cli(["--project-root", str(tmp_path), "status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "a" in out and "v0" in out
