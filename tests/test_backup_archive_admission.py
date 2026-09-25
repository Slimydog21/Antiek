"""Behavioral checks for strict closed-archive admission."""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from tools.deploy import backup_archive_admission as admission


def _destination(tmp_path: Path) -> Path:
    destination = tmp_path / "restore"
    destination.mkdir(mode=0o700)
    return destination


def _archive(tmp_path: Path, entries: list[tuple[str, bytes | None, int | None]]) -> Path:
    archive = tmp_path / "archive.tar.gz"
    with tarfile.open(archive, "w:gz", format=tarfile.USTAR_FORMAT) as tar:
        for name, payload, kind in entries:
            info = tarfile.TarInfo(name)
            info.type = (
                kind
                if kind is not None
                else (tarfile.DIRTYPE if payload is None else tarfile.REGTYPE)
            )
            info.size = len(payload) if payload is not None else 0
            tar.addfile(info, io.BytesIO(payload) if payload is not None else None)
    return archive


def _raw_archive(tmp_path: Path, tar_bytes: bytes) -> Path:
    archive = tmp_path / "archive.tar.gz"
    archive.write_bytes(gzip.compress(tar_bytes, mtime=0))
    return archive


def test_extracts_real_gzip_tar_with_deterministic_report(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path,
        [("antiek-backup.123/", None, None), ("antiek-backup.123/duckdb/data.bin", b"abc", None)],
    )
    destination = _destination(tmp_path)
    report = admission.admit_archive(archive, destination)
    assert (destination / "antiek-backup.123/duckdb/data.bin").read_bytes() == b"abc"
    assert [(member.path, member.size) for member in report.members] == [
        ("antiek-backup.123", 0),
        ("antiek-backup.123/duckdb/data.bin", 3),
    ]
    assert report.members[1].sha256 == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert report.compressed_bytes == archive.stat().st_size
    assert len(report.archive_sha256) == 64


@pytest.mark.parametrize(
    "kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE]
)
def test_rejects_special_entries_and_cleans_prior_files(tmp_path: Path, kind: bytes) -> None:
    archive = _archive(tmp_path, [("safe", b"ok", None), ("hostile", None, kind)])
    destination = _destination(tmp_path)
    with pytest.raises(admission.ArchiveAdmissionError):
        admission.admit_archive(archive, destination)
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/./b", "a//b", "a/../b"])
def test_rejects_noncanonical_paths(tmp_path: Path, name: str) -> None:
    archive = _archive(tmp_path, [("safe", b"ok", None), (name, b"bad", None)])
    destination = _destination(tmp_path)
    with pytest.raises(admission.ArchiveAdmissionError):
        admission.admit_archive(archive, destination)
    assert list(destination.iterdir()) == []


def test_rejects_duplicate_and_file_directory_collision(tmp_path: Path) -> None:
    for entries in (
        [("same", b"1", None), ("same", b"2", None)],
        [("same", b"1", None), ("same/child", b"2", None)],
    ):
        archive = _archive(tmp_path, entries)
        destination = _destination(tmp_path)
        with pytest.raises((admission.ArchiveAdmissionError, OSError)):
            admission.admit_archive(archive, destination)
        assert list(destination.iterdir()) == []
        destination.rmdir()


def _case_insensitive(tmp_path: Path) -> bool:
    probe = tmp_path / "CaseProbe"
    probe.mkdir()
    return (tmp_path / "caseprobe").exists()


@pytest.mark.parametrize(
    "first, second",
    [
        (("Foo/", None, None), ("foo/", None, None)),
        (("Foo/", None, None), ("foo/child", None, None)),
        (("Foo/child", None, None), ("foo/", None, None)),
    ],
)
def test_directory_case_alias_never_produces_two_report_paths(
    tmp_path: Path,
    first: tuple[str, bytes | None, int | None],
    second: tuple[str, bytes | None, int | None],
) -> None:
    archive = _archive(tmp_path, [first, second])
    destination = _destination(tmp_path)
    if _case_insensitive(tmp_path):
        with pytest.raises(admission.ArchiveAdmissionError, match="alias"):
            admission.admit_archive(archive, destination)
        assert list(destination.iterdir()) == []
    else:
        report = admission.admit_archive(archive, destination)
        assert [member.path for member in report.members] == [
            first[0].rstrip("/"),
            second[0].rstrip("/"),
        ]


