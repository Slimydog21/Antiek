/**
 * ModelPicker — reusable per-action model-driver dropdown (BYOT directive).
 *
 * Renders the composer projection's ranked candidates (task-specific) as a
 * Lemon-styled picker with honest pricing/quality badges. The choice is
 * ADVISORY: the server re-validates budget + eligibility at execution
 * (byok route-authority), so this component never claims a binding dispatch.
 *
 * Honesty rules (load-bearing, mirror ModelDecisionBar):
 *   * Unknown pricing renders "unknown", never "$0.00".
 *   * quality_basis measured vs static_prior is a visible badge.
 *   * Loading and error are explicit states; error carries the reason.
 *   * Empty candidate list renders a named empty state, not a blank menu.
 */

import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";

import type { ComposerCandidateView } from "../api/composerProjection";

export interface ModelPickerProps {
  candidates: ComposerCandidateView[] | null;
  selected: { provider: string; model: string } | null;
  onSelect: (candidate: ComposerCandidateView) => void;
  loading?: boolean;
  error?: string | null;
  /** Label for the picker; default "Model driver". */
  label?: string;
  /** Honest advisory note under the picker. */
  note?: string;
  disabled?: boolean;
}

function formatUsd(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "unknown";
  return `$${value.toFixed(2)}`;
}

function pricingLabel(c: ComposerCandidateView): string {
  if (c.pricing_status === "unknown") return "pricing unknown";
  return `≈${formatUsd(c.estimated_usd_low)}–${formatUsd(c.estimated_usd_high)}`;
}

export default function ModelPicker({
  candidates,
  selected,
  onSelect,
  loading = false,
  error = null,
  label = "Model driver",
  note = "Advisory — the server re-validates budget and eligibility at execution.",
  disabled = false,
}: ModelPickerProps) {
  const listboxId = useId();
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const selectedView = useMemo(
    () => candidates?.find((c) => c.provider === selected?.provider && c.model === selected?.model) ?? null,
    [candidates, selected],
  );

  function toggle() {
    if (disabled) return;
    setOpen((v) => !v);
  }

  function choose(c: ComposerCandidateView) {
    onSelect(c);
    setOpen(false);
    buttonRef.current?.focus();
  }

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    if (!candidates?.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActiveIndex((i) => (i + 1) % candidates.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setActiveIndex((i) => (i - 1 + candidates.length) % candidates.length);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (open) choose(candidates[activeIndex]);
      else setOpen(true);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-shadow-1 dark:text-moonlight" role="status">
        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-sun" />
        Loading model drivers…
      </div>
    );
  }

  if (error) {
    return (
      <p className="rounded border border-emperor/40 bg-emperor/5 px-3 py-2 text-[11px] text-emperor" role="alert">
        Model drivers unavailable · {error}
      </p>
    );
  }

  if (!candidates || candidates.length === 0) {
    return (
      <p className="rounded border border-sun/40 bg-ice-0 px-3 py-2 text-[11px] text-shadow-1 dark:bg-charcoal-2 dark:text-moonlight">
        No model drivers available for this action.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-semibold text-ink dark:text-bright">{label}</span>
      <div className="relative inline-block w-full max-w-sm">
        <button
          ref={buttonRef}
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listboxId}
          disabled={disabled}
          onClick={toggle}
          onKeyDown={onKeyDown}
          className="flex w-full items-center justify-between gap-2 rounded-md border-2 border-sun bg-ice-0 px-3 py-2 text-left text-sm text-ink shadow-[3px_3px_0_rgba(0,0,0,0.12)] transition-transform hover:-translate-y-px active:translate-y-0 active:shadow-none disabled:opacity-60 dark:bg-charcoal-2 dark:text-bright"
        >
          <span className="truncate">
            {selectedView
              ? `${selectedView.provider} / ${selectedView.model}`
              : "Auto (best available)"}
          </span>
          <span className="flex items-center gap-2">
            {selectedView && (
              <span className="text-[10px] text-shadow-1 dark:text-moonlight">
                {pricingLabel(selectedView)}
              </span>
            )}
            <span aria-hidden className="text-[10px]">{open ? "▲" : "▼"}</span>
          </span>
        </button>
        {open && (
          <ul
            id={listboxId}
            role="listbox"
            aria-label={label}
            className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border-2 border-sun bg-ice-0 py-1 shadow-[4px_4px_0_rgba(0,0,0,0.15)] dark:bg-charcoal-1"
          >
            {candidates.map((c, i) => {
              const isActive = i === activeIndex;
              const isSelected = selected?.provider === c.provider && selected?.model === c.model;
              return (
                <li key={`${c.provider}:${c.model}`}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => choose(c)}
                    onMouseEnter={() => setActiveIndex(i)}
                    className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs ${
                      isActive ? "bg-sun/20 dark:bg-sun/10" : ""
                    }`}
                  >
                    <span className="truncate">
                      <span className="font-semibold text-ink dark:text-bright">{c.provider}</span>
                      <span className="text-shadow-1 dark:text-moonlight"> / {c.model}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1.5">
                      {c.quality_basis === "measured" ? (
                        <span className="rounded bg-aurora/15 px-1 text-[9px] text-aurora">measured</span>
                      ) : (
                        <span className="rounded bg-moonlight/15 px-1 text-[9px] text-shadow-1 dark:text-moonlight">prior</span>
                      )}
                      <span className="text-[10px] text-shadow-1 dark:text-moonlight">
                        {c.eligible ? pricingLabel(c) : "ineligible"}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <p className="text-[10px] text-shadow-1/80 dark:text-moonlight/80">{note}</p>
    </div>
  );
}
