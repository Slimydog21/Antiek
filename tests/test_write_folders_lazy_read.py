"""Lazy folder schema: read paths degrade to empty on a graph with no folder tables yet."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

import duckdb

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write  # noqa: E402
from substrate.write.folders import (  # noqa: E402
    add_block_to_folder,
    create_folder,
    ensure_folders_schema,
    folders_for_node,
    is_block_in_folder,
    list_folder_node_ids,
    list_folders,
)


def test_read_paths_degrade_when_folder_schema_absent():
    con = sqlite3.connect(":memory:")
    try:
        assert list_folders(con) == []
        assert list_folder_node_ids(con, "fld_anything") == []
        assert folders_for_node(con, "node_anything") == []
        assert is_block_in_folder(con, folder_id="fld_x", node_id="n_y") is False
    finally:
        con.close()


def test_read_paths_return_data_after_schema_initialized():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "antiek.duckdb")
    with connect_write(path, purpose="test/write_folders_lazy_read") as wcon:
        ensure_folders_schema(wcon)
        fid = create_folder(wcon, name="one", folder_id="fld_test")
        add_block_to_folder(wcon, folder_id=fid, node_id="node_abc")

    con = duckdb.connect(path, read_only=True)
    try:
        folders = list_folders(con)
        assert len(folders) == 1
        assert folders[0].folder_id == "fld_test"
        assert folders[0].member_count == 1
        assert list_folder_node_ids(con, fid) == ["node_abc"]
        assert folders_for_node(con, "node_abc") == [fid]
        assert is_block_in_folder(con, folder_id=fid, node_id="node_abc") is True
        assert is_block_in_folder(con, folder_id=fid, node_id="other") is False
    finally:
        con.close()