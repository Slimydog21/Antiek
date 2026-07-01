"""Operator probe for OA-011 production KMS key provisioning.

OA-011 closes only after the operator runs a real KMS data-key round trip in
production and records the evidence. This probe exercises Antiek's production-
shaped ``KMSStubKeyProvider`` while avoiding plaintext or ciphertext output.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

from substrate.graph_per_user import KeyMaterial, KMSStubKeyProvider

DEFAULT_GRAPH_ID = "test-graph"
DEFAULT_KEY_ALIAS_PREFIX = "alias/antiek-graph"


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class KmsKeyProbeResult:
    status: str
    provider: str
    region: str | None
    graph_id: str
    expected_key_id: str
    generated_key_id: str | None
    wrapped_data_key_len: int | None
    plaintext_len: int | None
    checks: list[ProbeCheck]
    does_not_close_oa011: bool = True


ClientFactory = Callable[[str | None], object]


def _aws_boto3_client(region: str | None) -> object:
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is not installed; install `antiek[kms]` on the production host",
        ) from exc
    kwargs = {"region_name": region} if region else {}
    return boto3.client("kms", **kwargs)


def _material_lengths(material: KeyMaterial, plaintext: bytes | None) -> tuple[int, int | None]:
    return len(material.wrapped_data_key), len(plaintext) if plaintext is not None else None


def probe_kms_key(
    *,
    client: object,
    provider: str = "aws",
    region: str | None = None,
    graph_id: str = DEFAULT_GRAPH_ID,
    key_alias_prefix: str = DEFAULT_KEY_ALIAS_PREFIX,
) -> KmsKeyProbeResult:
    expected_key_id = f"{key_alias_prefix}-{graph_id}"
    checks: list[ProbeCheck] = []
    material: KeyMaterial | None = None
    plaintext: bytes | None = None

    checks.append(ProbeCheck(
        name="client_configured",
        passed=client is not None,
        detail=f"provider={provider}",
    ))

    try:
        key_provider = KMSStubKeyProvider(
            client=client,
            key_alias_prefix=key_alias_prefix,
        )
        material = key_provider.generate_data_key(graph_id=graph_id)
    except Exception as exc:  # noqa: BLE001 - live probe reports KMS failures
        checks.append(ProbeCheck(
            name="generate_data_key",
            passed=False,
            detail=f"{type(exc).__name__}: {exc}",
        ))
        return KmsKeyProbeResult(
            status="FAIL",
            provider=provider,
            region=region,
            graph_id=graph_id,
            expected_key_id=expected_key_id,
            generated_key_id=None,
            wrapped_data_key_len=None,
            plaintext_len=None,
            checks=checks,
        )

    checks.append(ProbeCheck(
        name="generate_data_key",
        passed=True,
        detail="KMS returned wrapped data key",
    ))
    checks.append(ProbeCheck(
        name="key_alias_matches_graph",
        passed=material.key_id == expected_key_id,
        detail=f"expected={expected_key_id} actual={material.key_id}",
    ))
    checks.append(ProbeCheck(
        name="wrapped_data_key_present",
        passed=bool(material.wrapped_data_key),
        detail=f"bytes={len(material.wrapped_data_key)}",
    ))

    try:
        plaintext = key_provider.decrypt_data_key(material=material)
    except Exception as exc:  # noqa: BLE001 - live probe reports KMS failures
        checks.append(ProbeCheck(
            name="decrypt_data_key",
            passed=False,
            detail=f"{type(exc).__name__}: {exc}",
        ))
    else:
        checks.append(ProbeCheck(
            name="decrypt_data_key",
            passed=bool(plaintext),
            detail=f"plaintext_bytes={len(plaintext)}",
        ))

    wrapped_len, plaintext_len = _material_lengths(material, plaintext)
    return KmsKeyProbeResult(
        status="PASS" if all(check.passed for check in checks) else "FAIL",
        provider=provider,
        region=region,
        graph_id=graph_id,
        expected_key_id=expected_key_id,
        generated_key_id=material.key_id,
        wrapped_data_key_len=wrapped_len,
        plaintext_len=plaintext_len,
        checks=checks,
    )


def format_text(result: KmsKeyProbeResult) -> str:
    lines = [
        f"kms-key-probe: {result.status}",
        f"provider: {result.provider}",
        f"region: {result.region or ''}",
        f"graph_id: {result.graph_id}",
        f"expected_key_id: {result.expected_key_id}",
        f"generated_key_id: {result.generated_key_id or ''}",
        f"wrapped_data_key_len: {result.wrapped_data_key_len}",
        f"plaintext_len: {result.plaintext_len}",
    ]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa011_closed_by_this_probe: no")
    return "\n".join(lines)


def _client_load_failure_result(
    *,
    provider: str,
    region: str | None,
    graph_id: str,
    key_alias_prefix: str,
    exc: Exception,
) -> KmsKeyProbeResult:
    return KmsKeyProbeResult(
        status="FAIL",
        provider=provider,
        region=region,
        graph_id=graph_id,
        expected_key_id=f"{key_alias_prefix}-{graph_id}",
        generated_key_id=None,
        wrapped_data_key_len=None,
        plaintext_len=None,
        checks=[
            ProbeCheck(
                name="client_configured",
                passed=False,
                detail=f"{type(exc).__name__}: {exc}",
            )
        ],
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the OA-011 production KMS data-key round trip. Does not print "
            "plaintext or wrapped key material and does not close OA-011 by itself."
        )
    )
    parser.add_argument(
        "--provider",
        choices=("aws",),
        default="aws",
        help="KMS provider to instantiate. Default: aws",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
        help="AWS region. Defaults to AWS_REGION/AWS_DEFAULT_REGION.",
    )
    parser.add_argument("--graph-id", default=DEFAULT_GRAPH_ID)
    parser.add_argument("--key-alias-prefix", default=DEFAULT_KEY_ALIAS_PREFIX)
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        client = _aws_boto3_client(args.region)
    except Exception as exc:  # noqa: BLE001 - CLI reports setup failure as probe JSON
        result = _client_load_failure_result(
            provider=args.provider,
            region=args.region,
            graph_id=args.graph_id,
            key_alias_prefix=args.key_alias_prefix,
            exc=exc,
        )
    else:
        result = probe_kms_key(
            client=client,
            provider=args.provider,
            region=args.region,
            graph_id=args.graph_id,
            key_alias_prefix=args.key_alias_prefix,
        )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
