import { Navigate, Route, Routes } from "react-router-dom";

import ResearchWorkstation from "./modes/ResearchWorkstation";
import WrestleApp from "./modes/WrestleApp";

/**
 * Top-level route registry.
 *
 * `/`            → Mode A (Research Workstation — chat-first research)
 * `/inv/:id`     → Mode A scoped to a specific investigation
 * `/wrestle`     → Mode B (Document Wrestler — existing PDF surface)
 * `/wrestle/:id` → Mode B scoped to a specific document, optionally
 *                  with ?page=N for cross-mode deep-link from Mode A's
 *                  chunk-citation modal
 *
 * The actual layout + state lives inside each mode's component. This
 * file is route mapping only.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ResearchWorkstation />} />
      <Route path="/inv/:investigationId" element={<ResearchWorkstation />} />
      <Route path="/wrestle" element={<WrestleApp />} />
      <Route path="/wrestle/:documentId" element={<WrestleApp />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
