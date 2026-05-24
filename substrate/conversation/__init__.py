"""Conversation substrate -- event-sourced agent conversation with hash-addressed checkpoints and branches."""

from substrate.conversation.branch import BranchLineage, create_branch, list_branches
from substrate.conversation.checkpoint import (
    Checkpoint,
    CheckpointVerifyFailed,
    create_checkpoint,
    list_checkpoints,
    verify_checkpoint,
)
from substrate.conversation.event import Event, EventKind
from substrate.conversation.event_log import ConversationLogCorrupted, EventLog

__all__ = [
    "BranchLineage", "Checkpoint", "CheckpointVerifyFailed",
    "ConversationLogCorrupted", "Event", "EventKind", "EventLog",
    "create_branch", "create_checkpoint", "list_branches",
    "list_checkpoints", "verify_checkpoint",
]
