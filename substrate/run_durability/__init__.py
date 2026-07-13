"""Pure run-durability domain layer; persistence is injected."""

from .checkpoints import Checkpoint, CheckpointKind, FloorName, FloorObservation
from .fake_runner import FakeDurableRunner, InMemoryEventLogPort
from .policy import FailureDecision, FailureKind, FailurePolicy, PolicyDecision
from .trace import (
    ConcurrentAppendError,
    EventKind,
    EventLogPort,
    RunView,
    TraceError,
    TraceEvent,
    append_cas,
    reconstruct,
)

__all__ = [
    "Checkpoint",
    "CheckpointKind",
    "ConcurrentAppendError",
    "EventKind",
    "EventLogPort",
    "FailureDecision",
    "FailureKind",
    "FailurePolicy",
    "PolicyDecision",
    "FakeDurableRunner",
    "FloorName",
    "FloorObservation",
    "InMemoryEventLogPort",
    "RunView",
    "TraceError",
    "TraceEvent",
    "append_cas",
    "reconstruct",
]
