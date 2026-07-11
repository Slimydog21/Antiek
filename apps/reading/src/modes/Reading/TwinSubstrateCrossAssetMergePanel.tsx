/**
 * TwinSubstrateCrossAssetMergePanel — merge twin substrate across assets.
 *
 * Free-file. merge_executed, twin_written, store_mutated always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeTwinSubstrateCrossAssetMerge,
  formatTwinSubstrateCrossAssetMergeSummary,
  type TwinSubstrateCrossAssetMergeCompose,
} from "../../api/twinSubstrateCrossAssetMergeCompose";

export interface TwinSubstrateCrossAssetMergePanelProps {
  composeFn?: typeof composeTwinSubstrateCrossAssetMerge;
}

export default function TwinSubstrateCrossAssetMergePanel({
  composeFn = composeTwinSubstrateCrossAssetMerge,
}: TwinSubstrateCrossAssetMergePanelProps) {
  const [packId, setPackId] = useState("pack-1");
  const [p1, setP1] = useState("asset-a");
  const [p2, setP2] = useState("asset-b");
  const [i1, setI1] = useState("claim holds under noise");
  const [q1, setQ1] = useState("what is the sample size?");
  const [i2, setI2] = useState("routing cost is non-linear");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<TwinSubstrateCrossAssetMergeCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          pack_id: packId.trim(),
          operator_ack: ack,
          slices: [
            {
              parent_asset_id: p1.trim(),
              insights: i1.trim() ? [i1.trim()] : [],
              questions: q1.trim() ? [q1.trim()] : [],
            },
            {
              parent_asset_id: p2.trim(),
              insights: i2.trim() ? [i2.trim()] : [],
              questions: [],
            },
          ],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="twin-substrate-cross-asset-merge-panel">
      <LemonCard
        title="Twin substrate · cross-asset merge"
        className="twin-substrate-cross-asset-merge-panel"
      >
        <p className="text-sm opacity-80" data-testid="tscam-blurb">
          Merge insights/questions twin substrate across parent assets.
          Pure — merge_executed, twin_written, store_mutated stay false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Pack id</span>
            <LemonInput
              value={packId}
              onChange={(e) => setPackId(e.target.value)}
              data-testid="tscam-pack"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent A</span>
            <LemonInput
              value={p1}
              onChange={(e) => setP1(e.target.value)}
              data-testid="tscam-p1"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Insight A</span>
            <LemonInput
              value={i1}
              onChange={(e) => setI1(e.target.value)}
              data-testid="tscam-i1"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Question A</span>
            <LemonInput
              value={q1}
              onChange={(e) => setQ1(e.target.value)}
              data-testid="tscam-q1"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent B</span>
            <LemonInput
              value={p2}
              onChange={(e) => setP2(e.target.value)}
              data-testid="tscam-p2"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Insight B</span>
            <LemonInput
              value={i2}
              onChange={(e) => setI2(e.target.value)}
              data-testid="tscam-i2"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="tscam-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="tscam-compose"
          >
            Compose twin merge pack
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="tscam-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="tscam-result"
            >
              <div data-testid="tscam-ready">
                merge_ready={String(result.merge_ready)}
              </div>
              <div data-testid="tscam-merged">
                merge_executed={String(result.merge_executed)}
              </div>
              <div data-testid="tscam-written">
                twin_written={String(result.twin_written)}
              </div>
              <div data-testid="tscam-store">
                store_mutated={String(result.store_mutated)}
              </div>
              <div data-testid="tscam-summary">
                {formatTwinSubstrateCrossAssetMergeSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
