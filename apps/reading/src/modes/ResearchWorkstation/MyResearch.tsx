/**
 * MyResearch — the one multi-research monitor (SPR-05 M1/M2/M4).
 *
 * The "launch 20 deep research agents at once" headline, made a calm home.
 * Before this, three surfaces each claimed a slice of "manage your
 * researches": the docked InvestigationSidebar tree, the /deep-research
 * cascade grid, and the /investigations flat list. The experience-spec
 * (E-04/E-05) flagged the duplicate doors as a defect. This folds them into
 * ONE overview that holds every running and completed research, narrated in
 * plain language, grouped by the cascade/chase that spawned them, with the
 * real aggregate cost and an honest "N running, M queued" — and one tap into
 * any single research's full view.
 *
 * What it does NOT reimplement (preserved, not dropped):
 *   - The cascade plan/edit/approve/launch flow + live per-research STEERING
 *     grid is the DeepResearchWorkspace's unique capability. MyResearch links
 *     INTO /deep-research/:sessionId for that; it does not duplicate steering.
 *   - Trajectory replay stays at /replay/:id; each row links to it.
 *   - The start-a-research composer stays StartResearch (the U-04 reference
 *     door); MyResearch's "Start a research" and "Launch several" route there
 *     rather than carrying a second composer.
 *
 * Source of truth: `listInvestigations` (the substrate's own list, polled),
 * which already carries `parent_investigation_id` and the real
 * `cost_usd_total`. No new "sessions" store is invented — session membership
 * is the parent/child relationship the substrate already records (the same
 * relationship cascade_session.reconstruct_session rebuilds from the event
 * log). So a reload reconstructs every research's state from the substrate,
 * never from in-memory UI state (M2).
 *
 * Honesty (rigor #1): concurrency is the host-local semaphore's real bound
 * read off the budget-defaults contract — never a number the UI invents. The
 * "20 at once" headline is reachable only when the operator provisions the
 * §16-gated remote runner; until then this is many-on-host-local within the
 * semaphore, and the surface says exactly that.
 */

import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { getBudgetDefaults, type BudgetDefaults } from "../../api/research";
import { openWindow } from "../../components/windows/openWindow";
import { useAuth } from "../../lib/auth";
import { useInvestigationList } from "../../hooks/useInvestigationList";
import type { InvestigationSummary } from "../../lib/api";
import AIActionFailure from "../../shared/AIActionFailure";
import LemonButton from "../../components/lemon/LemonButton";
import { LemonTag } from "../../components/lemon/LemonTag";
import SuggestedResearch from "./SuggestedResearch";
import chartRoomEnvironment from "../../brand/werner/investigations/investigation_chart_room_v1.webp";

// CSS-only tree connectors for the lineage board — pseudo-elements draw
// the trunk and branches; no SVG, no JS, no generated art.
import "./research-lineage-board.css";

// The Chart Room environment frame — decorative art + legibility veil.
import "./investigation-chart-room.css";

// ── Status → plain language (SPR-02 narration vocabulary) ─────────────────
//
// The monitor never shows a raw state (`in_progress`, `failed`). It uses the
// same human vocabulary the SPR-02 thinking stream uses: working / done /
// stopped / needs attention. One mapper, so a maintainer adds a state in one
// place. `not_found` is a list-edge case (a referenced id with no row); it
// reads as "unavailable" rather than leaking the enum.

type Plain = "working" | "done" | "stopped" | "needs attention" | "unavailable";

interface PlainStatus {
  label: Plain;
  /** LemonTag colour — sun=working, aurora=done, muted=stopped, danger=attention. */
  colour: "sun" | "aurora" | "muted" | "danger";
  /** Whether this research is still consuming concurrency (a "running" one). */
  running: boolean;
}

function plainStatus(status: InvestigationSummary["status"]): PlainStatus {
  switch (status) {
    case "in_progress":
      return { label: "working", colour: "sun", running: true };
    case "completed":
      return { label: "done", colour: "aurora", running: false };
    case "failed":
      return { label: "needs attention", colour: "danger", running: false };
    case "stopped":
      // Stopped/cancelled by the operator, or budget-halted by the runner
      // (the backend collapses both halted + outcome:stopped/cancelled into
      // this terminal state — never "working" forever). Not running.
      return { label: "stopped", colour: "muted", running: false };
    case "not_found":
      return { label: "unavailable", colour: "muted", running: false };
    default:
      // Exhaustive over the union; a new status is a compile error here.
      return assertNever(status);
  }
}

