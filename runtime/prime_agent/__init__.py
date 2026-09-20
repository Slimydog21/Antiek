"""Shared, hermetic Prime Agent installation and process primitives."""

from runtime.prime_agent.installation import (
    PRIME_AGENT_BINARY_ENV,
    PrimeAgentBinaryIdentity,
    PrimeAgentBundleEntry,
    PrimeAgentInstallation,
    PrimeAgentUnavailable,
    open_verified_prime_agent,
    resolve_prime_agent_binary,
    revalidate_prime_agent_installation,
    stage_verified_prime_agent,
    verify_prime_agent_installation,
)
from runtime.prime_agent.process import (
    PrimeAgentManagedProcess,
    PrimeAgentProcessConfig,
    PrimeAgentProcessResult,
    run_prime_agent_process,
    spawn_prime_agent_managed,
)

__all__ = [
    "PRIME_AGENT_BINARY_ENV",
    "PrimeAgentInstallation",
    "PrimeAgentBinaryIdentity",
    "PrimeAgentBundleEntry",
    "PrimeAgentProcessConfig",
    "PrimeAgentManagedProcess",
    "PrimeAgentProcessResult",
    "PrimeAgentUnavailable",
    "open_verified_prime_agent",
    "resolve_prime_agent_binary",
    "revalidate_prime_agent_installation",
    "run_prime_agent_process",
    "spawn_prime_agent_managed",
    "stage_verified_prime_agent",
    "verify_prime_agent_installation",
]
