from __future__ import annotations

from tools.lint.investigation_tenancy_check import inventory, new_sites, write_baseline


def test_repository_has_no_unreviewed_investigation_tenancy_sites(tmp_path):
    from tools.lint import investigation_tenancy_check as guard

    assert new_sites(guard._REPO, guard._BASELINE) == {}


def test_mutation_rejects_raw_trajectory_filename_and_unscoped_graph_sql(tmp_path):
    production = tmp_path / "substrate"
    production.mkdir()
    baseline = tmp_path / "baseline.json"
    write_baseline(tmp_path, baseline)
    (production / "new_consumer.py").write_text(
        """
def leak(investigation_id, db):
    events = trajectory(investigation_id)
    path = f"{investigation_id}.jsonl"
    return db.execute("SELECT * FROM edges WHERE investigation_id = ?", [investigation_id])
""",
        encoding="utf-8",
    )
    additions = new_sites(tmp_path, baseline)
    assert sum(additions.values()) == 3
    assert {site.split(":", 1)[0] for site in additions} == {
        "raw_stream",
        "raw_stream_filename",
        "unscoped_graph_sql",
    }


def test_composite_stream_and_account_scoped_sql_are_allowed(tmp_path):
    production = tmp_path / "substrate"
    production.mkdir()
    (production / "safe.py").write_text(
        """
def safe(authority, db):
    events = trajectory(authority.stream_key)
    return db.execute(
        "SELECT * FROM edges WHERE investigation_id = ? AND account_digest = ?",
        [authority.investigation_id, authority.account_digest],
    )
""",
        encoding="utf-8",
    )
    assert inventory(tmp_path) == {}


def test_only_named_migration_lock_may_construct_legacy_filenames(tmp_path):
    production = tmp_path / "substrate"
    production.mkdir()
    (production / "investigation_stream_migration.py").write_text(
        """
def _migration_locks(authority):
    return f"{authority.investigation_id}.jsonl"

def accidental_production_path(authority):
    return f"{authority.investigation_id}.jsonl"
""",
        encoding="utf-8",
    )

    sites = inventory(tmp_path)

    assert sum(sites.values()) == 1
    assert "accidental_production_path" in next(iter(sites))


def test_alias_getattr_and_assembled_sql_cannot_bypass_guard(tmp_path):
    production = tmp_path / "substrate"
    production.mkdir()
    (production / "bypass.py").write_text(
        """
def bypass(events, raw_investigation_id, db):
    reader = events.trajectory
    reader(raw_investigation_id)
    getattr(events, "trajectory")(raw_investigation_id)
    sql = "SELECT * FROM edges WHERE " + "investigation_id = ?"
    return db.execute(sql, [raw_investigation_id])
""",
        encoding="utf-8",
    )

    sites = inventory(tmp_path)

    assert sum(sites.values()) == 3
    assert {site.split(":", 1)[0] for site in sites} == {
        "raw_stream",
        "unscoped_graph_sql",
    }


def test_partial_format_and_joined_sql_cannot_bypass_guard(tmp_path):
    production = tmp_path / "substrate"
    production.mkdir()
    (production / "bypass.py").write_text(
        '''
import functools

def bypass(events, raw_investigation_id, db):
    functools.partial(events.trajectory, raw_investigation_id)()
    path = "{}.jsonl".format(raw_investigation_id)
    sql = " ".join(["SELECT * FROM edges WHERE", "investigation_id = ?"])
    return db.execute(sql, [raw_investigation_id]), path
''',
        encoding="utf-8",
    )

    sites = inventory(tmp_path)

    assert sum(sites.values()) == 3
    assert {site.split(":", 1)[0] for site in sites} == {
        "raw_stream",
        "raw_stream_filename",
        "unscoped_graph_sql",
    }
