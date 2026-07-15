from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from datetime import UTC, datetime

import pytest

from substrate.multimedia.bedrock_batch_adapter import (
    BedrockBatchRecoveryAdapter,
    BedrockBatchRequest,
)
from substrate.multimedia.bedrock_s3_publication import (
    BedrockS3PublicationError,
    BedrockS3PublicationProfile,
    BedrockS3VersionPublisher,
)
from substrate.research_spend import ResearchSpendLedger
from substrate.research_spend.ledger import _DDL, _MIGRATIONS, APPLICATION_ID
from tests.test_multimedia_bedrock_batch_adapter import (
    BedrockBatchRecoveryAdapter as LegacyBedrockBatchRecoveryAdapter,
)
from tests.test_multimedia_bedrock_batch_adapter import (
    StatefulBedrock,
    _authority,
    _bounded_workload,
)


class S3Error(Exception):
    def __init__(self, status: int) -> None:
        self.response = {"ResponseMetadata": {"HTTPStatusCode": status}}


class ExactS3:
    def __init__(self) -> None:
        self.puts: list[dict[str, object]] = []
        self.heads: list[dict[str, object]] = []
        self.versioning = "Enabled"
        self.lock = "Enabled"
        self.version = "version-1"
        self.current_version = self.version
        self.put_error: int | None = None
        self.object: dict[str, object] | None = None

    def get_bucket_versioning(self, **request: object) -> dict[str, object]:
        assert request["ExpectedBucketOwner"] == "123456789012"
        return {"Status": self.versioning}

    def get_object_lock_configuration(self, **request: object) -> dict[str, object]:
        return {"ObjectLockConfiguration": {"ObjectLockEnabled": self.lock}}

    def put_object(self, **request: object) -> dict[str, object]:
        self.puts.append(request)
        if self.put_error is not None:
            raise S3Error(self.put_error)
        self.object = self._head(request, self.version)
        return {"ChecksumSHA256": request["ChecksumSHA256"], "VersionId": self.version}

    def head_object(self, **request: object) -> dict[str, object]:
        self.heads.append(request)
        if self.object is None:
            raise S3Error(404)
        result = dict(self.object)
        if "VersionId" not in request:
            result["VersionId"] = self.current_version
        return result

    @staticmethod
    def _head(request: dict[str, object], version: str) -> dict[str, object]:
        return {
            "ChecksumSHA256": request["ChecksumSHA256"],
            "ChecksumType": "FULL_OBJECT",
            "ContentLength": len(request["Body"]),  # type: ignore[arg-type]
            "ContentType": "application/json",
            "VersionId": version,
            "ObjectLockMode": "COMPLIANCE",
            "ObjectLockRetainUntilDate": request["ObjectLockRetainUntilDate"],
        }


def _profile(**changes: object) -> BedrockS3PublicationProfile:
    values = {
        "bucket": "antiek-bedrock-input",
        "prefix": "server/bedrock/",
        "expected_owner": "123456789012",
        "region": "us-east-1",
        "retention_margin_hours": 12,
        "profile_version": "test-v1",
        "namespace_policy_digest": "b" * 64,
    }
    values.update(changes)
    return BedrockS3PublicationProfile(**values)  # type: ignore[arg-type]


def _publish(client: ExactS3):
    body, bound = _bounded_workload()
    receipt = BedrockS3VersionPublisher(client, _profile()).publish(
        workload_bound=bound,
        workload_bytes=body,
        verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        bedrock_timeout_hours=24,
    )
    return body, bound, receipt


