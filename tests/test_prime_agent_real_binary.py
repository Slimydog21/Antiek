"""SPR-01 Task 7: opt-in check against a GENUINE prime-agent install.

Every other Prime test in this tree drives a `#!/usr/bin/env python3` or
`#!/bin/sh` stand-in that echoes canned output. Until this file existed, the two
most environment-sensitive pieces of the lane — the ``--help`` capability probe in
``verify_prime_agent_installation`` and the bundle-hashing staging path in
``stage_verified_prime_agent`` — had never executed against the real Node bundle.

Selection: ``-m prime_real`` plus ``ANTIEK_PRIME_AGENT_BIN`` pointing at the
install (npm's ``bin/prime-agent`` symlink or ``dist/bundle/cli.js`` directly; the
resolver follows the link). With the env var unset the module SKIPS with a
reason, so the default suite is unaffected; with it set, a skip is impossible by
construction — a skip under ``-m prime_real`` therefore means the env var did
not reach pytest, not that the check passed.

MANDATORY LOCAL PRE-RATIFICATION CHECK. Run this against the host's install and
read the printed version, file count and byte total before flipping
``ANTIEK_PRIME_AGENT_RLM_ENABLED`` or ``ANTIEK_RLM_RATIFIED`` anywhere. It is not
a CI job: the backend runners install no Node runtime and the pinned prime-agent
tarball is distributed from R2, not public npm, so CI could only ever skip it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from runtime.prime_agent.installation import (
    PRIME_AGENT_BINARY_ENV,
    prime_agent_artifact_digest,
    resolve_prime_agent_binary,
    seal_staged_prime_agent,
    stage_verified_prime_agent,
    validate_staged_prime_agent,
    verify_prime_agent_installation,
)

pytestmark = pytest.mark.prime_real

_CONFIGURED = os.environ.get(PRIME_AGENT_BINARY_ENV, "").strip()


@pytest.fixture()
def real_binary() -> str:
    if not _CONFIGURED:
        pytest.skip(
            f"{PRIME_AGENT_BINARY_ENV} is unset; point it at a genuine prime-agent "
            "install to run the real-binary check"
        )
    return _CONFIGURED


def _tree_stats(root: Path) -> tuple[int, int]:
    files = [p for p in root.rglob("*") if p.is_file() and not p.is_symlink()]
    return len(files), sum(p.stat().st_size for p in files)


def test_real_install_resolves_verifies_and_stages(real_binary: str, tmp_path: Path) -> None:
    binary = resolve_prime_agent_binary()
    print(f"resolved: {binary}")
    assert binary.is_absolute() and binary.is_file()

    # The capability probe: two real spawns (--version, --help) of the real
    # bundle through the same hermetic, staged process envelope as production.
    installation = verify_prime_agent_installation(binary)
    version = ".".join(map(str, installation.version))
    bundle_files = len(installation.bundle)
    bundle_bytes = sum(entry.identity.size for entry in installation.bundle)
    print(f"verified version: {version}")
    print(f"bundle root: {installation.bundle_root}")
    print(f"bundle: {bundle_files} files, {bundle_bytes} bytes")
    print(f"artifact digest: {prime_agent_artifact_digest(installation)}")
    assert installation.version >= (0, 7, 0)

    # One staging round trip into a private tree, sealed and re-validated
    # exactly as the process cache does before every spawn.
    destination = tmp_path / "staged"
    entrypoint = stage_verified_prime_agent(installation, destination)
    seal_staged_prime_agent(destination)
    staged_files, staged_bytes = _tree_stats(destination)
    print(f"staged: {staged_files} files, {staged_bytes} bytes -> {entrypoint}")
    assert entrypoint.is_file()
    if installation.bundle_root is not None:
        assert (staged_files, staged_bytes) == (bundle_files, bundle_bytes)
    else:
        # A single-file install (e.g. a wrapper script): only the binary is staged.
        assert (staged_files, staged_bytes) == (1, installation.identity.size)
    assert validate_staged_prime_agent(installation, destination) == entrypoint
