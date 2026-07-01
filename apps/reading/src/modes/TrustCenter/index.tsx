import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "../../lib/api";
import {
  EPSILON_CAP,
  formatBudgetLabel,
  formatComplianceLabel,
  formatSystemControl,
  formatTrainingCriterion,
} from "../../lib/trustCopy";

interface TrustCenterData {
  differential_privacy_epsilon_budgets: Record<string, number>;
  deletion_sla_days: number;
  substrate_controls: string[];
  compliance_frameworks: string[];
  loop_3_unlock_status: Record<string, boolean>;
}

function normalizedEpsilon(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return 0;
  }
  return Math.min(value, EPSILON_CAP);
}

function formatEpsilon(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export default function TrustCenter() {
  const [data, setData] = useState<TrustCenterData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reloadSeq = useRef(0);

  const reload = useCallback(async () => {
    const requestId = reloadSeq.current + 1;
    reloadSeq.current = requestId;
    try {
      const resp = await apiFetch("/trust-center");
      if (requestId !== reloadSeq.current) return;
      if (!resp.ok) {
        setData(null);
        throw new Error(`Could not load the Trust Center (HTTP ${resp.status}).`);
      }
      setError(null);
      setData(await resp.json());
    } catch (e: unknown) {
      if (requestId !== reloadSeq.current) return;
      setData(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-10">
          <header className="space-y-3">
            <h1 className="text-3xl font-serif text-ink dark:text-bright">
              Trust Center
            </h1>
            <p className="text-base text-ink dark:text-bright leading-relaxed">
              Antiek's public commitments for privacy, deletion,
              compliance, and training controls. These values are
              served from Antiek's current trust publication so the
              page reflects the app's current commitments.
            </p>
          </header>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {data && (
            <>
              <Section title="Privacy budget">
                <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
                  Antiek caps epsilon at {EPSILON_CAP} for every data
                  category that can leave your private workspace. Any
                  future category above the cap is blocked before it can
                  be turned on. Categories not listed here are not
                  collected for this purpose.
                </p>
                <ul className="divide-y divide-rule dark:divide-charcoal-1">
                  {Object.entries(
                    data.differential_privacy_epsilon_budgets,
                  ).map(([category, epsilon]) => (
                    <li
                      key={category}
                      className="py-2 flex items-center justify-between"
                    >
                      <span className="text-sm font-mono text-ink dark:text-bright">
                        {formatBudgetLabel(category)}
                      </span>
                      <span className="text-sm font-mono text-ink dark:text-bright">
                        Epsilon: {formatEpsilon(normalizedEpsilon(epsilon))}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                  Hard cap: epsilon is always {EPSILON_CAP} or lower.
                </p>
              </Section>

              <Section title="Deletion window">
                <p className="text-sm text-ink dark:text-bright leading-relaxed">
                  Every deletion request, whether for one record or the
                  full account, is completed within {data.deletion_sla_days}{" "}
                  days. Deletion applies to saved content, search data,
                  personalization data, and attribution records, not just
                  the visible page.
                </p>
              </Section>

              <Section title="System controls">
                <ul className="text-sm text-ink dark:text-bright space-y-1 list-disc pl-5">
                  {data.substrate_controls.map((c) => (
                    <li key={c}>{formatSystemControl(c)}</li>
                  ))}
                </ul>
              </Section>

              <Section title="Compliance posture">
                <ul className="text-sm text-ink dark:text-bright space-y-1 list-disc pl-5">
                  {data.compliance_frameworks.map((c) => (
                    <li key={c}>{formatComplianceLabel(c)}</li>
                  ))}
                </ul>
              </Section>

              <Section title="Training controls">
                <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
                  Antiek does not train on your data until every
                  requirement below is satisfied and the account owner
                  gives explicit approval. Meeting the requirements is
                  not enough on its own.
                </p>
                <ul className="divide-y divide-rule dark:divide-charcoal-1">
                  {Object.entries(data.loop_3_unlock_status).map(
                    ([criterion, met]) => (
                      <li
                        key={criterion}
                        className="py-2 flex items-center justify-between"
                      >
                        <span className="text-sm font-mono text-ink dark:text-bright">
                          {formatTrainingCriterion(criterion)}
                        </span>
                        <span
                          className={`text-xs font-mono px-2 py-0.5 rounded ${
                            met
                              ? "bg-emerald-100 text-emerald-700"
                              : "bg-ice-3 dark:bg-charcoal-1 text-shadow-1 dark:text-moonlight"
                          }`}
                        >
                          {met ? "Met" : "Not met"}
                        </span>
                      </li>
                    ),
                  )}
                </ul>
              </Section>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function Section({
  title,
  children,
}: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 border-t border-rule dark:border-charcoal-1 pt-6 first:border-0 first:pt-0">
      <h2 className="text-xl font-serif text-ink dark:text-bright">{title}</h2>
      {children}
    </section>
  );
}
