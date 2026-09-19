from __future__ import annotations

import json
from pathlib import Path

from tools.lint.legal_admission_check import errors

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tools/lint/baselines/legal_admission_writers.json"


def test_repository_external_writer_ratchet_is_green():
    assert errors(ROOT, BASELINE) == []


def test_ratchet_rejects_new_raw_external_writer(tmp_path):
    acquisition = tmp_path / "acquisition"
    acquisition.mkdir()
    (acquisition / "new_connector.py").write_text(
        "def ingest(con):\n    return insert_document(con, document_id='x')\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"version": 1, "sites": {}}), encoding="utf-8")
    findings = errors(tmp_path, baseline)
    assert any("new raw external writer" in finding for finding in findings)


def test_ratchet_rejects_import_alias_and_getattr_bypasses(tmp_path):
    acquisition = tmp_path / "acquisition"
    acquisition.mkdir()
    (acquisition / "alias_connector.py").write_text(
        "from substrate.graph.ops import insert_document as write_doc\n"
        "import substrate.graph.ops as graph_ops\n"
        "module_writer = graph_ops.insert_edge\n"
        "def ingest(con, ops):\n"
        "    write_doc(con, document_id='x')\n"
        "    getattr(ops, 'insert_chunk')(con, document_id='x', text='y')\n"
        "    return module_writer(con, source_node_id='a', target_node_id='b')\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"version": 1, "sites": {}}), encoding="utf-8")
    findings = errors(tmp_path, baseline)
    assert sum("new raw external writer" in finding for finding in findings) == 3
