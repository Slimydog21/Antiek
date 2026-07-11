/**
 * NotDiamondShadowPanel — advisory shadow comparison UI (§16 non-authority).
 *
 * Uses postNotDiamondShadow (#836). Kill switch defaults off. Never production
 * dispatch. Free-file: does not own Settings/index.tsx.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  postNotDiamondShadow,
  type ShadowHttpResult,
} from "../../api/notdiamondShadowHttp";

export interface NotDiamondShadowPanelProps {
  shadowFn?: typeof postNotDiamondShadow;
  initialLocalModel?: string;
  initialNdModel?: string;
}

export default function NotDiamondShadowPanel({
  shadowFn = postNotDiamondShadow,
  initialLocalModel = "",
  initialNdModel = "",
}: NotDiamondShadowPanelProps) {
  const [localModel, setLocalModel] = useState(initialLocalModel);
  const [ndModel, setNdModel] = useState(initialNdModel);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ShadowHttpResult | null>(null);

  async function onRun() {
    setBusy(true);
    setError(null);
    try {
      const body = await shadowFn({
        local_model_id: localModel,
        nd_recommended_model_id: ndModel.trim() ? ndModel.trim() : null,
        enabled,
      });
      setResult(body);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="nd-shadow-panel">
      <LemonCard title="NotDiamond shadow (advisory)" className="nd-shadow-panel">
        <p className="text-sm opacity-80" data-testid="nd-shadow-blurb">
          Compare your local model selection against an injected NotDiamond
          recommendation. Kill switch defaults off. Authority is always shadow
          — never production dispatch.
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Local model id</span>
            <LemonInput
              value={localModel}
              onChange={(e) => setLocalModel(e.target.value)}
              data-testid="nd-shadow-local"
              aria-label="Local model id"
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Injected ND recommendation (required if shadow on)</span>
            <LemonInput
              value={ndModel}
              onChange={(e) => setNdModel(e.target.value)}
              placeholder="optional when kill switch off"
              data-testid="nd-shadow-nd"
              aria-label="Injected ND recommendation"
            />
          </label>

          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => {
                setEnabled(e.target.checked);
                setResult(null);
                setError(null);
              }}
              data-testid="nd-shadow-enabled"
            />
            <span>Enable shadow comparison (uses injected reco only — no live ND)</span>
          </label>

          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onRun()}
            data-testid="nd-shadow-run"
          >
            {busy ? "Recording…" : "Record shadow comparison"}
          </LemonButton>

          {error ? (
            <div className="text-sm text-danger" data-testid="nd-shadow-error">
              {error}
            </div>
          ) : null}

          {result ? (
            <div data-testid="nd-shadow-result" className="flex flex-col gap-1">
              <div data-testid="nd-shadow-authority">
                Authority: {result.authority}
              </div>
              <div data-testid="nd-shadow-enabled-echo">
                Kill switch: {result.enabled ? "on" : "off"}
              </div>
              <div data-testid="nd-shadow-local-echo">
                Local: {result.local_model_id}
              </div>
              <div data-testid="nd-shadow-nd-echo">
                ND:{" "}
                {result.nd_recommended_model_id === null
                  ? "(none)"
                  : result.nd_recommended_model_id}
              </div>
              <div data-testid="nd-shadow-agreement">
                Agreement:{" "}
                {result.agreement === null
                  ? "unknown"
                  : result.agreement
                    ? "yes"
                    : "no"}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
