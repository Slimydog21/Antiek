"""Reversible scoped-read rollout policy; legacy bytes are never served."""

from __future__ import annotations

import hashlib
import json
import os
from enum import StrEnum
from pathlib import Path
from typing import Any

from .authority import OPERATOR_ACCOUNT_ID, ArtifactAuthority, identity_digest
from .migration import ShadowResolution, shadow_resolution
from .observability import record_counter
from .paths import research_artifacts_dir
from .storage import FilesystemArtifactStore, UnsafeArtifactState, _read_regular


class ArtifactRolloutMode(StrEnum):
    SHADOW = "shadow"
    SCOPED = "scoped"
    ENFORCED = "enforced"


_REQUIRED_ACTIVATION_EVIDENCE = frozenset(
    {
        "real_http_canary",
        "backup_restore",
        "artifact_outbox_reconcile",
        "frontend_private_window",
        "tenancy_ratchets",
        "browser_visual_canary",
        "security_gate",
    }
)


def _canonical_receipt_body(receipt: dict[str, Any]) -> str:
    body = {key: value for key, value in receipt.items() if key != "receipt_fingerprint"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _receipt_fingerprint(receipt: dict[str, Any]) -> str:
    body_digest = hashlib.sha256(_canonical_receipt_body(receipt).encode()).hexdigest()
    return identity_digest("rollout-receipt", body_digest)


def _evidence_digest(root: Path, name: str) -> str:
    path = root / ".migration" / "evidence" / f"{name}.json"
    raw = _read_regular(path)
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise UnsafeArtifactState("activation evidence artifact is invalid") from exc
    if (
        not isinstance(document, dict)
        or document.get("gate") != name
        or document.get("status") != "pass"
        or document.get("exit_code") != 0
    ):
        raise UnsafeArtifactState("activation evidence artifact is not terminal-green")
    return hashlib.sha256(raw).hexdigest()


def build_activation_receipt(
    root: Path,
    mode: ArtifactRolloutMode,
    evidence: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Build a root-bound, integrity-protected terminal-green receipt."""
    if set(evidence) != _REQUIRED_ACTIVATION_EVIDENCE:
        raise ValueError("activation evidence set is incomplete")
    normalized: dict[str, dict[str, str]] = {}
    for name in sorted(evidence):
        item = evidence[name]
        if set(item) != {"status", "digest"} or item.get("status") != "pass":
            raise ValueError("activation evidence is not terminal-green")
        digest = item.get("digest")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("activation evidence digest is invalid")
        try:
            stored_digest = _evidence_digest(root, name)
        except (OSError, UnsafeArtifactState) as exc:
            raise ValueError("activation evidence artifact is unavailable") from exc
        if digest != stored_digest:
            raise ValueError("activation evidence digest does not match stored artifact")
        normalized[name] = {"status": "pass", "digest": digest}
    receipt: dict[str, Any] = {
        "version": 2,
        "mode": mode.value,
        "root_digest": identity_digest("rollout-root", str(root.resolve())),
        "evidence": normalized,
    }
    receipt["receipt_fingerprint"] = _receipt_fingerprint(receipt)
    return receipt


def rollout_mode() -> ArtifactRolloutMode:
    raw = os.environ.get("ANTIEK_ARTIFACT_ROLLOUT_MODE", "shadow").strip().lower()
    try:
        return ArtifactRolloutMode(raw)
    except ValueError as exc:
        raise RuntimeError("invalid ANTIEK_ARTIFACT_ROLLOUT_MODE") from exc


def _require_activation_receipt(root: Path, mode: ArtifactRolloutMode) -> None:
    path = root / ".migration" / f"rollout-{mode.value}.json"
    try:
        receipt = json.loads(_read_regular(path).decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, UnsafeArtifactState) as exc:
        raise RuntimeError(f"{mode.value} rollout requires a verified receipt") from exc
    if not isinstance(receipt, dict):
        raise RuntimeError(f"{mode.value} rollout receipt is not terminal-green")
    expected_keys = {
        "version",
        "mode",
        "root_digest",
        "evidence",
        "receipt_fingerprint",
    }
    evidence = receipt.get("evidence")
    valid_evidence = isinstance(evidence, dict) and set(evidence) == _REQUIRED_ACTIVATION_EVIDENCE
    if valid_evidence:
        valid_evidence = all(
            isinstance(item, dict)
            and set(item) == {"status", "digest"}
            and item.get("status") == "pass"
            and isinstance(item.get("digest"), str)
            and len(item["digest"]) == 64
            and all(character in "0123456789abcdef" for character in item["digest"])
            for item in evidence.values()
        )
    if valid_evidence:
        try:
            valid_evidence = all(
                item["digest"] == _evidence_digest(root, name) for name, item in evidence.items()
            )
        # fmt: off -- project supports Python 3.11+; py314 syntax is invalid there.
        except (OSError, UnsafeArtifactState):
            # fmt: on
            valid_evidence = False
    expected_fingerprint = _receipt_fingerprint(receipt)
    if (
        set(receipt) != expected_keys
        or receipt.get("version") != 2
        or receipt.get("mode") != mode.value
        or receipt.get("root_digest") != identity_digest("rollout-root", str(root.resolve()))
        or not valid_evidence
        or receipt.get("receipt_fingerprint") != expected_fingerprint
    ):
        raise RuntimeError(f"{mode.value} rollout receipt is not terminal-green")


def read_canonical_artifact(
    authority: ArtifactAuthority,
    *,
    root: Path | None = None,
    mode: ArtifactRolloutMode | None = None,
    store: FilesystemArtifactStore | None = None,
) -> tuple[str, ShadowResolution | None]:
    """Read only scoped bytes; SHADOW additionally compares operator legacy metadata."""
    root = root or research_artifacts_dir()
    selected = mode or rollout_mode()
    if selected is not ArtifactRolloutMode.SHADOW:
        _require_activation_receipt(root, selected)
    resolution: ShadowResolution | None = None
    if selected is ArtifactRolloutMode.SHADOW and authority.account_id == OPERATOR_ACCOUNT_ID:
        safe_legacy_name = authority.investigation_id.replace("/", "_") + ".html"
        resolution = shadow_resolution(authority, root=root, legacy_source=root / safe_legacy_name)
    else:
        record_counter(root, "artifact_resolution_total", mode="scoped")
    return (store or FilesystemArtifactStore(root)).read(authority), resolution
