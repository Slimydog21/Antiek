import { useCallback, useEffect, useState } from "react";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import { apiFetch } from "../../lib/api";

/**
 * Trust Center (master-spec §13.7 + PostHog Wedge 7).
 *
 * Public-facing transparency surface. Reads the backend
 * /trust-center endpoint and renders the operator's published
 * privacy/control posture. Per master-spec §13.7:
 *
 *   "A Trust Center is not a marketing artifact. It is the
 *    operator's standing commitment to the architecture; if a
 *    bullet here is wrong, the bullet is wrong, not the page."
 *
 * Per §16.2 binding rejection: differential-privacy ε budgets are
 * capped at 10. The endpoint surfaces them; the UI renders them and
 * the cap.
 */

interface TrustCenterData {
  differential_privacy_epsilon_budgets: Record<string, number>;
  deletion_sla_days: number;
  substrate_controls: string[];
  compliance_frameworks: string[];
  loop_3_unlock_status: Record<string, boolean>;
}

const EPSILON_CAP = 10;

export default function TrustCenter() {
  const [data, setData] = useState<TrustCenterData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const resp = await apiFetch("/trust-center");
      if (!resp.ok) {
        throw new Error(`GET /trust-center failed: HTTP ${resp.status}`);
      }
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
          <SessionBrandChrome
            testIdPrefix="trust-center"
            title="Trust Center"
            titleClassName="text-3xl font-serif text-ink dark:text-bright"
          >
            <p className="text-base text-ink dark:text-bright leading-relaxed">
              Antiek&rsquo;s standing commitments — privacy architecture,
              differential-privacy parameters, deletion SLA, and the
              gates that govern when the system learns from your
              behavior. The values below are pulled live from the
              substrate; if a bullet is wrong, the bullet is wrong.
            </p>
          </SessionBrandChrome>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {data && (
            <>
              <Section title="Differential-privacy ε budgets (§16.2)">
                <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
                  Antiek hard-caps ε at {EPSILON_CAP} for every
                  category that ever leaves your private partition.
                  Any future category that would exceed this is
                  rejected at registration time. Categories you don't
                  see below contribute zero ε (they are not collected).
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
                        {category}
                      </span>
                      <span className="text-sm font-mono text-ink dark:text-bright">
                        ε = {epsilon}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                  Hard cap: ε ≤ {EPSILON_CAP}. Beyond this is binding
                  REJECT per master-spec §16.2.
                </p>
              </Section>

              <Section title="Deletion SLA (§13.3)">
                <p className="text-sm text-ink dark:text-bright leading-relaxed">
                  Every deletion request — single-record or
                  delete-all — is honored within {data.deletion_sla_days}{" "}
                  days. The deletion path runs against the substrate,
                  not just the UI; chunks, embeddings, derived skills,
                  and per-user attribution shares all unwind.
                </p>
              </Section>

              <Section title="Substrate controls (§13.7)">
                <ul className="text-sm text-ink dark:text-bright space-y-1 list-disc pl-5">
                  {data.substrate_controls.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </Section>

              <Section title="Compliance posture">
                <ul className="text-sm text-ink dark:text-bright space-y-1 list-disc pl-5">
                  {data.compliance_frameworks.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </Section>

              <Section title="Loop 3 (RL training) unlock criteria">
                <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
                  Antiek does not train on your data until five
                  criteria are independently satisfied AND the
                  operator explicitly sets <code>ANTIEK_LOOP3_UNLOCKED=1</code>.
                  Criteria-met alone is not enough; the operator
                  authorizes the flip.
                </p>
                <ul className="divide-y divide-rule dark:divide-charcoal-1">
                  {Object.entries(data.loop_3_unlock_status).map(
                    ([criterion, met]) => (
                      <li
                        key={criterion}
                        className="py-2 flex items-center justify-between"
                      >
                        <span className="text-sm font-mono text-ink dark:text-bright">
                          {criterion}
                        </span>
                        <span
                          className={`text-xs font-mono px-2 py-0.5 rounded ${
                            met
                              ? "bg-emerald-100 text-emerald-700"
                              : "bg-ice-3 dark:bg-charcoal-1 text-shadow-1 dark:text-moonlight"
                          }`}
                        >
                          {met ? "MET" : "NOT MET"}
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
