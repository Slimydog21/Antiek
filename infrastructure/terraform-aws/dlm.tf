# ──────────────────────────────────────────────────────────────────────────────
# Daily EBS snapshots of the prod data volume (/home/antiek/.antiek), 14 kept.
#
# This is the fast-restore layer, not the backup of record. The snapshots are
# crash-consistent: a restore is equivalent to the host losing power at
# snapshot time, which DuckDB's WAL recovers from, but nothing verifies them.
# The verified, off-provider backup stays the nightly R2 logical export
# (backup.sh.j2 IMPORT-checks every bundle before upload), unchanged.
#
# Cost [I]: snapshots are incremental, so the bill is the changed blocks.
# Each deploy writes a fresh ~1.19 GB rollback copy of the DuckDB file (17
# deploys in the 24 h to 2026-10-07), so daily churn can approach the used
# size of the volume (~12 GB). Upper bound ~14 x 12 GB x USD 0.0475/GB-month
# (eu-north-1) ≈ USD 8/month; a quiet week is closer to USD 1.
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_dlm_lifecycle_policy" "prod_state" {
  description        = "antiek prod state volume daily keep ${var.snapshot_retain_count}"
  execution_role_arn = aws_iam_role.dlm.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]

    target_tags = {
      Snapshot = "antiek-prod-state-daily"
    }

    schedule {
      name      = "daily"
      copy_tags = true

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = [var.snapshot_time_utc]
      }

      retain_rule {
        count = var.snapshot_retain_count
      }

      tags_to_add = {
        SnapshotCreator = "dlm"
      }
    }
  }

  tags = { Role = "prod" }
}
