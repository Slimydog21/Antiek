"""The two Prime Agent invocation postures, named so the difference is reviewable.

Today every Prime Agent ``-p`` run is built from one hardcoded flag tuple. That
tuple is a security envelope rather than a configuration accident:
``PrimeAgentRLMBackend.run_session``'s own docstring calls it "the same
least-privilege subprocess envelope", and
``test_success_uses_fixed_argv_safe_cwd_and_sanitized_environment`` pins its
clauses beside the assertions that the prompt never reaches argv, that
``--api-key`` never reaches argv, and that ``OPENAI_API_KEY`` and
``AWS_SECRET_ACCESS_KEY`` are stripped from the child environment.

This module does not change that envelope. It gives it a name, ``EVIDENCE``,
and writes down next to it the one variant anybody has a reason to want,
``RLM`` — so that the cost of the change is stated in the tree rather than
rediscovered in a review.

What separates the two, and what does not
-----------------------------------------
``RLM`` drops ``--no-tools`` and nothing else. ``--no-tools`` is the flag that
removes ``ipython``, and ``ipython`` over a persistent kernel is the whole of
Prime's RLM mechanism: the binary's own ``--help`` line reads "AI coding
assistant with a Python REPL tool". Every other flag survives in both
profiles, because each one answers a question that has nothing to do with
tools:

``--offline`` and ``--no-session``
    Mode. No startup network, no session written to disk.

``--no-extensions``, ``--no-skills``, ``--no-prompt-templates``,
``--no-themes``, ``--no-context-files``
    Discovery. These stop the *host operator's* own ``CLAUDE.md``, skills,
    prompt templates and themes from being read into a server-side run. That
    hazard is orthogonal to tools and it does not go away when tools arrive,
    so neither do the flags.

Why ``RLM`` exists here and is wired to nothing
-----------------------------------------------
A seam with no consumer is usually an antipattern, and in this repository it
is a diagnosed one: eight RLM sites accept a ``prime_backend`` because each
was built before anything called it. Adding a ninth inert thing would repeat
that mistake, so the shape here is deliberately not that shape.

``EVIDENCE`` is not a seam waiting for a consumer. It *is* the production
argv — ``PrimeAgentRLMBackend._argv`` builds from ``ACTIVE_PROFILE`` below, so
this module is load-bearing from the commit that introduces it, and it earns
its place by holding in one reviewable spot a flag list that three files
currently restate independently (``prime_agent_backend._argv``,
``prime_rpc_evidence._argv``, and the ``_PRINT_FLAGS`` set that
``verify_prime_agent_installation`` probes the binary against). Those three
have to agree; until now nothing checked that they did.

``RLM`` is the other half of the same written-down decision: a value, pinned
by tests, that no code path selects. ``ACTIVE_PROFILE`` is the single
greppable place that would have to change, and a test asserts it is
``EVIDENCE``.

**``RLM`` must not be selected until Prime execution is contained.** As of
this commit it is not. ``PrimeAgentRLMBackend.run`` reaches
``run_prime_agent_process``, which calls ``subprocess.Popen`` directly at
``runtime/prime_agent/process.py:124`` — a child of the API process, on the
host, as the service user. No ``ExecutionBackend`` and no ``Workspace``
appears anywhere under ``runtime/prime_agent/`` or ``orchestration/rlm/``.
The contained gather loop added at
``runtime/research_runner/contained_gather.py`` contains a stdlib-only
placeholder program and never mentions Prime; the two paths do not meet.
Prime Agent's own README says its worker and kernel processes are not a
security sandbox, so on this deployment a tool-enabled run reads
``/etc/antiek/secrets.env`` and the whole corpus with the service user's
permissions.

When containment does land, ``--tools`` is the better lever than dropping
``--no-tools``. Prime 0.9.4 advertises ``-t, --tools <list>`` — "Allowlist
comma-separated tool names" — which grants exactly ``ipython`` instead of
granting everything. That flag is not in the installation probe's
``_PRINT_FLAGS`` set and has not been exercised against a real provider here,
so it is recorded as the recommended tightening rather than shipped untested.
"""

from __future__ import annotations

from enum import StrEnum

#: Output and session mode. Identical in both profiles.
MODE_FLAGS: tuple[str, ...] = ("--offline", "--no-session")

#: The flag that removes the ``ipython`` tool, and with it Prime's RLM
#: mechanism. This is the single clause the two profiles disagree about.
TOOL_FLAG: str = "--no-tools"

#: Host-discovery suppression. Identical in both profiles, deliberately: these
#: keep the operator's own agent configuration out of a server-side run, which
#: is a separate hazard from tool execution and survives it.
DISCOVERY_FLAGS: tuple[str, ...] = (
    "--no-extensions",
    "--no-skills",
    "--no-prompt-templates",
    "--no-themes",
    "--no-context-files",
)


class PrimeInvocationProfile(StrEnum):
    """Which capability envelope a ``prime-agent -p`` invocation runs under."""

    #: Today's posture, byte-for-byte. Tools off; Prime is a bounded second
    #: opinion that returns text marked ``supplemental``.
    EVIDENCE = "evidence"

    #: Tools on, everything else unchanged. Requires contained execution.
    #: Nothing selects this.
    RLM = "rlm"

    @property
    def tools_enabled(self) -> bool:
        """Whether this profile lets the model run code."""
        return self is PrimeInvocationProfile.RLM

    def print_mode_flags(self) -> tuple[str, ...]:
        """The flag block a ``-p`` run carries between executable and ``--cwd``.

        Order is part of the contract: ``EVIDENCE`` reproduces the historical
        argv exactly, and ``test_prime_invocation_profile`` compares it against
        a literal copy of that tuple so a reordering fails loudly rather than
        quietly changing a pinned command line.
        """
        tools = () if self.tools_enabled else (TOOL_FLAG,)
        return (*MODE_FLAGS, *tools, *DISCOVERY_FLAGS)


#: The profile every Prime invocation in this tree runs under.
#:
#: This is the one line that changes when containment lands. It is a module
#: constant rather than a constructor argument on purpose: a per-call selector
#: would make ``RLM`` reachable by configuration, and the whole point is that
#: it is currently reachable by nothing.
ACTIVE_PROFILE: PrimeInvocationProfile = PrimeInvocationProfile.EVIDENCE


__all__ = [
    "ACTIVE_PROFILE",
    "DISCOVERY_FLAGS",
    "MODE_FLAGS",
    "TOOL_FLAG",
    "PrimeInvocationProfile",
]
