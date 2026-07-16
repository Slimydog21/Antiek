import { useCallback, useEffect, useState } from "react";

import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import { apiFetch } from "../../lib/api";

/**
 * Privacy Dashboard (master-spec §13.3 — first-class product surface).
 *
 * "Real-time view of every telemetry collected from the user's
 * private graph, with toggles per category and a 'delete everything'
 * button that actually deletes everything within 30 days."
 *
 * The dashboard reads ε budgets from the live ``/trust-center``
 * endpoint so any future telemetry surface that registers with the
 * EpsilonRegistry appears here automatically. Per master-spec §13.3:
 * 'we are architecturally incapable of leaking your data' rather
 * than 'we promise not to.'
 */

interface TrustCenterData {
  differential_privacy_epsilon_budgets: Record<string, number>;
  deletion_sla_days: number;
  substrate_controls: string[];
  compliance_frameworks: string[];
  loop_3_unlock_status: Record<string, boolean>;
}

const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  skill_invocation_frequency:
    "Which substrate skills fire and at what rate. Low sensitivity; " +
    "the DP randomizer ensures no single invocation is identifying.",
  source_tier_preference_signals:
    "Which source tiers (Tier 1 = peer-reviewed primary, " +
    "Tier 5 = anonymous) you accept versus reject. The shuffled " +
    "aggregate informs the dispatch router's tier hints.",
  query_content_telemetry:
    "The text of your research queries and the content of your " +
    "private notes. Per master-spec §13.3: NOT COLLECTED at any ε " +
    "that preserves utility — Antiek chooses no collection.",
};

const SENSITIVITY_BY_EPSILON = (eps: number): "low" | "medium" | "high" | "forbidden" => {
  if (eps === 0) return "forbidden";
  if (eps <= 1.0) return "high";
  if (eps <= 2.0) return "medium";
  return "low";
};

interface DeletionRequest {
  request_id: string;
  status: string;
  requested_at: string;
  cancellation_window_days: number;
  deletion_sla_days: number;
}

