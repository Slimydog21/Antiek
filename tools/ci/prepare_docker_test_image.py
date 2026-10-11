"""Prepare the pinned official image used by the unchanged real Docker CI test."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from typing import BinaryIO

REPOSITORY = "public.ecr.aws/docker/library/alpine"
MANIFEST_DIGEST = "sha256:d56c381f961d307a21b3ca004cf1e3910f106644aefb1f43e654c8a56c4fd395"
IMAGE_ID = "sha256:320994c3b997e2ec6433f717f153e108023c5bec8fefa8d76b83451d16d05ea8"
SOURCE_REFERENCE = f"{REPOSITORY}@{MANIFEST_DIGEST}"
LOCAL_TAG = "alpine:latest"
PLATFORM = "linux/amd64"
LOCAL_DAEMON = "unix:///var/run/docker.sock"
MAX_INSPECT_BYTES = 65536
MAX_DIAGNOSTIC_BYTES = 65536
_FAILURE_MARKERS: tuple[tuple[str, tuple[bytes, ...]], ...] = (
    (
        "connection",
        (
            b"cannot connect to the docker daemon",
            b"connection refused",
            b"connection reset",
            b"connection timed out",
            b"context deadline exceeded",
            b"i/o timeout",
        ),
    ),
    (
        "dns",
        (
            b"no such host",
            b"temporary failure in name resolution",
            b"could not resolve host",
        ),
    ),
    (
        "tls",
        (
            b"x509:",
            b"tls handshake",
            b"certificate signed by unknown authority",
            b"certificate has expired",
            b"certificate verify failed",
        ),
    ),
    (
        "access",
        (
            b"unauthorized:",
            b"authentication required",
            b"access denied",
            b"requested access to the resource is denied",
            b"denied:",
            b"403 forbidden",
            b"401 unauthorized",
        ),
    ),
    ("rate-limit", (b"toomanyrequests:", b"too many requests", b"rate limit")),
    (
        "digest-unavailable",
        (b"manifest unknown", b"manifest_unknown", b"no such manifest", b"manifest not found"),
    ),
)


class ImagePreparationError(Exception):
    """The approved local image could not be prepared or verified."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ImagePreparationError("Docker inspection contains duplicate fields")
        result[key] = value
    return result


def _failure_diagnostic(stderr: BinaryIO) -> tuple[str, str]:
    # Only the prefix read is bounded. The private temporary sink can grow while
    # the direct child runs; it is closed and discarded with the command.
    try:
        stderr.seek(0, os.SEEK_END)
        truncated = "yes" if stderr.tell() > MAX_DIAGNOSTIC_BYTES else "no"
        stderr.seek(0)
        prefix = stderr.read(MAX_DIAGNOSTIC_BYTES).lower()
    except OSError:
        return "unknown", "unknown"
    except ValueError:
        return "unknown", "unknown"
    matches = [
        category
        for category, markers in _FAILURE_MARKERS
        if any(marker in prefix for marker in markers)
    ]
    return (matches[0] if len(matches) == 1 else "unknown"), truncated


def _command(
    prefix: list[str],
    arguments: list[str],
    environment: Mapping[str, str],
    *,
    inspect: bool = False,
) -> bytes:
    # run kills and waits for the direct child on timeout. Files close after it returns;
    # this does not promise retirement of Docker daemon work or unrelated processes.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as diagnostic:
        destination: BinaryIO | int = output if inspect else subprocess.DEVNULL
        try:
            result = subprocess.run(
                [*prefix, *arguments],
                stdin=subprocess.DEVNULL,
                stdout=destination,
                stderr=diagnostic,
                env=environment,
                timeout=120 if arguments[0] == "pull" else 30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ImagePreparationError(f"Docker {arguments[0]} did not complete") from error
        if result.returncode != 0:
            category, truncated = _failure_diagnostic(diagnostic)
            raise ImagePreparationError(
                f"Docker {arguments[0]} failed with exit {result.returncode}; "
                f"diagnostic={category}; stderr_truncated={truncated}"
            )
        if not inspect:
            return b""
        output.seek(0)
        data = output.read(MAX_INSPECT_BYTES + 1)
        if len(data) > MAX_INSPECT_BYTES:
            raise ImagePreparationError("Docker inspection exceeds the bounded response size")
        return data


def _verify(data: bytes, *, source: bool) -> None:
    try:
        value: object = json.loads(data, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ImagePreparationError("Docker inspection is not valid JSON") from error
    if not isinstance(value, dict):
        raise ImagePreparationError("Docker inspection is not an image object")
    if (
        value.get("Id") != IMAGE_ID
        or value.get("Os") != "linux"
        or value.get("Architecture") != "amd64"
    ):
        raise ImagePreparationError("Docker image ID or platform differs from the approved image")
    if source:
        digests = value.get("RepoDigests")
        if (
            not isinstance(digests, list)
            or not all(isinstance(item, str) for item in digests)
            or SOURCE_REFERENCE not in digests
        ):
            raise ImagePreparationError("Docker repository digest differs from the approved image")


def prepare_image() -> None:
    """Pull once, verify before tagging, then verify the tag consumed by the real test."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("DOCKER_")}
    with tempfile.TemporaryDirectory(prefix="antiek-ci-image-") as config:
        prefix = ["docker", "--config", config, "--host", LOCAL_DAEMON]
        _command(prefix, ["pull", "--platform", PLATFORM, SOURCE_REFERENCE], environment)
        inspected = _command(
            prefix,
            ["image", "inspect", "--format", "{{json .}}", SOURCE_REFERENCE],
            environment,
            inspect=True,
        )
        _verify(inspected, source=True)
        _command(prefix, ["tag", SOURCE_REFERENCE, LOCAL_TAG], environment)
        tagged = _command(
            prefix,
            ["image", "inspect", "--format", "{{json .}}", LOCAL_TAG],
            environment,
            inspect=True,
        )
        _verify(tagged, source=False)


def main() -> int:
    try:
        prepare_image()
    except ImagePreparationError as error:
        print(f"Official Docker test image preparation refused: {error}", file=sys.stderr)
        return 1
    print("Verified the pinned official linux/amd64 image at alpine:latest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
