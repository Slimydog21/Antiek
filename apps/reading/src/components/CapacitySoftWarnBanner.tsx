import { useEffect, useState } from "react";

import {
  formatCapacityWarnToast,
  takeCapacityWarning,
  type CapacityWarning,
} from "../lib/capacityWarn";

/** Inline soft-warn for InvestigationCenter (session stash from spin / POST). */
export default function CapacitySoftWarnBanner({
  investigationId,
  initial,
}: {
  investigationId: string;
  initial?: CapacityWarning | null;
}) {
  const [warn, setWarn] = useState<CapacityWarning | null>(initial ?? null);

  useEffect(() => {
    if (initial) {
      setWarn(initial);
      return;
    }
    setWarn(takeCapacityWarning(investigationId));
  }, [investigationId, initial]);

  if (!warn) return null;

  const used = warn.used_compute_units;
  const monthly = warn.monthly_compute_units;
  const ratio =
    used != null && monthly != null && monthly > 0 ? used / monthly : null;
  const pct = ratio == null ? 0 : Math.min(100, Math.round(ratio * 100));

  return (
    <div
      role="status"
      data-testid="capacity-soft-warn-banner"
      className="mx-3 mt-3 rounded-md border border-sun/60 bg-sun/10 px-3 py-2 text-sm text-ink dark:text-bright"
    >
      <div className="font-medium">Agent compute capacity</div>
      <p className="mt-0.5 text-sm leading-snug opacity-90">
        {formatCapacityWarnToast(warn)}
      </p>
      {ratio != null ? (
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded bg-sun/20">
          <div
            className="h-full bg-sun"
            style={{ width: pct + "%" }}
            data-testid="capacity-soft-warn-bar"
          />
        </div>
      ) : null}
      <button
        type="button"
        className="mt-2 text-xs font-mono uppercase tracking-wider underline opacity-70 hover:opacity-100"
        onClick={() => setWarn(null)}
      >
        Dismiss
      </button>
    </div>
  );
}
