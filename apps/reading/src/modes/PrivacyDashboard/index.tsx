import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "../../lib/api";
import {
  EPSILON_CAP,
  formatBudgetDescription,
  formatBudgetLabel,
  formatComplianceLabel,
  formatSensitivityLabel,
  formatSystemControl,
  sensitivityForBudget,
  type PrivacySensitivity,
} from "../../lib/trustCopy";

interface TrustCenterData {
  differential_privacy_epsilon_budgets: Record<string, number>;
  deletion_sla_days: number;
  substrate_controls: string[];
  compliance_frameworks: string[];
  loop_3_unlock_status: Record<string, boolean>;
  loop_3_evidence_status?: Record<string, boolean>;
  loop_3_evidence_summaries?: Record<string, string>;
  loop_3_all_evidence_passed?: boolean;
}

interface DeletionRequest {
  request_id: string;
  status: string;
  requested_at: string;
  cancellation_window_days: number;
  deletion_sla_days: number;
}

interface TelemetryPreference {
  surface_name: string;
  epsilon_per_day: number;
  sensitivity: PrivacySensitivity;
  description: string;
  opt_in_required: boolean;
  enabled: boolean;
  updated_at: string | null;
}

const KNOWN_BUDGET_CATEGORIES = new Set([
  "skill_invocation_frequency",
  "source_tier_preference_signals",
  "query_content_telemetry",
]);

function titleFromPreference(preference: TelemetryPreference | undefined, category: string) {
  if (!preference || KNOWN_BUDGET_CATEGORIES.has(category)) {
    return formatBudgetLabel(category);
  }
  const firstSentence = preference.description.split(/[.!?]/)[0]?.trim();
  const phrase = firstSentence || "Registered privacy signal";
  return phrase.charAt(0).toUpperCase() + phrase.slice(1);
}

