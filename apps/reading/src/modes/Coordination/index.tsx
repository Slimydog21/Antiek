import { useCallback, useEffect, useRef, useState } from "react";

import Werner from "../../brand/Werner";
import environment from "../../brand/werner/coordination/coordination_gatehouse_atlas_environment_v1.webp";
import { apiFetch } from "../../lib/api";
import "./coordination-gatehouse-atlas.css";

/**
 * Coordination Gatehouse Atlas — the distinctive Antarctic gatehouse view
 * of canonical operator gates and the dependency-derived cross-product roadmap.
 *
 * Truth contract:
 *  - Read-only: never mutates a gate, sprint, roster, payout, or training config.
 *  - Gate and sprint counts are payload-derived. No prose hardcodes a count.
 *  - status_raw preserves nuance; coarse status controls presentation only.
 *  - Empty impacts = "no reviewed per-product mapping", never "no product block".
 *  - Unblocked = dependency-unblocked, not done/approved/funded/ready-to-ship.
 *  - No raw network, HTTP, parser, or validation error reaches the DOM.
 *  - No freshness/completeness timestamp invented; neither endpoint supplies one.
 */

// ── Wire types ────────────────────────────────────────────────────────

type CoordProduct = "research" | "read" | "write" | "speak";

interface GateImpactView {
  product: CoordProduct;
  effect: string;
}

type GateStatus = "closed" | "open" | "calendar" | "data_bound";

interface GateView {
  gate_id: string;
  title: string;
  status: GateStatus;
  status_raw: string;
  is_provisional: boolean;
  owner: string | null;
  blocks: string | null;
  closure_record: string | null;
  impacts: GateImpactView[];
}

interface GatesResponse {
  source_path: string;
  gates: GateView[];
}

