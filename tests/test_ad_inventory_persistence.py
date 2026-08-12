"""Ad-inventory persistence tests (Sprint 23-24 phase 1)."""

from __future__ import annotations

import os
import tempfile

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.ad_inventory.inventory_persistence import (
    deactivate_inventory,
    load_active_inventory,
    load_serving_for_matcher,
    upsert_inventory,
)
from substrate.graph.schema import init_database


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="antiek-inv-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="inv_test")
    init_database(con)
    yield con
    con.close()


def test_insert_then_load(db):
    iid = upsert_inventory(
        db,
        advertiser_id="adv-x",
        advertiser_display_name="Acme",
        creative_url="https://x/c.png",
        landing_url="https://x/lp",
        cpm_usd_cents=500,
        target_topics=("defense",),
    )
    items = load_active_inventory(db)
    assert len(items) == 1
    assert items[0].inventory_id == iid
    assert items[0].advertiser_id == "adv-x"
    assert items[0].cpm_usd_cents == 500


def test_upsert_updates_existing_row(db):
    upsert_inventory(
        db,
        advertiser_id="adv-x", advertiser_display_name="Acme",
        creative_url="https://x/c.png", landing_url="https://x/lp",
        cpm_usd_cents=500, inventory_id="inv-fixed",
    )
    upsert_inventory(
        db,
        advertiser_id="adv-x", advertiser_display_name="Acme Updated",
        creative_url="https://x/c.png", landing_url="https://x/lp",
        cpm_usd_cents=800, inventory_id="inv-fixed",
    )
    items = load_active_inventory(db)
    assert len(items) == 1
    assert items[0].advertiser_display_name == "Acme Updated"
    assert items[0].cpm_usd_cents == 800


def test_deactivate_excludes_from_load(db):
    iid = upsert_inventory(
        db,
        advertiser_id="adv-x", advertiser_display_name="Acme",
        creative_url="https://x/c.png", landing_url="https://x/lp",
        cpm_usd_cents=500,
    )
    deactivate_inventory(db, inventory_id=iid)
    items = load_active_inventory(db)
    assert items == []


def test_load_serving_splits_targeted_vs_flat(db):
    # ``serving`` means both the inventory row and the advertiser's latest
    # registry state are ACTIVE.
    db.execute(
        """
        INSERT INTO advertisers (
            attempt_id, advertiser_id, display_name, contact_email, status,
            submitted_at, last_status_change_at
        ) VALUES
            ('attempt-a', 'adv-a', 'A', 'a@example.test', 'active',
             CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('attempt-b', 'adv-b', 'B', 'b@example.test', 'active',
             CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )
    upsert_inventory(
        db,
        advertiser_id="adv-a", advertiser_display_name="A",
        creative_url="https://a/c", landing_url="https://a/lp",
        cpm_usd_cents=300,
        target_sectors=("defense",),
    )
    upsert_inventory(
        db,
        advertiser_id="adv-b", advertiser_display_name="B",
        creative_url="https://b/c", landing_url="https://b/lp",
        cpm_usd_cents=200,
        target_topics=("biotech",),
    )
    targeted, flat = load_serving_for_matcher(db)
    assert len(targeted) == 1
    assert len(flat) == 1
    assert targeted[0].item.advertiser_display_name == "A"
    assert flat[0].advertiser_display_name == "B"


def test_negative_cpm_refused(db):
    with pytest.raises(ValueError):
        upsert_inventory(
            db, advertiser_id="x", advertiser_display_name="X",
            creative_url="https://x", landing_url="https://x",
            cpm_usd_cents=-1,
        )


def test_check_constraint_at_sql(db):
    db.execute(
        """
        INSERT INTO ad_inventory_items (
            inventory_id, advertiser_id, advertiser_display_name,
            cpm_usd_cents, creative_url, landing_url
        ) VALUES ('inv-ok', 'adv-x', 'X', 100, 'https://x', 'https://y')
        """
    )
    with pytest.raises(duckdb.ConstraintException):
        db.execute(
            """
            INSERT INTO ad_inventory_items (
                inventory_id, advertiser_id, advertiser_display_name,
                cpm_usd_cents, creative_url, landing_url
            ) VALUES ('inv-bad', 'adv-x', 'X', -5, 'https://x', 'https://y')
            """
        )
