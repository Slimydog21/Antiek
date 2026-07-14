import { useEffect, useState } from "react";

import {
  reconcileSessionSpend,
  type HardCeilingSnapshot,
} from "../../api/research";
import LemonButton from "../../components/lemon/LemonButton";

function usd(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export default function HardCeilingEvidence({
  sessionId,
  snapshot,
}: {
  sessionId: string;
  snapshot: HardCeilingSnapshot;
}) {
  const [current, setCurrent] = useState(snapshot);
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => setCurrent(snapshot), [snapshot]);

  const checkStatus = async () => {
    setChecking(true);
    setMessage(null);
    try {
      const response = await reconcileSessionSpend(sessionId);
      setCurrent(response.hard_ceiling);
      setMessage(response.message);
    } catch {
      setMessage("Provider status could not be refreshed. The existing holds remain unchanged.");
    } finally {
      setChecking(false);
    }
  };

  const unresolved = current.unknown_outcome_count > 0;
  return (
    <section
      aria-label="Hard spend ceiling evidence"
      className={`border-y px-3 py-3 ${
        current.ceiling_breached
          ? "border-emperor bg-emperor/5"
          : unresolved
            ? "border-sun bg-sun/5"
            : "border-rule bg-ice-1 dark:border-charcoal-1 dark:bg-charcoal-2"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-mono uppercase text-shadow-1 dark:text-moonlight">
            Hard authorized-spend ceiling · {current.run_state.replaceAll("_", " ")}
          </p>
          <p className="mt-1 text-xs text-ink-mute dark:text-moonlight">
            Server balances in USD cents. Observed provider billing is tracked separately from what Antiek authorized.
          </p>
        </div>
        {unresolved && (
          <LemonButton variant="secondary" size="sm" disabled={checking} onClick={() => void checkStatus()}>
            {checking ? "Checking…" : "Check provider status"}
          </LemonButton>
        )}
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-5 gap-y-2 sm:grid-cols-5">
        {[
          ["Approved", current.ceiling_cents],
          ["Authorized", current.authorized_spent_cents],
          ["Observed", current.observed_provider_spend_cents],
          ["Held", current.held_cents],
          ["Available", current.available_cents],
        ].map(([label, cents]) => (
          <div key={label}>
            <dt className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">{label}</dt>
            <dd className="font-mono text-sm text-ink dark:text-bright">{usd(cents as number)}</dd>
          </div>
        ))}
      </dl>
      {current.ceiling_breached && (
        <p className="mt-2 text-xs font-medium text-emperor" role="alert">
          Observed provider billing exceeded its reserved maximum. This run is frozen and the breach remains visible.
        </p>
      )}
      {unresolved && (
        <p className="mt-2 text-xs text-ink dark:text-bright">
          {current.unknown_outcome_count} provider {current.unknown_outcome_count === 1 ? "outcome is" : "outcomes are"} unresolved. Reserved funds will not be released without provider evidence.
        </p>
      )}
      {message && <p className="mt-2 text-xs text-ink-mute dark:text-moonlight" aria-live="polite">{message}</p>}
    </section>
  );
}
