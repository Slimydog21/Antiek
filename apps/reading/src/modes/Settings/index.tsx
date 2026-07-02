import { useViewportTier } from "../../workspace/useViewportTier";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonTag } from "../../components/lemon";
import { useProviderKeys } from "../../hooks/useProviderKeys";

/**
 * Operator Settings.
 *
 * Honest operator readout for the settings that already have substrate
 * signals: workspace environment, dispatch provider activation, and
 * the canonical routes where policy/economics controls live.
 */
export default function Settings() {
  const tier = useViewportTier();
  const providerKeys = useProviderKeys();
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
            Live workspace and activation readout. Mutating controls
            stay on their canonical operator surfaces; this page tells
            you what is active before you launch agentic work.
          </p>
        </header>

        <LemonCard title="Workspace environment" elevation="z1">
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

        <LemonCard title="Agentic activation" elevation="z1">
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-serif text-ink dark:text-bright">
                  Model provider registry
                </p>
                <p className="text-xs text-ink-soft dark:text-starlight">
                  Mirrors <code className="font-mono">/health.registered_providers</code>;
                  no secret values are exposed here.
                </p>
              </div>
              <ProviderStatusTag status={providerKeys.status} />
            </div>

            {providerKeys.status === "ready" ? (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-2">
                  {providerKeys.providers.map((provider) => (
                    <LemonTag key={provider} colour="aurora" dot>
                      {provider}
                    </LemonTag>
                  ))}
                </div>
                <p className="text-sm text-shadow-1 dark:text-moonlight">
                  Provider keys make live Dialogue and research spin-out sessions eligible
                  for the Read activation walk; closure still requires the
                  dogfood log in <code className="font-mono">specs/activation/golden-path.md</code>.
                </p>
              </div>
            ) : (
              <p className="text-sm text-shadow-1 dark:text-moonlight">
                {providerKeys.status === "loading"
                  ? "Checking provider registry..."
                  : providerKeys.status === "error"
                    ? "Could not read /health; agentic paths should be treated as unavailable."
                    : "No model providers are registered, so agentic research and generation stay inert until activation SPR-03 provider-key setup."}
              </p>
            )}

            <button
              type="button"
              onClick={providerKeys.refresh}
              className="text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 px-2 py-1 rounded hover:bg-ice-1 dark:hover:bg-charcoal-2"
            >
              Refresh provider status
            </button>
          </div>
        </LemonCard>

        <LemonCard title="Control surfaces" elevation="z1" colour="glacial">
          <div className="p-4 grid gap-2 sm:grid-cols-2">
            <ControlLink href="/trust" title="Trust Center" body="Published privacy, deletion, and training commitments" />
            <ControlLink href="/privacy" title="Privacy dashboard" body="Privacy budgets and deletion controls" />
            <ControlLink href="/coordination/cost-consent" title="Cost + consent" body="Unified spend, escrow, and consent status" />
            <ControlLink href="/operator" title="Operator dashboard" body="Operations snapshot" />
          </div>
        </LemonCard>
      </div>
    </div>
  );
}

function ProviderStatusTag({ status }: { status: ReturnType<typeof useProviderKeys>["status"] }) {
  if (status === "ready") return <LemonTag colour="aurora">ready</LemonTag>;
  if (status === "loading") return <LemonTag colour="muted">checking</LemonTag>;
  if (status === "error") return <LemonTag colour="danger">unreachable</LemonTag>;
  return <LemonTag colour="sun">not configured</LemonTag>;
}

function ControlLink({
  href,
  title,
  body,
}: {
  href: string;
  title: string;
  body: string;
}) {
  return (
    <a
      href={href}
      className="block rounded-md border border-rule dark:border-charcoal-1 px-3 py-2 hover:bg-ice-1 dark:hover:bg-charcoal-2 transition-colors"
    >
      <span className="block text-sm font-serif text-ink dark:text-bright">
        {title}
      </span>
      <span className="block text-[11px] font-mono text-shadow-1 dark:text-moonlight">
        {href}
      </span>
      <span className="block text-xs text-ink-soft dark:text-starlight mt-1">
        {body}
      </span>
    </a>
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
