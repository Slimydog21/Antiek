/**
 * LineupPitch — the FIFA-Ultimate-Team-style formation for the AI role
 * lineup. One "position" per general role on a pitch; tap a position to
 * select it, tap a bench card to substitute (swap) the model in, tap
 * "Auto" to return to the platform default.
 *
 * Honesty rules:
 *   * The STR badge is tier strength FROM THE DISPATCH TIER NAME — never
 *     a model quality measurement. Presets/user models are 7 "unmeasured".
 *   * Auto (null assignment) is always shown as the default state.
 *   * An empty bench renders a named empty state, not a blank list.
 *   * Substitution is optimistic-free: the parent persists first, then
 *     this component re-renders from the saved lineup.
 */

import { type KeyboardEvent, useId, useMemo, useState } from "react";

import { FORMATION, type BenchModelView, type LineupChoice, type RoleView, tierStrength } from "../api/settingsLineup";

const POSITION_LABEL: Record<string, string> = {
  gk: "GK",
  def: "DEF",
  mid: "MID",
  att: "ATT",
};

const TIER_COLOR: Record<string, string> = {
  synthesis: "bg-sun text-ink",
  verify: "bg-sun text-ink",
  pro: "bg-sun-light text-ink",
  flash: "bg-ice-2 text-shadow-1 dark:bg-charcoal-2 dark:text-moonlight",
};

function sourceBadge(b: BenchModelView): string {
  if (b.source === "user_model") return "YOUR KEY";
  if (b.source === "preset") return "BYOT";
  return b.default_tier ? b.default_tier.toUpperCase() : "SERVER";
}

export interface LineupPitchProps {
  roles: RoleView[];
  bench: BenchModelView[];
  assignments: Record<string, LineupChoice | null>;
  selectedRole: string | null;
  onSelectRole: (roleId: string | null) => void;
  /** Substitute: assign `choice` (or null for Auto) to `roleId`. */
  onAssign: (roleId: string, choice: LineupChoice | null) => void;
  busyRole: string | null;
  error?: string | null;
}

