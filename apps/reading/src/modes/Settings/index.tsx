import { useViewportTier } from "../../workspace/useViewportTier";
import LemonCard from "../../components/lemon/LemonCard";

/**
 * Operator Settings — stub page.
 *
 * S4's NavRail footer lists Settings per the master-spec layout
 * table. The full settings surface (UI flavor, default panel
 * starters, keyboard map customization, dispatch-tier overrides,
 * data privacy controls) lands in a separate sprint that's not
 * part of the redesign programme. This stub exists so the rail
 * icon resolves to a real page rather than a 404.
 *
 * What lives here today: a readout of the workspace's current
 * viewport tier, the active OS theme, and a pointer to where the
 * full settings surface will land.
 */
export default function Settings() {
  const tier = useViewportTier();
  const isDark =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  return (
    <div className="h-full overflow-y-auto bg-ice-2 dark:bg-space-2">
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <header>
          <h1 className="text-2xl font-serif text-ink dark:text-bright">
            Operator settings
          </h1>
          <p className="text-sm text-ink-soft dark:text-starlight font-serif italic mt-1">
            Settings surface stub — the full controls land in a
            follow-up sprint. For now this page shows what the
            workspace currently detects.
          </p>
        </header>

        <LemonCard title="Environment" elevation="z1">
          <div className="p-4 space-y-3 font-mono text-[13px]">
            <Row label="Viewport tier" value={tier} />
            <Row label="OS theme" value={isDark ? "dark" : "light"} />
            <Row
              label="Reduce motion"
              value={reduceMotion ? "yes" : "no"}
            />
            <Row
              label="UI version"
              value={
                (import.meta.env.VITE_ANTIEK_UI as string | undefined) ??
                "v2"
              }
            />
          </div>
        </LemonCard>

        <LemonCard title="Coming later" elevation="z1" colour="glacial">
          <ul className="p-4 space-y-2 text-sm text-ink dark:text-bright list-disc list-inside">
            <li>Default panel starters per route</li>
            <li>Keyboard map customisation</li>
            <li>Dispatch-tier overrides + budget caps</li>
            <li>Data-privacy + sharing controls</li>
            <li>Workspace layout export / import</li>
          </ul>
        </LemonCard>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-ink-soft dark:text-starlight uppercase tracking-wider text-[11px]">
        {label}
      </span>
      <span className="text-ink dark:text-bright">{value}</span>
    </div>
  );
}
