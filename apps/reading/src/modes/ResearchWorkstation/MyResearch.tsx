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

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { getBudgetDefaults, type BudgetDefaults } from "../../api/research";
import { useAuth } from "../../lib/auth";
import { useInvestigationList } from "../../hooks/useInvestigationList";
import type { InvestigationSummary } from "../../lib/api";
import AIActionFailure from "../../shared/AIActionFailure";
import { aggregateAttention, hasUnseen } from "../../shared/attention";
import {
  isUnseen,
  researchStateDotClass,
  researchStateLabel,
  researchStateStyle,
} from "../../shared/researchState";
import { useSeenVersion } from "../../hooks/useSeenVersion";
import { lastSeenAt } from "../../workspace/seen";
import LemonButton from "../../components/lemon/LemonButton";
import { LemonTag } from "../../components/lemon/LemonTag";
import SuggestedResearch from "./SuggestedResearch";

// ── Status → plain language: now the SHARED registry (herdr transfer P0-1).
// shared/researchState.ts owns the vocabulary (working / needs attention /
// done / stopped / unavailable) so every surface — this log, the sidebar,
// the palette, the rail badge — can never drift. ─────────────────────────

// ── Grouping: a "session" is a parent research + the researches spawned from
//    it (a cascade's leaves, or a chase's child). Standalone researches with
//    no parent are their own single-row group. This mirrors the substrate's
//    parent/child relationship — no separate session concept invented. ──

interface Group {
  /** The parent research id, or the standalone research's own id. */
  rootId: string;
  /** The parent summary if it is itself in the list; else null (orphan root). */
  root: InvestigationSummary | null;
  /** Members in newest-first order (root first when present). */
  members: InvestigationSummary[];
}

