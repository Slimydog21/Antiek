import { LemonCard, LemonTag } from "../../components/lemon";

/**
 * GateLedger — read-only view over docs/operator_gate_actions.md (SPR-05 M3).
 *
 * The eight binding gates presented ONCE as shared cross-workflow gates, each
 * with a per-product IMPACT column (which of Research/Read/Write/Speak it blocks
 * and how). No per-product gate duplication — this is the single canonical view.
 *
 * Presentational: it renders the data the parent fetched from
 * GET /coordination/gates. There is no control here that writes a gate's state;
 * gate state changes only in the operator's source markdown.
 */

export type CoordProduct = "research" | "read" | "write" | "speak";

export interface GateImpactView {
  product: CoordProduct;
  effect: string;
}

export interface GateView {
  gate_id: string;
  title: string;
  status: "closed" | "open" | "calendar" | "data_bound";
  status_raw: string;
  is_provisional: boolean;
  owner: string | null;
  blocks: string | null;
  closure_record: string | null;
  impacts: GateImpactView[];
}

// Coarse status → Lemon tag colour. Closed = muted (done); open = danger
// (blocking); calendar/data-bound = sun (waiting, not actionable today).
const statusColour: Record<GateView["status"], "muted" | "danger" | "sun"> = {
  closed: "muted",
  open: "danger",
  calendar: "sun",
  data_bound: "sun",
};

const statusLabel: Record<GateView["status"], string> = {
  closed: "closed",
  open: "open",
  calendar: "calendar",
  data_bound: "data-bound",
};

const productLabel: Record<CoordProduct, string> = {
  research: "Research",
  read: "Read",
  write: "Write",
  speak: "Speak",
};

export function GateLedger({
  gates,
  sourcePath,
}: {
  gates: GateView[];
  sourcePath: string;
}) {
  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-lg font-serif text-ink dark:text-bright">
          Gate ledger
        </h2>
        <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
          The eight binding gates blocking activation, presented once as shared
          cross-workflow gates. This is a read-only view over{" "}
          <code className="font-mono text-xs">{sourcePath}</code> — the
          canonical source. Gate state changes only in that file; nothing here
          can write it.
        </p>
      </header>

      <div className="space-y-3">
        {gates.map((g) => (
          <GateRow key={g.gate_id} gate={g} />
        ))}
      </div>
    </section>
  );
}

function GateRow({ gate }: { gate: GateView }) {
  const blocking = gate.status !== "closed" && gate.impacts.length > 0;
  return (
    <LemonCard elevation="z1">
      <div className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-0.5">
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-semibold text-ink dark:text-bright">
                {gate.gate_id}
              </span>
              <LemonTag colour={statusColour[gate.status]} dot>
                {statusLabel[gate.status]}
                {gate.is_provisional ? " (provisional)" : ""}
              </LemonTag>
            </div>
            <p className="text-sm font-serif text-ink dark:text-bright">
              {gate.title}
            </p>
            <p className="text-xs font-mono text-shadow-2 dark:text-moonlight">
              {gate.status_raw}
            </p>
          </div>
          {gate.closure_record && (
            <a
              href={`https://github.com/Slimydog21/antiek/blob/main/${gate.closure_record}`}
              target="_blank"
              rel="noreferrer"
              className="shrink-0 text-xs font-mono text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright underline"
            >
              closure record →
            </a>
          )}
        </div>

        {gate.owner && (
          <p className="text-xs text-ink-soft dark:text-starlight">
            <span className="font-semibold">Owner:</span> {gate.owner}
          </p>
        )}

        {/* Per-product impact column — the reason one canonical ledger wins
            over four per-product descriptions. */}
        {gate.impacts.length > 0 ? (
          <div className="space-y-1.5 border-t border-rule dark:border-charcoal-1 pt-2.5">
            <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
              {blocking ? "Blocks per workflow" : "Per-workflow impact"}
            </p>
            <ul className="space-y-1">
              {gate.impacts.map((im) => (
                <li
                  key={im.product}
                  className="flex items-start gap-2 text-xs"
                >
                  <span className="shrink-0 mt-0.5">
                    <LemonTag colour="default">
                      {productLabel[im.product]}
                    </LemonTag>
                  </span>
                  <span className="text-ink-soft dark:text-starlight leading-relaxed">
                    {im.effect}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-xs italic text-shadow-1 dark:text-moonlight border-t border-rule dark:border-charcoal-1 pt-2.5">
            Infrastructure verdict — no per-product block.
          </p>
        )}
      </div>
    </LemonCard>
  );
}
