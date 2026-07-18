import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import AppShell from "./AppShell";
import PanelWindowApp from "./PanelWindowApp";
import CommandPalette from "./components/CommandPalette";
import { AuthProvider, useAuth } from "./lib/auth";
import Backtest from "./modes/Backtest";
import Billing from "./modes/Billing";
import Biography from "./modes/Biography";
import BrainstormStation from "./modes/BrainstormStation";
import Coordination from "./modes/Coordination";
import CostConsent from "./modes/Coordination/CostConsent";
import CreationStudio from "./modes/CreationStudio";
import CrossGraphCitations from "./modes/CrossGraphCitations";
import DocumentsIndex from "./modes/DocumentsIndex";
import Federation from "./modes/Federation";
import Home from "./modes/Home/Home"
import { ArcadeCabinet } from "./arcade/ArcadeCabinet";
import Library from "./modes/Library";
import LibraryView from "./components/library/LibraryView";
import Login from "./modes/Login";
import Loop3 from "./modes/Loop3";
import Map from "./modes/Map";
import Multimedia from "./modes/Multimedia";
import Notebook from "./modes/Notebook";
import AutoNotebook from "./modes/Notebook/AutoNotebook";
import NotebooksIndex from "./modes/NotebooksIndex";
import OperatorDashboard from "./modes/OperatorDashboard";
import Outcomes from "./modes/Outcomes";
import OutcomesIndex from "./modes/OutcomesIndex";
import PayoutsAudit from "./modes/PayoutsAudit";
import PricingPage from "./modes/Pricing";
import PrivacyDashboard from "./modes/PrivacyDashboard";
import BookReader from "./modes/Reading";
import MetaReading from "./modes/Reading/MetaReading";
import PersonalSpace from "./modes/Reading/PersonalSpace";
import Replay from "./modes/Replay";
import DeepResearchWorkspace from "./modes/DeepResearchWorkspace";
import ResearchWorkstation from "./modes/ResearchWorkstation";
import MyResearch from "./modes/ResearchWorkstation/MyResearch";
import Settings from "./modes/Settings";
import SkillRuleDetail from "./modes/SkillRuleDetail";
import SkillRules from "./modes/SkillRules";
import Sources from "./modes/Sources";
import SpeakConsole from "./modes/Speak";
import SpeakIndex from "./modes/SpeakIndex";
import SpeakInvite from "./modes/SpeakInvite";
import Stats from "./modes/Stats";
import TrustCenter from "./modes/TrustCenter";
import WriteHome from "./modes/Write/WriteHome";
import WrestleApp from "./modes/WrestleApp";

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
      <div className="min-h-screen flex items-center justify-center bg-ice-2 dark:bg-space-2 text-shadow-1 dark:text-moonlight text-[12px] tracking-[0.18em] uppercase font-sans">
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
      <Routes>
        {/* SPR-12 M1 — the unified branded home. A NEW route (the top-left
            rail logo points here). "/" deliberately STAYS the Research door
            (StartResearch already serves it); see modes/Home/Home.tsx for
            the recorded, reversible routing decision. */}
        <Route path="/home" element={<Home />} />
        <Route path="/arcade" element={<ArcadeCabinet />} />
        <Route path="/" element={<ResearchWorkstation />} />
        <Route path="/inv/:investigationId" element={<ResearchWorkstation />} />
        {/* DRW SPR-09 — the glass-box N-research monitor (deep-research-workspace).
            The :sessionId route opens it straight onto a launched session
            (the Research-entry cascade navigates here after launch). */}
        <Route path="/deep-research" element={<DeepResearchWorkspace />} />
        <Route path="/deep-research/:sessionId" element={<DeepResearchWorkspace />} />
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
        {/* SPR-06 — the auto-notebook (PROPOSED — sign-off pending). The
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
        <Route path="/documents" element={<DocumentsIndex />} />
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
        <Route path="/stats" element={<Stats />} />
        <Route path="/map" element={<Map />} />
        <Route path="/multimedia" element={<Multimedia />} />
        <Route path="/backtest/:synthesisId" element={<Backtest />} />
        <Route path="/privacy" element={<PrivacyDashboard />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/operator" element={<OperatorDashboard />} />
        {/* antiek-unified SPR-05 — read-only coordination surface (gate ledger
            + 45-sprint roadmap). Slots into the SPR-04 shared/operator bucket
            when the four-workflow NavRail lands; reachable directly meanwhile. */}
        <Route path="/coordination" element={<Coordination />} />
        {/* antiek-unified SPR-07 — read-only unified cost + consent surface.
            Reads cost from the dispatch event log, escrow from the IP-holder
            ledger, gate state from the SPR-05 gate ledger. No disbursement
            path lives here. Slots into the SPR-04 shared/operator bucket. */}
        <Route path="/coordination/cost-consent" element={<CostConsent />} />
        <Route path="/outcomes" element={<OutcomesIndex />} />
        <Route path="/outcomes/:synthesisId" element={<Outcomes />} />
        <Route path="/replay/:investigationId" element={<Replay />} />
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
        <Route path="/federation" element={<Federation />} />
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
        <Route path="/payouts" element={<PayoutsAudit />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/trust" element={<TrustCenter />} />
        {/* Speak invitee landing — UNAUTHENTICATED (a subject's friend/
            family is a source, not an account; the URL token is their
            credential). Must precede the RequireAuth catch-all. */}
        <Route path="/speak/invite/:token" element={<SpeakInvite />} />
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
    </AuthProvider>
  );
}
