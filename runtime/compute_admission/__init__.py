"""Opt-in, process-local compute admission. No production callers are wired yet."""

from .policy import ComputePolicy, load_policy
from .scheduler import (
    ENABLE_ENV,
    AdmissionScheduler,
    BillingFailure,
    CredentialFailure,
    Decision,
    JobContext,
    JobEnvelope,
    JobRequest,
    JobState,
    OutcomeCode,
)

__all__ = [
    "ENABLE_ENV",
    "AdmissionScheduler",
    "BillingFailure",
    "ComputePolicy",
    "CredentialFailure",
    "Decision",
    "JobContext",
    "JobEnvelope",
    "JobRequest",
    "JobState",
    "OutcomeCode",
    "load_policy",
]