def test_exact_single_part_publication_and_truthful_receipt() -> None:
    client = ExactS3()
    body, bound, receipt = _publish(client)
    assert len(client.puts) == 1
    request = client.puts[0]
    assert request == {
        "Bucket": "antiek-bedrock-input",
        "Key": f"server/bedrock/{bound.workload_sha256}/manifest.jsonl",
        "Body": body,
        "ExpectedBucketOwner": "123456789012",
        "ContentType": "application/json",
        "ChecksumAlgorithm": "SHA256",
        "ChecksumSHA256": base64.b64encode(hashlib.sha256(body).digest()).decode(),
        "IfNoneMatch": "*",
        "ObjectLockMode": "COMPLIANCE",
        "ObjectLockRetainUntilDate": datetime(2026, 7, 16, 13, tzinfo=UTC),
    }
    assert client.heads == [
        {"Bucket": "antiek-bedrock-input", "Key": receipt.key,
         "ExpectedBucketOwner": "123456789012", "ChecksumMode": "ENABLED",
         "VersionId": "version-1"},
        {"Bucket": "antiek-bedrock-input", "Key": receipt.key,
         "ExpectedBucketOwner": "123456789012", "ChecksumMode": "ENABLED"},
    ]
    assert receipt.version_immutable is True
    assert receipt.current_at_verification is True
    assert receipt.bedrock_version_selected is False
    assert "modelInput" not in receipt.canonical_json
    assert type(receipt).from_json(receipt.canonical_json) == receipt


@pytest.mark.parametrize("status", [None, 412])
def test_ambiguous_or_preexisting_exact_object_is_adopted_without_second_put(status) -> None:
    client = ExactS3()
    body, bound = _bounded_workload()
    publisher = BedrockS3VersionPublisher(client, _profile())
    checksum = base64.b64encode(hashlib.sha256(body).digest()).decode()
    request = {
        "Body": body,
        "ChecksumSHA256": checksum,
        "ObjectLockRetainUntilDate": datetime(2026, 7, 16, 13, tzinfo=UTC),
    }
    client.object = client._head(request, client.version)
    client.put_error = status
    if status is None:
        def lost(**kwargs: object):
            client.puts.append(kwargs)
            raise TimeoutError("lost")
        client.put_object = lost  # type: ignore[method-assign]
    receipt = publisher.publish(
        workload_bound=bound, workload_bytes=body,
        verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC), bedrock_timeout_hours=24,
    )
    assert receipt.version_id == "version-1"
    assert len(client.puts) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "versioning", "lock", "checksum", "missing_checksum_type", "composite",
        "length", "null_version", "governance", "retention", "current",
    ],
)
def test_prerequisite_and_head_ambiguity_fail_closed(mutation: str) -> None:
    client = ExactS3()
    if mutation == "versioning":
        client.versioning = "Suspended"
    elif mutation == "lock":
        client.lock = "Disabled"
    else:
        body, _ = _bounded_workload()
        client.object = client._head({
            "Body": body,
            "ChecksumSHA256": base64.b64encode(hashlib.sha256(body).digest()).decode(),
            "ObjectLockRetainUntilDate": datetime(2026, 7, 16, 13, tzinfo=UTC),
        }, client.version)
        client.put_error = 412
        if mutation == "checksum":
            client.object["ChecksumSHA256"] = "wrong"
        elif mutation == "missing_checksum_type":
            del client.object["ChecksumType"]
        elif mutation == "composite":
            client.object["ChecksumType"] = "COMPOSITE"
        elif mutation == "length":
            client.object["ContentLength"] = len(body) + 1
        elif mutation == "null_version":
            client.object["VersionId"] = ""
        elif mutation == "governance":
            client.object["ObjectLockMode"] = "GOVERNANCE"
        elif mutation == "retention":
            client.object["ObjectLockRetainUntilDate"] = datetime(2026, 7, 16, 12, tzinfo=UTC)
        elif mutation == "current":
            client.current_version = "newer-version"
    with pytest.raises(BedrockS3PublicationError):
        _publish(client)


def test_409_is_not_adopted_even_when_current_object_matches() -> None:
    client = ExactS3()
    body, _ = _bounded_workload()
    client.object = client._head({
        "Body": body,
        "ChecksumSHA256": base64.b64encode(hashlib.sha256(body).digest()).decode(),
        "ObjectLockRetainUntilDate": datetime(2026, 7, 16, 13, tzinfo=UTC),
    }, client.version)
    client.put_error = 409
    with pytest.raises(BedrockS3PublicationError):
        _publish(client)
    assert len(client.puts) == 1