@pytest.mark.parametrize(
    "first, second",
    [
        (("Foo", b"x", None), ("foo/", None, None)),
        (("Foo/", None, None), ("foo", b"x", None)),
    ],
)
def test_file_directory_case_alias_is_rejected_on_aliasing_volume(
    tmp_path: Path,
    first: tuple[str, bytes | None, int | None],
    second: tuple[str, bytes | None, int | None],
) -> None:
    archive = _archive(tmp_path, [first, second])
    destination = _destination(tmp_path)
    if _case_insensitive(tmp_path):
        with pytest.raises((admission.ArchiveAdmissionError, OSError)):
            admission.admit_archive(archive, destination)
        assert list(destination.iterdir()) == []
    else:
        report = admission.admit_archive(archive, destination)
        assert len(report.members) == 2


def test_rejects_expansion_member_count_and_path_limits(tmp_path: Path) -> None:
    archive = _archive(tmp_path, [("one", b"a" * 2048, None), ("two", b"x", None)])
    limits = (
        admission.ArchiveLimits(expanded_bytes=1024),
        admission.ArchiveLimits(member_bytes=1024),
        admission.ArchiveLimits(members=1),
        admission.ArchiveLimits(path_bytes=2),
    )
    for limit in limits:
        destination = _destination(tmp_path)
        with pytest.raises(admission.ArchiveAdmissionError):
            admission.admit_archive(archive, destination, limits=limit)
        assert list(destination.iterdir()) == []
        destination.rmdir()
    nested = _archive(tmp_path, [("one/two", b"x", None)])
    destination = _destination(tmp_path)
    with pytest.raises(admission.ArchiveAdmissionError):
        admission.admit_archive(nested, destination, limits=admission.ArchiveLimits(path_depth=1))
    assert list(destination.iterdir()) == []


def test_rejects_truncated_gzip_and_compressed_tail(tmp_path: Path) -> None:
    archive = _archive(tmp_path, [("safe", b"ok", None)])
    original = archive.read_bytes()
    for altered in (original[:-3], original + b"tail", original + gzip.compress(b"next")):
        archive.write_bytes(altered)
        destination = _destination(tmp_path)
        with pytest.raises(admission.ArchiveAdmissionError):
            admission.admit_archive(archive, destination)
        assert list(destination.iterdir()) == []
        destination.rmdir()


def test_rejects_compressed_byte_cap(tmp_path: Path) -> None:
    archive = _archive(tmp_path, [("safe", os.urandom(1024), None)])
    destination = _destination(tmp_path)
    with pytest.raises(admission.ArchiveAdmissionError, match="compressed archive exceeds limit"):
        admission.admit_archive(
            archive,
            destination,
            limits=admission.ArchiveLimits(compressed_bytes=archive.stat().st_size - 1),
        )
    assert list(destination.iterdir()) == []


def test_nonregular_archive_rejects_without_blocking(tmp_path: Path) -> None:
    archive = tmp_path / "source.fifo"
    os.mkfifo(archive)
    destination = _destination(tmp_path)
    script = (
        "import sys\n"
        "from tools.deploy.backup_archive_admission import ArchiveAdmissionError, admit_archive\n"
        "try:\n"
        "    admit_archive(sys.argv[1], sys.argv[2])\n"
        "except ArchiveAdmissionError as exc:\n"
        "    assert str(exc) == 'archive must be a regular file'\n"
        "else:\n"
        "    raise AssertionError('FIFO unexpectedly admitted')\n"
    )
    subprocess.run(
        [sys.executable, "-c", script, str(archive), str(destination)],
        check=True,
        timeout=3,
    )
    assert list(destination.iterdir()) == []


