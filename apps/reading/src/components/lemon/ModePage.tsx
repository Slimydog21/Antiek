import type { ReactNode } from "react";

/**
 * ModePage — the shared mode page shell (ui-audit Q5, adjudication D5).
 *
 * One page background app-wide: the page ramp `bg-ice-2 dark:bg-space-2`
 * (Biography/Settings' pattern), never the card tones — cards keep
 * `ice-0`/`charcoal-2` so they lift off the page. The root is `h-full`
 * with an inner scroll main (the Q12/Q17 idiom: the mode fills AppShell's
 * `flex-1 min-h-0` slot and scrolls itself, never `h-screen`).
 *
 * Width tiers replace the four divergent page rhythms the audit found
 * (`px-8 py-10 max-w-3xl/4xl` vs `px-6 py-12 max-w-2xl` vs …):
 *
 *   sm  max-w-2xl  prose / landing (Biography, Speak)
 *   md  max-w-3xl  forms & operator detail (Settings, Billing)
 *   lg  max-w-4xl  data reports (Backtest, Coordination)
 *   xl  max-w-5xl  dense data (Signals, PayoutsAudit)
 *
 * `title`/`lede` render the standard header (serif h1 at the tested 24px
 * ceiling + muted lede). Pass `header` instead when a surface needs a
 * bespoke header (mascot art, tab lists, extra meta lines) — it replaces
 * the standard one verbatim.
 *
 * Not for canvas/workstation layouts (Reading, Notebook, PanelHost modes)
 * that own their own multi-pane roots — those keep their shells.
 */
type Width = "sm" | "md" | "lg" | "xl";

const widths: Record<Width, string> = {
  sm: "max-w-2xl",
  md: "max-w-3xl",
  lg: "max-w-4xl",
  xl: "max-w-5xl",
};

export type ModePageProps = {
  /** Standard header: serif h1 (text-2xl, the chrome ceiling). */
  title?: ReactNode;
  /** Standard header: muted lede under the title. */
  lede?: ReactNode;
  /** Bespoke header — replaces the title/lede header entirely. */
  header?: ReactNode;
  width?: Width;
  /** Extra classes on the scroll root. */
  className?: string;
  /** Extra classes on the width-tiered content column. */
  contentClassName?: string;
  children: ReactNode;
};

export function ModePage({
  title,
  lede,
  header,
  width = "md",
  className = "",
  contentClassName = "",
  children,
}: ModePageProps) {
  return (
    <div
      className={`h-full overflow-y-auto bg-ice-2 dark:bg-space-2 ${className}`}
    >
      <main
        className={
          `mx-auto ${widths[width]} px-6 py-8 space-y-6 ${contentClassName}`
        }
      >
        {header ??
          (title != null && (
            <header className="space-y-2">
              <h1 className="text-2xl font-serif text-ink dark:text-bright">
                {title}
              </h1>
              {lede != null && (
                <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
                  {lede}
                </p>
              )}
            </header>
          ))}
        {children}
      </main>
    </div>
  );
}

export default ModePage;
