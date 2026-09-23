import type { UserModelRow } from "../api/settingsModels";

/**
 * The variants one registered key can drive: `model_ids` when the server
 * sent them (SPR-03 Task 2: one key, many variants), else the single primary.
 *
 * Lives apart from `api/settingsModels` on purpose: every surface test mocks
 * that module wholesale (`vi.mock(..., () => ({ fetchUserModels: vi.fn() }))`),
 * and a helper exported from it would be undefined under every one of them.
 */
export function userModelVariants(row: UserModelRow): string[] {
  return row.model_ids && row.model_ids.length > 0 ? row.model_ids : [row.model_id];
}
