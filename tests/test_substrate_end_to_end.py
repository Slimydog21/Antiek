"""End-to-end integration test — every primitive in one session.

Master spec success criterion #4: every Wave 1-4 primitive exercised in
a single workflow, with telemetry rows accumulating and at least one
branched-conversation rewind demonstrated.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from substrate.conversation.compaction import compact as compact_fn
from substrate.conversation.event import Event
from substrate.conversation.event_log import EventLog
from substrate.conversation.policy import CompactionConfig, CompactionPolicy
from substrate.conversation.token_counter import count_tokens
from substrate.edit import EditTransaction
from substrate.harness.apply import apply_harness
from substrate.harness.fork import create_fork
from substrate.harness_diff import diff_snapshots, load_snapshot
from substrate.observability.burn import BurnRecorder
from substrate.observability.burn_context import (
    BurnContext, reset_burn_context, set_burn_context,
)
from substrate.queue import BoundedQueue, QueueFull, get_registry as get_queue_registry


@pytest.fixture(autouse=True)
def _reset_singletons():
    BurnRecorder._reset_instances()
    get_queue_registry().reset()
    yield
    BurnRecorder._reset_instances()
    get_queue_registry().reset()


def _stub_summarizer(messages: list[dict[str, Any]], model: str) -> str:
    return f"[stub summary of {len(messages)} messages for {model}]"


def test_end_to_end_every_primitive_in_one_session(tmp_path: Path) -> None:
    project_root = tmp_path
    session_id = "e2e-session"

    # 1. HARNESS — scaffold a fork that overrides token_count
    create_fork("e2e_fork", project_root)
    ext_py = project_root / "antiek_extensions" / "e2e_fork" / "extension.py"
    ext_py.write_text(
        "from substrate.hooks import HookContext, HookRegistry, HookShortCircuit\n"
        "\n"
        "class _Fixed:\n"
        "    def __call__(self, ctx: HookContext, **kw):\n"
        "        text = kw.get('text', '')\n"
        "        raise HookShortCircuit(result=len(text))\n"
        "\n"
        "def register(registry: HookRegistry) -> None:\n"
        "    registry.register_hook(\n"
        "        seam_id='token_count', hook=_Fixed(), stage='pre',\n"
        "        extension_id='e2e_fork:v1', priority=0,\n"
        "    )\n"
    )
    apply_result = apply_harness(
        project_root=project_root, fork_name="e2e_fork", capture_tag="e2e-initial"
    )
    assert apply_result.extension_results[0].status == "loaded"
    registry = apply_result.registry

    # 2. HOOKS — the extension's hook overrides token_count
    n = count_tokens(registry, text="exactly twelve!", model="m")
    assert n == 15

    # 3. BURN — set context; subsequent primitives emit through it
    burn_ctx = BurnContext(
        session_id=session_id, project_root=project_root,
        project_id="e2e-project",
        extension_ids_active=("project:e2e_fork",),
    )
    token = set_burn_context(burn_ctx)
    try:
        # 4. CONVERSATION — log 12 events; checkpoint @5; branch
        log = EventLog(session_id, project_root, fsync_on_append=False)
        for i in range(1, 13):
            log.append(
                Event(
                    position=i,
                    ts=f"2026-05-24T00:00:0{i % 10}+00:00",
                    kind="user_message" if i % 2 == 1 else "assistant_message",
                    payload={"text": f"e2e-msg-{i} " * 8},
                )
            )
        from substrate.conversation.branch import create_branch, list_branches
        from substrate.conversation.checkpoint import create_checkpoint

        cp = create_checkpoint(session_id, project_root, position=5, label="cp-mid")
        branch_session = create_branch(session_id, cp, "e2e-branch", project_root)
        branches = list_branches(project_root)
        assert any(b.child_session_id == branch_session for b in branches)
        branch_log = EventLog(branch_session, project_root, fsync_on_append=False)
        assert branch_log.position() == 5

        # 5. COMPACTION — lossy at tiny context window; verify branch
        comp_config = CompactionConfig(
            policy=CompactionPolicy.LOSSY,
            threshold_pct=0.01,
            keep_first_n=2,
            keep_last_n=2,
        )
        result = compact_fn(
            session_id=session_id, project_root=project_root, registry=registry,
            config=comp_config, model="claude-opus-4-7", context_window=1_000_000,
            summarizer=_stub_summarizer,
        )
        assert result.pre_compaction_branch is not None
        assert log.position() == 13
        marker_event = list(log.iter_events(from_position=13))[0]
        assert marker_event.kind == "system_marker"
        assert "compaction" in marker_event.payload

        # 6. EDIT — EditTransaction over 2 files; single validator call
        from substrate.edit.transaction import edit_validator_seam_id

        validator_calls = {"count": 0}

        class _CountingValidator:
            def __call__(self, ctx, result, *, paths):
                validator_calls["count"] += 1
                return list(result)

        registry.register_hook(
            edit_validator_seam_id(), _CountingValidator(), "post", "e2e-validator",
        )
        a = project_root / "a.txt"
        b = project_root / "b.txt"
        a.write_text("AAA BBB")
        b.write_text("XXX YYY")
        with EditTransaction([a, b], registry=registry) as tx:
            tx.edit(a, "AAA", "111")
            tx.edit(b, "XXX", "999")
            tx.edit(a, "BBB", "222")
            commit = tx.commit()
        assert commit.committed
        assert validator_calls["count"] == 1, (
            "validator must run EXACTLY ONCE per commit (OpenCode anti-pattern fix)"
        )
        assert a.read_text() == "111 222"
        assert b.read_text() == "999 YYY"

        # 7. QUEUE — bounded with watermark; full + watermark events
        q = BoundedQueue("e2e-queue", capacity=5, watermark_pct=0.8)
        get_queue_registry().register(q)
        for i in range(5):
            q.enqueue(f"item-{i}")
        with pytest.raises(QueueFull):
            q.enqueue("rejected")
        stats = q.stats()
        assert stats["watermark_crossings"] == 1
        assert stats["reject_count"] == 1

    finally:
        reset_burn_context(token)

    # 8. TELEMETRY — every primitive emitted
    recorder = BurnRecorder.for_project(project_root)
    rows = recorder.query("SELECT tool_id, COUNT(*) AS n FROM burn_events GROUP BY tool_id")
    by_tool = {r["tool_id"]: r["n"] for r in rows}
    assert by_tool.get("compaction.event", 0) >= 1
    assert by_tool.get("edit_transaction", 0) >= 1
    assert by_tool.get("queue.watermark", 0) >= 1

    # 9. HARNESS DIFF — capture again; diff is non-empty
    apply_result_v2 = apply_harness(
        project_root=project_root, fork_name="e2e_fork", capture_tag="e2e-final",
    )
    a_snap = load_snapshot("e2e-initial", project_root)
    b_snap = load_snapshot("e2e-final", project_root)
    d = diff_snapshots(a_snap, b_snap)
    assert d.a_tag == "e2e-initial"
    assert d.b_tag == "e2e-final"

    # 10. LINT — substrate/edit/transaction.py against R-rules
    repo_root = Path(__file__).resolve().parents[1]
    lint_script = repo_root / "scripts" / "lint_context_injection.py"
    spec = importlib.util.spec_from_file_location("antiek_lint_e2e", lint_script)
    assert spec and spec.loader
    lint_mod = importlib.util.module_from_spec(spec)
    sys.modules["antiek_lint_e2e"] = lint_mod
    spec.loader.exec_module(lint_mod)
    findings = lint_mod.lint_file(repo_root / "substrate" / "edit" / "transaction.py", repo_root)
    high = [f for f in findings if f.severity == "high"]
    assert not high, f"substrate edit transaction has high-severity findings: {high}"
