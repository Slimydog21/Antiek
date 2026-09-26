import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import AppShell from "./AppShell";
import CommandPalette from "./components/CommandPalette";
import { AuthProvider, useAuth } from "./lib/auth";

// ── WP-12.2 bundle budget (index chunk ceiling 700 KB gz) ──────────────
// Every routed mode is code-split. Only the shell, the auth provider and
// the ⌘K palette ship in the entry chunk — the route components arrive on
// visit, one chunk each. This is the architecturally correct split: the
// routes were already isolated by react-router, so lazy() costs nothing in
// behaviour and keeps the entry chunk from growing with the surface set.
//
// The two prior hand-rolled lazies (LinkMonster's p5 furnace-stage chunk,
// DocumentsIndex's style-wheel preview) are folded into this same policy
// rather than kept as special cases.
const LinkMonster = lazy(() => import("./modes/LinkMonster/LinkMonster"));
const AccountMemory = lazy(() => import("./modes/AccountMemory"));
const DocumentsIndex = lazy(() => import("./modes/DocumentsIndex"));
const Federation = lazy(() => import("./modes/Federation"));
const OperatorDashboard = lazy(() => import("./modes/OperatorDashboard"));
const PayoutsAudit = lazy(() => import("./modes/PayoutsAudit"));
const Replay = lazy(() => import("./modes/Replay"));
const Stats = lazy(() => import("./modes/Stats"));

const PanelWindowApp = lazy(() => import("./PanelWindowApp"));
const Backtest = lazy(() => import("./modes/Backtest"));
const Billing = lazy(() => import("./modes/Billing"));
const Biography = lazy(() => import("./modes/Biography"));
const BrainstormStation = lazy(() => import("./modes/BrainstormStation"));
const Coordination = lazy(() => import("./modes/Coordination"));
const CostConsent = lazy(() => import("./modes/Coordination/CostConsent"));
const CreationStudio = lazy(() => import("./modes/CreationStudio"));
const CrossGraphCitations = lazy(() => import("./modes/CrossGraphCitations"));
const Home = lazy(() => import("./modes/Home/Home"));
const Library = lazy(() => import("./modes/Library"));
const LibraryView = lazy(() => import("./components/library/LibraryView"));
const Login = lazy(() => import("./modes/Login"));
const Loop3 = lazy(() => import("./modes/Loop3"));
const Map = lazy(() => import("./modes/Map"));
const MidnightOil = lazy(() => import("./modes/MidnightOil"));
const Multimedia = lazy(() => import("./modes/Multimedia"));
const Notebook = lazy(() => import("./modes/Notebook"));
const AutoNotebook = lazy(() => import("./modes/Notebook/AutoNotebook"));
const NotebooksIndex = lazy(() => import("./modes/NotebooksIndex"));
const Outcomes = lazy(() => import("./modes/Outcomes"));
const OutcomesIndex = lazy(() => import("./modes/OutcomesIndex"));
const PricingPage = lazy(() => import("./modes/Pricing"));
const PrivacyDashboard = lazy(() => import("./modes/PrivacyDashboard"));
const BookReader = lazy(() => import("./modes/Reading"));
const MetaReading = lazy(() => import("./modes/Reading/MetaReading"));
const PersonalSpace = lazy(() => import("./modes/Reading/PersonalSpace"));
const DeepResearchWorkspace = lazy(() => import("./modes/DeepResearchWorkspace"));
const ResearchWorkstation = lazy(() => import("./modes/ResearchWorkstation"));
const MyResearch = lazy(() => import("./modes/ResearchWorkstation/MyResearch"));
const Settings = lazy(() => import("./modes/Settings"));
const SkillRuleDetail = lazy(() => import("./modes/SkillRuleDetail"));
const SkillRules = lazy(() => import("./modes/SkillRules"));
const Sources = lazy(() => import("./modes/Sources"));
const SpeakConsole = lazy(() => import("./modes/Speak"));
const SpeakIndex = lazy(() => import("./modes/SpeakIndex"));
const SpeakInvite = lazy(() => import("./modes/SpeakInvite"));
const SpeakPublicBrowse = lazy(() => import("./modes/SpeakPublicBrowse"));
const TrustCenter = lazy(() => import("./modes/TrustCenter"));
const Explain = lazy(() => import("./modes/Explain"));
const ObjectiveCard = lazy(() => import("./modes/ObjectiveCard"));
const Signals = lazy(() => import("./modes/Signals"));
const WriteHome = lazy(() => import("./modes/Write/WriteHome"));
const WrestleApp = lazy(() => import("./modes/WrestleApp"));

