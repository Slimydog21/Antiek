/**
 * NotDiamondShadowAdvisoryPanel — shadow advisory only (§16 REJECT router).
 *
 * Free-file. live_router_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeNotDiamondShadowAdvisory,
  formatNotDiamondShadowAdvisorySummary,
  type NotDiamondShadowAdvisoryCompose,
} from "../../api/notDiamondShadowAdvisoryCompose";

export interface NotDiamondShadowAdvisoryPanelProps {
  composeFn?: typeof composeNotDiamondShadowAdvisory;
}

export default function NotDiamondShadowAdvisoryPanel({
  composeFn = composeNotDiamondShadowAdvisory,
}: NotDiamondShadowAdvisoryPanelProps) {
  const [selected, setSelected] = useState("gpt-5");
  const [ndRec, setNdRec] = useState("claude-opus");
  const [kill, setKill] = useState(true);
  const [confidence, setConfidence] = useState("0.72");
  const [task, setTask] = useState("deep_research");
  const [inventory, setInventory] = useState("gpt-5,claude-opus,mimo");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<NotDiamondShadowAdvisoryCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const inv = inventory
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const confRaw = confidence.trim();
      setResult(
        composeFn({
          selected_model_id: selected.trim(),
          nd_recommended_model_id: ndRec.trim() || null,
          kill_switch_on: kill,
          confidence: confRaw === "" ? null : Number(confRaw),
          task: task.trim() || null,
          inventory_model_ids: inv.length ? inv : null,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="notdiamond-shadow-advisory-panel">
      <LemonCard
        title="NotDiamond shadow advisory (§16 REJECT production router)"
        className="notdiamond-shadow-advisory-panel"
      >
        <p className="text-sm opacity-80" data-testid="ndsa-blurb">
          NotDiamond is shadow/advisory only. production_router_verdict is
          always REJECT. live_router_authorized stays false — operator model
          selection remains authority.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Selected model (authority)</span>
            <LemonInput
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              data-testid="ndsa-selected"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>ND recommended (shadow)</span>
            <LemonInput
              value={ndRec}
              onChange={(e) => setNdRec(e.target.value)}
              data-testid="ndsa-rec"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={kill}
              onChange={(e) => setKill(e.target.checked)}
              data-testid="ndsa-kill"
            />
            <span>kill_switch_on (default safe = on)</span>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Confidence 0..1</span>
            <LemonInput
              value={confidence}
              onChange={(e) => setConfidence(e.target.value)}
              data-testid="ndsa-confidence"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Task</span>
            <LemonInput
              value={task}
              onChange={(e) => setTask(e.target.value)}
              data-testid="ndsa-task"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Inventory (comma ids)</span>
            <LemonInput
              value={inventory}
              onChange={(e) => setInventory(e.target.value)}
              data-testid="ndsa-inventory"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="ndsa-compose"
          >
            Compose ND shadow advisory
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="ndsa-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="ndsa-result"
            >
              <div data-testid="ndsa-verdict">
                production_router_verdict={result.production_router_verdict}
              </div>
              <div data-testid="ndsa-live">
                live_router_authorized=
                {String(result.live_router_authorized)}
              </div>
              <div data-testid="ndsa-visible">
                shadow_visible={String(result.shadow_visible)}
              </div>
              <div data-testid="ndsa-differs">
                differs=
                {result.differs_from_selected === null
                  ? "null"
                  : String(result.differs_from_selected)}
              </div>
              <div data-testid="ndsa-suggested">
                suggested={result.suggested_model_id ?? "null"}
              </div>
              <div data-testid="ndsa-summary">
                {formatNotDiamondShadowAdvisorySummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
