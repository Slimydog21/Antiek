import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../../lib/api";

interface TrustCenterData {
  differential_privacy_epsilon_budgets: Record<string, number>;
  deletion_sla_days: number;
  substrate_controls: string[];
  compliance_frameworks: string[];
  loop_3_unlock_status: Record<string, boolean>;
}

const EPSILON_CAP = 10;

const BUDGET_LABELS: Record<string, string> = {
  skill_invocation_frequency: "Skill Use Frequency",
  source_tier_preference_signals: "Source Preference Signals",
  query_content_telemetry: "Search Content Telemetry",
};

const SYSTEM_CONTROL_LABELS: Record<string, string> = {
  "encryption at rest (per-graph keys via KMS)":
    "Encryption at rest with managed keys",
  "access logging (append-only)": "Append-only access logs",
  "change management (CI gates on schema)":
    "Database changes pass automated checks",
  "vulnerability scanning (Dependabot/Snyk)":
    "Dependency and vulnerability scanning",
  "backup testing (quarterly restore drill)": "Quarterly backup restore tests",
  "retrieval-time policy_tag gating (§9.0)":
    "Access checks run before retrieved content is shown",
};

const COMPLIANCE_LABELS: Record<string, string> = {
  "GDPR Article 13/14 transparency": "GDPR transparency notice",
  "CCPA notice + opt-out": "CCPA notice and opt-out",
  "engineering-grade differential privacy (ε ≤ 10 hard cap)":
    "Differential privacy with epsilon capped at 10",
  "SOC 2 Type II — deferred (not required for consumer Phase 1)":
    "SOC 2 Type II is not required for the consumer preview",
};

const TRAINING_CRITERION_LABELS: Record<string, string> = {
  trajectory_volume: "Enough approved activity",
  sft_readiness: "Training data quality review",
  validated_reward: "Reward checks validated",
  open_weight_justification: "Open model release justification",
  eval_headroom: "Evaluation safety margin",
};

function formatTrustLabel(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatBudgetLabel(value: string): string {
  return BUDGET_LABELS[value] ?? formatTrustLabel(value);
}

function formatSystemControl(value: string): string {
  return SYSTEM_CONTROL_LABELS[value] ?? value;
}

function formatComplianceLabel(value: string): string {
  return COMPLIANCE_LABELS[value] ?? value;
}

function formatTrainingCriterion(value: string): string {
  return TRAINING_CRITERION_LABELS[value] ?? formatTrustLabel(value);
}

export default function TrustCenter() {
  const [data, setData] = useState<TrustCenterData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const resp = await apiFetch("/trust-center");
      if (!resp.ok) {
        throw new Error(`Could not load the Trust Center (HTTP ${resp.status}).`);
      }
      setError(null);
      setData(await resp.json());
    } catch (e: unknown) {
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
              pulled live from the trust endpoint so the page reflects
              the app's current policy.
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
                        Epsilon: {epsilon}
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
