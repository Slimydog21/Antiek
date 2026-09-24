# Evidence provenance

These receipts record the completed 2026-09-24 V10 migration and gate verification. This branch only preserves those receipts. It does not change production or authorize additional operations.

The original evidence was committed in the local home coordination repository at `/Users/slimydog`, commit `ec61b1fbf6033ea09680a0e2b503b8fde57819d7`, under `Antiek/.infinite/gated-actions-20260924/`. That commit belongs to the coordination repository, not the Antiek product repository.

All 24 original files were copied byte-for-byte from that commit. The original `SHA256SUMS.json` verifies 23 artifacts and is preserved unchanged. Its own SHA256 is `3bbb90e20debd77c64fd7261d01a0ce257d9603fe91e5f2c013f5039c48bd73e`. `PROVENANCE.md` is the only added artifact. Historical paths in the original receipts remain unchanged.

The operational source build was `874345539e9e2f75d9f85f7f2da54a2bf08e9877`. The receipts record 178 focused passing tests, 78 original tables compared, and an idempotent production migration. The user independently confirmed the operational results and all 23 artifact checksums.

The Python scripts are historical operational receipts. Do not rerun them as part of reviewing or verifying this evidence. Verify file hashes against the manifest instead.