export default function LineupPitch({
  roles,
  bench,
  assignments,
  selectedRole,
  onSelectRole,
  onAssign,
  busyRole,
  error = null,
}: LineupPitchProps) {
  const listboxId = useId();
  const [benchOpen, setBenchOpen] = useState(false);

  const byId = useMemo(() => new Map(roles.map((r) => [r.role_id, r])), [roles]);
  const selection = selectedRole ? byId.get(selectedRole) ?? null : null;

  const benchChoiceKey = (b: BenchModelView) => `${b.provider_id}:${b.model_id}`;
  const chosen = selection ? assignments[selection.role_id] ?? null : null;

  function pickBench(b: BenchModelView) {
    if (!selection) return;
    onAssign(selection.role_id, { provider_id: b.provider_id, model_id: b.model_id });
    setBenchOpen(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "Escape") {
      onSelectRole(null);
      setBenchOpen(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-shadow-1 dark:text-moonlight">
          Formation — tap a position, then a bench card to substitute
        </span>
        {selection && (
          <button
            type="button"
            onClick={() => {
              onSelectRole(null);
              setBenchOpen(false);
            }}
            className="text-[11px] font-semibold text-sun-deep underline-offset-2 hover:underline dark:text-sun-light"
          >
            Clear selection
          </button>
        )}
      </div>

      {/* ── The pitch ─────────────────────────────────────────────── */}
      <div
        className="relative w-full overflow-hidden rounded-hog border-2 border-sun/60 shadow-[4px_4px_0_rgba(0,0,0,0.15)]"
        style={{
          aspectRatio: "4 / 5",
          background:
            "linear-gradient(160deg, var(--pitch-base) 0%, var(--pitch-mid) 45%, var(--pitch-deep) 100%)",
        }}
        role="group"
        aria-label="AI role formation pitch"
      >
        {/* pitch markings */}
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-white/25" />
          <div className="absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white/25" />
          <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/30" />
          <div className="absolute left-0 top-[12%] h-[18%] w-[38%] rounded-r-2xl border-2 border-l-0 border-white/25" />
          <div className="absolute right-0 top-[12%] h-[18%] w-[38%] rounded-l-2xl border-2 border-r-0 border-white/25" />
          <div className="absolute bottom-0 left-0 h-[22%] w-[30%] rounded-tr-2xl border-2 border-b-0 border-l-0 border-white/25" />
          <div className="absolute bottom-0 right-0 h-[22%] w-[30%] rounded-tl-2xl border-2 border-b-0 border-r-0 border-white/25" />
        </div>

        {/* positions */}
        {roles.map((role) => {
          const pos = FORMATION[role.role_id] ?? { x: 50, y: 50 };
          const assigned = assignments[role.role_id] ?? null;
          const benchModel = assigned
            ? bench.find(
                (b) => b.provider_id === assigned.provider_id && b.model_id === assigned.model_id,
              ) ?? null
            : null;
          const strength = tierStrength(benchModel?.default_tier ?? null, benchModel?.source ?? null);
          const isSelected = selectedRole === role.role_id;
          const isBusy = busyRole === role.role_id;
          return (
            <button
              key={role.role_id}
              type="button"
              aria-pressed={isSelected}
              aria-label={`${role.label} position — ${assigned ? `${assigned.provider_id} / ${assigned.model_id}` : "Auto"}`}
              onClick={() => {
                onSelectRole(isSelected ? null : role.role_id);
                setBenchOpen(false);
              }}
              onKeyDown={onKeyDown}
              className={`absolute -translate-x-1/2 -translate-y-1/2 transition-transform duration-150 ${
                isSelected ? "z-10 scale-110" : "z-[5] hover:scale-105"
              } ${isBusy ? "animate-pulse" : ""}`}
              style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
            >
              <div
                className={`w-28 rounded-lg border-2 p-1.5 text-left shadow-[3px_3px_0_rgba(0,0,0,0.25)] backdrop-blur-[1px] sm:w-32 ${
                  isSelected
                    ? "border-sun bg-ice-0 dark:bg-charcoal-1"
                    : "border-white/40 bg-black/25"
                }`}
              >
                <div className="flex items-start justify-between gap-1">
                  <span className="font-mono text-[9px] font-bold text-white/80">
                    {POSITION_LABEL[role.position] ?? role.position.toUpperCase()}
                  </span>
                  {strength !== null ? (
                    <span
                      className={`flex h-5 w-5 items-center justify-center rounded-full border border-white/40 font-mono text-[10px] font-bold ${
                        TIER_COLOR[benchModel?.default_tier ?? ""] ?? "bg-ice-2 text-shadow-1"
                      }`}
                      title="Tier strength from the dispatch config — not a model quality measurement"
                    >
                      {strength}
                    </span>
                  ) : (
                    <span className="rounded-full border border-white/40 bg-white/10 px-1 font-mono text-[9px] font-bold text-white/80">
                      AUTO
                    </span>
                  )}
                </div>
                <div className="mt-1 truncate text-[11px] font-bold leading-tight text-white">
                  {role.label}
                </div>
                <div className="truncate font-mono text-[9px] text-white/70">
                  {assigned ? `${assigned.provider_id} / ${assigned.model_id}` : "Auto — platform default"}
                </div>
                {role.discovered && (
                  <div className="mt-0.5 inline-block rounded-sm bg-sun/20 px-1 font-mono text-[8px] font-bold text-white/90">
                    NEW SIGNING
                  </div>
                )}
              </div>
            </button>
          );
        })}

        {/* substitution splash — selected role callout */}
        {selection && (
          <div className="absolute inset-x-0 bottom-0 z-20 border-t-2 border-sun bg-ice-0/95 p-2 dark:bg-charcoal-1/95">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-[11px] font-bold text-ink dark:text-bright">
                  {selection.label}
                </div>
                <div className="truncate font-mono text-[9px] text-shadow-1 dark:text-moonlight">
                  {chosen ? `${chosen.provider_id} / ${chosen.model_id}` : "Auto — platform default"}
                </div>
              </div>
              <div className="flex shrink-0 gap-1.5">
                <button
                  type="button"
                  aria-label={`Reset ${selection.label} to Auto`}
                  onClick={() => {
                    onAssign(selection.role_id, null);
                    setBenchOpen(false);
                  }}
                  className="rounded-md border-2 border-emperor/40 px-2 py-1 text-[10px] font-bold text-emperor transition-colors hover:bg-emperor/10 dark:text-moonlight"
                >
                  Auto
                </button>
                <button
                  type="button"
                  aria-expanded={benchOpen}
                  aria-controls={listboxId}
                  onClick={() => setBenchOpen((v) => !v)}
                  className="rounded-md border-2 border-sun bg-sun px-2 py-1 text-[10px] font-bold text-ink shadow-[2px_2px_0_rgba(0,0,0,0.15)] transition-transform hover:-translate-y-px active:translate-y-0 active:shadow-none"
                >
                  {benchOpen ? "Close bench ▲" : "Substitute ▼"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── The bench ─────────────────────────────────────────────── */}
      {benchOpen && selection && (
        <div id={listboxId} className="rounded-hog border-2 border-sun bg-ice-0 p-3 dark:bg-charcoal-1">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] font-semibold text-ink dark:text-bright">
              Bench — pick the substitute for {selection.label}
            </span>
            {error && <span className="font-mono text-[10px] text-red-700 dark:text-red-300">{error}</span>}
          </div>
          {bench.length === 0 ? (
            <p className="rounded border border-emperor/40 bg-emperor/5 px-3 py-2 text-[11px] text-emperor">
              The bench is empty. Add your own API keys in Settings → Add model, or wire a BYOT
              subscription, to have substitutes available here.
            </p>
          ) : (
            <ul role="listbox" aria-label="Bench substitutes" className="grid max-h-56 grid-cols-2 gap-2 overflow-auto sm:grid-cols-3">
              {bench.map((b) => {
                const key = benchChoiceKey(b);
                const isCurrent = chosen?.provider_id === b.provider_id && chosen?.model_id === b.model_id;
                return (
                  <li key={key}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={isCurrent}
                      onClick={() => pickBench(b)}
                      className={`w-full rounded-md border-2 p-2 text-left transition-all ${
                        isCurrent
                          ? "border-sun bg-sun/10"
                          : "border-emperor/30 bg-ice-1 hover:-translate-y-px hover:border-sun/70 dark:bg-charcoal-2"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className="truncate text-[11px] font-bold text-ink dark:text-bright">
                          {b.label}
                        </span>
                        <span className="shrink-0 rounded-sm bg-emperor/10 px-1 font-mono text-[8px] font-bold text-shadow-1 dark:text-moonlight">
                          {sourceBadge(b)}
                        </span>
                      </div>
                      <div className="truncate font-mono text-[9px] text-shadow-1 dark:text-moonlight">
                        {b.provider_id} / {b.model_id}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