def test_arbitrary_local_exception_is_never_adopted() -> None:
    client = ExactS3()
    client.put_object = lambda **_: (_ for _ in ()).throw(RuntimeError("programming error"))  # type: ignore[method-assign]
    with pytest.raises(BedrockS3PublicationError, match="adoptable evidence"):
        _publish(client)
    assert client.heads == []


def test_public_adapter_rejects_legacy_workload_only_request(tmp_path) -> None:
    body, bound = _bounded_workload()
    request = BedrockBatchRequest.from_workload_bound(
        workload_bound=bound,
        job_name="job-name",
        model_id="provider-model",
        role_arn="arn:aws:iam::123456789012:role/AntiekBedrockBatch",
        input_s3_uri=f"s3://input/{bound.workload_sha256}/manifest.jsonl",
        output_s3_uri="s3://output/prefix/",
        timeout_hours=24,
        account_digest=hashlib.sha256(b"123456789012").hexdigest(),
        region="us-east-1",
    )
    ledger, binding = _authority(tmp_path)
    adapter = BedrockBatchRecoveryAdapter(
        ledger, StatefulBedrock("123456789012", "us-east-1")
    )
    with pytest.raises(RuntimeError, match="immutable S3 publication receipt"):
        adapter.prepare(
            command_key="prepare", binding=binding, operation_id="operation-1",
            model="batch-model", request=request, workload_bytes=body,
        )


def test_receipt_is_persisted_bound_to_identity_and_reverified_before_create(tmp_path) -> None:
    s3 = ExactS3()
    body, bound, receipt = _publish(s3)
    request = BedrockBatchRequest.from_publication(
        workload_bound=bound,
        publication_receipt=receipt,
        job_name="job-name",
        model_id="provider-model",
        role_arn="arn:aws:iam::123456789012:role/AntiekBedrockBatch",
        input_s3_uri=receipt.uri,
        output_s3_uri="s3://output-bucket/prefix/",
        timeout_hours=24,
        account_digest=hashlib.sha256(b"123456789012").hexdigest(),
        region="us-east-1",
    )
    ledger, binding = _authority(tmp_path)
    bedrock = StatefulBedrock("123456789012", "us-east-1")
    publisher = BedrockS3VersionPublisher(s3, _profile())
    adapter = BedrockBatchRecoveryAdapter(ledger, bedrock, publisher)
    submission = adapter.prepare(
        command_key="prepare", binding=binding, operation_id="operation-1",
        model="batch-model", request=request, workload_bytes=body,
    )
    assert submission.intent.publication_receipt_json == receipt.canonical_json
    assert submission.intent.publication_receipt_digest == receipt.digest
    assert ledger.hold(submission.hold_id).intent.rate_snapshot == bound.canonical_json
    with sqlite3.connect(tmp_path / "spend.sqlite3") as connection, pytest.raises(
        sqlite3.IntegrityError, match="immutable"
    ):
        connection.execute(
            "UPDATE research_provider_submissions SET publication_receipt_digest=? "
            "WHERE submission_id=?",
            ("0" * 64, submission.intent.submission_id),
        )
    submission = adapter.advance(
        command_key="mark", submission_id=submission.intent.submission_id, owner_id="owner-1"
    )
    s3.current_version = "substituted"
    with pytest.raises(RuntimeError, match="pre-create verification"):
        adapter.advance(
            command_key="create", submission_id=submission.intent.submission_id,
            owner_id="owner-1",
        )
    assert bedrock.create_attempts == 0


@pytest.mark.parametrize("bucket", ["bucket--x-s3", "192.168.0.1", "Bad_Bucket"])
def test_directory_and_noncanonical_buckets_are_rejected(bucket: str) -> None:
    with pytest.raises(ValueError):
        _profile(bucket=bucket)


def _schema_v5_database(path) -> bytes:
    with sqlite3.connect(path) as connection:
        for statement in (*_DDL, *_MIGRATIONS[2], *_MIGRATIONS[3], *_MIGRATIONS[4]):
            connection.execute(statement)
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute("PRAGMA user_version=5")
        return "\n".join(connection.iterdump()).encode()


