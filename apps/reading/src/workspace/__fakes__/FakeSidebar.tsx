/**
 * S3 demo panel — fake InvestigationSidebar. Pure presentational.
 * Replaces nothing in production; used only by the Workspace/Demo
 * Storybook story to prove the layout shell holds up.
 */
export function FakeSidebar() {
  const items = [
    { id: "nvda", title: "NVDA Q4 risk model", status: "running" },
    { id: "gaming", title: "Web gaming 2026", status: "done" },
    { id: "kalshi", title: "Kalshi liquidity gate", status: "done" },
    { id: "rlm", title: "Antiek-RLM round-3", status: "failed" },
    { id: "rosebud", title: "Rosebud diligence", status: "running" },
  ];
  const dot: Record<string, string> = {
    running: "bg-sun",
    done: "bg-aurora",
    failed: "bg-emperor",
  };
  return (
    <div className="p-3 space-y-1 text-[13px]">
      <div className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight pb-2 px-2">
        Recent
      </div>
      {items.map((it) => (
        <button
          key={it.id}
          type="button"
          className="w-full flex items-center gap-2 px-2 py-1.5 rounded hover:bg-sun/20 dark:hover:bg-sun/10 text-left text-ink dark:text-bright"
        >
          <span className={`w-1.5 h-1.5 rounded-full ${dot[it.status]} shrink-0`} aria-hidden />
          <span className="truncate">{it.title}</span>
        </button>
      ))}
    </div>
  );
}

export default FakeSidebar;
