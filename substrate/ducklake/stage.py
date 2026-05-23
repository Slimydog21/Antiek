"""Substrate stage enum — single source of truth for §13.6 transitions."""

from __future__ import annotations

import enum


class SubstrateStage(str, enum.Enum):
    STAGE_0_SINGLE_FILE = "stage_0_single_file"
    STAGE_1_PER_USER_FILE = "stage_1_per_user_file"
    STAGE_2_CATALOG_SHARDED = "stage_2_catalog_sharded"
    STAGE_3_POSTGRES_SHARDED = "stage_3_postgres_sharded"
