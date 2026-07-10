from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.html_projection_routes import (
    MAX_HTML_BYTES,
    make_html_projection_router,
)
from substrate.contracts.html_projection import HtmlProjectionContract, derive_projection_id


def _contract(
    document: str, locator: str, payload: bytes, *, status: str = "ready"
) -> dict[str, object]:
    identity = {
        "source_asset_id": f"asset-{document}",
        "source_document_id": document,
        "source_sha256": hashlib.sha256(document.encode()).hexdigest(),
        "converter_id": "test",
        "converter_version": "1",
        "sanitizer_policy": "strict",
        "sanitizer_version": "1",
    }
    data: dict[str, object] = {
        **identity,
        "projection_id": derive_projection_id(**identity),
        "status": status,
        "anchor_mappings": [],
    }
    if status == "ready":
        data.update(
            hosted_html_locator=locator, hosted_html_sha256=hashlib.sha256(payload).hexdigest()
        )
    elif status == "failed":
        data["reason_code"] = "conversion_failed"
    return HtmlProjectionContract.model_validate(data).model_dump()


def _client(
    tmp_path: Path, rows: list[dict[str, object]], *, root: Path | None = None
) -> tuple[TestClient, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "graph.duckdb"
    con = duckdb.connect(str(db))
    con.execute(
        "CREATE TABLE html_projections (projection_id TEXT, identity_json JSON, projection_json JSON)"
    )
    for row in rows:
        con.execute(
            "INSERT INTO html_projections VALUES (?, ?, ?)",
            [row["projection_id"], "{}", json.dumps(row)],
        )
    con.close()
    app = FastAPI()
    app.include_router(make_html_projection_router(db_path=db, object_root=root))
    return TestClient(app), db


def test_happy_path_by_projection_and_document(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    root.mkdir()
    payload = b"<article>Hello</article>"
    (root / "ok.html").write_bytes(payload)
    row = _contract("doc-1", "ok.html", payload)
    client, _ = _client(tmp_path, [row], root=root)
    for url in (f"/html-projections/{row['projection_id']}", "/html-projections/by-document/doc-1"):
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["html"] == payload.decode()
        assert response.json()["identity"]["source_document_id"] == "doc-1"


@pytest.mark.parametrize("status", ["queued", "failed"])
def test_missing_and_non_ready_are_404(tmp_path: Path, status: str) -> None:
    row = _contract("doc", "ignored.html", b"", status=status)
    client, _ = _client(tmp_path, [row], root=tmp_path)
    assert client.get(f"/html-projections/{row['projection_id']}").status_code == 404
    assert client.get("/html-projections/not-there").status_code == 404


def test_tampered_traversal_and_oversized_are_unavailable(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    root.mkdir()
    cases = [
        ("tampered.html", b"expected", b"changed"),
        ("large.html", b"x" * (MAX_HTML_BYTES + 1), b"x" * (MAX_HTML_BYTES + 1)),
    ]
    for index, (name, expected, actual) in enumerate(cases):
        (root / name).write_bytes(actual)
        row = _contract(f"doc-{index}", name, expected)
        client, _ = _client(tmp_path / f"case-{index}", [row], root=root)
        assert client.get(f"/html-projections/{row['projection_id']}").status_code == 404
    # Contract validation itself rejects traversal before it can reach the API.
    with pytest.raises(ValueError):
        _contract("escape", "../escape.html", b"x")


def test_symlink_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    root.mkdir()
    target = tmp_path / "target.html"
    target.write_text("<p>x</p>")
    os.symlink(target, root / "link.html")
    row = _contract("doc", "link.html", target.read_bytes())
    client, _ = _client(tmp_path, [row], root=root)
    assert client.get(f"/html-projections/{row['projection_id']}").status_code == 404


def test_containment_race_value_error_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "objects"
    root.mkdir()
    payload = b"<p>x</p>"
    (root / "ok.html").write_bytes(payload)
    row = _contract("doc", "ok.html", payload)
    client, _ = _client(tmp_path, [row], root=root)
    original = Path.resolve
    calls = 0

    def racing_resolve(path: Path, *, strict: bool = False) -> Path:
        nonlocal calls
        calls += 1
        if calls == 1:
            return original(path, strict=strict)
        raise ValueError("simulated containment race")

    monkeypatch.setattr(Path, "resolve", racing_resolve)
    assert client.get(f"/html-projections/{row['projection_id']}").status_code == 404


@pytest.mark.parametrize("payload", [b"<script>alert(1)</script>", b"\xff\xfe"])
def test_active_or_non_utf8_html_is_rejected(tmp_path: Path, payload: bytes) -> None:
    root = tmp_path / "objects"
    root.mkdir()
    (root / "bad.html").write_bytes(payload)
    row = _contract("doc", "bad.html", payload)
    client, _ = _client(tmp_path, [row], root=root)
    assert client.get(f"/html-projections/{row['projection_id']}").status_code == 404


def test_control_character_locator_and_anchor_amplification_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"<p>x</p>"
    row = _contract("doc", "bad\nname.html", payload)
    client, _ = _client(tmp_path, [row], root=tmp_path)
    assert client.get(f"/html-projections/{row['projection_id']}").status_code == 404

    from substrate.contracts.html_projection import AnchorMapping, PdfPageLocator, derive_anchor_id

    contract = HtmlProjectionContract.model_validate(_contract("many", "many.html", payload))
    monkeypatch.setattr("interfaces.research.api.html_projection_routes.MAX_ANCHOR_MAPPINGS", 1)
    mappings = tuple(
        AnchorMapping(
            source_locator=(
                locator := PdfPageLocator(page=index + 1, x0="0", y0="0", x1="1", y1="1")
            ),
            state="resolved",
            html_anchor_id=derive_anchor_id(contract.projection_id, locator),
        )
        for index in range(2)
    )
    amplified = contract.model_copy(update={"anchor_mappings": mappings}).model_dump()
    (tmp_path / "many.html").write_bytes(payload)
    many_client, _ = _client(tmp_path / "many", [amplified], root=tmp_path)
    assert many_client.get(f"/html-projections/{contract.projection_id}").status_code == 404


def test_duplicate_document_is_409(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    root.mkdir()
    rows = []
    for name in ("a.html", "b.html"):
        (root / name).write_text("<p>x</p>")
        row = _contract("same", name, b"<p>x</p>")
        row["converter_version"] = name  # create a distinct valid identity/id
        identity = {
            key: row[key]
            for key in HtmlProjectionContract.model_validate(
                _contract("same", name, b"<p>x</p>")
            ).identity()
        }
        row["projection_id"] = derive_projection_id(**identity)
        rows.append(HtmlProjectionContract.model_validate(row).model_dump())
    client, _ = _client(tmp_path, rows, root=root)
    assert client.get("/html-projections/by-document/same").status_code == 409


def test_no_table_root_missing_and_read_only(tmp_path: Path) -> None:
    db = tmp_path / "empty.duckdb"
    duckdb.connect(str(db)).close()
    app = FastAPI()
    app.include_router(make_html_projection_router(db_path=db))
    client = TestClient(app)
    before = db.stat().st_mtime_ns
    assert client.get("/html-projections/unknown").status_code == 404
    assert db.stat().st_mtime_ns == before

    payload = b"<p>x</p>"
    row = _contract("doc", "x.html", payload)
    configured, _ = _client(tmp_path / "configured", [row], root=None)
    assert configured.get(f"/html-projections/{row['projection_id']}").status_code == 503


def test_create_app_wires_projection_router_exactly_once() -> None:
    source = Path("interfaces/research/api/app.py").read_text()
    assert source.count("make_html_projection_router(") == 1
    assert "app.include_router(make_html_projection_router(" in source
    assert "html_projection_db_path=html_projection_db_path" not in source
    assert "db_path=html_projection_db_path" in source
    assert "object_root=html_projection_object_root" in source
