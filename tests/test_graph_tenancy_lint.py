from __future__ import annotations

import json

from tools.lint.graph_tenancy_check import (
    _BASELINE,
    _INVENTORY,
    _REPO,
    inventory_errors,
    new_sql_sites,
    sql_inventory,
    write_baseline,
)


def _inventory(path, tables):
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "tables": {
                    table: {
                        "domain": "test domain",
                        "authority": "composite_required",
                        "rationale": "test rationale",
                    }
                    for table in tables
                },
            }
        ),
        encoding="utf-8",
    )


def test_repository_inventory_and_sql_ratchet_are_green():
    assert inventory_errors(_REPO / "substrate/graph/schema.py", _INVENTORY) == []
    assert new_sql_sites(_REPO, _BASELINE) == {}


def test_new_investigation_table_requires_semantic_classification(tmp_path):
    schema = tmp_path / "schema.py"
    schema.write_text(
        'ANTIEK_GRAPH_SCHEMA_TEST_SQL = """CREATE TABLE IF NOT EXISTS private_rows ('
        'row_id TEXT, investigation_id TEXT);"""\n',
        encoding="utf-8",
    )
    inventory = tmp_path / "inventory.json"
    _inventory(inventory, [])

    assert inventory_errors(schema, inventory) == [
        "unclassified investigation tables: private_rows"
    ]


def test_stale_semantic_classification_is_rejected(tmp_path):
    schema = tmp_path / "schema.py"
    schema.write_text('ANTIEK_GRAPH_SCHEMA_TEST_SQL = """"""\n', encoding="utf-8")
    inventory = tmp_path / "inventory.json"
    _inventory(inventory, ["removed_rows"])

    assert inventory_errors(schema, inventory) == [
        "stale graph tenancy classifications: removed_rows"
    ]


def test_new_display_only_sql_in_roles_and_middleware_fails_ratchet(tmp_path):
    (tmp_path / "roles").mkdir()
    baseline = tmp_path / "baseline.json"
    write_baseline(tmp_path, baseline)
    (tmp_path / "roles" / "leak.py").write_text(
        '''
def leak(con, investigation_id):
    return con.execute(
        "SELECT * FROM syntheses WHERE investigation_id = ?",
        [investigation_id],
    ).fetchall()
''',
        encoding="utf-8",
    )

    additions = new_sql_sites(tmp_path, baseline)

    assert sum(additions.values()) == 1
    assert next(iter(additions)).startswith("display_only_graph_sql:roles/leak.py:")


def test_exact_composite_sql_is_not_display_only_debt(tmp_path):
    (tmp_path / "substrate").mkdir()
    (tmp_path / "substrate" / "safe.py").write_text(
        '''
def safe(con, authority):
    return con.execute(
        "SELECT * FROM syntheses WHERE investigation_id = ? "
        "AND account_digest = ? AND investigation_digest = ?",
        [authority.investigation_id, authority.account_digest, authority.investigation_digest],
    ).fetchall()
''',
        encoding="utf-8",
    )

    sites = sql_inventory(tmp_path)

    assert sum(sites.values()) == 1
    assert next(iter(sites)).startswith("composite_graph_sql:")


def test_account_digest_alone_is_not_sufficient_scope(tmp_path):
    (tmp_path / "interfaces").mkdir()
    (tmp_path / "interfaces" / "partial.py").write_text(
        '''
def partial(con, authority):
    return con.execute(
        "DELETE FROM edges WHERE investigation_id = ? AND account_digest = ?",
        [authority.investigation_id, authority.account_digest],
    )
''',
        encoding="utf-8",
    )

    sites = sql_inventory(tmp_path)

    assert sum(sites.values()) == 1
    assert next(iter(sites)).startswith("display_only_graph_sql:")
