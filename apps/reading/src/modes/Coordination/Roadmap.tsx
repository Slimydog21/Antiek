import { LemonCard, LemonTable, LemonTag } from "../../components/lemon";
import type { LemonColumn } from "../../components/lemon";

/**
 * Roadmap — read-only view over the five specs' sprint rosters + SPR-01's
 * dependency DAG (SPR-05 M3).
 *
 * Renders the reconciled 45-sprint count (DRW 10 + Read 9 + Write 9 + Speak 9 +
 * unified 8; shell's 6 superseded), the DRW critical path (drw:1 → drw:3 →
 * drw:10) made explicit, what's unblocked-now (derived from dependency state,
 * not hand-set), and the substrate-execution layer beneath the products.
 *
 * Presentational: renders the data the parent fetched from
 * GET /coordination/roadmap. It authors no roster and writes no state.
 */

export interface SprintView {
  spec: string;
  spec_label: string;
  sprint: number;
  slug: string;
  node_id: string;
  status: string;
  on_critical_path: boolean;
  blocked_on: string[];
  unblocked: boolean;
}

export interface RosterView {
  spec: string;
  label: string;
  directory: string;
  count: number;
  sprints: SprintView[];
}

export interface SubstrateLayerView {
  name: string;
  owner: string;
  status: string;
}

export interface RoadmapView {
  total_sprints: number;
  superseded_count: number;
  superseded_note: string;
  reconciliation: string;
  critical_path: string[];
  rosters: RosterView[];
  unblocked_now: string[];
  substrate_layers: SubstrateLayerView[];
}

const sprintStatusColour = (s: string): "muted" | "sun" | "default" => {
  if (s === "live") return "muted";
  if (s === "provisional") return "sun";
  return "default";
};

export function Roadmap({ roadmap }: { roadmap: RoadmapView }) {
  return (
    <section className="space-y-5">
      <header className="space-y-1">
        <h2 className="text-lg font-serif text-ink dark:text-bright">
          Roadmap
        </h2>
        <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
          Every sprint across the five live specs + the SPR-01 dependency DAG.
          The count is summed from the real roster files, not trusted from
          prose.
        </p>
      </header>

      {/* Reconciliation banner — the count, summed out loud (rigor #1). */}
      <LemonCard colour="glacial" elevation="z1">
        <div className="p-4 space-y-1">
          <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
            Reconciled sprint count
          </p>
          <p className="text-sm font-mono text-ink dark:text-bright">
            {roadmap.reconciliation}
          </p>
        </div>
      </LemonCard>

      {/* DRW critical path — the load-bearing spine, explicit. */}
      <div className="space-y-2">
        <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
          DRW critical path
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          {roadmap.critical_path.map((node, i) => (
            <span key={node} className="flex items-center gap-2">
              <LemonTag colour="sun" dot>
                {node}
              </LemonTag>
              {i < roadmap.critical_path.length - 1 && (
                <span aria-hidden="true" className="text-shadow-1 dark:text-moonlight">
                  →
                </span>
              )}
            </span>
          ))}
        </div>
        <p className="text-xs text-ink-soft dark:text-starlight">
          Read, Write and Speak all rest on these three DRW primitives. A slip
          here slips everything downstream.
        </p>
      </div>

      {/* Per-spec rosters. */}
      <div className="space-y-4">
        {roadmap.rosters.map((r) => (
          <RosterTable key={r.spec} roster={r} criticalPath={roadmap.critical_path} />
        ))}
      </div>

      {/* Substrate-execution layer — the real foundation beneath the products. */}
      <SubstrateLayerSection layers={roadmap.substrate_layers} />
    </section>
  );
}

function RosterTable({
  roster,
  criticalPath,
}: {
  roster: RosterView;
  criticalPath: string[];
}) {
  const crit = new Set(criticalPath);
  const columns: LemonColumn<SprintView>[] = [
    {
      key: "sprint",
      header: "Sprint",
      width: "12%",
      render: (s) => (
        <span className="font-mono text-xs text-ink dark:text-bright">
          SPR-{String(s.sprint).padStart(2, "0")}
        </span>
      ),
    },
    {
      key: "slug",
      header: "Deliverable",
      render: (s) => (
        <span className="flex items-center gap-2">
          {crit.has(s.node_id) && (
            <LemonTag colour="sun" dot>
              critical path
            </LemonTag>
          )}
          <span className="text-sm text-ink dark:text-bright">
            {s.slug.replace(/-/g, " ")}
          </span>
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      width: "16%",
      render: (s) =>
        s.status === "unknown" ? (
          <span className="text-xs italic text-shadow-1 dark:text-moonlight">
            (product-owned)
          </span>
        ) : (
          <LemonTag colour={sprintStatusColour(s.status)}>{s.status}</LemonTag>
        ),
    },
    {
      key: "blocked",
      header: "Unblocked / waiting on",
      width: "30%",
      render: (s) =>
        s.unblocked ? (
          <LemonTag colour="muted" dot>
            unblocked
          </LemonTag>
        ) : (
          <span className="text-xs font-mono text-shadow-2 dark:text-moonlight">
            waits on {s.blocked_on.join(", ")}
          </span>
        ),
    },
  ];

  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <h3 className="text-base font-serif text-ink dark:text-bright">
          {roster.label}
        </h3>
        <span className="text-xs font-mono text-shadow-1 dark:text-moonlight">
          {roster.count} sprints
        </span>
      </div>
      <LemonTable<SprintView>
        rows={roster.sprints}
        columns={columns}
        rowKey={(s) => s.node_id}
        dense
        emptyState={
          <span className="text-xs italic text-shadow-1 dark:text-moonlight">
            No sprint files found for {roster.directory}/.
          </span>
        }
      />
    </div>
  );
}

function SubstrateLayerSection({ layers }: { layers: SubstrateLayerView[] }) {
  if (layers.length === 0) return null;
  return (
    <div className="space-y-2">
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        Substrate-execution layer (the foundation beneath the four workflows)
      </p>
      <LemonCard elevation="z1">
        <ul className="divide-y divide-rule dark:divide-charcoal-1">
          {layers.map((l) => (
            <li key={l.name} className="px-4 py-2.5 space-y-0.5">
              <p className="text-sm font-serif text-ink dark:text-bright">
                {l.name}
              </p>
              <p className="text-xs font-mono text-shadow-2 dark:text-moonlight">
                {l.owner} · {l.status}
              </p>
            </li>
          ))}
        </ul>
      </LemonCard>
    </div>
  );
}
