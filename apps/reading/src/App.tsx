import { Navigate, Route, Routes } from "react-router-dom";

import AISidecar from "./components/AISidecar";
import CommandPalette from "./components/CommandPalette";
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
import SkillRuleDetail from "./modes/SkillRuleDetail";
import SkillRules from "./modes/SkillRules";
import Sources from "./modes/Sources";
import Stats from "./modes/Stats";
import TrustCenter from "./modes/TrustCenter";
import WrestleApp from "./modes/WrestleApp";

/**
 * Top-level route registry.
 *
 * `/`             → Mode A (Research Workstation — chat-first research)
 * `/inv/:id`      → Mode A scoped to a specific investigation
 * `/wrestle`      → Mode B (Document Wrestler — existing PDF surface)
 * `/wrestle/:id`  → Mode B scoped to a specific document, optionally
 *                   with ?page=N for cross-mode deep-link from Mode A's
 *                   chunk-citation modal
 * `/sources`      → Sources tab (acquisition adapters)
 * `/create`       → Mode C (Creation Workstation — Lego-block writing)
 * `/brainstorm`   → Mode E (Brainstorming Workstation — watch-for-later
 *                   folder + thought-partner; operator's stated preferred
 *                   product direction, master-spec §4.5)
 *
 * The actual layout + state lives inside each mode's component. This
 * file is route mapping only.
 */
export default function App() {
  return (
    <>
      <CommandPalette />
      <AISidecar />
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
      <Route path="/operator" element={<OperatorDashboard />} />
      <Route path="/outcomes" element={<OutcomesIndex />} />
      <Route path="/outcomes/:synthesisId" element={<Outcomes />} />
      <Route path="/replay/:investigationId" element={<Replay />} />
      <Route path="/interview/:interviewId" element={<InterviewMode />} />
      <Route path="/interviews" element={<InterviewIndex />} />
      <Route path="/loop-3" element={<Loop3 />} />
      <Route path="/skill-rules" element={<SkillRules />} />
      <Route path="/skill-rules/:ruleId" element={<SkillRuleDetail />} />
      <Route path="/federation" element={<Federation />} />
      <Route path="/cross-graph/citations" element={<CrossGraphCitations />} />
      <Route path="/investigations" element={<InvestigationsIndex />} />
      <Route path="/payouts" element={<PayoutsAudit />} />
      <Route path="/trust" element={<TrustCenter />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  );
}
