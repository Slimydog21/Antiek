"""Compaction — context-pressure handler with STRICT/LOSSY/INTERACTIVE policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from substrate.conversation.branch import create_branch
from substrate.conversation.checkpoint import create_checkpoint
from substrate.conversation.event import Event
from substrate.conversation.event_log import EventLog
from substrate.conversation.policy import CompactionConfig, CompactionPolicy
from substrate.conversation.token_counter import count_tokens
from substrate.hooks import HookRegistry
from substrate.observability.burn import BurnEvent, BurnRecorder
from substrate.observability.burn_context import current_burn_context


_COMPACTION_MARKER = "[compacted by antiek at position {position} — {n_summarized} messages removed]"


class ContextPressureTooHigh(RuntimeError):
    def __init__(self, current_tokens, threshold, threshold_pct, model, session_id):
        self.current_tokens = current_tokens
        self.threshold = threshold
        self.threshold_pct = threshold_pct
        self.model = model
        self.session_id = session_id
        super().__init__(
            f"context pressure too high for {model}: "
            f"{current_tokens} tokens > threshold {threshold} "
            f"({int(threshold_pct * 100)}% of context window). "
            f"Options: `antiek compact --policy lossy --session {session_id}` "
            f"(creates pre-compaction branch), "
            f"or branch and start fresh: `antiek branch from {session_id}:<position> --name fresh`"
        )


class ContextPressureNeedsOperator(RuntimeError):
    def __init__(self, session_id, current_tokens, threshold):
        self.session_id = session_id
        self.current_tokens = current_tokens
        self.threshold = threshold
        super().__init__(
            f"INTERACTIVE policy: session {session_id} at {current_tokens}/{threshold} tokens. "
            f"Run `antiek compact status` then `antiek compact --policy lossy --session {session_id}` "
            f"or branch."
        )


@dataclass(frozen=True)
class CompactionResult:
    session_id: str
    pre_compaction_branch: str | None
    pre_tokens: int
    post_tokens: int
    n_summarized: int
    position_at_compaction: int
    summary_marker_position: int


Summarizer = Callable[[list[dict[str, Any]], str], str]


def _messages_from_log(log: EventLog) -> list[Event]:
    return list(log.iter_events())


def _format_for_summary(events: list[Event]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in events:
        if e.kind == "user_message":
            out.append({"role": "user", "content": e.payload.get("text", "")})
        elif e.kind == "assistant_message":
            out.append({"role": "assistant", "content": e.payload.get("text", "")})
        elif e.kind == "tool_call":
            out.append({"role": "assistant", "content": f"[tool_call {e.payload.get('tool')}]"})
        elif e.kind == "tool_result":
            out.append({"role": "tool", "content": str(e.payload.get("result", ""))[:500]})
    return out


def _total_text(events: list[Event]) -> str:
    parts: list[str] = []
    for e in events:
        if e.kind in ("user_message", "assistant_message"):
            parts.append(str(e.payload.get("text", "")))
        elif e.kind == "tool_call":
            parts.append(f"{e.payload.get('tool')} {e.payload.get('args')}")
        elif e.kind == "tool_result":
            parts.append(str(e.payload.get("result", "")))
    return "\n".join(parts)


def should_compact(*, registry, log, config, model, context_window, project_id=None):
    text = _total_text(_messages_from_log(log))
    current = count_tokens(registry, text=text, model=model, project_id=project_id)
    threshold = int(context_window * config.threshold_pct)
    return current >= threshold, current, threshold


def compact(*, session_id, project_root, registry, config, model, context_window, summarizer):
    log = EventLog(session_id, project_root, fsync_on_append=False)
    events = _messages_from_log(log)
    text = _total_text(events)
    current_tokens = count_tokens(registry, text=text, model=model)
    threshold = int(context_window * config.threshold_pct)

    if config.policy is CompactionPolicy.STRICT:
        raise ContextPressureTooHigh(
            current_tokens=current_tokens, threshold=threshold,
            threshold_pct=config.threshold_pct, model=model, session_id=session_id,
        )
    if config.policy is CompactionPolicy.INTERACTIVE:
        raise ContextPressureNeedsOperator(
            session_id=session_id, current_tokens=current_tokens, threshold=threshold,
        )

    return _compact_lossy(
        log=log, session_id=session_id, project_root=project_root, registry=registry,
        config=config, model=model, events=events, pre_tokens=current_tokens,
        summarizer=summarizer,
    )


def _compact_lossy(*, log, session_id, project_root, registry, config, model, events, pre_tokens, summarizer):
    if len(events) <= config.keep_first_n + config.keep_last_n:
        return CompactionResult(
            session_id=session_id, pre_compaction_branch=None,
            pre_tokens=pre_tokens, post_tokens=pre_tokens, n_summarized=0,
            position_at_compaction=log.position(), summary_marker_position=log.position(),
        )

    pos_now = log.position()
    cp = create_checkpoint(session_id, project_root, position=pos_now, label="pre-compaction")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch_name = f"pre-compaction-{ts}"
    branch_session = create_branch(session_id, cp, branch_name, project_root)

    first = events[: config.keep_first_n]
    middle = events[config.keep_first_n : len(events) - config.keep_last_n]
    last = events[len(events) - config.keep_last_n :]

    summary_messages = _format_for_summary(middle)
    summary_text = summarizer(summary_messages, config.summary_model or model)
    marker = _COMPACTION_MARKER.format(position=pos_now, n_summarized=len(middle))
    summary_with_marker = f"{marker}\n\n{summary_text}"

    marker_event = Event(
        position=pos_now + 1,
        ts=datetime.now(timezone.utc).isoformat(),
        kind="system_marker",
        payload={
            "compaction": {
                "summary": summary_with_marker,
                "n_summarized": len(middle),
                "pre_compaction_branch": branch_session,
                "pre_compaction_position": pos_now,
            }
        },
    )
    log.append(marker_event)

    post_text = "\n".join(
        [
            *(str(e.payload.get("text", "")) for e in first if e.kind in ("user_message", "assistant_message")),
            summary_with_marker,
            *(str(e.payload.get("text", "")) for e in last if e.kind in ("user_message", "assistant_message")),
        ]
    )
    post_tokens = count_tokens(registry, text=post_text, model=model)

    try:
        ctx = current_burn_context()
        recorder = BurnRecorder.for_project(ctx.project_root)
        recorder.record(
            BurnEvent(
                session_id=session_id, project_id=ctx.project_id,
                call_id=f"compaction-{ts}",
                model=config.summary_model or model, tool_id="compaction.event",
                input_tokens=pre_tokens, output_tokens=post_tokens,
                extension_ids_active=ctx.extension_ids_active,
            )
        )
    except Exception:
        pass

    return CompactionResult(
        session_id=session_id, pre_compaction_branch=branch_session,
        pre_tokens=pre_tokens, post_tokens=post_tokens, n_summarized=len(middle),
        position_at_compaction=pos_now, summary_marker_position=marker_event.position,
    )
