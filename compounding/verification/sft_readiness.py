"""Loop 3 SFT-readiness audit.

This read-only audit covers criterion 2 in ``docs/loop_3_unlock_criteria.md``:
an Antiek-specific SFT model must exist, be registered in dispatch config, and
have loss/eval evidence recorded in ``docs/training_log.md`` before any RL work.

The audit does not build or train a model. It only validates the evidence chain
the operator must provide after a real SFT run exists.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_METADATA_PATH = Path("reports/loop3/sft-model.json")
DEFAULT_DISPATCH_CONFIG_PATH = Path("substrate/dispatch/config.yaml")
DEFAULT_TRAINING_LOG_PATH = Path("docs/training_log.md")

REQUIRED_METADATA_FIELDS = (
    "policy_id",
    "base_architecture",
    "rl_target_base_architecture",
    "model_artifact",
    "training_dataset_ref",
    "heldout_eval_ref",
    "model_sha256",
    "train_loss",
    "heldout_eval_score",
    "produced_at",
)


@dataclass(frozen=True)
class SFTReadinessAudit:
    status: str
    metadata_path: str
    dispatch_config_path: str
    training_log_path: str
    policy_id: str | None
    base_architecture: str | None
    rl_target_base_architecture: str | None
    registered_tier: str | None
    checks: list[dict[str, Any]]
    does_not_unlock_loop3: bool = True


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _dispatch_tier_for_policy(config_path: Path, policy_id: str | None) -> str | None:
    if not policy_id or "/" not in policy_id or not config_path.is_file():
        return None
    provider, model = policy_id.split("/", 1)
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    tiers = config.get("tiers")
    if not isinstance(tiers, dict):
        return None
    for tier_name, tier in tiers.items():
        if not isinstance(tier, dict):
            continue
        if tier.get("provider") == provider and tier.get("model") == model:
            return str(tier_name)
    return None


def _training_log_references(
    *,
    training_log_path: Path,
    metadata: dict[str, Any] | None,
) -> bool:
    if not training_log_path.is_file() or metadata is None:
        return False
    try:
        text = training_log_path.read_text(encoding="utf-8")
    except OSError:
        return False
    required_terms = [
        str(metadata.get("policy_id", "")).strip(),
        str(metadata.get("base_architecture", "")).strip(),
        str(metadata.get("rl_target_base_architecture", "")).strip(),
        str(metadata.get("train_loss", "")).strip(),
        str(metadata.get("heldout_eval_score", "")).strip(),
    ]
    return all(term and term in text for term in required_terms)


def _artifact_reference_present(
    metadata: dict[str, Any] | None,
    *,
    metadata_dir: Path,
) -> bool:
    if metadata is None:
        return False
    artifact = metadata.get("model_artifact")
    if not _nonempty_str(artifact):
        return False
    value = artifact.strip()
    if "://" in value:
        return True
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = metadata_dir / path
    return path.exists()


def _has_numeric_metric(metadata: dict[str, Any] | None, field: str) -> bool:
    if metadata is None:
        return False
    value = metadata.get(field)
    if isinstance(value, int | float):
        return True
    if isinstance(value, str) and value.strip():
        try:
            float(value)
        except ValueError:
            return False
        return True
    return False


def _has_sha256(metadata: dict[str, Any] | None) -> bool:
    if metadata is None:
        return False
    value = metadata.get("model_sha256")
    if not isinstance(value, str):
        return False
    stripped = value.strip().lower()
    return len(stripped) == 64 and all(ch in "0123456789abcdef" for ch in stripped)


def _metadata_field_present(metadata: dict[str, Any] | None, field: str) -> bool:
    if field == "model_sha256":
        return _has_sha256(metadata)
    if field in {"train_loss", "heldout_eval_score"}:
        return _has_numeric_metric(metadata, field)
    return metadata is not None and _nonempty_str(metadata.get(field))


def audit_sft_readiness(
    *,
    metadata_path: Path = DEFAULT_METADATA_PATH,
    dispatch_config_path: Path = DEFAULT_DISPATCH_CONFIG_PATH,
    training_log_path: Path = DEFAULT_TRAINING_LOG_PATH,
) -> SFTReadinessAudit:
    metadata_abs = metadata_path.expanduser().resolve()
    dispatch_abs = dispatch_config_path.expanduser().resolve()
    training_log_abs = training_log_path.expanduser().resolve()
    metadata = _load_json_object(metadata_abs) if metadata_abs.is_file() else None
    policy_id = (
        metadata.get("policy_id").strip()
        if metadata is not None and _nonempty_str(metadata.get("policy_id"))
        else None
    )
    base_architecture = (
        metadata.get("base_architecture").strip()
        if metadata is not None and _nonempty_str(metadata.get("base_architecture"))
        else None
    )
    rl_target_base_architecture = (
        metadata.get("rl_target_base_architecture").strip()
        if metadata is not None
        and _nonempty_str(metadata.get("rl_target_base_architecture"))
        else None
    )
    missing_fields = [
        field
        for field in REQUIRED_METADATA_FIELDS
        if not _metadata_field_present(metadata, field)
    ]
    registered_tier = _dispatch_tier_for_policy(dispatch_abs, policy_id)
    checks = [
        {
            "name": "metadata_exists",
            "passed": metadata_abs.is_file(),
            "detail": str(metadata_abs),
        },
        {
            "name": "metadata_required_fields",
            "passed": metadata is not None and not missing_fields,
            "detail": (
                "all required fields present"
                if metadata is not None and not missing_fields
                else "missing: " + ", ".join(missing_fields)
            ),
        },
        {
            "name": "model_artifact_reference",
            "passed": _artifact_reference_present(metadata, metadata_dir=metadata_abs.parent),
            "detail": (
                str(metadata.get("model_artifact"))
                if metadata is not None and metadata.get("model_artifact")
                else "<missing>"
            ),
        },
        {
            "name": "model_sha256_present",
            "passed": _has_sha256(metadata),
            "detail": (
                str(metadata.get("model_sha256"))
                if metadata is not None and metadata.get("model_sha256")
                else "<missing>"
            ),
        },
        {
            "name": "loss_and_eval_metrics_present",
            "passed": _has_numeric_metric(metadata, "train_loss")
            and _has_numeric_metric(metadata, "heldout_eval_score"),
            "detail": (
                "requires numeric train_loss and heldout_eval_score"
            ),
        },
        {
            "name": "base_architecture_matches_rl_target",
            "passed": (
                base_architecture is not None
                and base_architecture == rl_target_base_architecture
            ),
            "detail": (
                f"base_architecture={base_architecture!r} "
                f"rl_target_base_architecture={rl_target_base_architecture!r}"
            ),
        },
        {
            "name": "dispatch_config_exists",
            "passed": dispatch_abs.is_file(),
            "detail": str(dispatch_abs),
        },
        {
            "name": "sft_policy_registered_in_dispatch",
            "passed": registered_tier is not None,
            "detail": (
                f"tier={registered_tier}"
                if registered_tier is not None
                else f"policy_id={policy_id!r} not registered"
            ),
        },
        {
            "name": "training_log_exists",
            "passed": training_log_abs.is_file(),
            "detail": str(training_log_abs),
        },
        {
            "name": "training_log_references_model",
            "passed": _training_log_references(training_log_path=training_log_abs, metadata=metadata),
            "detail": (
                "requires policy_id, base architecture, RL target architecture, "
                "train_loss, and heldout_eval_score"
            ),
        },
    ]
    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return SFTReadinessAudit(
        status=status,
        metadata_path=str(metadata_abs),
        dispatch_config_path=str(dispatch_abs),
        training_log_path=str(training_log_abs),
        policy_id=policy_id,
        base_architecture=base_architecture,
        rl_target_base_architecture=rl_target_base_architecture,
        registered_tier=registered_tier,
        checks=checks,
    )


def format_text(result: SFTReadinessAudit) -> str:
    lines = [
        f"loop3-sft-readiness: {result.status}",
        f"metadata_path: {result.metadata_path}",
        f"dispatch_config_path: {result.dispatch_config_path}",
        f"training_log_path: {result.training_log_path}",
        f"policy_id: {result.policy_id}",
        f"base_architecture: {result.base_architecture}",
        f"rl_target_base_architecture: {result.rl_target_base_architecture}",
        f"registered_tier: {result.registered_tier}",
    ]
    for check in result.checks:
        marker = "PASS" if check["passed"] else "FAIL"
        lines.append(f"{marker} {check['name']}: {check['detail']}")
    lines.append("loop3_unlocked_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Loop 3 SFT evidence. This is read-only and does not train "
            "or unlock Loop 3 by itself."
        )
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=DEFAULT_METADATA_PATH,
        help=f"SFT metadata JSON. Default: {DEFAULT_METADATA_PATH}.",
    )
    parser.add_argument(
        "--dispatch-config",
        type=Path,
        default=DEFAULT_DISPATCH_CONFIG_PATH,
        help=f"Dispatch config YAML. Default: {DEFAULT_DISPATCH_CONFIG_PATH}.",
    )
    parser.add_argument(
        "--training-log",
        type=Path,
        default=DEFAULT_TRAINING_LOG_PATH,
        help=f"Training log markdown. Default: {DEFAULT_TRAINING_LOG_PATH}.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = audit_sft_readiness(
        metadata_path=args.metadata,
        dispatch_config_path=args.dispatch_config,
        training_log_path=args.training_log,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