def test_rejects_pax_override(tmp_path: Path) -> None:
    archive = tmp_path / "archive.tar.gz"
    info = tarfile.TarInfo("safe")
    info.pax_headers = {"path": "../escape"}
    info.size = 1
    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        tar.addfile(info, io.BytesIO(b"x"))
    destination = _destination(tmp_path)
    with pytest.raises(admission.ArchiveAdmissionError):
        admission.admit_archive(archive, destination)
    assert list(destination.iterdir()) == []


def test_rejects_nonzero_tar_tail(tmp_path: Path) -> None:
    archive = _archive(tmp_path, [("safe", b"ok", None)])
    raw = bytearray(gzip.decompress(archive.read_bytes()))
    raw[-1] = 1
    _raw_archive(tmp_path, bytes(raw))
    destination = _destination(tmp_path)
    with pytest.raises(admission.ArchiveAdmissionError, match="after tar end"):
        admission.admit_archive(archive, destination)
    assert list(destination.iterdir()) == []


def test_gnu_tar_producer_layout_and_bounded_long_name(tmp_path: Path) -> None:
    tar_command = shutil.which("gtar") or shutil.which("tar")
    if (
        tar_command is None
        or "GNU tar"
        not in subprocess.run(
            [tar_command, "--version"], capture_output=True, text=True, check=False
        ).stdout
    ):
        pytest.skip("GNU tar is unavailable")
    staging = tmp_path / "antiek-backup.123"
    staging.mkdir()
    long_name = "x" * 150
    (staging / long_name).write_bytes(b"content")
    archive = tmp_path / "archive.tar.gz"
    subprocess.run(
        [tar_command, "-czf", str(archive), "-C", str(tmp_path), staging.name], check=True
    )
    destination = _destination(tmp_path)
    report = admission.admit_archive(archive, destination)
    assert (destination / staging.name / long_name).read_bytes() == b"content"
    assert report.members[-1].path == f"{staging.name}/{long_name}"


def test_real_duckdb_export_survives_producer_tar_admission_and_import(tmp_path: Path) -> None:
    duckdb = pytest.importorskip("duckdb")
    tar_command = shutil.which("gtar") or shutil.which("tar")
    if (
        tar_command is None
        or "GNU tar"
        not in subprocess.run(
            [tar_command, "--version"], capture_output=True, text=True, check=False
        ).stdout
    ):
        pytest.skip("GNU tar is unavailable")

    staging = tmp_path / "antiek-backup.123"
    staging.mkdir()
    export = staging / "duckdb"
    export_sql_path = export.as_posix().replace("'", "''")
    source = duckdb.connect(":memory:")
    try:
        source.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, payload VARCHAR)")
        source.execute("INSERT INTO items VALUES (1, 'alpha'), (2, 'beta')")
        source.execute(f"EXPORT DATABASE '{export_sql_path}' (FORMAT PARQUET)")
    finally:
        source.close()

    archive = tmp_path / "archive.tar.gz"
    subprocess.run(
        [tar_command, "-czf", str(archive), "-C", str(tmp_path), staging.name], check=True
    )
    destination = _destination(tmp_path)
    report = admission.admit_archive(archive, destination)

    restored_export = destination / staging.name / "duckdb"
    restored_sql_path = restored_export.as_posix().replace("'", "''")
    restored = duckdb.connect(":memory:")
    try:
        restored.execute(f"IMPORT DATABASE '{restored_sql_path}'")
        assert restored.execute("SELECT * FROM items ORDER BY id").fetchall() == [
            (1, "alpha"),
            (2, "beta"),
        ]
    finally:
        restored.close()
    assert report.archive_sha256 == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert any(member.path.endswith("/duckdb/schema.sql") for member in report.members)


def test_destination_symlink_race_cannot_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _archive(tmp_path, [("safe/child", b"data", None)])
    destination = _destination(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    original = admission._member

    def plant_symlink(
        header: bytes, limits: admission.ArchiveLimits, long_name: bytes | None = None
    ) -> tuple[str, int, bool, bool]:
        result = original(header, limits, long_name)
        os.symlink(outside, destination / "safe")
        return result

    monkeypatch.setattr(admission, "_member", plant_symlink)
    with pytest.raises(OSError):
        admission.admit_archive(archive, destination)
    assert list(outside.iterdir()) == []
