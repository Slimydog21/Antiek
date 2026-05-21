import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../../lib/api";
import HeaderBar from "../shared/HeaderBar";

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
      <HeaderBar />
      <main className="flex-1 overflow-y-auto bg-white">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-10">
          <header className="space-y-3">
            <h1 className="text-3xl font-serif text-stone-900">
              Trust Center
            </h1>
            <p className="text-base text-stone-700 leading-relaxed">
              Antiek's standing commitments — privacy architecture,
              differential-privacy parameters, deletion SLA, and the
              gates that govern when the system learns from your
              behavior. The values below are pulled live from the
              substrate; if a bullet is wrong, the bullet is wrong.
            </p>
          </header>

          {error && (
            <p className="text-sm text-red-700 border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {data && (
            <>
              <Section title="Differential-privacy ε budgets (§16.2)">
                <p className="text-sm text-stone-600 leading-relaxed">
                  Antiek hard-caps ε at {EPSILON_CAP} for every
                  category that ever leaves your private partition.
                  Any future category that would exceed this is
                  rejected at registration time. Categories you don't
                  see below contribute zero ε (they are not collected).
                </p>
                <ul className="divide-y divide-stone-200">
                  {Object.entries(
                    data.differential_privacy_epsilon_budgets,
                  ).map(([category, epsilon]) => (
                    <li
                      key={category}
                      className="py-2 flex items-center justify-between"
                    >
                      <span className="text-sm font-mono text-stone-700">
                        {category}
                      </span>
                      <span className="text-sm font-mono text-stone-900">
                        ε = {epsilon}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="text-[11px] font-mono text-stone-500">
                  Hard cap: ε ≤ {EPSILON_CAP}. Beyond this is binding
                  REJECT per master-spec §16.2.
                </p>
              </Section>

              <Section title="Deletion SLA (§13.3)">
                <p className="text-sm text-stone-700 leading-relaxed">
                  Every deletion request — single-record or
                  delete-all — is honored within {data.deletion_sla_days}{" "}
                  days. The deletion path runs against the substrate,
                  not just the UI; chunks, embeddings, derived skills,
                  and per-user attribution shares all unwind.
                </p>
              </Section>

              <Section title="Substrate controls (§13.7)">
                <ul className="text-sm text-stone-700 space-y-1 list-disc pl-5">
                  {data.substrate_controls.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </Section>

              <Section title="Compliance posture">
                <ul className="text-sm text-stone-700 space-y-1 list-disc pl-5">
                  {data.compliance_frameworks.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </Section>

              <Section title="Loop 3 (RL training) unlock criteria">
                <p className="text-sm text-stone-600 leading-relaxed">
                  Antiek does not train on your data until five
                  criteria are independently satisfied AND the
                  operator explicitly sets <code>ANTIEK_LOOP3_UNLOCKED=1</code>.
                  Criteria-met alone is not enough; the operator
                  authorizes the flip.
                </p>
                <ul className="divide-y divide-stone-200">
                  {Object.entries(data.loop_3_unlock_status).map(
                    ([criterion, met]) => (
                      <li
                        key={criterion}
                        className="py-2 flex items-center justify-between"
                      >
                        <span className="text-sm font-mono text-stone-700">
                          {criterion}
                        </span>
                        <span
                          className={`text-xs font-mono px-2 py-0.5 rounded ${
                            met
                              ? "bg-emerald-100 text-emerald-700"
                              : "bg-stone-100 text-stone-500"
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
    <section className="space-y-3 border-t border-stone-200 pt-6 first:border-0 first:pt-0">
      <h2 className="text-xl font-serif text-stone-900">{title}</h2>
      {children}
    </section>
  );
}
