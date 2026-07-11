/**
 * CollectivePackPanel — multi-twin cohesive deep-research pack UI.
 *
 * Consumes POST /twins/collective (PR #794). Allows cross-parent twins.
 * Builds a prompt pack only — does not dispatch models or mutate stores.
 *
 * Free-file: does not own Reading/index or rrv-712 spawn surfaces.
 */

import { useMemo, useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../lemon";
import {
  formatPackPreview,
  formatParentIds,
  parseCollectivePackResult,
  postCollectivePack,
  type CollectivePackResult,
} from "../../api/twinCollective";

export interface CollectivePackPanelProps {
  /**
   * Injectable pack builder. Return value is re-validated with
   * parseCollectivePackResult so empty pack_text cannot surface as success
   * even when the injector bypasses postCollectivePack.
   */
  packFn?: (
    req: Parameters<typeof postCollectivePack>[0],
  ) => Promise<CollectivePackResult | unknown>;
  initialTwinIds?: string;
  initialInstruction?: string;
}

function parseTwinIds(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function CollectivePackPanel({
  packFn = postCollectivePack,
  initialTwinIds = "",
  initialInstruction = "",
}: CollectivePackPanelProps) {
  const [twinIdsRaw, setTwinIdsRaw] = useState(initialTwinIds);
  const [instruction, setInstruction] = useState(initialInstruction);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CollectivePackResult | null>(null);

  const twinIds = useMemo(() => parseTwinIds(twinIdsRaw), [twinIdsRaw]);

  async function onBuild() {
    setBusy(true);
    setError(null);
    try {
      const raw = await packFn({
        twin_ids: twinIds,
        instruction,
      });
      // Fail closed at panel boundary (covers injectable stubs).
      const body = parseCollectivePackResult(raw);
      setResult(body);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="collective-pack-panel">
      <LemonCard title="Collective deep-research pack" className="collective-pack-panel">
        <p className="text-sm opacity-80" data-testid="collective-pack-blurb">
          Select multiple twin notes and build one prompt pack so you can engage
          them as a cohesive research unit. Cross-parent twins are allowed.
          This panel does not dispatch models.
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Twin ids (comma or space separated)</span>
            <LemonInput
              value={twinIdsRaw}
              onChange={(e) => setTwinIdsRaw(e.target.value)}
              placeholder="twin-a, twin-b"
              data-testid="collective-pack-twin-ids"
              aria-label="Twin ids"
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Instruction (optional operator goal for the pack)</span>
            <textarea
              className="min-h-[64px] w-full rounded border border-border bg-bg-light px-2 py-1 text-sm"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="Compare findings and surface open questions…"
              data-testid="collective-pack-instruction"
              aria-label="Collective instruction"
            />
          </label>

          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onBuild()}
            data-testid="collective-pack-build"
          >
            {busy ? "Building…" : "Build collective pack"}
          </LemonButton>

          {error ? (
            <div className="text-sm text-danger" data-testid="collective-pack-error">
              {error}
            </div>
          ) : null}

          {result ? (
            <div data-testid="collective-pack-result" className="flex flex-col gap-2">
              <div data-testid="collective-pack-twins">
                Twins: {result.twin_ids.join(", ")}
              </div>
              <div data-testid="collective-pack-parents">
                {formatParentIds(result.parent_asset_ids)}
              </div>
              <div data-testid="collective-pack-counts">
                Insights: {result.insight_count}; questions:{" "}
                {result.question_count}
              </div>
              {result.instruction ? (
                <div data-testid="collective-pack-instruction-echo">
                  Instruction: {result.instruction}
                </div>
              ) : null}
              <pre
                className="max-h-56 overflow-auto rounded border border-border bg-bg-light p-2 text-xs whitespace-pre-wrap"
                data-testid="collective-pack-text"
              >
                {result.pack_text}
              </pre>
              <div className="text-xs opacity-70" data-testid="collective-pack-preview">
                Preview: {formatPackPreview(result.pack_text)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
