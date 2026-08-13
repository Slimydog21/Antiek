/**
 * LineupPanel — the AI role lineup surface (Settings → Lineup).
 *
 * Two layers of the SAME selector:
 *   1. FORMATION (general) — the FIFA-style pitch: one model per role.
 *   2. TACTICS (advanced)  — per-action/behavior model overrides, bucketed
 *      under the role that owns them, with "Auto" meaning "follow the
 *      role's formation pick".
 *
 * Persistence: every substitution PUTs the whole owner lineup through
 * /settings/lineup (the server re-validates each choice against the live
 * bench). Honest states: loading, error with retry, empty bench, saved
 * receipt with timestamp.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  fetchLineup,
  saveLineup,
  type LineupChoice,
  type LineupResponse,
} from "../../api/settingsLineup";
import LineupPitch from "../../components/LineupPitch";
import { LemonButton } from "../../components/lemon";
import LemonCard from "../../components/lemon/LemonCard";

export default function LineupPanel() {
  const [lineup, setLineup] = useState<LineupResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyRole, setBusyRole] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [advancedRole, setAdvancedRole] = useState<string | null>("writer");
  const [saveError, setSaveError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLineup();
      setLineup(data);
      setSavedAt(data.updated_at);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const assignments = useMemo(() => {
    if (!lineup) return { general: {} as Record<string, LineupChoice | null>, advanced: {} as Record<string, LineupChoice | null> };
    return lineup.assignments;
  }, [lineup]);

  const persist = useCallback(
    async (next: { general: Record<string, LineupChoice | null>; advanced: Record<string, LineupChoice | null> }) => {
      setSaving(true);
      setSaveError(null);
      try {
        const saved = await saveLineup(next);
        setLineup(saved);
        setSavedAt(saved.updated_at);
        return true;
      } catch (e) {
        setSaveError(e instanceof Error ? e.message : String(e));
        return false;
      } finally {
        setSaving(false);
        setBusyRole(null);
      }
    },
    [],
  );

  const assignRole = useCallback(
    async (roleId: string, choice: LineupChoice | null) => {
      if (!lineup) return;
      setBusyRole(roleId);
      const general = { ...assignments.general, [roleId]: choice };
      const advanced = { ...assignments.advanced };
      const ok = await persist({ general, advanced });
      if (ok && selectedRole === roleId) setSelectedRole(null);
    },
    [lineup, assignments, persist, selectedRole],
  );

  const assignAction = useCallback(
    async (actionId: string, choice: LineupChoice | null) => {
      if (!lineup) return;
      setBusyRole(actionId);
      const advanced = { ...assignments.advanced, [actionId]: choice };
      const general = { ...assignments.general };
      await persist({ general, advanced });
    },
    [lineup, assignments, persist],
  );

  if (loading && !lineup) {
    return (
      <LemonCard title="AI Role Lineup" elevation="z1">
        <div className="flex items-center gap-2 p-4 text-[11px] text-shadow-1 dark:text-moonlight" role="status">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-sun" />
          Loading the lineup…
        </div>
      </LemonCard>
    );
  }

  if (error && !lineup) {
    return (
      <LemonCard title="AI Role Lineup" elevation="z1">
        <div className="flex flex-col items-start gap-3 p-4">
          <p className="rounded border border-emperor/40 bg-emperor/5 px-3 py-2 text-[11px] text-emperor" role="alert">
            Lineup unavailable · {error}
          </p>
          <LemonButton variant="secondary" size="sm" onClick={() => void refresh()}>
            Retry
          </LemonButton>
        </div>
      </LemonCard>
    );
  }

  if (!lineup) return null;

  const roleById = new Map(lineup.general.map((r) => [r.role_id, r]));

  return (
    <div className="space-y-4">
      <LemonCard
        title="Formation — general selector"
        elevation="z1"
        footer={
          <div className="flex items-center justify-between px-4 py-2">
            <span className="font-mono text-[10px] text-shadow-1 dark:text-moonlight">
              {saving
                ? "Saving lineup…"
                : savedAt
                  ? `Last saved ${savedAt}`
                  : "No changes saved yet"}
            </span>
            {saveError && (
              <span className="font-mono text-[10px] text-red-700 dark:text-red-300" role="alert">
                Save failed · {saveError}
              </span>
            )}
          </div>
        }
      >
        <div className="p-4">
          <p className="mb-3 text-[11px] leading-relaxed text-shadow-1 dark:text-moonlight">
            One model per role. <span className="font-bold">Writer</span> scores the human-facing
            deliverables, <span className="font-bold">Data Refinement</span> builds the play,
            <span className="font-bold"> Data Miner</span> does the grunt work, and
            <span className="font-bold"> Data Verification</span> keeps the last line — plus the
            roles the forensic inventory found missing (NEW SIGNING). Substitutions bind into the
            dispatch router for every role with a backend dispatch role; the tier's fallback chain
            is always preserved (a down or unregistered pick falls through, never bricks a call).
          </p>
          <LineupPitch
            roles={lineup.general}
            bench={lineup.bench}
            assignments={assignments.general}
            selectedRole={selectedRole}
            onSelectRole={setSelectedRole}
            onAssign={(roleId, choice) => void assignRole(roleId, choice)}
            busyRole={busyRole}
            error={saveError}
          />
        </div>
      </LemonCard>

      <LemonCard title="Tactics — advanced selector" elevation="z1">
        <div className="p-4">
          <p className="mb-3 text-[11px] leading-relaxed text-shadow-1 dark:text-moonlight">
            Pick a model for a specific action/behavior. <span className="font-bold">Auto</span>{" "}
            follows the role's formation pick; a direct pick overrides it for that action only.
            The dispatch role + default tier shown are from{" "}
            <code className="font-mono text-[10px]">substrate/dispatch/config.yaml</code>.
          </p>
          <div className="mb-3 flex flex-wrap gap-1.5">
            {lineup.general.map((role) => (
              <button
                key={role.role_id}
                type="button"
                aria-pressed={advancedRole === role.role_id}
                onClick={() => setAdvancedRole(role.role_id)}
                className={`rounded-md border-2 px-2.5 py-1 text-[11px] font-bold transition-colors ${
                  advancedRole === role.role_id
                    ? "border-sun bg-sun text-ink"
                    : "border-emperor/30 text-shadow-1 hover:border-sun/70 dark:text-moonlight"
                }`}
              >
                {role.label}
                {role.discovered && <span className="ml-1 text-[8px] font-mono">NEW</span>}
              </button>
            ))}
          </div>

          {advancedRole && roleById.has(advancedRole) ? (
            <ul className="space-y-2">
              {roleById.get(advancedRole)!.actions.map((action) => {
                const current = assignments.advanced[action.action_id] ?? null;
                const isBusy = busyRole === action.action_id;
                return (
                  <li
                    key={action.action_id}
                    className="rounded-md border-2 border-emperor/25 bg-ice-1 p-3 dark:bg-charcoal-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-[12px] font-bold text-ink dark:text-bright">
                          {action.label}
                        </div>
                        <div className="truncate font-mono text-[9px] text-shadow-1 dark:text-moonlight">
                          {action.blurb} · dispatch_role={action.dispatch_role ?? "none"} · default_tier=
                          {action.default_tier ?? "none"}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <button
                          type="button"
                          aria-label={`${action.label}: Auto`}
                          onClick={() => void assignAction(action.action_id, null)}
                          disabled={isBusy || saving}
                          className={`rounded-md border-2 px-2 py-1 text-[10px] font-bold transition-colors ${
                            current === null
                              ? "border-sun bg-sun text-ink"
                              : "border-emperor/30 text-shadow-1 hover:border-sun/70 dark:text-moonlight"
                          }`}
                        >
                          Auto
                        </button>
                        <select
                          aria-label={`${action.label} model`}
                          value={current ? `${current.provider_id}:${current.model_id}` : ""}
                          onChange={(e) => {
                            const [provider_id, ...rest] = e.target.value.split(":");
                            const model_id = rest.join(":");
                            if (!provider_id) {
                              void assignAction(action.action_id, null);
                              return;
                            }
                            void assignAction(action.action_id, { provider_id, model_id });
                          }}
                          disabled={isBusy || saving}
                          className="max-w-[220px] rounded-md border-2 border-emperor/40 bg-ice-0 px-2 py-1 text-[11px] font-semibold text-ink dark:bg-charcoal-1 dark:text-bright"
                        >
                          <option value="">Auto (follow formation)</option>
                          {(action.allowed_models
                            ? lineup.bench.filter((b) => action.allowed_models!.includes(b.model_id))
                            : lineup.bench
                          ).map((b) => (
                            <option
                              key={`${b.provider_id}:${b.model_id}`}
                              value={`${b.provider_id}:${b.model_id}`}
                            >
                              {b.label} ({b.source})
                            </option>
                          ))}
                        </select>
                        {isBusy && <span className="font-mono text-[9px] text-shadow-1">…</span>}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="rounded border border-emperor/40 bg-emperor/5 px-3 py-2 text-[11px] text-emperor">
              Select a role above to see its actions.
            </p>
          )}
        </div>
      </LemonCard>
    </div>
  );
}
