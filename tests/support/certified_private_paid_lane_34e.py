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
from typing import Final, cast

CERTIFIED_34E_COMMIT: Final = "68f2547c72d7a5351dde67f4fb83daac6fc45508"
CERTIFIED_34E_CHECKPOINT_SOURCE_SHA256: Final = (
    "be1d53dc5661f052e419c79cedb04e9b28e949bf3fc87c56c040eb20c5fb3b90"
)
CERTIFIED_34E_SUPPORT_SOURCE_SHA256: Final = (
    "a2e93747a8e8be69623b1fcff7fb76dc25d198fcebbd1d8a5e3c96a171dbdcb3"
)
CERTIFIED_34E_STORE_ID: Final = "mpstore1_" + "b2" * 32
CERTIFIED_34E_SEMANTIC_SHA256: Final = (
    "a21550642f926069ab730e849fe0ac10718a114f0adb2242e9552a6c0124c7eb"
)
CERTIFIED_34E_CONTRACT_SHA256: Final = (
    "482ab934c724f6f4cc5efa36dad75e89314f4c25a11f78cc17b3ddf90696e757"
)
_CHECKPOINT_PATH: Final = "substrate/midnight_oil/private_paid_lane_authority_checkpoint.py"
_SUPPORT_PATH: Final = "tests/support/private_paid_lane_authority_checkpoint_v1.py"


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
    support_source = _run(
        "git", "show", f"{CERTIFIED_34E_COMMIT}:{_SUPPORT_PATH}", cwd=canonical_root
    )
    if hashlib.sha256(support_source).hexdigest() != CERTIFIED_34E_SUPPORT_SOURCE_SHA256:
        raise RuntimeError("certified 34E support source mismatch")

    archive = _run("git", "archive", "--format=tar", CERTIFIED_34E_COMMIT, cwd=canonical_root)
    with tempfile.TemporaryDirectory(prefix="antiek-certified-34e-") as temporary:
        extracted = Path(temporary)
        _run("tar", "-xf", "-", "-C", str(extracted), cwd=canonical_root, input_bytes=archive)
        extracted_source = (extracted / _CHECKPOINT_PATH).read_bytes()
        if hashlib.sha256(extracted_source).hexdigest() != CERTIFIED_34E_CHECKPOINT_SOURCE_SHA256:
            raise RuntimeError("materialized 34E checkpoint source mismatch")
        if (
            hashlib.sha256((extracted / _SUPPORT_PATH).read_bytes()).hexdigest()
            != CERTIFIED_34E_SUPPORT_SOURCE_SHA256
        ):
            raise RuntimeError("materialized 34E support source mismatch")
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


