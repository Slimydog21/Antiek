"""The Prime invocation profiles, and the three files that must agree with them.

Two jobs. First, prove the default path did not move: ``EVIDENCE`` is compared
against a literal copy of the argv block that ``prime_agent_backend._argv``
carried before this module existed, so a refactor cannot quietly widen a
command line that is a security envelope. Second, prove ``RLM`` is a written
decision and not a live one: nothing selects it, and the flags it keeps are
enumerated rather than described.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from orchestration.rlm.prime_agent_backend import PrimeAgentRequest, PrimeAgentRLMBackend
from orchestration.rlm.prime_authority import PrimeAuthorizationRequest
from orchestration.rlm.prime_invocation_profile import (
    ACTIVE_PROFILE,
    DISCOVERY_FLAGS,
    MODE_FLAGS,
    TOOL_FLAG,
    PrimeInvocationProfile,
)
from orchestration.rlm.prime_rpc_evidence import _argv as _rpc_argv
from runtime.prime_agent.installation import _PRINT_FLAGS

#: A literal, independent copy of the flag block ``prime_agent_backend._argv``
#: hardcoded at ``orchestration/rlm/prime_agent_backend.py:308-322`` before the
#: profile module existed. Deliberately duplicated rather than imported: a test
#: that derived this from the code under test could not detect the code under
#: test changing.
HISTORICAL_FLAG_BLOCK: tuple[str, ...] = (
    "--offline",
    "--no-session",
    "--no-tools",
    "--no-extensions",
    "--no-skills",
    "--no-prompt-templates",
    "--no-themes",
    "--no-context-files",
)


def _authorization() -> PrimeAuthorizationRequest:
    return PrimeAuthorizationRequest(
        owner_id="owner",
        payer_id="payer",
        session_id="session",
        request_id="request",
        idempotency_key="idempotency",
        workflow="evidence",
        prompt_digest=hashlib.sha256(b"prompt").hexdigest(),
        provider="anthropic",
        credential_id="anthropic-primary",
        credential_fingerprint=hashlib.sha256(b"top-secret").hexdigest(),
        credential_env_name="ANTHROPIC_API_KEY",
        model="claude-sonnet",
        prime_version="0.9.4",
        max_cost_micro_usd=500_000,
        issued_at_ms=100,
        expires_at_ms=10_100,
        nonce="nonce",
    )


class TestDefaultPathUnmoved:
    def test_evidence_reproduces_the_historical_flag_block_exactly(self) -> None:
        assert PrimeInvocationProfile.EVIDENCE.print_mode_flags() == HISTORICAL_FLAG_BLOCK

    def test_active_profile_is_evidence_because_execution_is_not_contained(self) -> None:
        # PrimeAgentRLMBackend.run still reaches subprocess.Popen on the host
        # (runtime/prime_agent/process.py:124). Nothing under runtime/prime_agent
        # or orchestration/rlm touches an ExecutionBackend, and the contained
        # gather loop never mentions Prime. Flipping this constant before that
        # changes hands a model-authored script the service user's read access
        # to /etc/antiek/secrets.env and the corpus.
        assert ACTIVE_PROFILE is PrimeInvocationProfile.EVIDENCE
        assert ACTIVE_PROFILE.tools_enabled is False

    def test_backend_argv_is_the_full_historical_command_line(self, tmp_path: Path) -> None:
        backend = PrimeAgentRLMBackend(cwd=tmp_path, environ={})
        argv = backend._argv(PrimeAgentRequest(prompt="p", workflow="w", request_id="r"))
        assert argv == (
            "prime-agent",
            *HISTORICAL_FLAG_BLOCK,
            "--cwd",
            str(tmp_path.resolve()),
            "-p",
        )

    def test_argv_does_not_vary_with_the_request(self, tmp_path: Path) -> None:
        backend = PrimeAgentRLMBackend(cwd=tmp_path, environ={})
        first = backend._argv(PrimeAgentRequest(prompt="a", workflow="w", request_id="1"))
        second = backend._argv(PrimeAgentRequest(prompt="b", workflow="w", request_id="2"))
        assert first == second


class TestRlmProfileIsWrittenDownNotWiredUp:
    def test_rlm_drops_the_tool_flag_and_only_the_tool_flag(self) -> None:
        evidence = PrimeInvocationProfile.EVIDENCE.print_mode_flags()
        rlm = PrimeInvocationProfile.RLM.print_mode_flags()
        assert set(evidence) - set(rlm) == {TOOL_FLAG}
        assert set(rlm) - set(evidence) == set()

    def test_rlm_keeps_every_discovery_flag(self) -> None:
        # These suppress the host operator's own CLAUDE.md, skills, prompt
        # templates and themes. That hazard is orthogonal to tool execution, so
        # enabling tools is not a reason to drop any of them.
        rlm = PrimeInvocationProfile.RLM.print_mode_flags()
        for flag in (*MODE_FLAGS, *DISCOVERY_FLAGS):
            assert flag in rlm

    def test_no_production_code_path_selects_rlm(self, tmp_path: Path) -> None:
        # The constructor takes no profile argument, so RLM cannot be reached by
        # configuration — only by editing ACTIVE_PROFILE, which the test above
        # pins. Constructing a backend and reading its argv is the whole surface.
        backend = PrimeAgentRLMBackend(cwd=tmp_path, environ={})
        argv = backend._argv(PrimeAgentRequest(prompt="p", workflow="w", request_id="r"))
        assert TOOL_FLAG in argv


class TestTheThreeFlagListsAgree:
    def test_installation_probe_verifies_every_flag_both_profiles_use(self) -> None:
        # verify_prime_agent_installation probes the binary's --help for
        # _PRINT_FLAGS. A profile flag missing from that set would be sent to a
        # binary nobody checked supports it, and would fail at runtime instead
        # of at the installation gate.
        for profile in PrimeInvocationProfile:
            assert set(profile.print_mode_flags()) <= _PRINT_FLAGS

    def test_rpc_evidence_carries_the_same_containment_flags(self) -> None:
        # prime_rpc_evidence builds its own argv for --mode rpc, which has a
        # different shape (no --no-session; it adds --provider/--model). The
        # containment clauses must still match, or the two Prime entry points
        # would run under different postures while both being called "evidence".
        rpc = _rpc_argv(Path("/nonexistent/prime-agent"), _authorization())
        assert TOOL_FLAG in rpc
        for flag in DISCOVERY_FLAGS:
            assert flag in rpc
        assert "--offline" in rpc