function assertNever(x: never): never {
  // A status the union doesn't cover reached here — fail loudly in dev
  // rather than silently mislabelling. Returns a safe muted fallback shape
  // only to satisfy the never-return at runtime (unreachable in practice).
  throw new Error(`unhandled investigation status: ${String(x)}`);
}

// ── Chart Room frame — decorative environment for standalone MyResearch ──
//
// A `div`-based presentational frame that wraps the standalone monitor in a
// polar cartographic room with a legibility veil. The image is decorative:
// empty-alt, aria-hidden, lazy-loaded, async-decoded, non-draggable, and
// pointer-inert. It
// supplies atmosphere only; every title, cost, status, link, and launch
// control remains live HTML.
//
// Embedded MyResearch (<MyResearch embedded />) does NOT use this frame —
// it renders the existing log section unchanged.

export function ChartRoomFrame({
  fixture = false,
  children,
}: {
  /** When true, hides the real image and uses a deterministic CSS gradient
   *  background for Storybook fixtures (no asset I/O dependency). */
  fixture?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      data-testid="chart-room-frame"
      className={`investigation-chart-room${fixture ? " investigation-chart-room--fixture" : ""}`}
    >
      <img
        src={chartRoomEnvironment}
        alt=""
        aria-hidden="true"
        loading="lazy"
        decoding="async"
        draggable={false}
        data-testid="investigation-chart-room-art"
      />
      <div className="investigation-chart-room__veil" aria-hidden="true" />
      <header className="investigation-chart-room__masthead">
        <p className="investigation-chart-room__eyebrow">
          Antiek · investigation chart room
        </p>
        <h1>My research</h1>
        <p>
          Every research you have running and finished, in one place. Each
          shows what it is doing in plain language; open any one for the full
          view.
        </p>
      </header>
      <div className="investigation-chart-room__content">{children}</div>
    </div>
  );
}

// ── Lineage forest. Every research appears exactly once, at its real depth.
//    Standalones remain flat cards; cascades and recursive chases retain their
//    full ancestry without inventing a separate session concept. ───────────

interface TreeNode {
  summary: InvestigationSummary;
  children: TreeNode[];
}

function buildLineageTree(items: InvestigationSummary[]): TreeNode[] {
  // The list contract normally returns unique IDs. Preserve the first row if
  // a malformed response repeats one so React keys and lineage stay stable.
  const byId = new Map<string, InvestigationSummary>();
  for (const summary of items) {
    if (!byId.has(summary.investigation_id)) {
      byId.set(summary.investigation_id, summary);
    }
  }
  const nodes = new Map(
    [...byId.values()].map((summary) => [
      summary.investigation_id,
      { summary, children: [] } as TreeNode,
    ]),
  );
  const roots: TreeNode[] = [];

  const wouldCreateCycle = (childId: string, parentId: string): boolean => {
    const seen = new Set<string>();
    let current: string | null | undefined = parentId;
    while (current && byId.has(current) && !seen.has(current)) {
      if (current === childId) return true;
      seen.add(current);
      current = byId.get(current)?.parent_investigation_id;
    }
    return false;
  };

  for (const s of byId.values()) {
    const pid = s.parent_investigation_id;
    const node = nodes.get(s.investigation_id)!;
    if (pid && byId.has(pid) && !wouldCreateCycle(s.investigation_id, pid)) {
      nodes.get(pid)!.children.push(node);
    } else {
      // Missing parents and cyclic edges become visible roots, never omissions.
      roots.push(node);
    }
  }

  const newestFirst = (a: TreeNode, b: TreeNode) =>
    (b.summary.started_at ?? "").localeCompare(a.summary.started_at ?? "");
  for (const node of nodes.values()) node.children.sort(newestFirst);
  roots.sort(newestFirst);
  return roots;
}

function descendantCount(node: TreeNode): number {
  return node.children.reduce((total, child) => total + 1 + descendantCount(child), 0);
}

// ── Aggregate (M2): real counts + real summed cost. ───────────────────────

interface Aggregate {
  total: number;
  running: number;
  done: number;
  attention: number;
  /** Sum of every research's real cost_usd_total — not an estimate. */
  costUsd: number;
}