@pytest.mark.parametrize("statement_index", range(1, len(_MIGRATIONS[5]) + 1))
def test_schema_v5_to_v6_failure_rolls_back_every_statement(
    tmp_path, statement_index: int,
) -> None:
    db = tmp_path / f"v5-{statement_index}.sqlite3"
    before = _schema_v5_database(db)

    def fail(name: str) -> None:
        if name == f"schema:5:after_migration:{statement_index}":
            raise RuntimeError("injected v6 migration failure")

    with pytest.raises(RuntimeError, match="injected v6"):
        ResearchSpendLedger(db, failure_injector=fail).ensure_schema()
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert "\n".join(connection.iterdump()).encode() == before


def test_schema_v5_to_v6_before_commit_failure_rolls_back(tmp_path) -> None:
    db = tmp_path / "v5-before-commit.sqlite3"
    before = _schema_v5_database(db)

    def fail(name: str) -> None:
        if name == "schema:before_commit":
            raise RuntimeError("injected v6 before commit")

    with pytest.raises(RuntimeError, match="before commit"):
        ResearchSpendLedger(db, failure_injector=fail).ensure_schema()
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert "\n".join(connection.iterdump()).encode() == before


def test_populated_v5_submission_reopens_after_v6_migration(tmp_path) -> None:
    body, bound = _bounded_workload()
    request = BedrockBatchRequest.from_workload_bound(
        workload_bound=bound,
        job_name="job-name", model_id="provider-model",
        role_arn="arn:aws:iam::123456789012:role/AntiekBedrockBatch",
        input_s3_uri=f"s3://input/{bound.workload_sha256}/manifest.jsonl",
        output_s3_uri="s3://output/prefix/", timeout_hours=24,
        account_digest=hashlib.sha256(b"123456789012").hexdigest(),
        region="us-east-1",
    )
    ledger, binding = _authority(tmp_path)
    submission = LegacyBedrockBatchRecoveryAdapter(
        ledger, StatefulBedrock("123456789012", "us-east-1")
    ).prepare(
        command_key="prepare", binding=binding, operation_id="operation-1",
        model="batch-model", request=request, workload_bytes=body,
    )
    db = tmp_path / "spend.sqlite3"
    old_guard = next(
        statement for statement in (*_DDL, *_MIGRATIONS[2], *_MIGRATIONS[3], *_MIGRATIONS[4])
        if "CREATE TRIGGER research_provider_submissions_guard_update" in statement
    )
    old_transition = next(
        statement for statement in _MIGRATIONS[3]
        if "CREATE TRIGGER research_provider_submissions_guard_transition" in statement
    )
    with sqlite3.connect(db) as connection:
        connection.execute("DROP TRIGGER research_provider_submissions_guard_update")
        connection.execute("DROP TRIGGER research_provider_submissions_guard_transition")
        stored_intent = json.loads(
            connection.execute(
                "SELECT intent_json FROM research_provider_submissions WHERE submission_id=?",
                (submission.intent.submission_id,),
            ).fetchone()[0]
        )
        stored_intent.pop("publication_receipt_json")
        stored_intent.pop("publication_receipt_digest")
        legacy_json = json.dumps(
            stored_intent, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        connection.execute(
            "UPDATE research_provider_submissions SET intent_json=?,intent_sha256=? "
            "WHERE submission_id=?",
            (legacy_json, hashlib.sha256(legacy_json.encode()).hexdigest(), submission.intent.submission_id),
        )
        connection.execute(
            "ALTER TABLE research_provider_submissions DROP COLUMN publication_receipt_digest"
        )
        connection.execute(
            "ALTER TABLE research_provider_submissions DROP COLUMN publication_receipt_json"
        )
        connection.execute(old_guard)
        connection.execute(old_transition)
        connection.execute("PRAGMA user_version=5")

    migrated = ResearchSpendLedger(db)
    migrated.ensure_schema()
    reopened = migrated.provider_submission(submission.intent.submission_id, "owner-1")
    assert reopened.intent.submission_id == submission.intent.submission_id
    assert reopened.intent.create_request_json == submission.intent.create_request_json
    assert reopened.intent.publication_receipt_json is None
    assert reopened.intent.publication_receipt_digest is None
