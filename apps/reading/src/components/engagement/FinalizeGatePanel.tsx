/**
 * FinalizeGatePanel — explicit operator accept before parent merge.
 *
 * Uses pure authorizeFinalize (#816). Never mutates the parent asset.
 * Free-file: does not own Reading/index or rrv-712 SpawnMergePanel.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../lemon";
import {
  authorizeFinalize,
  formatFinalizeReason,
  type FinalizeAuthorization,
  type FinalizeRequest,
} from "../../api/draftFinalize";

export interface FinalizeGatePanelProps {
  authorizeFn?: (req: FinalizeRequest) => FinalizeAuthorization;
  initialDraftId?: string;
  initialParentId?: string;
  initialTwinIds?: string;
  initialProvisional?: boolean;
}

function parseIds(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function FinalizeGatePanel({
  authorizeFn = authorizeFinalize,
  initialDraftId = "",
  initialParentId = "",
  initialTwinIds = "",
  initialProvisional = true,
}: FinalizeGatePanelProps) {
  const [draftId, setDraftId] = useState(initialDraftId);
  const [parentId, setParentId] = useState(initialParentId);
  const [twinIdsRaw, setTwinIdsRaw] = useState(initialTwinIds);
  const [provisional, setProvisional] = useState(initialProvisional);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FinalizeAuthorization | null>(null);

  function onCheck() {
    setError(null);
    try {
      const body = authorizeFn({
        draft_id: draftId,
        parent_asset_id: parentId,
        provisional,
        operator_accepted: accepted,
        twin_ids: twinIdsRaw.trim() ? parseIds(twinIdsRaw) : undefined,
      });
      setResult(body);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="finalize-gate-panel">
      <LemonCard title="Finalize provisional draft" className="finalize-gate-panel">
        <p className="text-sm opacity-80" data-testid="finalize-gate-blurb">
          Authorize parent mutation only after reviewing a provisional draft.
          This panel does not merge — it only checks the finalize gate.
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Draft id</span>
            <LemonInput
              value={draftId}
              onChange={(e) => setDraftId(e.target.value)}
              data-testid="finalize-gate-draft-id"
              aria-label="Draft id"
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parentId}
              onChange={(e) => setParentId(e.target.value)}
              data-testid="finalize-gate-parent-id"
              aria-label="Parent asset id"
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Twin ids (optional, comma-separated)</span>
            <LemonInput
              value={twinIdsRaw}
              onChange={(e) => setTwinIdsRaw(e.target.value)}
              data-testid="finalize-gate-twin-ids"
              aria-label="Twin ids"
            />
          </label>

          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={provisional}
              onChange={(e) => setProvisional(e.target.checked)}
              data-testid="finalize-gate-provisional"
            />
            <span>Draft is provisional</span>
          </label>

          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
              data-testid="finalize-gate-accept"
            />
            <span>I accept this provisional draft for parent merge</span>
          </label>

          <LemonButton
            variant="primary"
            onClick={onCheck}
            data-testid="finalize-gate-check"
          >
            Check finalize authorization
          </LemonButton>

          {error ? (
            <div className="text-sm text-danger" data-testid="finalize-gate-error">
              {error}
            </div>
          ) : null}

          {result ? (
            <div data-testid="finalize-gate-result" className="flex flex-col gap-1">
              <div
                data-testid="finalize-gate-authorized"
                data-authorized={result.authorized ? "true" : "false"}
              >
                {result.authorized
                  ? "AUTHORIZED — caller may proceed to merge (not performed here)"
                  : `DENIED — ${formatFinalizeReason(result.reason)}`}
              </div>
              <div data-testid="finalize-gate-reason">reason: {result.reason}</div>
              <ul data-testid="finalize-gate-notes">
                {result.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