function aggregate(items: InvestigationSummary[]): Aggregate {
  let running = 0;
  let done = 0;
  let attention = 0;
  let costUsd = 0;
  for (const s of items) {
    const ps = plainStatus(s.status);
    if (ps.running) running += 1;
    else if (ps.label === "done") done += 1;
    else if (ps.label === "needs attention") attention += 1;
    costUsd += s.cost_usd_total ?? 0;
  }
  return { total: items.length, running, done, attention, costUsd };
}

/**
 * SPR-05 M3 — `embedded` folds this log INTO the Research home (StartResearch),
 * per the operator's "the research home IS the research log" decision. When
 * embedded:
 *   - the LaunchBar is dropped (the composer ABOVE the log is the one entry —
 *     keeping a second "Start a research" button would be the duplicate door
 *     M3 is removing);
 *   - the outer container loses its full-screen scroll/padding chrome (the
 *     home scrolls; the log is a section in it), and the header reads as a log
 *     heading rather than the page title.
 * Standalone (embedded=false, the /my-research route — kept non-breaking) it
 * renders exactly as before: full page, header, launch bar, suggested lane.
 * The row → /inv/{id} navigation contract is identical in both.
 */

export default function MyResearch({
  embedded = false,
}: { embedded?: boolean } = {}) {
  const navigate = useNavigate();
  const { state: auth } = useAuth();
  // The substrate's own list, polled. Limit generous — the monitor is the
  // home for ALL researches, not a recent slice.
  const { investigations, loading, error, refetch } = useInvestigationList({
    limit: 200,
  });

  // The real host-local concurrency bound, read off the contract (never
  // hardcoded — it would drift from runtime/research_runner). Best-effort: a
  // null cap (no-key / endpoint unreachable) degrades the concurrency line to
  // "running" only, honestly, rather than inventing a cap.
  const [budget, setBudget] = useState<BudgetDefaults | null>(null);
  useEffect(() => {
    let cancelled = false;
    void getBudgetDefaults()
      .then((b) => {
        if (!cancelled) setBudget(b);
      })
      .catch(() => {
        /* leave null — the concurrency line falls back to "running" only */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const agg = useMemo(() => aggregate(investigations), [investigations]);
  const [compositionIds, setCompositionIds] = useState<string[]>([]);
  useEffect(() => {
    const completed = new Set(
      investigations
        .filter((item) => item.status === "completed")
        .map((item) => item.investigation_id),
    );
    setCompositionIds((current) => current.filter((id) => completed.has(id)).slice(0, 8));
  }, [investigations]);

  // Honest "N running, M queued": the host-local runner multiplexes browse
  // loops under a bounded semaphore (the contract's max_concurrency). More
  // running researches than the cap means the surplus is queued behind the
  // semaphore — visible, not a hang (rigor #3). When we couldn't read the cap,
  // we show running only and say nothing false about queueing.
  const cap = budget?.host_local_max_concurrency ?? null;
  const runningActive = cap === null ? agg.running : Math.min(agg.running, cap);
  const queued = cap === null ? 0 : Math.max(0, agg.running - cap);

  // ── Content shared between standalone and embedded modes. ─────────────
  //    Extracted so the frame wrapper doesn't duplicate JSX.
  const content = (
    <>
      {/* Concurrency bar + refresh. In standalone mode the header lives
          inside the Chart Room frame's masthead, so the bar + refresh are
          rendered as content below it. In embedded mode they sit inside the
          existing compact header. */}
      {embedded && (
        <header className="space-y-2">
          <div className="flex items-start justify-between gap-4">
            <h1 className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
              Your research
            </h1>
            <button
              type="button"
              onClick={refetch}
              aria-label="Refresh"
              className="shrink-0 text-shadow-1 transition-colors hover:text-ink dark:text-moonlight dark:hover:text-bright"
            >
              ⟳
            </button>
          </div>
          <ConcurrencyBar
            running={runningActive}
            queued={queued}
            done={agg.done}
            attention={agg.attention}
            costUsd={agg.costUsd}
            cap={cap}
          />
        </header>
      )}

      {!embedded && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <ConcurrencyBar
            running={runningActive}
            queued={queued}
            done={agg.done}
            attention={agg.attention}
            costUsd={agg.costUsd}
            cap={cap}
          />
          <button
            type="button"
            onClick={refetch}
            aria-label="Refresh"
            className="shrink-0 text-shadow-1 transition-colors hover:text-ink dark:text-moonlight dark:hover:text-bright"
          >
            ⟳
          </button>
        </div>
      )}

      {/* Launch affordances. Disabled with a clear reason when no research
          can run (no provider keys). Both route to the start surface — one
          composer, no second entry point (M1 consolidation).
          SPR-05 M3: SUPPRESSED when embedded in the home — the composer
          sitting directly above the log IS the entry, so a second "Start a
          research" button here would be exactly the duplicate door the
          consolidation removes. */}
      {!embedded && (
        <LaunchBar
          disabled={auth.status !== "authenticated"}
          onStartOne={() => navigate("/")}
          onLaunchSeveral={() => navigate("/")}
        />
      )}

      {/* SPR-09: the compounding flywheel, surfaced. A calm "what to chase
          next" lane sourced from the §7 daemon's existing scored gaps — an
          offer, never a nag (§2.6 curiosity-gated). Read-only to render;
          chasing one launches through the same capped path. */}
      <SuggestedResearch
        variant="lane"
        canLaunch={auth.status === "authenticated"}
      />

      {error && <ListError onRetry={refetch} />}

      {/* No-key / nothing-yet honest state. The common production reason a
          research list is empty is that no model provider is configured, so
          we reuse the shared AIActionFailure no-reason branch which says
          exactly that — never a hopeful spinner. */}
      {!loading && !error && investigations.length === 0 && (
        <div className="rounded-md border border-rule px-4 py-8 dark:border-charcoal-1">
          <AIActionFailure
            title="No research yet"
            onRetry={() => navigate("/")}
            retryLabel="Start a research"
          />
        </div>
      )}

      {loading && investigations.length === 0 && (
        <p className="text-sm italic text-shadow-1 dark:text-moonlight">
          Loading…
        </p>
      )}

      <ResearchLineageBoard
        investigations={investigations}
        selectedInvestigationIds={compositionIds}
        onSelectionChange={setCompositionIds}
      />
      {compositionIds.length > 0 && (
        <aside className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-rule p-4 dark:border-charcoal-1" aria-label="Research composition selection">
          <p className="text-sm text-shadow-1 dark:text-moonlight">
            {compositionIds.length} selected in collection order
          </p>
          <div className="flex items-center gap-2">
            <LemonButton
              variant="secondary"
              size="md"
              onClick={() => setCompositionIds([])}
            >
              Clear
            </LemonButton>
            <LemonButton
              variant="primary"
              size="md"
              disabled={compositionIds.length < 2}
              onClick={() =>
                openWindow(
                  "research-composition-review",
                  { investigationIds: compositionIds },
                  {
                    title: "Collected research",
                    refreshExistingPayload: true,
                    replaceOldestAtLimit: true,
                  },
                )
              }
            >
              Review {compositionIds.length} researches
            </LemonButton>
          </div>
        </aside>
      )}
    </>
  );

  // ── Standalone: the Chart Room frame wraps the monitor. ──────────────
  //    Embedded: the existing log section, visually and behaviourally
  //    unchanged.
  if (embedded) {
    return (
      <div className="w-full">
        <div className="w-full space-y-6">{content}</div>
      </div>
    );
  }

  return (
    <ChartRoomFrame>
      <div className="space-y-6">{content}</div>
    </ChartRoomFrame>
  );
}

function ConcurrencyBar({
  running,
  queued,
  done,
  attention,
  costUsd,
  cap,
}: {
  running: number;
  queued: number;
  done: number;
  attention: number;
  costUsd: number;
  cap: number | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 font-mono text-[12px] text-shadow-1 dark:text-moonlight">
      <span aria-live="polite" data-testid="concurrency-line">
        <span className="text-ink dark:text-bright">{running}</span> running
        {queued > 0 && (
          <>
            , <span className="text-ink dark:text-bright">{queued}</span> queued
          </>
        )}
      </span>
      {done > 0 && (
        <span>
          <span className="text-ink dark:text-bright">{done}</span> done
        </span>
      )}
      {attention > 0 && (
        <span className="text-emperor">
          <span className="font-semibold">{attention}</span> need attention
        </span>
      )}
      <span>
        <span className="text-ink dark:text-bright">${costUsd.toFixed(4)}</span>{" "}
        spent so far
      </span>
      {/* The honest concurrency framing: how many can run at once, and the
          fact that "20 at once" is the remote-provisioned ceiling, not what
          host-local delivers today. Shown only when we read the real cap. */}
      {cap !== null && (
        <span className="text-ink-mute dark:text-moonlight">
          up to {cap} at once on this machine
        </span>
      )}
    </div>
  );
}

function LaunchBar({
  disabled,
  onStartOne,
  onLaunchSeveral,
}: {
  disabled: boolean;
  onStartOne: () => void;
  onLaunchSeveral: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <LemonButton
        variant="primary"
        size="md"
        onClick={onStartOne}
        disabled={disabled}
      >
        Start a research
      </LemonButton>
      <LemonButton
        variant="secondary"
        size="md"
        onClick={onLaunchSeveral}
        disabled={disabled}
      >
        Launch several at once
      </LemonButton>
      {disabled && (
        <span className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
          Sign in to start a research.
        </span>
      )}
    </div>
  );
}

/**
 * The visual read of the canonical parent/child relationship. Kept pure so
 * Storybook can prove the hierarchy without replacing production hooks or
 * inventing a second research model.
 */
export function ResearchLineageBoard({
  investigations,
  nowMs = Date.now(),
  selectedInvestigationIds,
  onSelectionChange,
}: {
  investigations: InvestigationSummary[];
  /** Fixed by visual fixtures; production naturally uses the current time. */
  nowMs?: number;
  selectedInvestigationIds?: readonly string[];
  onSelectionChange?: (ids: string[]) => void;
}) {
  const tree = useMemo(() => buildLineageTree(investigations), [investigations]);
  if (tree.length === 0) return null;
  return (
    <div className="research-lineage-board" aria-label="Research lineages">
      {tree.map((node) => (
        <FamilyCard
          key={node.summary.investigation_id}
          node={node}
          nowMs={nowMs}
          selectedInvestigationIds={selectedInvestigationIds}
          onSelectionChange={onSelectionChange}
        />
      ))}
    </div>
  );
}

function FamilyCard({
  node,
  nowMs,
  selectedInvestigationIds,
  onSelectionChange,
}: {
  node: TreeNode;
  nowMs: number;
  selectedInvestigationIds?: readonly string[];
  onSelectionChange?: (ids: string[]) => void;
}) {
  // A node with children is a cascade/chase family; without children it is a
  // standalone research. The header names the family by the root's question.
  const isFamily = node.children.length > 0;
  const headTitle = node.summary.question ?? "Research";
  const descendants = descendantCount(node);

  return (
    <section
      className={`research-lineage ${isFamily ? "research-lineage--family" : "research-lineage--standalone"}`}
      aria-label={
        isFamily
          ? `Research family: ${headTitle}`
          : `Standalone research: ${headTitle}`
      }
    >
      {isFamily && (
        <header className="research-lineage__header">
          <div className="min-w-0 flex-1">
            <p className="research-lineage__eyebrow">Research family</p>
            <h2 className="research-lineage__title">{headTitle}</h2>
          </div>
          <span className="research-lineage__count">
            {descendants} {descendants === 1 ? "branch" : "branches"}
          </span>
        </header>
      )}
      <ol
        className="research-lineage__members"
        data-tree-role={isFamily ? "family" : "standalone"}
      >
        {/* Origin/root first — it anchors the tree trunk. */}
        <ResearchRow
          summary={node.summary}
          role={isFamily ? "origin" : "standalone"}
          branchNumber={null}
          depth={0}
          nowMs={nowMs}
          selectedInvestigationIds={selectedInvestigationIds}
          onSelectionChange={onSelectionChange}
        />
        {node.children.map((child, index) => (
          <LineageBranch
            key={child.summary.investigation_id}
            node={child}
            index={index + 1}
            depth={1}
            nowMs={nowMs}
            selectedInvestigationIds={selectedInvestigationIds}
            onSelectionChange={onSelectionChange}
          />
        ))}
      </ol>
    </section>
  );
}

function LineageBranch({
  node,
  index,
  depth,
  nowMs,
  selectedInvestigationIds,
  onSelectionChange,
}: {
  node: TreeNode;
  index: number;
  depth: number;
  nowMs: number;
  selectedInvestigationIds?: readonly string[];
  onSelectionChange?: (ids: string[]) => void;
}) {
  return (
    <>
      <ResearchRow
        summary={node.summary}
        role="branch"
        branchNumber={index}
        depth={depth}
        nowMs={nowMs}
        selectedInvestigationIds={selectedInvestigationIds}
        onSelectionChange={onSelectionChange}
      />
      {node.children.map((child, childIndex) => (
        <LineageBranch
          key={child.summary.investigation_id}
          node={child}
          index={childIndex + 1}
          depth={depth + 1}
          nowMs={nowMs}
          selectedInvestigationIds={selectedInvestigationIds}
          onSelectionChange={onSelectionChange}
        />
      ))}
    </>
  );
}

function ResearchRow({
  summary,
  role,
  branchNumber,
  depth,
  nowMs,
  selectedInvestigationIds,
  onSelectionChange,
}: {
  summary: InvestigationSummary;
  role: "origin" | "branch" | "standalone";
  branchNumber: number | null;
  depth: number;
  nowMs: number;
  selectedInvestigationIds?: readonly string[];
  onSelectionChange?: (ids: string[]) => void;
}) {
  const ps = plainStatus(summary.status);
  const selected = selectedInvestigationIds?.includes(summary.investigation_id) ?? false;
  const selectionEnabled = selectedInvestigationIds !== undefined && onSelectionChange !== undefined;
  return (
    <li
      className="research-lineage__member"
      data-lineage-role={role}
      data-lineage-depth={depth}
      style={{ "--lineage-depth": depth } as CSSProperties}
    >
      <article className="research-lineage__research">
        <div className="research-lineage__marker" aria-hidden="true" />
        {selectionEnabled && summary.status === "completed" && (
          <input
            className="research-lineage__composition-select"
            type="checkbox"
            checked={selected}
            disabled={!selected && selectedInvestigationIds.length >= 8}
            aria-label={`Select ${summary.question ?? "Untitled research"} for composition`}
            onChange={() => {
              onSelectionChange(
                selected
                  ? selectedInvestigationIds.filter((id) => id !== summary.investigation_id)
                  : [...selectedInvestigationIds, summary.investigation_id],
              );
            }}
          />
        )}
        <div className="research-lineage__body">
          {role !== "standalone" && (
            <p className="research-lineage__role">
              {role === "origin"
                ? "Origin"
                : `${depth > 1 ? `Depth ${depth} · ` : ""}Branch ${String(branchNumber).padStart(2, "0")}`}
            </p>
          )}
          <div className="research-lineage__summary flex items-baseline justify-between gap-3">
            <Link
              to={`/inv/${encodeURIComponent(summary.investigation_id)}`}
              className="min-w-0 flex-1"
            >
              <p className="truncate font-serif text-sm text-ink dark:text-bright">
                {summary.question ?? "Untitled research"}
              </p>
            </Link>
            <div className="research-lineage__meta flex shrink-0 items-center gap-3">
              {/* SPR-09 distinction: a research the §7 loop launched autonomously
              is badged "found by the loop" (translated from its policy_id —
              the id is never shown), so the user can tell what the loop did on
              its own from what they launched. */}
              {summary.spawned_by_daemon && (
                <LemonTag colour="muted" className="text-[10px]">
                  found by the loop
                </LemonTag>
              )}
              <LemonTag dot colour={ps.colour} className="text-[10px]">
                {ps.label}
              </LemonTag>
              <span className="font-mono text-[10px] text-shadow-1 dark:text-moonlight tabular-nums">
                ${(summary.cost_usd_total ?? 0).toFixed(4)}
              </span>
            </div>
          </div>
          <div className="mt-1.5 flex items-center gap-3 font-mono text-[11px] text-shadow-1 dark:text-moonlight">
            <Link
              to={`/replay/${encodeURIComponent(summary.investigation_id)}`}
              className="hover:text-ink hover:underline dark:hover:text-bright"
            >
              replay →
            </Link>
            {summary.started_at && (
              <span>started {relative(summary.started_at, nowMs)}</span>
            )}
          </div>
        </div>
      </article>
    </li>
  );
}

function ListError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-md border border-rule px-4 py-6 dark:border-charcoal-1">
      <AIActionFailure
        title="Couldn’t load your research"
        onRetry={onRetry}
      />
    </div>
  );
}

function relative(iso: string, nowMs: number): string {
  try {
    const ago = nowMs - new Date(iso).getTime();
    const s = Math.floor(ago / 1000);
    if (s < 60) return `${s}s ago`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    if (d < 30) return `${d}d ago`;
    return new Date(iso).toLocaleDateString();
  } catch {
    return "";
  }
}
