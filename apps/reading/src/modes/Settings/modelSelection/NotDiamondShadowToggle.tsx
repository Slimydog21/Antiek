/**
 * NotDiamond advisor mode control — Settings.
 *
 * Never enables live routing authority. Shadow/advisory modes are operator
 * intent signals for the backend advisor contract; live HTTP stays gated.
 *
 * Controlled when `mode` + `onModeChange` are provided; otherwise owns local
 * state so the toggle still works in isolation / Storybook.
 */

import { useState } from "react";

import { emitWernerExperience } from "../../../werner/reactionBus";
import {
  defaultNotDiamondState,
  modeLabel,
  setNotDiamondMode,
  type NotDiamondMode,
  type NotDiamondUiState,
} from "./notDiamondPolicy";

const MODES: NotDiamondMode[] = ["disabled", "shadow", "advisory"];

export type NotDiamondShadowToggleProps = {
  mode?: NotDiamondMode;
  onModeChange?: (mode: NotDiamondMode) => void;
};

export function NotDiamondShadowToggle({
  mode: modeProp,
  onModeChange,
}: NotDiamondShadowToggleProps = {}) {
  const [internal, setInternal] = useState<NotDiamondUiState>(
    defaultNotDiamondState,
  );
  const controlled = modeProp !== undefined;
  const mode = controlled ? modeProp : internal.mode;
  const liveAdapterEnabled = controlled
    ? false
    : internal.liveAdapterEnabled;
  const authority = controlled ? "advisory_or_less" : internal.authority;

  const setMode = (next: NotDiamondMode) => {
    // Living-TV: advisor mode change is a noted honesty beat (never live authority).
    emitWernerExperience(next === "disabled" ? "highlight" : "note_saved");
    if (onModeChange) onModeChange(next);
    if (!controlled) {
      setInternal((s) => setNotDiamondMode(s, next));
    }
  };

  return (
    <section
      data-testid="notdiamond-shadow-toggle"
      className="space-y-3"
      aria-label="NotDiamond advisor"
    >
      <header className="space-y-1">
        <h2 className="text-lg font-serif text-ink dark:text-bright">
          NotDiamond advisor
        </h2>
        <p className="text-sm text-ink-soft dark:text-starlight font-serif italic">
          Third-party model router — shadow or advisory only. Live authority
          is forbidden until two consecutive Antiek-bench weeks ratify a
          cost-per-acceptable-answer win. Prompts would leave Antiek if a live
          adapter is ever enabled (privacy risk — operator-gated).
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {MODES.map((m) => {
          const active = mode === m;
          return (
            <button
              key={m}
              type="button"
              data-testid={`notdiamond-mode-${m}`}
              aria-pressed={active}
              onClick={() => setMode(m)}
              className={
                "rounded border px-2.5 py-1 font-mono text-[10px] uppercase " +
                (active
                  ? "border-sun bg-sun/20 text-ink dark:text-bright"
                  : "border-rule text-shadow-1 dark:border-charcoal-1 dark:text-moonlight")
              }
            >
              {m}
            </button>
          );
        })}
      </div>

      <div
        data-testid="notdiamond-mode-label"
        className="font-mono text-[11px] text-ink dark:text-bright"
      >
        {modeLabel(mode)}
      </div>
      <div
        data-testid="notdiamond-authority"
        className="font-mono text-[10px] uppercase tracking-wide text-shadow-1 dark:text-moonlight"
      >
        liveAdapter={String(liveAdapterEnabled)} · authority=
        {authority}
      </div>
    </section>
  );
}

export default NotDiamondShadowToggle;