function RouteLoading({ label }: { label: string }) {
  return (
    <div
      role="status"
      className="h-full flex items-center justify-center text-shadow-1 dark:text-moonlight text-xs tracking-[0.18em] uppercase font-sans"
    >
      {label}
    </div>
  );
}

/**
 * Top-level route registry.
 *
 * `/login`        → Antiek's owned login page (master-spec §13.8 +
 *                   the 2026-05-21 PostHog-style auth decision)
 * `/trust`        → public Trust Center (also reachable when logged out)
 * Everything else → wrapped by RequireAuth; redirects to /login when
 *                   /auth/me returns 401.
 *
 * The actual layout + state lives inside each mode's component. This
 * file is route mapping + auth gating only.
 */

/** Auth gate. Children render only when authenticated; otherwise we
 * redirect to /login with the original path preserved in ?next= so the
 * post-callback redirect lands the user where they tried to go. */
function RequireAuth({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const location = useLocation();
  if (state.status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-ice-2 dark:bg-space-2 text-shadow-1 dark:text-moonlight text-xs tracking-[0.18em] uppercase font-sans">
        Loading…
      </div>
    );
  }
  if (state.status === "unauthenticated") {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}

/** Speak SPR-08 one-door redirect for legacy /interview/:id deep-links.
 *  The duplicate Interview surface is gone; interview-as-acquisition has one
 *  door (/speak). An old interview link lands on the Speak home, where the
 *  project that owns the interview is one tap away — never a dead route. */
function InterviewRedirect() {
  return <Navigate to="/speak" replace />;
}

function AuthenticatedRoutes() {
  return (
    <AppShell>
      <CommandPalette />
      {/* AISidecar is no longer mounted directly here — it lives as
          PanelKind="AISidecar" and is mounted by the panel system
          when the operator opens it via ⌘/ (S8-full refactor). */}
      {/* Outer Suspense boundary for the code-split mode routes (WP-12.2).
          Per-route Suspense blocks below keep their specific copy and take
          precedence; anything lazy without its own boundary lands here. */}
      <Suspense fallback={<RouteLoading label="Loading…" />}>
      <Routes>
        {/* SPR-12 M1 — the unified branded home. A NEW route (the top-left
            rail logo points here). "/" deliberately STAYS the Research door
            (StartResearch already serves it); see modes/Home/Home.tsx for
            the recorded, reversible routing decision. */}
        <Route path="/home" element={<Home />} />
        <Route
          path="/link-monster"
          element={
            <Suspense fallback={
              // Styled like the RequireAuth veil (App.tsx RequireAuth loading
              // branch) — the old `lm-loading` class had no CSS definition
              // anywhere, so the fallback rendered unstyled.
              <div className="h-full flex items-center justify-center text-shadow-1 dark:text-moonlight text-xs tracking-[0.18em] uppercase font-sans">
                summoning the Monster…
              </div>
            }>
              <LinkMonster />
            </Suspense>
          }
        />
        <Route path="/" element={<ResearchWorkstation />} />
        <Route path="/inv/:investigationId" element={<ResearchWorkstation />} />
        {/* DRW SPR-09 — the glass-box N-research monitor (deep-research-workspace).
            The :sessionId route opens it straight onto a launched session
            (the Research-entry cascade navigates here after launch). */}
        <Route path="/deep-research" element={<DeepResearchWorkspace />} />
        <Route path="/deep-research/:sessionId" element={<DeepResearchWorkspace />} />
        <Route path="/midnight-oil" element={<MidnightOil />} />
        <Route path="/wrestle" element={<WrestleApp />} />
        <Route path="/wrestle/:documentId" element={<WrestleApp />} />
        <Route path="/sources" element={<Sources />} />
        {/* Write SPR-07 door re-home: the Write door opens on WriteHome — the
            real blocks → outline → generate → edit loop — not the legacy
            CreationStudio "select or create a deliverable" dead-end. The studio
            stays reachable at /create (a demoted power surface, off the door),
            its capability untouched; the door is /write (write.defaultRoute). */}
        <Route path="/write" element={<WriteHome />} />
        <Route path="/write/:deliverableId" element={<WriteHome />} />
        <Route path="/create" element={<CreationStudio />} />
        <Route path="/create/:deliverableId" element={<CreationStudio />} />
        <Route path="/brainstorm" element={<BrainstormStation />} />
        <Route path="/notebooks" element={<NotebooksIndex />} />
        {/* SPR-06 — the auto-notebook (RATIFIED 2026-09-18). The
            derived, always-current narrative VIEW of one research's
            insight/question graph, behind a visible "proposed" banner. A
            REVERSIBLE leaf: removing this route + AutoNotebook.tsx reverts to
            the manual TipTap notebook below, which is untouched. Not a hard
            dependency of any sprint. React-Router v6 ranks routes by SPECIFICITY
            (the static "auto" segment outranks the ":notebookId" param), so "auto"
            is never read as a notebook id — robust regardless of declaration order.
            See docs/decisions/spr-06-auto-notebook-proposed.md. */}
        <Route path="/notebook/auto/:investigationId" element={<AutoNotebook />} />
        <Route path="/notebook/auto" element={<AutoNotebook />} />
        <Route path="/notebook/:notebookId" element={<Notebook />} />
        <Route
          path="/documents"
          element={
            <Suspense
              fallback={
                <div className="h-full flex items-center justify-center text-shadow-1 dark:text-moonlight text-xs tracking-[0.18em] uppercase font-sans">
                  Loading documents…
                </div>
              }
            >
              <DocumentsIndex />
            </Suspense>
          }
        />
        <Route path="/library" element={<Library />} />
        {/* SPR-09 M2 — the paginated browse view over the new /library catalog
            endpoint (Unit A). ADDITIVE: a static segment declared before any
            /library param route, so it never shadows the feature-rich Library
            door above. Reachable from the Library header's "Browse all" link. */}
        <Route path="/library/browse" element={<LibraryView />} />
        {/* SPR-08 M4 — meta-reading surface (PROPOSED, sign-off pending).
            Literal route declared BEFORE /read/:documentId; React-Router v6
            ranks static segments above params, so /read/meta-reading never
            resolves the book reader. */}
        <Route path="/read/meta-reading" element={<MetaReading />} />
        {/* SPR-13 M1 — re-open a SAVED meta-reading asset by id (the personal
            space item opens back into the meta-doc view). Declared after the
            literal /read/meta-reading so it doesn't shadow the generator. */}
        <Route path="/read/meta-reading/:assetId" element={<MetaReading />} />
        {/* SPR-13 M1 — the personal document space (created deliverables +
            saved reads, auto-categorized, suggest-file-into-project). */}
        <Route path="/readings" element={<PersonalSpace />} />
        {/* SPR-13 M4 — the meta-docs tab: the same personal space filtered to
            created deliverables, after the Library in the Read nav. */}
        <Route path="/meta-readings" element={<PersonalSpace metaDocsOnly />} />
        <Route path="/read/:documentId" element={<BookReader />} />
        <Route path="/billing" element={<Billing />} />
        <Route
          path="/stats"
          element={
            <Suspense fallback={<RouteLoading label="Loading statistics…" />}>
              <Stats />
            </Suspense>
          }
        />
        <Route path="/map" element={<Map />} />
        <Route path="/multimedia" element={<Multimedia />} />
        <Route path="/backtest/:synthesisId" element={<Backtest />} />
        {/* SPR-11 Task 6 — the owner-private account-memory panel. Both
            /account/memory routes have been live and gated since the
            account-memory sprint; until this route nothing in apps/ called
            either, so the facts an account accumulated were curl-only. */}
        <Route
          path="/memory"
          element={
            <Suspense
              fallback={
                <div className="h-full flex items-center justify-center text-shadow-1 dark:text-moonlight text-xs tracking-[0.18em] uppercase font-sans">
                  Loading memory…
                </div>
              }
            >
              <AccountMemory />
            </Suspense>
          }
        />
        <Route path="/privacy" element={<PrivacyDashboard />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/settings" element={<Settings />} />
        <Route
          path="/operator"
          element={
            <Suspense
              fallback={<RouteLoading label="Loading operator dashboard…" />}
            >
              <OperatorDashboard />
            </Suspense>
          }
        />
        {/* antiek-unified SPR-05 — read-only coordination surface (gate ledger
            + 45-sprint roadmap). Slots into the SPR-04 shared/operator bucket
            when the four-workflow NavRail lands; reachable directly meanwhile. */}
        <Route path="/coordination" element={<Coordination />} />
        {/* antiek-unified SPR-07 — read-only unified cost + consent surface.
            Reads cost from the dispatch event log, escrow from the IP-holder
            ledger, gate state from the SPR-05 gate ledger. No disbursement
            path lives here. Slots into the SPR-04 shared/operator bucket. */}
        <Route path="/coordination/cost-consent" element={<CostConsent />} />
        {/* Own Your Mind P0 — read-only surfaces (docs/own-your-mind/
            10-p0-implementation-brief.md). Explain is the D1 "why this
            claim" provenance panel (kind ∈ claim | synthesis | document);
            ObjectiveCard (C1a) + Signals (L15) are the /ops read-only
            cards. All three are additive GET-only surfaces. */}
        <Route path="/explain/:kind/:id" element={<Explain />} />
        <Route path="/objective" element={<ObjectiveCard />} />
        <Route path="/signals" element={<Signals />} />
        <Route path="/outcomes" element={<OutcomesIndex />} />
        <Route path="/outcomes/:synthesisId" element={<Outcomes />} />
        <Route
          path="/replay/:investigationId"
          element={
            <Suspense fallback={<RouteLoading label="Loading replay…" />}>
              <Replay />
            </Suspense>
          }
        />
        {/* Speak SPR-08 ONE DOOR: the duplicate Interview surface is folded
            into Speak. There is exactly one door to interview-as-acquisition —
            /speak. The old /interviews index redirects to /speak (the warm
            home); an /interview/:id deep-link redirects into that interview's
            Speak project console (the substance — recording, transcript,
            corroboration — lives there now). The Interview / InterviewIndex
            components stay on disk (capability preserved, mirrors the SPR-05
            InvestigationsIndex fold) but are retired from routing. */}
        <Route path="/interviews" element={<Navigate to="/speak" replace />} />
        <Route path="/interview/:interviewId" element={<InterviewRedirect />} />
        <Route path="/speak" element={<SpeakIndex />} />
        <Route path="/speak/:projectId" element={<SpeakConsole />} />
        {/* SPR-11 — the Biography TEMPLATE landing. A dedicated route (NOT a
            fifth NavRail door — the four-door rail is sacred); reachable from
            the home's "Start a biography" feature card. "Start a biography"
            composes a Research folder + a Write deliverable + a Speak project
            over the ONE graph (it is a template, not a fifth product/graph).
            See docs/decisions/spr-11-biography-template-not-graph.md. */}
        <Route path="/biography" element={<Biography />} />
        <Route path="/loop-3" element={<Loop3 />} />
        <Route path="/skill-rules" element={<SkillRules />} />
        <Route path="/skill-rules/:ruleId" element={<SkillRuleDetail />} />
        <Route
          path="/federation"
          element={
            <Suspense fallback={<RouteLoading label="Loading federation…" />}>
              <Federation />
            </Suspense>
          }
        />
        <Route path="/cross-graph/citations" element={<CrossGraphCitations />} />
        {/* SPR-05 — the one multi-research monitor. Folds the three split
            "manage your researches" surfaces (the docked sidebar tree, the
            /deep-research grid, and the old /investigations flat list) into a
            single calm home over every running + completed research. The old
            /investigations path redirects here so there is exactly one door
            (the experience-spec E-04/E-05 consolidation); the InvestigationsIndex
            component is retired from routing, its capabilities (start, status,
            cost, replay) preserved in MyResearch. */}
        <Route path="/my-research" element={<MyResearch />} />
        <Route path="/investigations" element={<Navigate to="/my-research" replace />} />
        <Route
          path="/payouts"
          element={
            <Suspense fallback={<RouteLoading label="Loading payouts…" />}>
              <PayoutsAudit />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
    </AppShell>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Suspense fallback={<RouteLoading label="Loading…" />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/trust" element={<TrustCenter />} />
        {/* Speak invitee landing — UNAUTHENTICATED (a subject's friend/
            family is a source, not an account; the URL token is their
            credential). Must precede the RequireAuth catch-all. */}
        <Route path="/speak/invite/:token" element={<SpeakInvite />} />
        {/* Unauthenticated public remembrances browse (read-only). */}
        <Route path="/speak/browse" element={<SpeakPublicBrowse />} />
        {/* S9 — popout panel windows render outside AppShell. The
            popout app handles its own chrome; no NavRail/Topbar/
            PanelLayout wrapping. */}
        <Route path="/_panel/:panelId" element={<PanelWindowApp />} />
        <Route
          path="*"
          element={
            <RequireAuth>
              <AuthenticatedRoutes />
            </RequireAuth>
          }
        />
      </Routes>
      </Suspense>
    </AuthProvider>
  );
}