export default function PrivacyDashboard() {
  const [data, setData] = useState<TrustCenterData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingDeletion, setPendingDeletion] = useState<DeletionRequest | null>(null);

  const reload = useCallback(async () => {
    try {
      const [tc, dr] = await Promise.all([
        apiFetch("/trust-center"),
        apiFetch("/trust-center/deletion-requests").catch(() => null),
      ]);
      if (!tc.ok) {
        throw new Error(`GET /trust-center failed: HTTP ${tc.status}`);
      }
      setData(await tc.json());

      if (dr?.ok) {
        const drData = await dr.json();
        const pending = (drData.requests ?? []).find(
          (r: DeletionRequest) => r.status === "pending",
        );
        setPendingDeletion(pending ?? null);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const requestDeletion = async () => {
    try {
      const resp = await apiFetch("/trust-center/deletion-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: null }),
      });
      if (!resp.ok) {
        throw new Error(`POST deletion request: HTTP ${resp.status}`);
      }
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const cancelDeletion = async () => {
    if (!pendingDeletion) return;
    try {
      const resp = await apiFetch(
        `/trust-center/deletion-requests/${encodeURIComponent(pendingDeletion.request_id)}/cancel`,
        { method: "POST" },
      );
      if (!resp.ok) {
        throw new Error(`Cancel deletion: HTTP ${resp.status}`);
      }
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const totalEpsilon = data
    ? Object.values(data.differential_privacy_epsilon_budgets).reduce(
        (a, b) => a + b,
        0,
      )
    : 0;

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-8">
          <header className="space-y-2">
            <div className="flex items-center gap-3">
              <img
                src={thinkingArt}
                alt=""
                aria-hidden="true"
                data-testid="privacy-dashboard-werner-brand"
                className="h-12 w-12 shrink-0 object-contain"
              />
              <h1 className="text-2xl font-serif text-ink dark:text-bright">
                Privacy dashboard
              </h1>
            </div>
            <img
              src={livingTvArt}
              alt=""
              aria-hidden="true"
              data-testid="privacy-dashboard-living-tv-art"
              className="h-16 w-full max-w-md rounded-md object-cover object-center"
              loading="lazy"
              decoding="async"
            />
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Every telemetry signal Antiek collects from your private
              graph is listed below with its live ε budget pulled from
              the substrate's published trust posture. The substrate
              is architecturally incapable of crossing these boundaries.
            </p>
            {data && (
              <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                substrate-wide daily ε total: {totalEpsilon.toFixed(2)}{" "}
                (master-spec §16.2 cap: 10.00)
              </p>
            )}
          </header>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {data &&
            Object.entries(data.differential_privacy_epsilon_budgets).map(
              ([category, epsilon]) => (
                <TelemetrySection
                  key={category}
                  title={category.replace(/_/g, " ")}
                  description={
                    CATEGORY_DESCRIPTIONS[category] ??
                    "Telemetry surface registered by the substrate. " +
                    "ε budget reflects the EpsilonRegistry's per-day " +
                    "cap for this category."
                  }
                  epsilon={epsilon}
                  sensitivity={SENSITIVITY_BY_EPSILON(epsilon)}
                />
              ),
            )}

          {data && <ArchitecturalGuarantees data={data} />}

          {data && (
            <DeleteEverything
              pendingDeletion={pendingDeletion}
              deletionSlaDays={data.deletion_sla_days}
              onRequest={requestDeletion}
              onCancel={cancelDeletion}
            />
          )}
        </div>
      </main>
    </div>
  );
}

function TelemetrySection({
  title,
  description,
  epsilon,
  sensitivity,
}: {
  title: string;
  description: string;
  epsilon: number;
  sensitivity: "low" | "medium" | "high" | "forbidden";
}) {
  const isForbidden = sensitivity === "forbidden";
  return (
    <section className="border border-rule dark:border-charcoal-1 rounded-md px-5 py-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-base font-serif text-ink dark:text-bright capitalize">
          {title}
        </h3>
        <span className="text-xs font-mono text-shadow-1 dark:text-moonlight">
          ε = {epsilon}/day
        </span>
      </div>
      <p className="text-sm text-ink dark:text-bright leading-relaxed">{description}</p>
      <div className="flex items-center gap-3 pt-1">
        {isForbidden ? (
          <span className="text-xs font-mono text-emerald-700 bg-emerald-50 px-2 py-1 rounded">
            never collected (architectural)
          </span>
        ) : (
          <span className="text-xs font-mono text-ink dark:text-bright bg-ice-3 dark:bg-charcoal-1 px-2 py-1 rounded">
            collected · noisy aggregate · ε-bounded
          </span>
        )}
        <span
          className={`text-xs font-mono px-2 py-1 rounded ${
            sensitivity === "low"
              ? "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright"
              : sensitivity === "medium"
                ? "bg-sun/10 text-amber-800"
                : sensitivity === "high"
                  ? "bg-red-50 text-red-800"
                  : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright"
          }`}
        >
          sensitivity: {sensitivity}
        </span>
      </div>
    </section>
  );
}

function ArchitecturalGuarantees({ data }: { data: TrustCenterData }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-serif text-ink dark:text-bright">
        Architectural guarantees
      </h2>
      <ul className="text-sm text-ink dark:text-bright leading-relaxed space-y-2 list-disc pl-5">
        {data.substrate_controls.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <p className="text-xs text-shadow-1 dark:text-moonlight font-mono leading-relaxed pt-2">
        Compliance posture: {data.compliance_frameworks.join(" · ")}
      </p>
    </section>
  );
}

function DeleteEverything({
  pendingDeletion,
  deletionSlaDays,
  onRequest,
  onCancel,
}: {
  pendingDeletion: DeletionRequest | null;
  deletionSlaDays: number;
  onRequest: () => void;
  onCancel: () => void;
}) {
  return (
    <section className="border border-red-200 rounded-md px-5 py-4 space-y-3 bg-red-50">
      <h2 className="text-base font-serif text-red-900">Delete everything</h2>
      <p className="text-sm text-red-900 leading-relaxed">
        Schedules deletion of your private partition, telemetry, and
        billing records within {deletionSlaDays} days. Public-graph
        contributions you've made stay attributed to your account
        unless you also opt out of cross-user surfacing (separate
        setting). Master-spec §13.3 commits the substrate to this SLA.
      </p>
      {pendingDeletion ? (
        <div className="space-y-2">
          <p className="text-sm font-mono text-red-900">
            Pending — request_id = {pendingDeletion.request_id} ·
            requested {pendingDeletion.requested_at}
          </p>
          <p className="text-sm text-red-900">
            Cancellation window: {pendingDeletion.cancellation_window_days} days.
            Deletion proceeds {Math.max(
              0,
              deletionSlaDays - pendingDeletion.cancellation_window_days,
            )}{" "}
            days after this request unless cancelled.
          </p>
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 rounded-md border border-red-300 text-red-900 text-xs font-medium hover:bg-emperor/20 transition-colors"
          >
            Cancel deletion request
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={onRequest}
          className="px-3 py-1.5 rounded-md bg-red-700 text-white text-xs font-medium hover:bg-red-800 transition-colors"
        >
          Request deletion
        </button>
      )}
    </section>
  );
}
