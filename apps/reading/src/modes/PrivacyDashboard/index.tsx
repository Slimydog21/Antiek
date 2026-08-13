import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../../lib/api";
import {
  fetchPrivacySettings,
  setPrivacySurface,
  type PrivacySurface,
} from "../../api/privacy";

/**
 * Privacy Dashboard (master-spec §13.3 — first-class product surface).
 *
 * "Real-time view of every telemetry collected from the user's
 * private graph, with toggles per category and a 'delete everything'
 * button that actually deletes everything within 30 days."
 *
 * Since OYM P1 §2 the toggle state is REAL: each section reads its
 * enabled/default_enabled from ``GET /settings/privacy`` (backed by
 * the telemetry-preferences store, the DP shuffler's predicate) and
 * flips it through ``PUT /settings/privacy`` with an optimistic
 * update + rollback on failure. The ε budgets still come from the
 * live ``/trust-center`` publication so any future surface that
 * registers with the EpsilonRegistry appears here automatically.
 *
 * The forbidden surface (query-content telemetry) is rendered locked:
 * per master-spec §13.3 the substrate is architecturally incapable of
 * collecting it, so there is no toggle to flip — "we are
 * architecturally incapable of leaking your data" rather than
 * "we promise not to."
 */

interface TrustCenterData {
  differential_privacy_epsilon_budgets: Record<string, number>;
  deletion_sla_days: number;
  substrate_controls: string[];
  compliance_frameworks: string[];
  loop_3_unlock_status: Record<string, boolean>;
}

/**
 * Fallback copy keyed by CANONICAL registry names. The registry names
 * the tier surface ``source_tier_preference`` (the dashboard's old
 * ``source_tier_preference_signals`` key never matched a live surface);
 * the backend serves the authoritative descriptions from the same copy,
 * so this map only fills in for trust-center-only categories.
 */
const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  skill_invocation_frequency:
    "Which substrate skills fire and at what rate. Low sensitivity; " +
    "the DP randomizer ensures no single invocation is identifying.",
  source_tier_preference:
    "Which source tiers (Tier 1 = peer-reviewed primary, " +
    "Tier 5 = anonymous) you accept versus reject. The shuffled " +
    "aggregate informs the dispatch router's tier hints.",
  query_content_telemetry:
    "The text of your research queries and the content of your " +
    "private notes. Per master-spec §13.3: NOT COLLECTED at any ε " +
    "that preserves utility — Antiek chooses no collection.",
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
  const [privacy, setPrivacy] = useState<PrivacySurface[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingDeletion, setPendingDeletion] = useState<DeletionRequest | null>(null);
  const [savingSurface, setSavingSurface] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [tc, dr, privacyResp] = await Promise.all([
        apiFetch("/trust-center"),
        apiFetch("/trust-center/deletion-requests").catch(() => null),
        fetchPrivacySettings(),
      ]);
      if (!tc.ok) {
        throw new Error(`GET /trust-center failed: HTTP ${tc.status}`);
      }
      setData(await tc.json());
      setPrivacy(privacyResp.surfaces);

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

  const toggleSurface = async (surface: PrivacySurface, enabled: boolean) => {
    if (!privacy || savingSurface !== null) return;
    const previous = privacy;
    // Optimistic update; roll back on failure.
    setPrivacy(
      privacy.map((s) =>
        s.surface_name === surface.surface_name ? { ...s, enabled } : s,
      ),
    );
    setSavingSurface(surface.surface_name);
    try {
      const updated = await setPrivacySurface(surface.surface_name, enabled);
      setPrivacy((prev) =>
        prev?.map((s) =>
          s.surface_name === updated.surface_name ? updated : s,
        ) ?? prev,
      );
    } catch (e: unknown) {
      setPrivacy(previous);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingSurface(null);
    }
  };

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
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Privacy dashboard
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Every telemetry signal Antiek collects from your private
              graph is listed below with its live ε budget pulled from
              the substrate's published trust posture. Toggles write
              straight to your telemetry preferences — the same store
              the DP shuffler consults before emitting anything. The
              substrate is architecturally incapable of crossing these
              boundaries.
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

          {privacy &&
            privacy.map((surface) => (
              <TelemetrySection
                key={surface.surface_name}
                surface={surface}
                saving={savingSurface === surface.surface_name}
                onToggle={(enabled) => void toggleSurface(surface, enabled)}
              />
            ))}

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
  surface,
  saving,
  onToggle,
}: {
  surface: PrivacySurface;
  saving: boolean;
  onToggle: (enabled: boolean) => void;
}) {
  const isForbidden = surface.sensitivity === "forbidden";
  const title = surface.surface_name.replace(/_/g, " ");
  // Server description is authoritative (it mirrors this copy
  // keyed by registry names); the map is only a rendering fallback.
  const description = surface.description || CATEGORY_DESCRIPTIONS[surface.surface_name];
  return (
    <section
      className={`border border-rule dark:border-charcoal-1 rounded-md px-5 py-4 space-y-3 ${
        isForbidden ? "opacity-70" : ""
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-base font-serif text-ink dark:text-bright capitalize">
          {title}
        </h3>
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-shadow-1 dark:text-moonlight">
            ε = {surface.epsilon_per_day}/day
          </span>
          {!isForbidden && (
            <ToggleSwitch
              label={`${title} telemetry`}
              checked={surface.enabled}
              disabled={saving}
              onChange={onToggle}
            />
          )}
        </div>
      </div>
      <p className="text-sm text-ink dark:text-bright leading-relaxed">
        {description}
      </p>
      <div className="flex items-center gap-3 pt-1">
        {isForbidden ? (
          <span className="text-xs font-mono text-emerald-700 bg-emerald-50 px-2 py-1 rounded">
            never collected (architectural) — locked
          </span>
        ) : (
          <span className="text-xs font-mono text-ink dark:text-bright bg-ice-3 dark:bg-charcoal-1 px-2 py-1 rounded">
            {surface.enabled
              ? "collected · noisy aggregate · ε-bounded"
              : "paused — no telemetry routed"}
          </span>
        )}
        <span
          className={`text-xs font-mono px-2 py-1 rounded ${
            surface.sensitivity === "low"
              ? "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright"
              : surface.sensitivity === "medium"
                ? "bg-sun/10 text-amber-800"
                : surface.sensitivity === "high"
                  ? "bg-red-50 text-red-800"
                  : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright"
          }`}
        >
          sensitivity: {surface.sensitivity}
        </span>
        <span className="text-xs text-shadow-1 dark:text-moonlight">
          {surface.opt_in_required
            ? "off by default (opt-in)"
            : isForbidden
              ? "never enabled"
              : "on by default"}
        </span>
      </div>
    </section>
  );
}

function ToggleSwitch({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onChange: (enabled: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-base ease-standard focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sun disabled:cursor-not-allowed disabled:opacity-disabled ${
        checked
          ? "bg-emerald-600"
          : "bg-ice-3 dark:bg-charcoal-1 border border-rule dark:border-slate-1"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-base ease-standard ${
          checked ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
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