export default function PrivacyDashboard() {
  const [data, setData] = useState<TrustCenterData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingDeletion, setPendingDeletion] = useState<DeletionRequest | null>(null);
  const [deletionStatusKnown, setDeletionStatusKnown] = useState(false);
  const [deletionBusy, setDeletionBusy] = useState(false);
  const [preferences, setPreferences] = useState<Record<string, TelemetryPreference>>({});
  const [preferencesKnown, setPreferencesKnown] = useState(false);
  const [preferenceError, setPreferenceError] = useState<string | null>(null);
  const [preferenceBusy, setPreferenceBusy] = useState<string | null>(null);
  const reloadSeq = useRef(0);

  const reload = useCallback(async (options?: {
    preserveDataOnFailure?: boolean;
    preservePendingOnFailure?: boolean;
    suppressPendingOnSuccess?: boolean;
  }) => {
    const requestId = reloadSeq.current + 1;
    reloadSeq.current = requestId;
    try {
      const [tc, dr, pref] = await Promise.all([
        apiFetch("/trust-center"),
        apiFetch("/trust-center/deletion-requests").catch(() => null),
        apiFetch("/trust-center/telemetry-preferences").catch(() => null),
      ]);
      if (requestId !== reloadSeq.current) return false;
      if (!tc.ok) {
        if (!options?.preserveDataOnFailure) setData(null);
        if (!options?.preservePendingOnFailure) {
          setPendingDeletion(null);
          setDeletionStatusKnown(false);
        }
        setPreferences({});
        setPreferencesKnown(false);
        setPreferenceError(null);
        throw new Error(`Could not load privacy settings (HTTP ${tc.status}).`);
      }
      setError(null);
      setData(await tc.json());

      if (dr?.ok) {
        const drData = await dr.json();
        const pending = (drData.requests ?? []).find(
          (r: DeletionRequest) => r.status === "pending",
        );
        setDeletionStatusKnown(true);
        if (options?.suppressPendingOnSuccess) {
          setPendingDeletion(null);
        } else if (pending) {
          setPendingDeletion(pending);
        } else if (!options?.preservePendingOnFailure) {
          setPendingDeletion(null);
        }
      } else {
        setDeletionStatusKnown(false);
        if (!options?.preservePendingOnFailure) setPendingDeletion(null);
      }
      if (pref?.ok) {
        const prefData = await pref.json();
        setPreferences(
          Object.fromEntries(
            (prefData.preferences ?? []).map((p: TelemetryPreference) => [
              p.surface_name,
              p,
            ]),
          ),
        );
        setPreferencesKnown(true);
        setPreferenceError(null);
      } else {
        setPreferences({});
        setPreferencesKnown(false);
        setPreferenceError("Could not load privacy preferences; toggles unavailable.");
      }
      return true;
    } catch (e: unknown) {
      if (requestId !== reloadSeq.current) return false;
      if (!options?.preserveDataOnFailure) setData(null);
      if (!options?.preservePendingOnFailure) {
        setPendingDeletion(null);
        setDeletionStatusKnown(false);
      }
      setPreferences({});
      setPreferencesKnown(false);
      setPreferenceError(null);
      setError(e instanceof Error ? e.message : String(e));
      return false;
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const requestDeletion = async () => {
    if (deletionBusy || !deletionStatusKnown) return;
    setDeletionBusy(true);
    try {
      const resp = await apiFetch("/trust-center/deletion-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: null }),
      });
      if (!resp.ok) {
        throw new Error(`Could not request deletion (HTTP ${resp.status}).`);
      }
      setPendingDeletion(await resp.json());
      setDeletionStatusKnown(true);
      await reload({
        preserveDataOnFailure: true,
        preservePendingOnFailure: true,
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletionBusy(false);
    }
  };

  const cancelDeletion = async () => {
    if (!pendingDeletion || deletionBusy) return;
    setDeletionBusy(true);
    try {
      const resp = await apiFetch(
        `/trust-center/deletion-requests/${encodeURIComponent(pendingDeletion.request_id)}/cancel`,
        { method: "POST" },
      );
      if (!resp.ok) {
        throw new Error(`Could not cancel deletion (HTTP ${resp.status}).`);
      }
      setPendingDeletion(null);
      setDeletionStatusKnown(true);
      await reload({
        preserveDataOnFailure: true,
        suppressPendingOnSuccess: true,
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletionBusy(false);
    }
  };

  const updatePreference = async (surfaceName: string, enabled: boolean) => {
    if (preferenceBusy) return;
    setPreferenceBusy(surfaceName);
    try {
      const resp = await apiFetch(
        `/trust-center/telemetry-preferences/${encodeURIComponent(surfaceName)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled }),
        },
      );
      if (!resp.ok) {
        throw new Error(`Could not update privacy preference (HTTP ${resp.status}).`);
      }
      const updated = await resp.json();
      setPreferences((current) => ({
        ...current,
        [updated.surface_name]: updated,
      }));
      setPreferencesKnown(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPreferenceBusy(null);
    }
  };

  const totalEpsilon = data
    ? Object.values(data.differential_privacy_epsilon_budgets).reduce(
        (a, b) => a + b,
        0,
      )
    : 0;
  const telemetryRows = data
    ? (preferencesKnown
        ? Object.values(preferences).map((preference) => ({
            category: preference.surface_name,
            epsilon: preference.epsilon_per_day,
            sensitivity: preference.sensitivity,
            preference,
          }))
        : Object.entries(data.differential_privacy_epsilon_budgets).map(
            ([category, epsilon]) => ({
              category,
              epsilon,
              sensitivity: sensitivityForBudget(category, epsilon),
              preference: undefined,
            }),
          ))
    : [];

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-8">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Privacy dashboard
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Every privacy signal Antiek collects is listed below with
              its live daily privacy budget. Categories marked as never
              collected do not leave your private workspace.
            </p>
            {data && (
              <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                Daily privacy budget total: {totalEpsilon.toFixed(2)} of{" "}
                {EPSILON_CAP.toFixed(2)}
              </p>
            )}
          </header>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {preferenceError && (
            <p className="text-sm text-amber-900 border border-amber-200 bg-amber-50 px-3 py-2 rounded">
              {preferenceError}
            </p>
          )}

          {data &&
            telemetryRows.map(
              ({ category, epsilon, sensitivity, preference }) => (
                <TelemetrySection
                  key={category}
                  title={titleFromPreference(preference, category)}
                  description={
                    preference && !KNOWN_BUDGET_CATEGORIES.has(category)
                      ? preference.description
                      : formatBudgetDescription(category)
                  }
                  epsilon={epsilon}
                  sensitivity={sensitivity}
                  preference={preference}
                  preferencesKnown={preferencesKnown}
                  preferenceBusy={preferenceBusy === category}
                  onPreferenceChange={(enabled) => updatePreference(category, enabled)}
                />
              ),
            )}

          {data && <ArchitecturalGuarantees data={data} />}

          {data && (
            <DeleteEverything
              pendingDeletion={pendingDeletion}
              deletionStatusKnown={deletionStatusKnown}
              deletionBusy={deletionBusy}
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
  preference,
  preferencesKnown,
  preferenceBusy,
  onPreferenceChange,
}: {
  title: string;
  description: string;
  epsilon: number;
  sensitivity: PrivacySensitivity;
  preference: TelemetryPreference | undefined;
  preferencesKnown: boolean;
  preferenceBusy: boolean;
  onPreferenceChange: (enabled: boolean) => void;
}) {
  const isForbidden = sensitivity === "forbidden";
  const enabled = preference?.enabled ?? !isForbidden;
  return (
    <section className="border border-rule dark:border-charcoal-1 rounded-md px-5 py-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-base font-serif text-ink dark:text-bright capitalize">
          {title}
        </h3>
        <span className="text-xs font-mono text-shadow-1 dark:text-moonlight">
          Privacy budget: {epsilon}/day
        </span>
      </div>
      <p className="text-sm text-ink dark:text-bright leading-relaxed">{description}</p>
      <div className="flex items-center gap-3 pt-1">
        {isForbidden ? (
          <span className="text-xs font-mono text-emerald-700 bg-emerald-50 px-2 py-1 rounded">
            Never collected
          </span>
        ) : (
          <label className="inline-flex items-center gap-2 text-xs font-mono text-ink dark:text-bright bg-ice-3 dark:bg-charcoal-1 px-2 py-1 rounded">
            <input
              type="checkbox"
              checked={enabled}
              disabled={!preferencesKnown || preferenceBusy}
              onChange={(event) => onPreferenceChange(event.currentTarget.checked)}
            />
            <span>
              {!preferencesKnown
                ? "Preference unavailable"
                : enabled
                  ? "Noisy aggregate on"
                  : "Noisy aggregate off"}
            </span>
          </label>
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
          Sensitivity: {formatSensitivityLabel(sensitivity)}
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
          <li key={c}>{formatSystemControl(c)}</li>
        ))}
      </ul>
      <p className="text-xs text-shadow-1 dark:text-moonlight font-mono leading-relaxed pt-2">
        Compliance posture:{" "}
        {data.compliance_frameworks.map(formatComplianceLabel).join(" · ")}
      </p>
    </section>
  );
}

function DeleteEverything({
  pendingDeletion,
  deletionStatusKnown,
  deletionBusy,
  deletionSlaDays,
  onRequest,
  onCancel,
}: {
  pendingDeletion: DeletionRequest | null;
  deletionStatusKnown: boolean;
  deletionBusy: boolean;
  deletionSlaDays: number;
  onRequest: () => void;
  onCancel: () => void;
}) {
  return (
    <section className="border border-red-200 rounded-md px-5 py-4 space-y-3 bg-red-50">
      <h2 className="text-base font-serif text-red-900">Delete everything</h2>
      <p className="text-sm text-red-900 leading-relaxed">
        Schedules deletion of your saved content, personalization data,
        privacy signals, and billing records within {deletionSlaDays} days.
        Public contributions stay attributed to your account unless you
        also turn off cross-user sharing.
      </p>
      {pendingDeletion ? (
        <div className="space-y-2">
          <p className="text-sm font-mono text-red-900">
            Pending deletion request · requested{" "}
            {new Date(pendingDeletion.requested_at).toLocaleDateString()}
          </p>
          <p className="text-sm text-red-900">
            Cancellation window: {pendingDeletion.cancellation_window_days} days.
            Deletion completes within {deletionSlaDays} days of the original
            request unless cancelled.
          </p>
          <button
            type="button"
            onClick={onCancel}
            disabled={deletionBusy}
            className="px-3 py-1.5 rounded-md border border-red-300 text-red-900 text-xs font-medium hover:bg-emperor/20 transition-colors"
          >
            {deletionBusy ? "Cancelling deletion..." : "Cancel deletion request"}
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={onRequest}
          disabled={deletionBusy || !deletionStatusKnown}
          className="px-3 py-1.5 rounded-md bg-red-700 text-white text-xs font-medium hover:bg-red-800 disabled:bg-red-300 disabled:cursor-not-allowed transition-colors"
        >
          {deletionBusy
            ? "Requesting deletion..."
            : deletionStatusKnown
              ? "Request deletion"
              : "Deletion status unavailable"}
        </button>
      )}
    </section>
  );
}
