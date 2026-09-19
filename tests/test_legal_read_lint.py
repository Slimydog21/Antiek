from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tools.lint.legal_read_check import debt_classes, errors

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tools/lint/baselines/legal_document_reads.json"


def test_repository_legal_read_ratchet_is_green():
    assert errors(ROOT, BASELINE) == []


def test_ratchet_rejects_literal_join_and_assembled_sql(tmp_path):
    module = tmp_path / "reader.py"
    module.write_text(
        "def leak(con):\n"
        "    table = 'documents'\n"
        "    con.execute('SELECT d.raw_text FROM ' + table + ' d')\n"
        "    con.execute('SELECT c.text FROM chunks c JOIN documents d ON 1=1')\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"version": 1, "sites": {}}), encoding="utf-8")
    findings = errors(tmp_path, baseline)
    assert len(findings) == 2


def test_unclassified_non_tool_reader_is_product_runtime():
    sites = Counter(
        {
            "new_package/reader.py:<module>.leak:read:documents:digest": 1,
            "tools/migrate_history.py:<module>.inspect:read:documents:digest": 1,
        }
    )

    assert debt_classes(sites) == Counter(
        {"product_runtime": 1, "operator_tooling": 1}
    )
