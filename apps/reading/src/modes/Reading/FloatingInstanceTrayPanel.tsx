/**
 * FloatingInstanceTrayPanel — multi floating DR selection tray.
 *
 * Free-file. pack_dispatched, merge_executed, live_dispatched always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeFloatingInstanceTray,
  formatFloatingInstanceTraySummary,
  type FloatingInstanceTrayCompose,
  type TrayAction,
} from "../../api/floatingInstanceTrayCompose";

export interface FloatingInstanceTrayPanelProps {
  composeFn?: typeof composeFloatingInstanceTray;
}

export default function FloatingInstanceTrayPanel({
  composeFn = composeFloatingInstanceTray,
}: FloatingInstanceTrayPanelProps) {
  const [sel1, setSel1] = useState(true);
  const [sel2, setSel2] = useState(true);
  const [sel3, setSel3] = useState(false);
  const [action, setAction] = useState<TrayAction>("collective_pack");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FloatingInstanceTrayCompose | null>(
    null,
  );

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const selected: string[] = [];
      if (sel1) selected.push("f1");
      if (sel2) selected.push("f2");
      if (sel3) selected.push("f3");
      setResult(
        composeFn({
          parent_asset_id: "asset-1",
          members: [
            {
              instance_id: "f1",
              parent_asset_id: "asset-1",
              status: "completed",
              live_dispatched: false,
              merge_executed: false,
            },
            {
              instance_id: "f2",
              parent_asset_id: "asset-1",
              status: "open",
              live_dispatched: false,
              merge_executed: false,
            },
            {
              instance_id: "f3",
              parent_asset_id: "asset-1",
              status: "completed",
              live_dispatched: false,
              merge_executed: false,
            },
          ],
          selected_instance_ids: selected,
          action,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="floating-instance-tray-panel">
      <LemonCard
        title="Floating research instance tray"
        className="floating-instance-tray-panel"
      >
        <p className="text-sm opacity-80" data-testid="fit-blurb">
          Multi-select floating deep researches for collective, cohesive,
          fullscreen, or merge intents. Pure — pack_dispatched and
          merge_executed stay false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={sel1}
              onChange={(e) => setSel1(e.target.checked)}
              data-testid="fit-f1"
            />
            <span>f1 completed</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={sel2}
              onChange={(e) => setSel2(e.target.checked)}
              data-testid="fit-f2"
            />
            <span>f2 open</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={sel3}
              onChange={(e) => setSel3(e.target.checked)}
              data-testid="fit-f3"
            />
            <span>f3 completed</span>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Action</span>
            <select
              value={action}
              onChange={(e) => setAction(e.target.value as TrayAction)}
              data-testid="fit-action"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="collective_pack">collective_pack</option>
              <option value="cohesive_prompt">cohesive_prompt</option>
              <option value="fullscreen_one">fullscreen_one</option>
              <option value="draft_merge_one">draft_merge_one</option>
              <option value="full_merge_one">full_merge_one</option>
              <option value="none">none</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="fit-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="fit-compose"
          >
            Compose tray intent
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="fit-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="fit-result"
            >
              <div data-testid="fit-ready">
                tray_ready={String(result.tray_ready)}
              </div>
              <div data-testid="fit-pack">
                pack_dispatched={String(result.pack_dispatched)}
              </div>
              <div data-testid="fit-merged">
                merge_executed={String(result.merge_executed)}
              </div>
              <div data-testid="fit-live">
                live_dispatched={String(result.live_dispatched)}
              </div>
              <div data-testid="fit-summary">
                {formatFloatingInstanceTraySummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
