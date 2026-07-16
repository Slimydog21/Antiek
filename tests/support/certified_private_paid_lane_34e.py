"""Materialize and probe the exact certified Cycle 34E runtime.

The positive 34F cutover fixture must be created on its live inode by this
historical implementation.  Importing the evolving checkout and merely writing
the predecessor labels would not prove compatibility.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

CERTIFIED_34E_COMMIT: Final = "68f2547c72d7a5351dde67f4fb83daac6fc45508"
CERTIFIED_34E_CHECKPOINT_SOURCE_SHA256: Final = (
    "be1d53dc5661f052e419c79cedb04e9b28e949bf3fc87c56c040eb20c5fb3b90"
)
CERTIFIED_34E_SEMANTIC_SHA256: Final = (
    "a21550642f926069ab730e849fe0ac10718a114f0adb2242e9552a6c0124c7eb"
)
CERTIFIED_34E_CONTRACT_SHA256: Final = (
    "482ab934c724f6f4cc5efa36dad75e89314f4c25a11f78cc17b3ddf90696e757"
)
_CHECKPOINT_PATH: Final = "substrate/midnight_oil/private_paid_lane_authority_checkpoint.py"


def _run(*args: str, cwd: Path, input_bytes: bytes | None = None) -> bytes:
    completed = subprocess.run(
        args,
        cwd=cwd,
        input=input_bytes,
        capture_output=True,
        check=False,
        env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"},
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))
    return completed.stdout


@contextmanager
def materialized_certified_34e_runtime(repo_root: Path) -> Iterator[Path]:
    """Yield an archive-extracted, source-verified historical checkout."""
    canonical_root = repo_root.resolve(strict=True)
    resolved = _run(
        "git", "rev-parse", f"{CERTIFIED_34E_COMMIT}^{{commit}}", cwd=canonical_root
    ).decode("ascii").strip()
    if resolved != CERTIFIED_34E_COMMIT:
        raise RuntimeError("certified 34E commit identity mismatch")
    source = _run(
        "git", "show", f"{CERTIFIED_34E_COMMIT}:{_CHECKPOINT_PATH}", cwd=canonical_root
    )
    if hashlib.sha256(source).hexdigest() != CERTIFIED_34E_CHECKPOINT_SOURCE_SHA256:
        raise RuntimeError("certified 34E checkpoint source mismatch")

    archive = _run("git", "archive", "--format=tar", CERTIFIED_34E_COMMIT, cwd=canonical_root)
    with tempfile.TemporaryDirectory(prefix="antiek-certified-34e-") as temporary:
        extracted = Path(temporary)
        _run("tar", "-xf", "-", "-C", str(extracted), cwd=canonical_root, input_bytes=archive)
        extracted_source = (extracted / _CHECKPOINT_PATH).read_bytes()
        if hashlib.sha256(extracted_source).hexdigest() != CERTIFIED_34E_CHECKPOINT_SOURCE_SHA256:
            raise RuntimeError("materialized 34E checkpoint source mismatch")
        yield extracted


def probe_certified_34e_runtime(repo_root: Path) -> dict[str, str]:
    """Import the historical module in a fresh interpreter and return its pins."""
    probe = """
import json
import os
import sys
import hashlib
sys.path.insert(0, os.getcwd())
from substrate.midnight_oil import private_paid_lane_authority_checkpoint as checkpoint
print(json.dumps({
    "semantic_sha256": checkpoint.PRIVATE_PAID_LANE_CHECKPOINT_SEMANTIC_SHA256_V1,
    "contract_sha256": checkpoint.PRIVATE_PAID_LANE_CHECKPOINT_CONTRACT_SHA256_V1,
    "source_sha256": hashlib.sha256(open(checkpoint.__file__, "rb").read()).hexdigest(),
}, sort_keys=True, separators=(",", ":")))
"""
    with materialized_certified_34e_runtime(repo_root) as runtime_root:
        output = _run(sys.executable, "-I", "-c", probe, cwd=runtime_root)
    parsed = json.loads(output)
    if parsed != {
        "contract_sha256": CERTIFIED_34E_CONTRACT_SHA256,
        "semantic_sha256": CERTIFIED_34E_SEMANTIC_SHA256,
        "source_sha256": CERTIFIED_34E_CHECKPOINT_SOURCE_SHA256,
    }:
        raise RuntimeError("certified 34E runtime identity mismatch")
    return {
        "contract_sha256": CERTIFIED_34E_CONTRACT_SHA256,
        "semantic_sha256": CERTIFIED_34E_SEMANTIC_SHA256,
        "source_sha256": CERTIFIED_34E_CHECKPOINT_SOURCE_SHA256,
    }


__all__ = [
    "CERTIFIED_34E_CHECKPOINT_SOURCE_SHA256",
    "CERTIFIED_34E_COMMIT",
    "CERTIFIED_34E_CONTRACT_SHA256",
    "CERTIFIED_34E_SEMANTIC_SHA256",
    "materialized_certified_34e_runtime",
    "probe_certified_34e_runtime",
]