interface SprintView {
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

interface RosterView {
  spec: string;
  label: string;
  directory: string;
  count: number;
  sprints: SprintView[];
}

interface SubstrateLayerView {
  name: string;
  owner: string;
  status: string;
}

interface RoadmapView {
  total_sprints: number;
  superseded_count: number;
  superseded_note: string;
  reconciliation: string;
  critical_path: string[];
  rosters: RosterView[];
  unblocked_now: string[];
  substrate_layers: SubstrateLayerView[];
}

// ── Validation helpers ────────────────────────────────────────────────

const VALID_STATUSES: ReadonlySet<string> = new Set([
  "closed",
  "open",
  "calendar",
  "data_bound",
]);
const VALID_PRODUCTS: ReadonlySet<string> = new Set([
  "research",
  "read",
  "write",
  "speak",
]);
const VALID_SPRINT_STATUSES: ReadonlySet<string> = new Set([
  "live",
  "provisional",
  "planned",
  "unknown",
]);
const GATE_ID_RE = /^G[1-9]\d*$/;

const isSafeInt = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const isNonEmptyString = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;

function validateGateImpact(v: unknown): v is GateImpactView {
  if (!v || typeof v !== "object") return false;
  const r = v as Record<string, unknown>;
  return (
    typeof r.product === "string" &&
    VALID_PRODUCTS.has(r.product) &&
    isNonEmptyString(r.effect)
  );
}

function validateGate(v: unknown): v is GateView {
  if (!v || typeof v !== "object") return false;
  const r = v as Record<string, unknown>;
  if (
    !isNonEmptyString(r.gate_id) ||
    !GATE_ID_RE.test(r.gate_id) ||
    !isNonEmptyString(r.title) ||
    typeof r.status !== "string" ||
    !VALID_STATUSES.has(r.status) ||
    typeof r.status_raw !== "string" ||
    typeof r.is_provisional !== "boolean"
  )
    return false;
  if (r.owner !== null && typeof r.owner !== "string") return false;
  if (r.blocks !== null && typeof r.blocks !== "string") return false;
  if (r.closure_record !== null && typeof r.closure_record !== "string")
    return false;
  if (!Array.isArray(r.impacts)) return false;
  const impactedProducts = new Set<string>();
  for (const imp of r.impacts) {
    if (!validateGateImpact(imp)) return false;
    if (impactedProducts.has(imp.product)) return false;
    impactedProducts.add(imp.product);
  }
  return true;
}

function validateGatesResponse(v: unknown): v is GatesResponse {
  if (!v || typeof v !== "object") return false;
  const r = v as Record<string, unknown>;
  if (!isNonEmptyString(r.source_path) || !Array.isArray(r.gates)) return false;
  const ids = new Set<string>();
  for (const g of r.gates) {
    if (!validateGate(g)) return false;
    if (ids.has(g.gate_id)) return false;
    ids.add(g.gate_id);
  }
  return true;
}

function validateSprint(v: unknown): v is SprintView {
  if (!v || typeof v !== "object") return false;
  const r = v as Record<string, unknown>;
  if (
    !isNonEmptyString(r.spec) ||
    !isNonEmptyString(r.spec_label) ||
    !isSafeInt(r.sprint) ||
    !isNonEmptyString(r.slug) ||
    !isNonEmptyString(r.node_id) ||
    typeof r.status !== "string" ||
    !VALID_SPRINT_STATUSES.has(r.status) ||
    typeof r.on_critical_path !== "boolean" ||
    !Array.isArray(r.blocked_on) ||
    typeof r.unblocked !== "boolean"
  )
    return false;
  for (const dep of r.blocked_on) {
    if (typeof dep !== "string") return false;
  }
  // unblocked semantics: if unblocked=true, blocked_on must be empty
  // (dependency-unblocked means no blockers)
  if (r.unblocked && (r.blocked_on as string[]).length > 0) return false;
  // if blocked_on has entries, unblocked must be false
  if (!r.unblocked && (r.blocked_on as string[]).length === 0) return false;
  return true;
}

function validateRoster(v: unknown): v is RosterView {
  if (!v || typeof v !== "object") return false;
  const r = v as Record<string, unknown>;
  if (
    !isNonEmptyString(r.spec) ||
    !isNonEmptyString(r.label) ||
    !isNonEmptyString(r.directory) ||
    !isSafeInt(r.count) ||
    !Array.isArray(r.sprints)
  )
    return false;
  // roster count must equal sprints length
  if (r.count !== (r.sprints as unknown[]).length) return false;
  for (const s of r.sprints) {
    if (!validateSprint(s)) return false;
  }
  return true;
}

function validateSubstrateLayer(v: unknown): v is SubstrateLayerView {
  if (!v || typeof v !== "object") return false;
  const r = v as Record<string, unknown>;
  return isNonEmptyString(r.name) && isNonEmptyString(r.owner) && isNonEmptyString(r.status);
}

function validateRoadmap(v: unknown): v is RoadmapView {
  if (!v || typeof v !== "object") return false;
  const r = v as Record<string, unknown>;
  if (
    !isSafeInt(r.total_sprints) ||
    !isSafeInt(r.superseded_count) ||
    isNonEmptyString(r.superseded_note) === false &&
    typeof r.superseded_note !== "string" ||
    !isNonEmptyString(r.reconciliation) ||
    !Array.isArray(r.critical_path) ||
    !Array.isArray(r.rosters) ||
    !Array.isArray(r.unblocked_now) ||
    !Array.isArray(r.substrate_layers)
  )
    return false;
  // Validate critical_path entries are strings
  for (const cp of r.critical_path) {
    if (typeof cp !== "string") return false;
  }
  // Validate total_sprints = sum of all roster counts
  let sum = 0;
  const allNodeIds = new Set<string>();
  const rosterSpecs = new Set<string>();
  for (const roster of r.rosters) {
    if (!validateRoster(roster)) return false;
    if (rosterSpecs.has(roster.spec)) return false;
    rosterSpecs.add(roster.spec);
    sum += roster.count;
    for (const sprint of roster.sprints) {
      if (
        sprint.spec !== roster.spec ||
        sprint.spec_label !== roster.label ||
        sprint.sprint < 1 ||
        sprint.node_id !== `${roster.spec}:${sprint.sprint}`
      )
        return false;
      if (allNodeIds.has(sprint.node_id)) return false;
      allNodeIds.add(sprint.node_id);
    }
  }
  if (r.total_sprints !== sum) return false;
  // Validate unblocked_now references unique, dependency-unblocked nodes.
  const unblockedRefs = new Set<string>();
  for (const u of r.unblocked_now) {
    if (typeof u !== "string" || unblockedRefs.has(u)) return false;
    unblockedRefs.add(u);
  }
  // Validate substrate_layers
  for (const l of r.substrate_layers) {
    if (!validateSubstrateLayer(l)) return false;
  }
  // Validate critical_path entries exist as node_ids in rosters
  const criticalRefs = new Set<string>();
  for (const cp of r.critical_path) {
    if (!allNodeIds.has(cp) || criticalRefs.has(cp)) return false;
    criticalRefs.add(cp);
  }
  // Validate dependency references: each blocked_on entry exists as a node_id
  for (const roster of r.rosters) {
    for (const s of roster.sprints) {
      if (s.on_critical_path !== criticalRefs.has(s.node_id)) return false;
      for (const dep of s.blocked_on) {
        if (!allNodeIds.has(dep)) return false;
      }
      if (unblockedRefs.has(s.node_id) !== s.unblocked) return false;
    }
  }
  for (const node of unblockedRefs) {
    if (!allNodeIds.has(node)) return false;
  }
  return true;
}

// ── Safe copy (validation failure messages) ───────────────────────────

const SAFE_COPY = {
  gatesUnavailable:
    "The current gate view could not be loaded. Retry to read the canonical register again.",
  roadmapUnavailable:
    "The current roadmap view could not be loaded. Retry to read sprint rosters and dependency state again.",
  gatesMalformed:
    "Gate data arrived in an unexpected format and cannot be displayed safely. Retry to attempt a clean load.",
  roadmapMalformed:
    "Roadmap data arrived in an unexpected format and cannot be displayed safely. Retry to attempt a clean load.",
} as const;

// ── Gate Wall sorting ─────────────────────────────────────────────────

const STATUS_ORDER: Record<GateStatus, number> = {
  open: 0,
  calendar: 1,
  data_bound: 2,
  closed: 3,
};

function sortGates(gates: GateView[]): GateView[] {
  return [...gates].sort((a, b) => {
    const statusDiff = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
    if (statusDiff !== 0) return statusDiff;
    // Sort by numeric ID within each status group
    const numA = parseInt(a.gate_id.replace(/\D/g, ""), 10) || 0;
    const numB = parseInt(b.gate_id.replace(/\D/g, ""), 10) || 0;
    return numA - numB;
  });
}

// ── Display helpers ───────────────────────────────────────────────────

const PRODUCT_LABEL: Record<CoordProduct, string> = {
  research: "Research",
  read: "Read",
  write: "Write",
  speak: "Speak",
};

const STATUS_DISPLAY: Record<GateStatus, { label: string; dotClass: string; tagClass: string }> = {
  open: { label: "open", dotClass: "cga-status-dot--open", tagClass: "cga-status-tag--open" },
  closed: { label: "closed", dotClass: "cga-status-dot--closed", tagClass: "cga-status-tag--closed" },
  calendar: { label: "calendar", dotClass: "cga-status-dot--calendar", tagClass: "cga-status-tag--calendar" },
  data_bound: { label: "data-bound", dotClass: "cga-status-dot--data_bound", tagClass: "cga-status-tag--data_bound" },
};

function sprintStatusClass(s: string): string {
  if (s === "live") return "cga-sprint-status--live";
  if (s === "provisional") return "cga-sprint-status--provisional";
  return "cga-sprint-status--default";
}

// ── Derived counts ────────────────────────────────────────────────────

function deriveStatusTally(gates: GateView[]): Record<GateStatus, number> {
  const tally: Record<GateStatus, number> = {
    open: 0,
    closed: 0,
    calendar: 0,
    data_bound: 0,
  };
  for (const g of gates) {
    tally[g.status]++;
  }
  return tally;
}

// ── Components ────────────────────────────────────────────────────────

function GateWallSection({ gates }: { gates: GateView[] }) {
  const sorted = sortGates(gates);
  return (
    <div className="cga-gate-wall">
      {sorted.map((g) => (
        <GateCard key={g.gate_id} gate={g} />
      ))}
    </div>
  );
}

function GateCard({ gate }: { gate: GateView }) {
  const statusInfo = STATUS_DISPLAY[gate.status];
  const hasImpacts = gate.impacts.length > 0;
  const isBlocking = gate.status !== "closed" && hasImpacts;

  return (
    <article className="cga-gate-card" aria-labelledby={`gate-${gate.gate_id}`}>
      <div className="cga-gate-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="cga-gate-id" id={`gate-${gate.gate_id}`}>
              {gate.gate_id}
            </span>
            <span className={`cga-status-tag ${statusInfo.tagClass}`}>
              <span className={`cga-status-dot ${statusInfo.dotClass}`} />
              {statusInfo.label}
              {gate.is_provisional ? " (provisional)" : ""}
            </span>
          </div>
          <p className="cga-gate-title">{gate.title}</p>
          <p className="cga-gate-raw">{gate.status_raw}</p>
        </div>
        {gate.closure_record && (
          <a
            href={`https://github.com/Slimydog21/antiek/blob/main/${gate.closure_record}`}
            target="_blank"
            rel="noreferrer"
            className="cga-closure-link"
          >
            closure record
          </a>
        )}
      </div>

      {gate.owner && (
        <p className="cga-gate-owner">
          <strong>Owner:</strong> {gate.owner}
        </p>
      )}

      {gate.blocks && (
        <p className="cga-gate-blocks">
          <strong>Blocks:</strong> {gate.blocks}
        </p>
      )}

      {hasImpacts ? (
        <div className="cga-gate-impacts">
          <p className="cga-gate-impacts-label">
            {isBlocking ? "Blocks per workflow" : "Per-workflow impact"}
          </p>
          {gate.impacts.map((im) => (
            <div key={im.product} className="cga-gate-impact">
              <span className="cga-gate-impact-tag">
                {PRODUCT_LABEL[im.product]}
              </span>
              <span className="cga-gate-impact-effect">{im.effect}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="cga-gate-no-impact">
          {gate.status === "closed"
            ? "Historical — no active per-product mapping."
            : "No reviewed per-product mapping."}
        </p>
      )}
    </article>
  );
}

function RouteAtlasSection({ roadmap }: { roadmap: RoadmapView }) {
  return (
    <div className="cga-route-atlas">
      {/* Reconciliation */}
      <div className="cga-reconciliation">
        <p className="cga-reconciliation-label">Reconciled sprint count</p>
        <p className="cga-reconciliation-value">{roadmap.reconciliation}</p>
      </div>

      {/* Critical path */}
      {roadmap.critical_path.length > 0 && (
        <div className="cga-critical-path">
          <p className="cga-critical-path-label">DRW critical path</p>
          <div className="cga-critical-path-chain">
            {roadmap.critical_path.map((node, i) => (
              <span key={node} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span className="cga-critical-node">{node}</span>
                {i < roadmap.critical_path.length - 1 && (
                  <span className="cga-critical-arrow" aria-hidden="true">
                    →
                  </span>
                )}
              </span>
            ))}
          </div>
          <p className="cga-critical-note">
            Read, Write and Speak all rest on these DRW primitives. A slip here
            slips everything downstream.
          </p>
        </div>
      )}

      {/* Rosters */}
      {roadmap.rosters.map((r) => (
        <RosterTable key={r.spec} roster={r} criticalPath={roadmap.critical_path} />
      ))}

      {/* Unblocked now */}
      {roadmap.unblocked_now.length > 0 && (
        <div className="cga-unblocked-now">
          <p className="cga-unblocked-now-label">Unblocked now</p>
          <ul className="cga-unblocked-now-list">
            {roadmap.unblocked_now.map((n) => (
              <li key={n} className="cga-unblocked-now-item">{n}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Substrate */}
      {roadmap.substrate_layers.length > 0 && (
        <div className="cga-substrate">
          <p className="cga-substrate-label">
            Substrate-execution layer (the foundation beneath the workflows)
          </p>
          <ul className="cga-substrate-list">
            {roadmap.substrate_layers.map((l) => (
              <li key={l.name} className="cga-substrate-item">
                <p className="cga-substrate-name">{l.name}</p>
                <p className="cga-substrate-meta">
                  {l.owner} · {l.status}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function RosterTable({
  roster,
  criticalPath,
}: {
  roster: RosterView;
  criticalPath: string[];
}) {
  const critSet = new Set(criticalPath);
  return (
    <div className="cga-roster">
      <div className="cga-roster-header">
        <h3 className="cga-roster-title">{roster.label}</h3>
        <span className="cga-roster-count">{roster.count} sprints</span>
      </div>
      <table className="cga-roster-table">
        <thead>
          <tr>
            <th style={{ width: "12%" }}>Sprint</th>
            <th>Deliverable</th>
            <th style={{ width: "16%" }}>Status</th>
            <th style={{ width: "30%" }}>Unblocked / waiting on</th>
          </tr>
        </thead>
        <tbody>
          {roster.sprints.map((s) => (
            <tr key={s.node_id}>
              <td data-label="Sprint">
                <span className="cga-sprint-id">
                  SPR-{String(s.sprint).padStart(2, "0")}
                </span>
              </td>
              <td data-label="Deliverable">
                <span className="cga-sprint-slug">
                  {critSet.has(s.node_id) && (
                    <span className="cga-critical-node" style={{ marginRight: 6 }}>
                      critical path
                    </span>
                  )}
                  {s.slug.replace(/-/g, " ")}
                </span>
              </td>
              <td data-label="Status">
                {s.status === "unknown" ? (
                  <span style={{ fontStyle: "italic", color: "var(--cga-muted)", fontSize: 12 }}>
                    (product-owned)
                  </span>
                ) : (
                  <span className={`cga-sprint-status ${sprintStatusClass(s.status)}`}>
                    {s.status}
                  </span>
                )}
              </td>
              <td data-label="Dependency state">
                {s.unblocked ? (
                  <span className="cga-sprint-unblocked">unblocked</span>
                ) : (
                  <span className="cga-sprint-waits">
                    waits on {s.blocked_on.join(", ")}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {roster.sprints.length === 0 && (
        <p style={{ fontStyle: "italic", color: "var(--cga-muted)", fontSize: 12, padding: "12px 0" }}>
          No sprint files found for {roster.directory}/.
        </p>
      )}
    </div>
  );
}

// ── CoordinationView (pure, exported) ─────────────────────────────────

export type CoordinationGatesState =
  | { phase: "loading" }
  | { phase: "ready"; data: GatesResponse }
  | { phase: "error"; copy: string }
  | { phase: "malformed"; copy: string };

export type CoordinationRoadmapState =
  | { phase: "loading" }
  | { phase: "ready"; data: RoadmapView }
  | { phase: "error"; copy: string }
  | { phase: "malformed"; copy: string };

export type CoordinationViewProps = {
  gatesState: CoordinationGatesState;
  roadmapState: CoordinationRoadmapState;
  onRetryGates: () => void;
  onRetryRoadmap: () => void;
  fixtureTheme?: "dark";
};

export function CoordinationView({
  gatesState,
  roadmapState,
  onRetryGates,
  onRetryRoadmap,
  fixtureTheme,
}: CoordinationViewProps) {
  const gatesLoading = gatesState.phase === "loading";
  const roadmapLoading = roadmapState.phase === "loading";
  const gatesReady = gatesState.phase === "ready";
  const roadmapReady = roadmapState.phase === "ready";
  const gatesError = gatesState.phase === "error" || gatesState.phase === "malformed";
  const roadmapError = roadmapState.phase === "error" || roadmapState.phase === "malformed";

  // Werner mood: thinking if either loading, empty only both error, else idle
  const wernerMood = gatesLoading || roadmapLoading
    ? "thinking"
    : gatesError && roadmapError
      ? "empty"
      : "idle";

  // Status tally from ready gates
  const tally = gatesReady ? deriveStatusTally(gatesState.data.gates) : null;

  return (
    <main className="cga-shell" data-theme={fixtureTheme}>
      <img
        className="cga-environment"
        src={environment}
        alt=""
        aria-hidden="true"
      />
      <div className="cga-veil" aria-hidden="true" />

      <div className="cga-content">
        {/* ── Hero ──────────────────────────────────── */}
        <header className="cga-hero">
          <div>
            <p className="cga-eyebrow">Operator · read-only</p>
            <h1>Coordination Gatehouse Atlas</h1>
            <p className="cga-lede">
              What is blocked, what is unblocked, and what the dependency
              topology reveals. A read-only view over the canonical operator
              gate file and the five specs&rsquo; sprint rosters. Nothing on
              this surface can change a gate&rsquo;s state.
            </p>
            <a className="cga-doorway" href="/coordination/cost-consent">
              Open Cost &amp; Consent
              <span aria-hidden="true">→</span>
            </a>
          </div>
          <Werner
            mood={wernerMood}
            size={58}
            label={`Werner ${wernerMood === "empty" ? "found no data" : wernerMood === "thinking" ? "is listening" : "watches the gatehouse"}`}
          />
        </header>

        {/* ── Truth boundary ────────────────────────── */}
        <aside className="cga-truth" aria-label="Gatehouse boundary">
          <p className="cga-eyebrow">What this surface establishes</p>
          <p>
            This is a <strong>read-only operator view</strong> of canonical
            gate state and sprint dependency topology. Gate state changes only
            in the operator&rsquo;s source markdown. No control here can
            mutate a gate, sprint, roster, payout, or training configuration.
          </p>
          <p>
            <strong>status_raw</strong> preserves the original nuance; the
            coarse status controls presentation only. Empty impacts mean
            &ldquo;no reviewed per-product mapping,&rdquo; never &ldquo;no
            product block.&rdquo; Unblocked means dependency-unblocked, not
            done, approved, funded, or ready to ship.
          </p>
          <p>
            Neither endpoint supplies a freshness or completeness timestamp.
            None is invented here.
          </p>
        </aside>

        {/* ── Status tally ──────────────────────────── */}
        {tally && (
          <div className="cga-tally" aria-label="Gate status tally">
            <div className="cga-tally-item">
              <span className="cga-tally-count">{tally.open}</span>
              <span className="cga-tally-label">open</span>
            </div>
            <div className="cga-tally-item">
              <span className="cga-tally-count">{tally.calendar}</span>
              <span className="cga-tally-label">calendar</span>
            </div>
            <div className="cga-tally-item">
              <span className="cga-tally-count">{tally.data_bound}</span>
              <span className="cga-tally-label">data-bound</span>
            </div>
            <div className="cga-tally-item">
              <span className="cga-tally-count">{tally.closed}</span>
              <span className="cga-tally-label">closed</span>
            </div>
          </div>
        )}

        {/* ── Gates loading/error states ─────────────── */}
        {gatesState.phase === "loading" && (
          <section className="cga-state" aria-live="polite">
            <h2>Loading gate register…</h2>
            <p>
              Reading the canonical operator gate file. No status is inferred
              while the endpoint responds.
            </p>
          </section>
        )}

        {gatesState.phase === "error" && (
          <section className="cga-state cga-state--error" role="alert">
            <h2>Gate data unavailable</h2>
            <p>{gatesState.copy}</p>
            <button type="button" onClick={onRetryGates}>
              Retry gates
            </button>
          </section>
        )}

        {gatesState.phase === "malformed" && (
          <section className="cga-state cga-state--error" role="alert">
            <h2>Gate data malformed</h2>
            <p>{gatesState.copy}</p>
            <button type="button" onClick={onRetryGates}>
              Retry gates
            </button>
          </section>
        )}

        {/* ── Gate Wall ─────────────────────────────── */}
        {gatesReady && (
          <section className="cga-station" aria-labelledby="gate-wall-heading">
            <header className="cga-station-heading">
              <div>
                <p className="cga-eyebrow">Canonical register</p>
                <h2 id="gate-wall-heading">Gate wall</h2>
              </div>
              <p>
                Open and waiting gates first, then closed. Every gate presented
                once with its raw status and per-product impact mapping.
              </p>
            </header>
            <GateWallSection gates={gatesState.data.gates} />
          </section>
        )}

        {/* ── Roadmap loading/error states ───────────── */}
        {roadmapState.phase === "loading" && (
          <section className="cga-state" aria-live="polite">
            <h2>Loading roadmap…</h2>
            <p>
              Reading sprint rosters and dependency state. No count is inferred
              while the endpoint responds.
            </p>
          </section>
        )}

        {roadmapState.phase === "error" && (
          <section className="cga-state cga-state--error" role="alert">
            <h2>Roadmap unavailable</h2>
            <p>{roadmapState.copy}</p>
            <button type="button" onClick={onRetryRoadmap}>
              Retry roadmap
            </button>
          </section>
        )}

        {roadmapState.phase === "malformed" && (
          <section className="cga-state cga-state--error" role="alert">
            <h2>Roadmap malformed</h2>
            <p>{roadmapState.copy}</p>
            <button type="button" onClick={onRetryRoadmap}>
              Retry roadmap
            </button>
          </section>
        )}

        {/* ── Route Atlas ───────────────────────────── */}
        {roadmapReady && (
          <section className="cga-station" aria-labelledby="route-atlas-heading">
            <header className="cga-station-heading">
              <div>
                <p className="cga-eyebrow">Dependency topology</p>
                <h2 id="route-atlas-heading">Route atlas</h2>
              </div>
              <p>
                Every sprint across the live specs plus the DRW dependency
                DAG. The count is summed from real roster files, not trusted
                from prose.
              </p>
            </header>
            <RouteAtlasSection roadmap={roadmapState.data} />
          </section>
        )}
      </div>
    </main>
  );
}

// ── Controller (default export) ───────────────────────────────────────

export default function Coordination() {
  const [gatesState, setGatesState] = useState<CoordinationGatesState>({
    phase: "loading",
  });
  const [roadmapState, setRoadmapState] = useState<CoordinationRoadmapState>({
    phase: "loading",
  });
  const gatesRequestRef = useRef(0);
  const roadmapRequestRef = useRef(0);

  // Stale-response guard: bump token on each request; discard
  // responses whose token no longer matches.
  // Unmount guard: cleanup bumps token so in-flight responses are discarded.
  useEffect(() => {
    return () => {
      gatesRequestRef.current += 1;
      roadmapRequestRef.current += 1;
    };
  }, []);

  const loadGates = useCallback(async () => {
    const token = ++gatesRequestRef.current;
    setGatesState({ phase: "loading" });
    try {
      const resp = await apiFetch("/coordination/gates");
      if (token !== gatesRequestRef.current) return;
      if (!resp.ok) {
        setGatesState({
          phase: "error",
          copy: SAFE_COPY.gatesUnavailable,
        });
        return;
      }
      const raw: unknown = await resp.json();
      if (token !== gatesRequestRef.current) return;
      if (!validateGatesResponse(raw)) {
        setGatesState({
          phase: "malformed",
          copy: SAFE_COPY.gatesMalformed,
        });
        return;
      }
      setGatesState({ phase: "ready", data: raw });
    } catch {
      if (token !== gatesRequestRef.current) return;
      setGatesState({ phase: "error", copy: SAFE_COPY.gatesUnavailable });
    }
  }, []);

  const loadRoadmap = useCallback(async () => {
    const token = ++roadmapRequestRef.current;
    setRoadmapState({ phase: "loading" });
    try {
      const resp = await apiFetch("/coordination/roadmap");
      if (token !== roadmapRequestRef.current) return;
      if (!resp.ok) {
        setRoadmapState({
          phase: "error",
          copy: SAFE_COPY.roadmapUnavailable,
        });
        return;
      }
      const raw: unknown = await resp.json();
      if (token !== roadmapRequestRef.current) return;
      if (!validateRoadmap(raw)) {
        setRoadmapState({
          phase: "malformed",
          copy: SAFE_COPY.roadmapMalformed,
        });
        return;
      }
      setRoadmapState({ phase: "ready", data: raw });
    } catch {
      if (token !== roadmapRequestRef.current) return;
      setRoadmapState({
        phase: "error",
        copy: SAFE_COPY.roadmapUnavailable,
      });
    }
  }, []);

  // Initial load: both endpoints independently
  useEffect(() => {
    void loadGates();
  }, [loadGates]);

  useEffect(() => {
    void loadRoadmap();
  }, [loadRoadmap]);

  // Scoped retry: only refetch the failed endpoint
  const retryGates = useCallback(() => {
    void loadGates();
  }, [loadGates]);

  const retryRoadmap = useCallback(() => {
    void loadRoadmap();
  }, [loadRoadmap]);

  return (
    <CoordinationView
      gatesState={gatesState}
      roadmapState={roadmapState}
      onRetryGates={retryGates}
      onRetryRoadmap={retryRoadmap}
    />
  );
}

// Re-export types for stories/tests
export type { GateView, GatesResponse, RoadmapView, SprintView, RosterView, SubstrateLayerView, GateImpactView, CoordProduct, GateStatus };
