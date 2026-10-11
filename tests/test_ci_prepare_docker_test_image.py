"""Synthetic CLI responses: these controls never invoke Docker or a registry."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, BinaryIO, cast
from unittest.mock import patch

from tools.ci import prepare_docker_test_image as image

NATIVE_RUN = subprocess.run


def valid_image() -> dict[str, object]:
    return {
        "Id": image.IMAGE_ID,
        "Os": "linux",
        "Architecture": "amd64",
        "RepoDigests": [image.SOURCE_REFERENCE],
    }


class SyntheticDocker:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.environments: list[dict[str, str]] = []
        self.configs: set[Path] = set()
        self.outputs: list[BinaryIO] = []
        self.timeouts: list[int] = []
        self.source_data = json.dumps(valid_image()).encode()
        self.tag_data = self.source_data
        self.fail_at: int | None = None
        self.failure: BaseException | None = None
        self.stderr_data = b""
        self.stderr_outputs: list[BinaryIO] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(list(args))
        self.environments.append(dict(kwargs["env"]))
        self.timeouts.append(kwargs["timeout"])
        config = Path(args[2])
        self.configs.add(config)
        if list(config.iterdir()) or config.stat().st_mode & 0o777 != 0o700:
            raise AssertionError("Each command requires the new private empty configuration")
        if kwargs["stdin"] != subprocess.DEVNULL:
            raise AssertionError("No inherited input or credential-bearing stderr capture")
        diagnostic = cast(BinaryIO, kwargs["stderr"])
        if os.fstat(diagnostic.fileno()).st_mode & 0o777 != 0o600:
            raise AssertionError("The diagnostic sink must be an owned private temporary file")
        self.stderr_outputs.append(diagnostic)
        diagnostic.write(self.stderr_data)
        output = kwargs["stdout"]
        if output != subprocess.DEVNULL:
            self.outputs.append(cast(BinaryIO, output))
        if len(self.calls) == self.fail_at:
            if self.failure is not None:
                raise self.failure
            return subprocess.CompletedProcess[bytes](args, 7)
        if args[5:7] == ["image", "inspect"]:
            output.write(self.tag_data if args[-1] == image.LOCAL_TAG else self.source_data)
        elif output != subprocess.DEVNULL:
            raise AssertionError("Pull and tag output must not be accumulated")
        return subprocess.CompletedProcess[bytes](args, 0)


class DockerImagePreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.docker = SyntheticDocker()
        self.environment_patch = patch.dict(
            os.environ,
            {
                "PATH": "/synthetic",
                "DOCKER_HOST": "tcp://foreign:2376",
                "DOCKER_CONTEXT": "foreign",
                "DOCKER_CONFIG": "/foreign",
                "DOCKER_AUTH_CONFIG": "synthetic-only",
            },
            clear=True,
        )
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)
        self.command_patch = patch.object(subprocess, "run", side_effect=self.docker)
        self.command_patch.start()
        self.addCleanup(self.command_patch.stop)

    def tearDown(self) -> None:
        self.assertTrue(all(not config.exists() for config in self.docker.configs))
        self.assertTrue(all(output.closed for output in self.docker.outputs))

    def assert_refused(self, calls: int) -> None:
        with self.assertRaises(image.ImagePreparationError):
            image.prepare_image()
        self.assertEqual(len(self.docker.calls), calls)
        self.assertEqual(sum(call[5] == "pull" for call in self.docker.calls), 1)

    def source_field(self, key: str, value: object) -> None:
        data = valid_image()
        data[key] = value
        self.docker.source_data = json.dumps(data).encode()
        self.assert_refused(2)

    def tag_field(self, key: str, value: object) -> None:
        data = valid_image()
        data[key] = value
        self.docker.tag_data = json.dumps(data).encode()
        self.assert_refused(4)

    def test_verified_pull_inspect_tag_inspect_order(self) -> None:
        image.prepare_image()
        config = next(iter(self.docker.configs))
        prefix = ["docker", "--config", str(config), "--host", "unix:///var/run/docker.sock"]
        self.assertEqual(
            self.docker.calls,
            [
                [*prefix, "pull", "--platform", "linux/amd64", image.SOURCE_REFERENCE],
                [*prefix, "image", "inspect", "--format", "{{json .}}", image.SOURCE_REFERENCE],
                [*prefix, "tag", image.SOURCE_REFERENCE, "alpine:latest"],
                [*prefix, "image", "inspect", "--format", "{{json .}}", "alpine:latest"],
            ],
        )
        self.assertEqual(self.docker.environments, [{"PATH": "/synthetic"}] * 4)
        self.assertEqual(self.docker.timeouts, [120, 30, 30, 30])
        self.assertEqual(len(self.docker.configs), 1)

    def test_source_wrong_id_refuses_before_tag(self) -> None:
        self.source_field("Id", "sha256:wrong")

    def test_source_wrong_os_refuses_before_tag(self) -> None:
        self.source_field("Os", "windows")

    def test_source_wrong_architecture_refuses_before_tag(self) -> None:
        self.source_field("Architecture", "arm64")

    def test_source_wrong_digest_refuses_before_tag(self) -> None:
        self.source_field("RepoDigests", ["public.ecr.aws/docker/library/alpine@sha256:wrong"])

    def test_source_digest_missing_refuses_before_tag(self) -> None:
        self.source_field("RepoDigests", [])

    def test_source_digest_scalar_refuses_before_tag(self) -> None:
        self.source_field("RepoDigests", image.SOURCE_REFERENCE)

    def test_source_digest_nonstring_refuses_before_tag(self) -> None:
        self.source_field("RepoDigests", [image.SOURCE_REFERENCE, None])

    def test_source_missing_identity_refuses_before_tag(self) -> None:
        self.docker.source_data = b"{}"
        self.assert_refused(2)

    def test_source_empty_response_refuses_before_tag(self) -> None:
        self.docker.source_data = b""
        self.assert_refused(2)

    def test_source_invalid_json_refuses_before_tag(self) -> None:
        self.docker.source_data = b"{invalid"
        self.assert_refused(2)

    def test_source_invalid_unicode_refuses_before_tag(self) -> None:
        self.docker.source_data = b"\xff"
        self.assert_refused(2)

    def test_source_array_refuses_before_tag(self) -> None:
        self.docker.source_data = b"[]"
        self.assert_refused(2)

    def test_source_duplicate_field_refuses_before_tag(self) -> None:
        self.docker.source_data = b'{"Id":"wrong","Id":"also wrong"}'
        self.assert_refused(2)

    def test_source_oversized_response_refuses_before_tag(self) -> None:
        self.docker.source_data = b" " * (image.MAX_INSPECT_BYTES + 1)
        self.assert_refused(2)

    def test_local_tag_wrong_id_refuses_success(self) -> None:
        self.tag_field("Id", "sha256:wrong")

    def test_local_tag_wrong_os_refuses_success(self) -> None:
        self.tag_field("Os", "windows")

    def test_local_tag_wrong_architecture_refuses_success(self) -> None:
        self.tag_field("Architecture", "arm64")

    def test_local_tag_malformed_refuses_success(self) -> None:
        self.docker.tag_data = b"null"
        self.assert_refused(4)

    def test_successful_pull_alone_is_not_verification(self) -> None:
        self.docker.fail_at = 2
        self.assert_refused(2)

    def test_cli_failure_returns_nonzero(self) -> None:
        self.docker.fail_at = 1
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(image.main(), 1)
        self.assertIn("refused", error.getvalue())
        self.assertEqual(len(self.docker.calls), 1)

    def test_cli_success_only_after_final_verification(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(image.main(), 0)
        self.assertIn("Verified", output.getvalue())
        self.assertEqual(len(self.docker.calls), 4)

    def test_pull_native_failure_stops_without_retry(self) -> None:
        self.docker.fail_at = 1
        self.assert_refused(1)

    def test_pull_timeout_stops_without_retry(self) -> None:
        self.docker.fail_at = 1
        self.docker.failure = subprocess.TimeoutExpired("synthetic-docker", 30)
        self.assert_refused(1)

    def test_pull_executable_error_stops_without_retry(self) -> None:
        self.docker.fail_at = 1
        self.docker.failure = OSError("synthetic execution failure")
        self.assert_refused(1)

    def test_source_inspect_native_failure_stops_without_retry(self) -> None:
        self.docker.fail_at = 2
        self.assert_refused(2)

    def test_source_inspect_timeout_stops_without_retry(self) -> None:
        self.docker.fail_at = 2
        self.docker.failure = subprocess.TimeoutExpired("synthetic-docker", 30)
        self.assert_refused(2)

    def test_source_inspect_executable_error_stops_without_retry(self) -> None:
        self.docker.fail_at = 2
        self.docker.failure = OSError("synthetic execution failure")
        self.assert_refused(2)

    def test_tag_native_failure_stops_without_retry(self) -> None:
        self.docker.fail_at = 3
        self.assert_refused(3)

    def test_tag_timeout_stops_without_retry(self) -> None:
        self.docker.fail_at = 3
        self.docker.failure = subprocess.TimeoutExpired("synthetic-docker", 30)
        self.assert_refused(3)

    def test_tag_executable_error_stops_without_retry(self) -> None:
        self.docker.fail_at = 3
        self.docker.failure = OSError("synthetic execution failure")
        self.assert_refused(3)

    def test_local_inspect_native_failure_stops_without_retry(self) -> None:
        self.docker.fail_at = 4
        self.assert_refused(4)

    def test_local_inspect_timeout_stops_without_retry(self) -> None:
        self.docker.fail_at = 4
        self.docker.failure = subprocess.TimeoutExpired("synthetic-docker", 30)
        self.assert_refused(4)

    def test_local_inspect_executable_error_stops_without_retry(self) -> None:
        self.docker.fail_at = 4
        self.docker.failure = OSError("synthetic execution failure")
        self.assert_refused(4)

    def diagnostic_refused(self, data: bytes, category: str, truncated: str = "no") -> str:
        self.docker.fail_at = 1
        self.docker.stderr_data = data
        with (
            contextlib.redirect_stderr(io.StringIO()) as error,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(image.main(), 1)
        message = error.getvalue()
        self.assertIn(f"exit 7; diagnostic={category}; stderr_truncated={truncated}", message)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(len(self.docker.calls), 1)
        self.assertEqual(sum(call[5] == "pull" for call in self.docker.calls), 1)
        self.assertTrue(all(handle.closed for handle in self.docker.stderr_outputs))
        return message

    def test_failed_pull_access_category(self) -> None:
        self.diagnostic_refused(b"unauthorized: authentication required", "access")

    def test_failed_pull_connection_category(self) -> None:
        self.diagnostic_refused(
            b"Cannot connect to the Docker daemon: connection refused", "connection"
        )

    def test_failed_pull_dns_category(self) -> None:
        self.diagnostic_refused(b"lookup synthetic.invalid: no such host", "dns")

    def test_failed_pull_tls_category(self) -> None:
        self.diagnostic_refused(b"x509: certificate signed by unknown authority", "tls")

    def test_failed_pull_rate_category(self) -> None:
        self.diagnostic_refused(b"toomanyrequests: rate limit exceeded", "rate-limit")

    def test_failed_pull_missing_digest_category(self) -> None:
        self.diagnostic_refused(b"manifest unknown: manifest not found", "digest-unavailable")

    def test_failed_pull_unknown_stays_unknown(self) -> None:
        message = self.diagnostic_refused(
            b"PRIVATE_DIAGNOSTIC_MARKER unrecognized failure", "unknown"
        )
        self.assertNotIn("PRIVATE_DIAGNOSTIC_MARKER", message)

    def test_failed_pull_invalid_unicode_remains_private(self) -> None:
        message = self.diagnostic_refused(b"\xff\xfePRIVATE_DIAGNOSTIC_MARKER", "unknown")
        self.assertNotIn("PRIVATE_DIAGNOSTIC_MARKER", message)

    def test_failed_pull_oversized_prefix_does_not_read_late_marker(self) -> None:
        message = self.diagnostic_refused(
            b"a" * image.MAX_DIAGNOSTIC_BYTES + b"unauthorized: PRIVATE_DIAGNOSTIC_MARKER",
            "unknown",
            "yes",
        )
        self.assertNotIn("PRIVATE_DIAGNOSTIC_MARKER", message)

    def test_failed_pull_credentials_and_urls_are_not_published(self) -> None:
        message = self.diagnostic_refused(
            b"unauthorized: https://marker-user:marker-pass@synthetic.invalid/v2?token=marker-token\n"
            b"Authorization: Bearer PRIVATE_DIAGNOSTIC_MARKER",
            "access",
        )
        for marker in (
            "https://",
            "marker-user",
            "marker-pass",
            "marker-token",
            "Authorization",
            "PRIVATE_DIAGNOSTIC_MARKER",
        ):
            self.assertNotIn(marker, message)

    def test_failed_pull_conflicting_categories_stay_unknown(self) -> None:
        self.diagnostic_refused(b"unauthorized: x509: certificate verify failed", "unknown")

    def test_diagnostic_reads_at_most_the_prefix_ceiling(self) -> None:
        class CountingBuffer(io.BytesIO):
            def __init__(self, data: bytes) -> None:
                super().__init__(data)
                self.read_sizes: list[int | None] = []

            def read(self, size: int | None = -1) -> bytes:
                self.read_sizes.append(size)
                return super().read(size)

        sink = CountingBuffer(b"a" * image.MAX_DIAGNOSTIC_BYTES + b"unauthorized:")
        self.assertEqual(image._failure_diagnostic(sink), ("unknown", "yes"))
        self.assertEqual(sink.read_sizes, [65536])

    def test_diagnostic_unavailable_stays_unknown(self) -> None:
        sink = io.BytesIO(b"unauthorized: PRIVATE_DIAGNOSTIC_MARKER")
        sink.close()
        self.assertEqual(image._failure_diagnostic(sink), ("unknown", "unknown"))

    def test_success_closes_all_private_diagnostic_sinks(self) -> None:
        image.prepare_image()
        self.assertEqual(len(self.docker.stderr_outputs), 4)
        self.assertTrue(all(handle.closed for handle in self.docker.stderr_outputs))

    def test_timeout_closes_private_diagnostic_sink_without_retry(self) -> None:
        self.docker.fail_at = 1
        self.docker.failure = subprocess.TimeoutExpired("synthetic-docker", 30)
        self.assert_refused(1)
        self.assertEqual(len(self.docker.stderr_outputs), 1)
        self.assertTrue(self.docker.stderr_outputs[0].closed)

    def test_tiny_local_child_failure_classification_and_stdout_suppression(self) -> None:
        code = (
            "import os; os.write(1, b'PRIVATE_STDOUT_MARKER'); "
            "os.write(2, b'\\xffunauthorized: PRIVATE_DIAGNOSTIC_MARKER'); "
            "raise SystemExit(7)"
        )
        with (
            patch.object(subprocess, "run", NATIVE_RUN),
            self.assertRaises(image.ImagePreparationError) as error,
        ):
            image._command([sys.executable, "-c", code], ["pull"], {"PATH": "/synthetic"})
        self.assertEqual(
            str(error.exception),
            "Docker pull failed with exit 7; diagnostic=access; stderr_truncated=no",
        )

    def test_diagnostic_oserror_read_refusal_stays_unknown_without_output(self) -> None:
        class ReadRefusal(io.BytesIO):
            def __init__(self) -> None:
                super().__init__(b"unauthorized: PRIVATE_DIAGNOSTIC_MARKER")
                self.read_sizes: list[int | None] = []

            def read(self, size: int | None = -1) -> bytes:
                self.read_sizes.append(size)
                raise OSError("PRIVATE_DIAGNOSTIC_MARKER")

        sink = ReadRefusal()
        with (
            contextlib.redirect_stderr(io.StringIO()) as error,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            result = image._failure_diagnostic(sink)
        self.assertEqual(result, ("unknown", "unknown"))
        self.assertEqual(sink.read_sizes, [image.MAX_DIAGNOSTIC_BYTES])
        self.assertEqual(error.getvalue(), "")
        self.assertEqual(output.getvalue(), "")
