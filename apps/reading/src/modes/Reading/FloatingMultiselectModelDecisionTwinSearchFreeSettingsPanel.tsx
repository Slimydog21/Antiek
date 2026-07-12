/**
 * FloatingMultiselectModelDecisionTwinSearchFreeSettingsPanel — free-file.
 * Floating multi-select collective over model decision budget residual.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeFloatingMultiselectModelDecisionTwinSearchFreeSettings,
  formatFloatingMultiselectModelDecisionTwinSearchFreeSettingsSummary,
  type FloatingMultiselectModelDecisionTwinSearchFreeSettingsCompose,
} from "../../api/floatingMultiselectModelDecisionTwinSearchFreeSettingsCompose";

export default function FloatingMultiselectModelDecisionTwinSearchFreeSettingsPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FloatingMultiselectModelDecisionTwinSearchFreeSettingsCompose | null>(
      null,
    );

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeFloatingMultiselectModelDecisionTwinSearchFreeSettings;
      void formatFloatingMultiselectModelDecisionTwinSearchFreeSettingsSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Floating multi-select · model decision · twin-search free settings
      </h2>
      <p className="text-sm text-muted">
        Pure residual: multi-select floating sub-agents as a cohesive unit over
        model decision budget + twin intelligent search HTML-native free
        marketplace. Alignment + would_exceed gates · ND REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={ack}
          onChange={(e) => setAck(e.target.checked)}
        />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>
        Compose floating multi-select residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatFloatingMultiselectModelDecisionTwinSearchFreeSettingsSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
