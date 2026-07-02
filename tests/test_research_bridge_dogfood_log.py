"""Operator log scaffold tests for the Deep Research Bridge."""

from __future__ import annotations

from pathlib import Path

from substrate.research_bridge.dogfood_log import (
    DOGFOOD_TEMPLATE,
    main,
    write_dogfood_scaffold,
)


def test_dogfood_scaffold_creates_template_and_operator_log(tmp_path: Path) -> None:
    result = write_dogfood_scaffold(tmp_path)

    assert result.root == tmp_path
    assert result.template_path == tmp_path / "_template.md"
    assert result.operator_log_path == tmp_path / "operator-log.md"
    assert result.template_written is True
    assert result.operator_log_written is True

    template = result.template_path.read_text(encoding="utf-8")
    for label in (
        "Project name",
        "Goal",
        "Provider mix",
        "Block count at start / end",
        "Mode(s) used",
        "Draft produced",
        "Did mode A produce something I'd send / publish?",
        "Did mode B's prompts cause me to actually run prompts?",
        "What failed?",
        "What surprised me?",
        "Would I open this again tomorrow?",
    ):
        assert f"## {label}" in template

    log = result.operator_log_path.read_text(encoding="utf-8")
    assert "# Antiek Deep Research Bridge Operator Log" in log
    assert "## Five projects chosen up front" in log
    assert "## Project entries" in log


def test_dogfood_scaffold_preserves_operator_owned_log(tmp_path: Path) -> None:
    first = write_dogfood_scaffold(tmp_path)
    first.operator_log_path.write_text("operator-owned content\n", encoding="utf-8")
    first.template_path.write_text("local template edits\n", encoding="utf-8")

    second = write_dogfood_scaffold(tmp_path)

    assert second.operator_log_written is False
    assert second.template_written is False
    assert second.operator_log_path.read_text(encoding="utf-8") == (
        "operator-owned content\n"
    )
    assert second.template_path.read_text(encoding="utf-8") == "local template edits\n"


def test_dogfood_scaffold_can_refresh_template_only(tmp_path: Path) -> None:
    result = write_dogfood_scaffold(tmp_path)
    result.operator_log_path.write_text("operator-owned content\n", encoding="utf-8")
    result.template_path.write_text("stale template\n", encoding="utf-8")

    refreshed = write_dogfood_scaffold(tmp_path, overwrite_template=True)

    assert refreshed.template_written is True
    assert refreshed.operator_log_written is False
    assert refreshed.template_path.read_text(encoding="utf-8") == DOGFOOD_TEMPLATE
    assert refreshed.operator_log_path.read_text(encoding="utf-8") == (
        "operator-owned content\n"
    )


def test_dogfood_scaffold_cli_init(tmp_path: Path) -> None:
    rc = main(["init", "--root", str(tmp_path)])

    assert rc == 0
    assert (tmp_path / "_template.md").exists()
    assert (tmp_path / "operator-log.md").exists()