function groupByParent(items: InvestigationSummary[]): Group[] {
  const byId = new Map(items.map((s) => [s.investigation_id, s]));
  const groups = new Map<string, InvestigationSummary[]>();
  for (const s of items) {
    // A research belongs to its parent's group when the parent is also in the
    // list; otherwise it heads its own group (an orphan root, or a standalone).
    const parent = s.parent_investigation_id;
    const key = parent && byId.has(parent) ? parent : s.investigation_id;
    const arr = groups.get(key) ?? [];
    arr.push(s);
    groups.set(key, arr);
  }
  const out: Group[] = [];
  for (const [rootId, members] of groups) {
    // Root first (if present), then newest-first.
    members.sort((a, b) => {
      if (a.investigation_id === rootId) return -1;
      if (b.investigation_id === rootId) return 1;
      return (b.started_at ?? "").localeCompare(a.started_at ?? "");
    });
    out.push({ rootId, root: byId.get(rootId) ?? null, members });
  }
  // Newest group first, by the freshest member's start time.
  out.sort((a, b) => {
    const ta = a.members[0]?.started_at ?? "";
    const tb = b.members[0]?.started_at ?? "";
    return tb.localeCompare(ta);
  });
  return out;
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
    const style = researchStateStyle(s.status);
    if (style.running) running += 1;
    else if (style.state === "done") done += 1;
    else if (style.state === "blocked") attention += 1;
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
export default function MyResearch({ embedded = false }: { embedded?: boolean } = {}) {
  const navigate = useNavigate();
  const { state: auth } = useAuth();
  // The substrate's own list, polled. Limit generous — the monitor is the
  // home for ALL researches, not a recent slice.
  const { investigations, loading, error, refetch } = useInvestigationList({ limit: 200 });

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
  const groups = useMemo(() => groupByParent(investigations), [investigations]);

  // P0-3 — re-render when ANY surface marks an investigation seen, so the
  // unread axis updates live instead of waiting for the next 30s poll.
  useSeenVersion();

  // Honest "N running, M queued": the host-local runner multiplexes browse
  // loops under a bounded semaphore (the contract's max_concurrency). More
  // running researches than the cap means the surplus is queued behind the
  // semaphore — visible, not a hang (rigor #3). When we couldn't read the cap,
  // we show running only and say nothing false about queueing.
  const cap = budget?.host_local_max_concurrency ?? null;
  const runningActive = cap === null ? agg.running : Math.min(agg.running, cap);
  const queued = cap === null ? 0 : Math.max(0, agg.running - cap);

  // SPR-05 M3 — when embedded in the home, shed the full-screen page chrome
  // (the home owns the scroll + background) and read as a log section.
  const outerClass = embedded
    ? "w-full"
    : "flex h-full flex-col overflow-y-auto bg-ice-0 dark:bg-charcoal-2";
  const innerClass = embedded
    ? "w-full space-y-6"
    : "mx-auto w-full max-w-5xl space-y-6 px-8 py-10";

  return (
    <div className={outerClass}>
      <div className={innerClass}>
        <header className="space-y-2">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1
                className={
                  embedded
                    ? "text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight"
                    : "text-2xl font-serif text-ink dark:text-bright"
                }
              >
                {embedded ? "Your research" : "My research"}
              </h1>
              {!embedded && (
                <p className="max-w-2xl text-sm leading-relaxed text-shadow-1 dark:text-moonlight">
                  Every research you have running and finished, in one place. Each
                  shows what it is doing in plain language; open any one for the
                  full view. Launch several at once and watch them here together.
                </p>
              )}
            </div>
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

        {error && <ListError error={error} onRetry={refetch} />}

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
          <p className="text-sm italic text-shadow-1 dark:text-moonlight">Loading…</p>
        )}

        {groups.length > 0 && (
          <div className="space-y-4">
            {groups.map((g) => (
              <GroupCard key={g.rootId} group={g} />
            ))}
          </div>
        )}
      </div>
    </div>
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
        <span className="text-ink dark:text-bright">${costUsd.toFixed(4)}</span> spent so far
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
      <LemonButton variant="primary" size="md" onClick={onStartOne} disabled={disabled}>
        Start a research
      </LemonButton>
      <LemonButton variant="secondary" size="md" onClick={onLaunchSeveral} disabled={disabled}>
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

function GroupCard({ group }: { group: Group }) {
  // A group with one member is a standalone research; >1 is a cascade/chase
  // family. The header names the family by its parent question when present.
  const isFamily = group.members.length > 1;
  const headTitle =
    group.root?.question ??
    group.members[0]?.question ??
    "Research";

  // Attention rollup (herdr transfer P0-2): one blocked child reddens the
  // whole family header. The dot is the aggregate state; unseen-done gets
  // the halo when the aggregate lands on done.
  const memberAttention = group.members.map((s) => ({
    state: researchStateStyle(s.status).state,
    unseen: isUnseen(s, lastSeenAt(s.investigation_id)),
  }));
  const aggregateState = aggregateAttention(memberAttention);
  const aggregateUnseen =
    aggregateState === "done" && hasUnseen(memberAttention);

  return (
    <section className="rounded-md border border-rule dark:border-charcoal-1">
      {isFamily && (
        <header className="flex items-baseline justify-between gap-3 border-b border-rule px-4 py-2.5 dark:border-charcoal-1">
          <p className="min-w-0 flex-1 truncate font-serif text-sm text-ink dark:text-bright">
            {headTitle}
          </p>
          <span className="flex shrink-0 items-center gap-2">
            {aggregateState && (
              <span
                aria-label={`family: ${researchStateLabel(aggregateState)}`}
                title={`family state: ${researchStateLabel(aggregateState)}`}
                className={`w-2 h-2 rounded-full ${researchStateDotClass(aggregateState, aggregateUnseen)}`}
              />
            )}
            <span className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
              {group.members.length} researches
            </span>
          </span>
        </header>
      )}
      <div className="divide-y divide-rule dark:divide-charcoal-1">
        {group.members.map((s) => (
          <ResearchRow key={s.investigation_id} summary={s} indented={isFamily} />
        ))}
      </div>
    </section>
  );
}

function ResearchRow({
  summary,
  indented,
}: {
  summary: InvestigationSummary;
  indented: boolean;
}) {
  // The ONE registry (herdr transfer P0-1): label, colour, running all come
  // from shared/researchState.ts. Unseen-done (P0-3) bolds the row — the
  // unread flag turns the log into a to-do list.
  const style = researchStateStyle(summary.status);
  const unseen = isUnseen(summary, lastSeenAt(summary.investigation_id));
  return (
    <article
      className={`px-4 py-3 transition-colors hover:bg-ice-1 dark:hover:bg-charcoal-1 ${
        indented ? "pl-6" : ""
      }`}
    >
      <div className="flex items-baseline justify-between gap-3">
        <Link to={`/inv/${encodeURIComponent(summary.investigation_id)}`} className="min-w-0 flex-1">
          <p
            className={`truncate font-serif text-sm text-ink dark:text-bright ${
              unseen ? "font-bold" : ""
            }`}
          >
            {summary.question ?? "Untitled research"}
          </p>
        </Link>
        <div className="flex shrink-0 items-center gap-3">
          {/* SPR-09 distinction: a research the §7 loop launched autonomously
              is badged "found by the loop" (translated from its policy_id —
              the id is never shown), so the user can tell what the loop did on
              its own from what they launched. */}
          {summary.spawned_by_daemon && (
            <LemonTag colour="muted" className="text-[10px]">
              found by the loop
            </LemonTag>
          )}
          <span
            aria-label={`${style.label}${unseen ? " · unseen" : ""}`}
            className={`w-2 h-2 rounded-full shrink-0 ${researchStateDotClass(style.state, unseen)}`}
          />
          <LemonTag colour={style.colour} className="text-[10px]">
            {style.label}
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
        {summary.started_at && <span>started {relative(summary.started_at)}</span>}
      </div>
    </article>
  );
}

function ListError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="rounded-md border border-rule px-4 py-6 dark:border-charcoal-1">
      <AIActionFailure title="Couldn’t load your research" reason={error} onRetry={onRetry} />
    </div>
  );
}

function relative(iso: string): string {
  try {
    const ago = Date.now() - new Date(iso).getTime();
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
