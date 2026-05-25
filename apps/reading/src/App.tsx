import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import AppShell from "./AppShell";
import PanelWindowApp from "./PanelWindowApp";
import CommandPalette from "./components/CommandPalette";
import { AuthProvider, useAuth } from "./lib/auth";
import Backtest from "./modes/Backtest";
import Billing from "./modes/Billing";
import BrainstormStation from "./modes/BrainstormStation";
import CreationStudio from "./modes/CreationStudio";
import CrossGraphCitations from "./modes/CrossGraphCitations";
import DocumentsIndex from "./modes/DocumentsIndex";
import Federation from "./modes/Federation";
import InterviewMode from "./modes/Interview";
import InterviewIndex from "./modes/InterviewIndex";
import InvestigationsIndex from "./modes/InvestigationsIndex";
import Login from "./modes/Login";
import Loop3 from "./modes/Loop3";
import Map from "./modes/Map";
import Notebook from "./modes/Notebook";
import NotebooksIndex from "./modes/NotebooksIndex";
import OperatorDashboard from "./modes/OperatorDashboard";
import Outcomes from "./modes/Outcomes";
import OutcomesIndex from "./modes/OutcomesIndex";
import PayoutsAudit from "./modes/PayoutsAudit";
import PricingPage from "./modes/Pricing";
import PrivacyDashboard from "./modes/PrivacyDashboard";
import Replay from "./modes/Replay";
import ResearchWorkstation from "./modes/ResearchWorkstation";
import Settings from "./modes/Settings";
import SkillRuleDetail from "./modes/SkillRuleDetail";
import SkillRules from "./modes/SkillRules";
import Sources from "./modes/Sources";
import SpeakConsole from "./modes/Speak";
import SpeakIndex from "./modes/SpeakIndex";
import SpeakInvite from "./modes/SpeakInvite";
import Stats from "./modes/Stats";
import TrustCenter from "./modes/TrustCenter";
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

function AuthenticatedRoutes() {
  return (
    <AppShell>
      <CommandPalette />
      {/* AISidecar is no longer mounted directly here — it lives as
          PanelKind="AISidecar" and is mounted by the panel system
          when the operator opens it via ⌘/ (S8-full refactor). */}
      <Routes>
        <Route path="/" element={<ResearchWorkstation />} />
        <Route path="/inv/:investigationId" element={<ResearchWorkstation />} />
        <Route path="/wrestle" element={<WrestleApp />} />
        <Route path="/wrestle/:documentId" element={<WrestleApp />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/create" element={<CreationStudio />} />
        <Route path="/create/:deliverableId" element={<CreationStudio />} />
        <Route path="/brainstorm" element={<BrainstormStation />} />
        <Route path="/notebooks" element={<NotebooksIndex />} />
        <Route path="/notebook/:notebookId" element={<Notebook />} />
        <Route path="/documents" element={<DocumentsIndex />} />
        <Route path="/billing" element={<Billing />} />
        <Route path="/stats" element={<Stats />} />
        <Route path="/map" element={<Map />} />
        <Route path="/backtest/:synthesisId" element={<Backtest />} />
        <Route path="/privacy" element={<PrivacyDashboard />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/operator" element={<OperatorDashboard />} />
        <Route path="/outcomes" element={<OutcomesIndex />} />
        <Route path="/outcomes/:synthesisId" element={<Outcomes />} />
        <Route path="/replay/:investigationId" element={<Replay />} />
        <Route path="/interview/:interviewId" element={<InterviewMode />} />
        <Route path="/interviews" element={<InterviewIndex />} />
        <Route path="/speak" element={<SpeakIndex />} />
        <Route path="/speak/:projectId" element={<SpeakConsole />} />
        <Route path="/loop-3" element={<Loop3 />} />
        <Route path="/skill-rules" element={<SkillRules />} />
        <Route path="/skill-rules/:ruleId" element={<SkillRuleDetail />} />
        <Route path="/federation" element={<Federation />} />
        <Route path="/cross-graph/citations" element={<CrossGraphCitations />} />
        <Route path="/investigations" element={<InvestigationsIndex />} />
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