def create_certified_34e_schema_only_genesis(
    repo_root: Path, destination_root: Path
) -> dict[str, int | str]:
    """Create the historical schema-only target directly at its final pathname."""
    if destination_root.exists():
        raise ValueError("certified 34E destination must be fresh")
    create_script = """
import json
import os
import sqlite3
import sys
import hashlib
from pathlib import Path
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
from substrate.midnight_oil import private_paid_lane_authority_checkpoint as checkpoint
from support import private_paid_lane_authority_checkpoint_v1 as support

if hashlib.sha256(open(support.__file__, "rb").read()).hexdigest() != "a2e93747a8e8be69623b1fcff7fb76dc25d198fcebbd1d8a5e3c96a171dbdcb3":
    raise RuntimeError("historical support import mismatch")

destination = Path(sys.argv[1])
destination.mkdir(mode=0o700, parents=False)
destination.chmod(0o700)
legacy_root = support.QuarantinedSyntheticLegacyRootV1.create_new(
    root_path=destination / "legacy-root",
    root_id="certified-34e-root",
    writer_inventory=support._CHILD_ROLES,
    source_store_identities=support._CHILD_ROLES,
    now_ms=0,
    typed_rows=support.fixture_genesis_migration_rows(),
)
authority = support.OpaqueOwnerPathAuthority()
target = destination / "paid-lane.sqlite3"
store = checkpoint.PrivatePaidLaneEligibilityCheckpointStoreV1.open(
    database_path=target,
    open_mode="create_epoch0",
    expected_store_id=support.STORE_ID,
    expected_schema_version=1,
    expected_migration_epoch=0,
    expected_cutover_marker_sha256=None,
    expected_source_manifest_sha256=None,
    expected_copy_audit_sha256=None,
    expected_external_pin_store_id=support.STORE_ID,
    expected_semantic_source_sha256=checkpoint.PRIVATE_PAID_LANE_CHECKPOINT_SEMANTIC_SHA256_V1,
    expected_contract_sha256=checkpoint.PRIVATE_PAID_LANE_CHECKPOINT_CONTRACT_SHA256_V1,
    provider_capability_verification_keys=support.capability_verification_keys(),
    provider_revocation_verification_keys=support.revocation_verification_keys(),
    source_head_verification_keys=support.source_head_verification_keys(),
    cutover_verification_keys=support.cutover_verification_keys(),
    provider_revocation_floor_pins=support.provider_revocation_floor_pins(),
    source_floor_pins=support.source_floor_pins(),
    source_bundle_key_provider=support.FixtureSourceKeyProvider(),
    owner_key_provider=support.FixtureOwnerKeyProvider(authority),
    synthetic_legacy_root=legacy_root,
    synthetic_external_pin_store=support._OpenExternalPinStoreV1(store_id=support.STORE_ID),
)
if store.database_path != target.resolve():
    raise RuntimeError("historical target path mismatch")
with sqlite3.connect(target) as connection:
    schema = connection.execute(
        "SELECT schema_version,migration_epoch,store_id,semantic_source_sha256,"
        "contract_sha256,cutover_marker_sha256 FROM paid_lane_schema WHERE singleton=1"
    ).fetchone()
    non_schema_rows = sum(
        connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        for name in checkpoint._EXPECTED_TABLE_SET
        if name != "paid_lane_schema"
    )
info = target.stat(follow_symlinks=False)
root_info = legacy_root.root_path.stat(follow_symlinks=False)
root_record = json.loads(
    (legacy_root.root_path / "legacy-root-state-v1.json").read_text(encoding="utf-8")
)
print(json.dumps({
    "target_path": os.fspath(target.resolve()),
    "target_device": info.st_dev,
    "target_inode": info.st_ino,
    "schema_version": schema[0],
    "migration_epoch": schema[1],
    "store_id": schema[2],
    "semantic_sha256": schema[3],
    "contract_sha256": schema[4],
    "cutover_marker": "null" if schema[5] is None else schema[5],
    "non_schema_rows": non_schema_rows,
    "root_path": os.fspath(legacy_root.root_path.resolve()),
    "root_device": root_info.st_dev,
    "root_inode": root_info.st_ino,
    "root_id": root_record["root_id"],
    "root_manifest_sha256": root_record["root_manifest_sha256"],
    "inventory_sha256": root_record["inventory_sha256"],
    "root_state": root_record["state"],
    "support_source_sha256": hashlib.sha256(open(support.__file__, "rb").read()).hexdigest(),
}, sort_keys=True, separators=(",", ":")))
"""
    with materialized_certified_34e_runtime(repo_root) as runtime_root:
        output = _run(
            sys.executable,
            "-I",
            "-c",
            create_script,
            str(destination_root.resolve(strict=False)),
            cwd=runtime_root,
        )
    parsed: object = json.loads(output)
    if type(parsed) is not dict:
        raise RuntimeError("certified 34E genesis response shape")
    result = dict(parsed)
    expected = {
        "contract_sha256": CERTIFIED_34E_CONTRACT_SHA256,
        "cutover_marker": "null",
        "migration_epoch": 0,
        "non_schema_rows": 0,
        "schema_version": 1,
        "semantic_sha256": CERTIFIED_34E_SEMANTIC_SHA256,
        "store_id": CERTIFIED_34E_STORE_ID,
        "root_id": "certified-34e-root",
        "root_state": "open",
        "support_source_sha256": CERTIFIED_34E_SUPPORT_SOURCE_SHA256,
    }
    if any(result.get(key) != value for key, value in expected.items()):
        raise RuntimeError("certified 34E schema-only genesis mismatch")
    target = destination_root / "paid-lane.sqlite3"
    info = target.stat(follow_symlinks=False)
    if (
        result.get("target_path") != str(target.resolve(strict=True))
        or result.get("target_device") != info.st_dev
        or result.get("target_inode") != info.st_ino
    ):
        raise RuntimeError("certified 34E live target identity mismatch")
    legacy_root = destination_root / "legacy-root"
    root_info = legacy_root.stat(follow_symlinks=False)
    if (
        result.get("root_path") != str(legacy_root.resolve(strict=True))
        or result.get("root_device") != root_info.st_dev
        or result.get("root_inode") != root_info.st_ino
    ):
        raise RuntimeError("certified 34E live root identity mismatch")
    if not all(type(value) in {int, str} for value in result.values()):
        raise RuntimeError("certified 34E genesis response values")
    return cast(dict[str, int | str], result)


__all__ = [
    "CERTIFIED_34E_CHECKPOINT_SOURCE_SHA256",
    "CERTIFIED_34E_COMMIT",
    "CERTIFIED_34E_CONTRACT_SHA256",
    "CERTIFIED_34E_SEMANTIC_SHA256",
    "CERTIFIED_34E_STORE_ID",
    "CERTIFIED_34E_SUPPORT_SOURCE_SHA256",
    "materialized_certified_34e_runtime",
    "create_certified_34e_schema_only_genesis",
    "probe_certified_34e_runtime",
]
